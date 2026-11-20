"""Test worker — runs INSIDE a Daytona sandbox started from the `adlens-worker` snapshot.

    python -m core.worker job.json

job.json (written by the API):
  { test_id, filename, context, personas: [...],
    media_url: <signed GET of the upload>,
    uploads: { "result.json": <signed PUT>, "media.bin": <signed PUT>, "thumb.jpg": <signed PUT> } }

It has no database and no storage keys: it only reads the media through a signed URL and writes its
outputs through signed upload URLs. Progress goes to ./progress.json, which the API polls.
"""
import base64
import json
import sys
import time
import traceback
from pathlib import Path

import httpx

HERE = Path.cwd()
PROGRESS = HERE / "progress.json"


def progress(step, percent, message, **extra):
    PROGRESS.write_text(json.dumps({"step": step, "percent": percent, "message": message,
                                    "at": time.time(), **extra}, ensure_ascii=False))


def put(url, data: bytes, ctype: str):
    for attempt in range(4):
        try:
            r = httpx.put(url, content=data, headers={"content-type": ctype, "x-upsert": "true"}, timeout=300)
            if r.status_code < 300:
                return
            err = f"{r.status_code} {r.text[:200]}"
        except httpx.HTTPError as e:
            err = str(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"upload failed: {err}")


def main(job_path):
    job = json.loads(Path(job_path).read_text())
    try:
        from core import analyze_video, llm
        from core.gaze import persona_gaze
        from core.persona_profile import ensure_profiles
        from core.summary import summarize
        from core.themes import summarize as summarize_themes

        progress("sandbox", 12, "Downloading the ad")
        ext = Path(job["filename"]).suffix.lower() or ".mp4"
        src = HERE / f"input{ext}"
        with httpx.stream("GET", job["media_url"], timeout=600) as r:
            r.raise_for_status()
            with src.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)

        progress("analysis", 25, "Mapping attention and transcribing speech")
        out = HERE / "analysis.json"
        analyze_video.main(str(src), str(out))  # also writes proxy.mp4 next to out for videos
        analysis = json.loads(out.read_text())
        proxy = HERE / "proxy.mp4"

        personas = job["personas"]
        if any(not p.get("profile") for p in personas):
            progress("viewers", 45, "Writing profiles for the viewers")
            ensure_profiles(personas)

        progress("viewers", 55, f"{len(personas)} viewers are watching {len(analysis['keyframes'])} moments")
        gaze = persona_gaze(analysis["keyframes"], personas, job.get("context", ""),
                            log=lambda m: None, transcript=analysis.get("transcript"))

        progress("saving", 88, "Grouping reactions into themes")
        summary = summarize(gaze)
        try:
            themes = summarize_themes(gaze, personas, job.get("lang", "ja"))
        except Exception:  # noqa: BLE001 - a report without themes is still useful
            themes = None

        progress("saving", 95, "Saving the report")
        result = {"analysis": analysis, "gaze": gaze, "personas": personas, "summary": summary, "themes": themes}
        up = job["uploads"]
        put(up["result.json"], json.dumps(result, ensure_ascii=False).encode(), "application/json")
        if proxy.exists():
            put(up["media.bin"], proxy.read_bytes(), "video/mp4")
            media_mime = "video/mp4"
        else:
            put(up["media.bin"], src.read_bytes(), job.get("mime", "application/octet-stream"))
            media_mime = job.get("mime")
        if analysis.get("keyframes"):
            put(up["thumb.jpg"], base64.b64decode(analysis["keyframes"][0]["jpg_b64"]), "image/jpeg")
        progress("done", 100, "", done=True, summary=summary, mime=media_mime, usage=llm.TOTALS)
    except Exception as e:  # noqa: BLE001
        progress("failed", 100, "", done=True, error=f"{type(e).__name__}: {str(e)[:300]}",
                 trace=traceback.format_exc()[-2000:])
        raise


if __name__ == "__main__":
    main(sys.argv[1])
