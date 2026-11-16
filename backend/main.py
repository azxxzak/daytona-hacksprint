"""AdLens API. Run: .venv/bin/uvicorn backend.main:app --port 8000"""
import io
import json
import logging
import re
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlmodel import select  # noqa: E402

from backend import auth, db, jobs  # noqa: E402
from backend.db import Test, User  # noqa: E402
from core import avatars  # noqa: E402
from core.gaze import chat_with_persona  # noqa: E402
from core.personas import load_csv, sample_personas, with_colors  # noqa: E402

logging.basicConfig(level=logging.INFO)
db.init()
app = FastAPI(title="AdLens API", docs_url="/api/docs", openapi_url="/api/openapi.json")

MAX_UPLOAD = 500 * 1024 * 1024
MEDIA_TYPES = {".mp4": ("video", "video/mp4"), ".mov": ("video", "video/quicktime"), ".webm": ("video", "video/webm"),
               ".png": ("image", "image/png"), ".jpg": ("image", "image/jpeg"), ".jpeg": ("image", "image/jpeg")}
AVATAR_INDEX = avatars.CACHE


# ---------------- helpers ----------------
def persona_out(p: dict) -> dict:
    """Public persona shape; also remembers the profile so its portrait can be drawn on demand."""
    k = avatars.key(p)
    AVATAR_INDEX.mkdir(parents=True, exist_ok=True)
    idx = AVATAR_INDEX / f"{k}.json"
    if not idx.exists():
        idx.write_text(json.dumps(p, ensure_ascii=False, default=str))
    fields = ("id", "name", "age", "gender", "region", "occupation", "income", "interests", "media", "values", "color")
    out = {f: p.get(f, "") for f in fields}
    out["age"] = int(p.get("age") or 0)
    out["avatar_url"] = f"/api/avatars/{k}.jpg"
    return out


def build_panel(age_min, age_max, genders, count, csv_bytes=None) -> list[dict]:
    if age_min > age_max or not (5 <= count <= 60):
        raise HTTPException(400, "Age range or viewer count is out of bounds.")
    gs = [g for g in genders.split(",") if g in ("F", "M")]
    if not gs:
        raise HTTPException(400, "Pick at least one gender.")
    if csv_bytes:
        df = load_csv(io.BytesIO(csv_bytes), (age_min, age_max), gs).head(count)
        if df.empty:
            raise HTTPException(400, "No one in the CSV matches this age range and gender.")
    else:
        df = sample_personas(count, (age_min, age_max), gs)
    return with_colors(df).to_dict("records")


def own_test(test_id: str, user: User) -> Test:
    if not re.fullmatch(r"[a-f0-9]{12}", test_id):
        raise HTTPException(404, "Test not found.")
    with db.session() as s:
        t = s.get(Test, test_id)
    if not t or t.owner != user.email:
        raise HTTPException(404, "Test not found.")
    return t


def summary_out(t: Test) -> dict:
    return {"id": t.id, "name": t.name, "created_at": t.created_at.isoformat(), "status": t.status,
            "viewers": t.viewers, "media_kind": t.media_kind,
            "thumb_url": f"/api/tests/{t.id}/thumb.jpg" if (db.test_dir(t.id) / "thumb.jpg").exists() else None,
            "engaged": t.engaged, "avg_interest": t.avg_interest}


# ---------------- auth ----------------
class LoginIn(BaseModel):
    email: str
    password: str


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    u = auth.login(body.email, body.password, request, response)
    return {"email": u.email, "name": u.name}


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    auth.logout(response)


@app.get("/api/auth/me")
def me(user: User = auth.CurrentUser):
    return {"email": user.email, "name": user.name}


# ---------------- audience ----------------
@app.get("/api/audience/preview")
def preview(age_min: int = 20, age_max: int = 45, genders: str = "F,M", count: int = 20,
            user: User = auth.CurrentUser):
    return {"personas": [persona_out(p) for p in build_panel(age_min, age_max, genders, count)]}


@app.get("/api/avatars/{key}.jpg")
def avatar(key: str, user: User = auth.CurrentUser):
    if not re.fullmatch(r"[a-f0-9]{16}", key):
        raise HTTPException(404, "Not found.")
    jpg = AVATAR_INDEX / f"{key}.jpg"
    if not jpg.exists():
        idx = AVATAR_INDEX / f"{key}.json"
        if not idx.exists() or not avatars.available():
            raise HTTPException(404, "Portrait not available.")
        try:
            avatars.generate_one(json.loads(idx.read_text()))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Could not draw the portrait: {str(e)[:120]}") from None
    return FileResponse(jpg, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000"})


# ---------------- tests ----------------
@app.post("/api/tests", status_code=201)
async def create_test(media: UploadFile = File(...), age_min: int = Form(20), age_max: int = Form(45),
                      genders: str = Form("F,M"), count: int = Form(20), context: str = Form(""),
                      people_csv: UploadFile | None = File(None), user: User = auth.CurrentUser):
    ext = Path(media.filename or "").suffix.lower()
    if ext not in MEDIA_TYPES:
        raise HTTPException(400, "Upload an MP4, MOV, WEBM, PNG or JPG file.")
    csv_bytes = await people_csv.read() if people_csv else None
    personas = build_panel(age_min, age_max, genders, count, csv_bytes)

    test_id = uuid.uuid4().hex[:12]
    d = db.test_dir(test_id)
    size = 0
    with open(d / "upload.bin", "wb") as f:
        while chunk := await media.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD:
                f.close()
                shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(413, "The file is larger than 500 MB.")
            f.write(chunk)

    kind, mime = MEDIA_TYPES[ext]
    for p in personas:
        persona_out(p)  # register portraits
    with db.session() as s:
        s.add(Test(id=test_id, owner=user.email, name=Path(media.filename).stem[:120], context=context[:500],
                   media_kind=kind, mime=mime, viewers=len(personas), message="Waiting to start"))
        s.commit()
    jobs.submit(test_id, media.filename, personas, context)
    return {"id": test_id}


@app.get("/api/tests")
def list_tests(user: User = auth.CurrentUser):
    with db.session() as s:
        rows = s.exec(select(Test).where(Test.owner == user.email).order_by(Test.created_at.desc())).all()
    return {"tests": [summary_out(t) for t in rows]}


@app.get("/api/tests/{test_id}")
def get_test(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    out = {**summary_out(t), "context": t.context,
           "progress": {"step": t.step, "message": t.message, "percent": t.percent},
           "error": t.error, "where": t.where, "media_url": f"/api/tests/{t.id}/media",
           "duration": 0, "width": 0, "height": 0, "grid": [48, 27], "frames": [], "transcript": [],
           "personas": [], "gaze": [], "summary": None}
    f = db.test_dir(t.id) / "result.json"
    if t.status == "done" and f.exists():
        r = json.loads(f.read_text())
        a = r["analysis"]
        out.update(duration=a.get("duration", 0), width=a.get("width", 0), height=a.get("height", 0),
                   grid=a.get("grid", [48, 27]), frames=[{"t": x["t"], "heat": x["heat"]} for x in a["frames"]],
                   transcript=a.get("transcript", []), personas=[persona_out(p) for p in r["personas"]],
                   gaze=[{**g, "thought_en": g.get("thought_en", "")} for g in r["gaze"]], summary=r["summary"])
    return out


@app.delete("/api/tests/{test_id}", status_code=204)
def delete_test(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    if t.status in ("queued", "running"):
        raise HTTPException(409, "This test is still running. Delete it when it has finished.")
    with db.session() as s:
        s.delete(s.get(Test, t.id))
        s.commit()
    shutil.rmtree(db.test_dir(t.id), ignore_errors=True)


@app.get("/api/tests/{test_id}/media")
def media(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    f = db.test_dir(t.id) / "media.bin"
    if not f.exists():
        raise HTTPException(404, "Media is not ready yet.")
    return FileResponse(f, media_type=t.mime)


@app.get("/api/tests/{test_id}/thumb.jpg")
def thumb(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    f = db.test_dir(t.id) / "thumb.jpg"
    if not f.exists():
        raise HTTPException(404, "No thumbnail yet.")
    return FileResponse(f, media_type="image/jpeg")


# ---------------- interviews ----------------
class AskIn(BaseModel):
    message: str


def _result(t: Test) -> dict:
    f = db.test_dir(t.id) / "result.json"
    if t.status != "done" or not f.exists():
        raise HTTPException(409, "The test has not finished yet.")
    return json.loads(f.read_text())


def _history_file(t: Test, pid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid):
        raise HTTPException(404, "Viewer not found.")
    return db.test_dir(t.id) / f"interview-{pid}.json"


@app.get("/api/tests/{test_id}/interviews/{pid}")
def get_interview(test_id: str, pid: str, user: User = auth.CurrentUser):
    f = _history_file(own_test(test_id, user), pid)
    return {"messages": json.loads(f.read_text()) if f.exists() else []}


@app.post("/api/tests/{test_id}/interviews/{pid}")
def ask(test_id: str, pid: str, body: AskIn, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    msg = body.message.strip()[:2000]
    if not msg:
        raise HTTPException(400, "Write a question first.")
    r = _result(t)
    persona = next((p for p in r["personas"] if p["id"] == pid), None)
    if not persona:
        raise HTTPException(404, "Viewer not found.")
    f = _history_file(t, pid)
    history = json.loads(f.read_text()) if f.exists() else []
    kf = r["analysis"]["keyframes"][0] if r["analysis"].get("keyframes") else None
    mine = [g for g in r["gaze"] if g["id"] == pid]
    try:
        reply = chat_with_persona(persona, mine, list(history), msg, kf, r["analysis"].get("transcript"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"The viewer could not answer right now: {str(e)[:120]}") from None
    history += [{"role": "user", "content": msg}, {"role": "assistant", "content": reply}]
    f.write_text(json.dumps(history, ensure_ascii=False))
    return {"reply": reply, "messages": history}
