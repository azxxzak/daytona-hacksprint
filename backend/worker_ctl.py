"""Start, watch and finish the per-test Daytona worker (serverless-friendly: no background threads).

start()  — called by POST /api/tests: sandbox from the prebuilt snapshot, upload the worker code + job,
           launch `python -m core.worker job.json` in a background session.
poll()   — called by GET /api/tests/{id} (throttled): reads progress.json from the sandbox, mirrors it into
           the Test row, and on completion records usage and deletes the sandbox.
"""
import json
import logging
import os
import time
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona, SessionExecuteRequest

from backend import db
from backend.db import Test
from core import llm
from core.store import SPath

log = logging.getLogger("adlens.worker")
ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = os.getenv("WORKER_SNAPSHOT", "adlens-worker-v1")
JOB_DIR = "/home/daytona/job"
WORKER_FILES = ["core/__init__.py", "core/analyze_video.py", "core/gaze.py", "core/llm.py", "core/personas.py",
                "core/persona_profile.py", "core/themes.py", "core/store.py", "core/summary.py", "core/worker.py"]
POLL_EVERY_S = 2.0
TIMEOUT_S = 25 * 60

_daytona = None


def daytona() -> Daytona:
    global _daytona
    if _daytona is None:
        _daytona = Daytona()
    return _daytona


def _save(test_id: str, **fields):
    with db.session() as s:
        t = s.get(Test, test_id)
        for k, v in fields.items():
            setattr(t, k, v)
        s.add(t)
        s.commit()


def start(test: Test, personas: list[dict], media_key: str, filename: str, mime: str, lang: str = "ja"):
    d = db.test_dir(test.id)
    job = {
        "test_id": test.id, "filename": filename, "mime": mime, "context": test.context, "lang": lang,
        "personas": personas,
        "media_url": SPath(media_key).signed_download_url(expires=3 * 3600),
        "uploads": {name: (d / name).signed_upload_url() for name in ("result.json", "media.bin", "thumb.jpg")},
    }
    env = {k: os.environ[k] for k in ("ANTHROPIC_API_KEY", "FAST_MODEL", "CHAT_MODEL") if os.getenv(k)}
    _save(test.id, status="running", step="sandbox", percent=4, message="Starting a Daytona sandbox",
          started_at=time.time())
    sb = daytona().create(CreateSandboxFromSnapshotParams(
        snapshot=SNAPSHOT, env_vars=env, labels={"app": "adlens-worker", "test": test.id},
        auto_stop_interval=30, auto_delete_interval=60), timeout=120)
    try:
        sb.process.exec(f"mkdir -p {JOB_DIR}/core")
        for f in WORKER_FILES:
            sb.fs.upload_file((ROOT / f).read_bytes(), f"{JOB_DIR}/{f}")
        sb.fs.upload_file(json.dumps(job, ensure_ascii=False).encode(), f"{JOB_DIR}/job.json")
        sb.process.create_session("job")
        sb.process.execute_session_command("job", SessionExecuteRequest(
            command=f"cd {JOB_DIR} && python -m core.worker job.json > worker.log 2>&1", run_async=True))
    except Exception:
        daytona().delete(sb)
        raise
    _save(test.id, worker_id=sb.id, step="sandbox", percent=8, message="Sandbox ready, starting analysis",
          where="daytona")


def poll(test: Test) -> Test:
    """Advance a running test from the worker's progress file. Cheap to call; throttled per test."""
    if test.status not in ("queued", "running") or not test.worker_id:
        return test
    now = time.time()
    if now - (test.worker_checked_at or 0) < POLL_EVERY_S:
        return test
    _save(test.id, worker_checked_at=now)
    try:
        sb = daytona().get(test.worker_id)
        raw = sb.fs.download_file(f"{JOB_DIR}/progress.json")
        prog = json.loads(raw) if raw else None
    except Exception as e:  # noqa: BLE001 - progress file not written yet, or the sandbox is gone
        prog, sb = None, None
        if "not found" in str(e).lower() and now - test.started_at > 60:
            _fail(test, None, "The analysis sandbox stopped unexpectedly. Please run the test again.")
            return _reload(test)
    if prog is None:
        if now - (test.started_at or now) > TIMEOUT_S:
            _fail(test, sb, "The analysis took too long and was stopped.")
        return _reload(test)
    if not prog.get("done"):
        _save(test.id, step=prog["step"], percent=int(prog["percent"]), message=prog.get("message", ""))
        return _reload(test)
    if prog.get("error"):
        log.warning("worker failed for %s: %s", test.id, prog.get("trace", prog["error"]))
        _fail(test, sb, "The analysis failed: " + prog["error"][:200])
        return _reload(test)
    summary = prog.get("summary") or {}
    usage = prog.get("usage") or {}
    llm.record_usage(test.owner, "test-worker", llm.FAST_MODEL, usage.get("in", 0), usage.get("out", 0),
                     usage.get("usd", 0.0))
    _save(test.id, status="done", step="done", percent=100, message="", mime=prog.get("mime") or test.mime,
          engaged=summary.get("engaged"), avg_interest=summary.get("avg_interest"), worker_id=None)
    _cleanup(sb)
    return _reload(test)


def _fail(test, sb, message):
    _save(test.id, status="failed", error=message, worker_id=None)
    _cleanup(sb)


def _cleanup(sb):
    if sb is not None:
        try:
            daytona().delete(sb)
        except Exception as e:  # noqa: BLE001 - auto-delete will catch it
            log.warning("could not delete sandbox: %s", e)


def _reload(test: Test) -> Test:
    with db.session() as s:
        return s.get(Test, test.id)
