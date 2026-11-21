"""Decision report endpoints. Include with `app.include_router(report_routes.router)`."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from backend.auth import CurrentUser
from backend.db import Test, session, test_dir

load_dotenv()
log = __import__("logging").getLogger("adlens.report")
router = APIRouter()

ID_RE = re.compile(r"[a-f0-9]{12}")
STALE_AFTER = 15 * 60          # a "generating" status older than this (e.g. server restarted) counts as failed
_lock = threading.Lock()       # single-process guard for the check-then-start of generation
_pdf_lock = threading.Semaphore(2)


class ReportIn(BaseModel):
    decision_question: str | None = Field(default=None, max_length=500)
    lang: str = Field(default="ja", pattern="^(ja|en)$")


def _owned_test(test_id: str, user) -> tuple[Test, Path]:
    if not ID_RE.fullmatch(test_id):
        raise HTTPException(404, "Test not found.")
    with session() as s:
        t = s.get(Test, test_id)
    if not t or t.owner != user.email:   # 404, not 403: do not reveal other users' ids
        raise HTTPException(404, "Test not found.")
    return t, test_dir(test_id)


def _write_json(path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False))  # object storage writes are atomic per object


def _status(d: Path) -> dict:
    f = d / "report_status.json"
    if not f.exists():
        return {"status": "none"}
    try:
        st = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "failed", "error": "Report status is unreadable."}
    if st.get("status") == "generating" and time.time() - st.get("started", 0) > STALE_AFTER:
        return {"status": "failed", "error": "Report generation was interrupted. Try again."}
    return st


def _work(test_id: str, d: Path, test: Test, body: ReportIn, started: float):
    from core.decision_report import generate
    try:
        result = json.loads((d / "result.json").read_text(encoding="utf-8"))
        rep = generate(result, test.name, test.context or "", body.decision_question or "", test.lang or "ja")
        _write_json(d / "report.json", rep)
        _write_json(d / "report_status.json", {"status": "ready", "started": started, "finished": time.time()})
    except Exception as e:  # noqa: BLE001 - surfaced to the client as a status, logged with the id
        log.exception("report generation failed test=%s", test_id)
        _write_json(d / "report_status.json", {"status": "failed", "started": started,
                                               "error": f"Report generation failed ({type(e).__name__}). Try again."})


@router.post("/api/tests/{test_id}/report")
def create_report(test_id: str, body: ReportIn, user=CurrentUser):
    """Runs generation inside the request (serverless: no background threads) and returns the result."""
    test, d = _owned_test(test_id, user)
    if test.status != "done" or not (d / "result.json").exists():
        raise HTTPException(409, "The test has not finished yet.")
    with _lock:   # idempotent: a second POST while one is running returns the same 202 without a second LLM run
        if _status(d).get("status") == "generating":
            return {"status": "generating"}
        started = time.time()
        _write_json(d / "report_status.json", {"status": "generating", "started": started})
    from core import llm
    llm.current_user.set(user.email)  # bill the report to its owner
    _work(test_id, d, test, body, started)
    return get_report(test_id, user)


@router.get("/api/tests/{test_id}/report")
def get_report(test_id: str, user=CurrentUser):
    _, d = _owned_test(test_id, user)
    st = _status(d)
    out = {"status": st["status"], "report": None}
    if st["status"] == "failed":
        out["error"] = st.get("error", "Report generation failed.")
    f = d / "report.json"
    if f.exists() and st["status"] in ("ready", "generating", "failed"):
        try:   # during a regenerate / after a failure, the previous report is still served
            out["report"] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return out


def _deck(test_id: str, user) -> tuple[bytes, str]:
    test, d = _owned_test(test_id, user)
    f = d / "report.json"
    if not f.exists():
        raise HTTPException(409, "No report yet. Generate one first.")
    from core.pptx_export import build_pptx
    report = json.loads(f.read_text(encoding="utf-8"))
    result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    return build_pptx(report, result, test.name), test.name


def _download(data: bytes, test_id: str, ext: str, mime: str) -> Response:
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="adlens-report-{test_id}.{ext}"'})


@router.get("/api/tests/{test_id}/report.pptx")
def report_pptx(test_id: str, user=CurrentUser):
    data, _ = _deck(test_id, user)
    return _download(data, test_id, "pptx",
                     "application/vnd.openxmlformats-officedocument.presentationml.presentation")


@router.get("/api/tests/{test_id}/report.pdf")
def report_pdf(test_id: str, user=CurrentUser):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise HTTPException(501, "PDF export is not available on this server.")
    data, _ = _deck(test_id, user)
    with _pdf_lock, tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "report.pptx"
        src.write_bytes(data)
        try:   # private profile dir so concurrent conversions do not fight over the default lock
            subprocess.run([soffice, f"-env:UserInstallationDir=file://{tmp}/profile", "--headless",
                            "--convert-to", "pdf", "--outdir", tmp, str(src)],
                           check=True, capture_output=True, timeout=180)
            pdf = (Path(tmp) / "report.pdf").read_bytes()
        except (subprocess.SubprocessError, OSError):
            log.exception("pdf conversion failed test=%s", test_id)
            raise HTTPException(500, "PDF conversion failed.") from None
    return _download(pdf, test_id, "pdf", "application/pdf")
