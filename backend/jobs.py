"""Background test runs. One worker thread pool; each run updates its progress row as it goes.

For production, swap the thread pool for a real queue (RQ/Celery/Arq) — run_test() is self-contained.
"""
import base64
import json
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

from backend.db import Test, session, test_dir
from core import llm
from core.gaze import persona_gaze
from core.persona_profile import ensure_profiles
from core.sandbox import analyze
from core.themes import summarize as summarize_themes

log = logging.getLogger("adlens.jobs")
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="adlens-job")


def _progress(test_id: str, **fields):
    with session() as s:
        t = s.get(Test, test_id)
        for k, v in fields.items():
            setattr(t, k, v)
        s.add(t)
        s.commit()


def summarize(gaze: list[dict]) -> dict | None:
    if not gaze:
        return None
    per, curve, focus = {}, {}, {}
    for g in gaze:
        per.setdefault(g["id"], []).append(g["interest"])
        curve.setdefault(g["t"], []).append(g["interest"])
        k = (g.get("looking_at") or "").lower().strip()
        if k:
            focus[k] = focus.get(k, 0) + 1
    means = {k: sum(v) / len(v) for k, v in per.items()}
    pts = sorted((t, sum(v) / len(v)) for t, v in curve.items())
    low = min(pts, key=lambda p: p[1])[0] if len(pts) > 1 else None
    return {"engaged": sum(1 for m in means.values() if m >= 3.5), "total": len(means),
            "avg_interest": round(sum(g["interest"] for g in gaze) / len(gaze), 2),
            "low_t": low, "top_focus": max(focus, key=focus.get) if focus else None,
            "curve": [{"t": t, "avg": round(a, 2)} for t, a in pts]}


def run_test(test_id: str, filename: str, personas: list[dict], context: str, owner: str = "system"):
    llm.current_user.set(owner)  # every model call in this run is billed to the test owner
    d = test_dir(test_id)
    try:
        # profiles are written while the sandbox works on the media
        profiles = ThreadPoolExecutor(max_workers=1).submit(llm.bind(
            lambda: ensure_profiles(personas, log=lambda m: log.info("%s: %s", test_id, m))))
        _progress(test_id, status="running", step="sandbox", percent=5, message="Starting a Daytona sandbox")
        media = (d / "upload.bin").read_bytes()

        stages = [("Creating", "sandbox", 10, "Starting a Daytona sandbox"),
                  ("Uploading", "sandbox", 15, "Uploading the ad"),
                  ("Installing", "sandbox", 22, "Preparing the analysis tools"),
                  ("Heatmaps", "analysis", 35, "Mapping attention and transcribing speech"),
                  ("Running inside", "analysis", 35, "Mapping attention and transcribing speech"),
                  ("Using local", "analysis", 35, "Mapping attention and transcribing speech"),
                  ("Sandbox:", "analysis", 50, "Attention map and transcript ready")]
        reached = {"pct": 5}

        def sandbox_log(msg):  # progress only ever moves forward
            m = str(msg)
            for needle, step, pct, text in stages:
                if needle in m and pct > reached["pct"]:
                    reached["pct"] = pct
                    _progress(test_id, step=step, percent=pct, message=text)
                    return

        analysis, where = analyze(media, filename, sandbox_log)
        proxy = analysis.pop("proxy", None)
        if proxy:
            (d / "media.bin").write_bytes(proxy)
            _progress(test_id, mime="video/mp4")
        else:
            (d / "media.bin").write_bytes(media)
        if analysis.get("keyframes"):
            (d / "thumb.jpg").write_bytes(base64.b64decode(analysis["keyframes"][0]["jpg_b64"]))

        _progress(test_id, step="viewers", percent=55, where=where,
                  message=f"{len(personas)} viewers are watching {len(analysis['keyframes'])} moments")
        done = {"n": 0}
        total = max(1, len(analysis["keyframes"]) * ((len(personas) + 14) // 15))

        def gaze_log(msg):
            if "failed" in str(msg):
                log.warning("%s: %s", test_id, msg)
            done["n"] += 1

        try:
            profiles.result(timeout=600)
        except Exception as e:  # noqa: BLE001 - viewers still work from their short attributes
            log.warning("%s: profiles unavailable: %s", test_id, e)
        gaze = persona_gaze(analysis["keyframes"], personas, context, gaze_log, analysis.get("transcript"))
        _progress(test_id, step="saving", percent=90, message="Grouping reactions into themes")
        summary = summarize(gaze)
        try:
            themes = summarize_themes(gaze, personas, "ja")
        except Exception as e:  # noqa: BLE001
            log.warning("%s: themes failed: %s", test_id, e)
            themes = None
        _progress(test_id, percent=97, message="Saving the report")
        (d / "result.json").write_text(json.dumps(
            {"analysis": analysis, "gaze": gaze, "personas": personas, "summary": summary, "themes": themes},
            ensure_ascii=False))
        (d / "upload.bin").unlink(missing_ok=True)
        _progress(test_id, status="done", step="done", percent=100, message="",
                  engaged=summary["engaged"] if summary else None,
                  avg_interest=summary["avg_interest"] if summary else None)
    except Exception as e:  # noqa: BLE001
        log.error("test %s failed: %s\n%s", test_id, e, traceback.format_exc())
        _progress(test_id, status="failed", error=f"The test could not finish: {str(e)[:300]}")


def submit(test_id: str, filename: str, personas: list[dict], context: str, owner: str = "system"):
    pool.submit(run_test, test_id, filename, personas, context, owner)
