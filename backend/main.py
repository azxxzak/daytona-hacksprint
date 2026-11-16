"""AdLens API. Run: .venv/bin/uvicorn backend.main:app --port 8000"""
import io
import json
import logging
import re
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlmodel import select  # noqa: E402

from backend import auth, db, jobs  # noqa: E402
from backend.db import Test, User  # noqa: E402
from core import avatars  # noqa: E402
from core import talk as talk_mod  # noqa: E402
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
    g = str(p.get("gender", "")).strip().lower()
    out["gender"] = "Female" if g in ("f", "female", "女性", "女") else "Male" if g in ("m", "male", "男性", "男") else p.get("gender", "")
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
                      name: str = Form(""), people_csv: UploadFile | None = File(None),
                      user: User = auth.CurrentUser):
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
        s.add(Test(id=test_id, owner=user.email, name=(name.strip() or Path(media.filename).stem)[:120],
                   context=context[:500],
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


# ---------------- v2: rename, CSV preview, talks ----------------
class RenameIn(BaseModel):
    name: str


@app.patch("/api/tests/{test_id}")
def rename_test(test_id: str, body: RenameIn, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    name = body.name.strip()[:120]
    if not name:
        raise HTTPException(400, "Give the test a name.")
    with db.session() as s:
        row = s.get(Test, t.id)
        row.name = name
        s.add(row)
        s.commit()
        s.refresh(row)
        return summary_out(row)


@app.post("/api/audience/preview")
async def preview_csv(age_min: int = Form(20), age_max: int = Form(45), genders: str = Form("F,M"),
                      count: int = Form(20), people_csv: UploadFile | None = File(None),
                      user: User = auth.CurrentUser):
    csv_bytes = await people_csv.read() if people_csv else None
    return {"personas": [persona_out(p) for p in build_panel(age_min, age_max, genders, count, csv_bytes)]}


class NewTalkIn(BaseModel):
    persona_ids: list[str]
    mode: str = "qa"


class TalkModeIn(BaseModel):
    mode: str


class TalkAskIn(BaseModel):
    message: str | None = None
    use_suggestion: bool = False


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _talk_file(t: Test, talk_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{10}", talk_id):
        raise HTTPException(404, "Talk not found.")
    f = db.test_dir(t.id) / "talks" / f"{talk_id}.json"
    if not f.exists():
        raise HTTPException(404, "Talk not found.")
    return f


def _save_talk(t: Test, talk: dict):
    d = db.test_dir(t.id) / "talks"
    d.mkdir(exist_ok=True)
    talk["updated_at"] = _iso()
    (d / f"{talk['id']}.json").write_text(json.dumps(talk, ensure_ascii=False))


@app.get("/api/tests/{test_id}/talks")
def list_talks(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    talks = []
    for f in (db.test_dir(t.id) / "talks").glob("*.json"):
        talk = json.loads(f.read_text())
        talk.pop("messages", None)
        talks.append(talk)
    return {"talks": sorted(talks, key=lambda x: x["updated_at"], reverse=True)}


@app.post("/api/tests/{test_id}/talks", status_code=201)
def new_talk(test_id: str, body: NewTalkIn, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    r = _result(t)
    known = {p["id"] for p in r["personas"]}
    ids = list(dict.fromkeys(body.persona_ids))
    if not ids or len(ids) > 20 or not set(ids) <= known:
        raise HTTPException(400, "Pick between 1 and 20 viewers from this test.")
    if body.mode not in ("qa", "conversation"):
        raise HTTPException(400, "Mode must be qa or conversation.")
    now = _iso()
    talk = {"id": uuid.uuid4().hex[:10], "test_id": t.id, "mode": body.mode, "persona_ids": ids, "title": "",
            "created_at": now, "updated_at": now, "messages": [], "suggestion": None}
    _save_talk(t, talk)
    return talk


@app.get("/api/tests/{test_id}/talks/{talk_id}")
def get_talk(test_id: str, talk_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    return json.loads(_talk_file(t, talk_id).read_text())


@app.patch("/api/tests/{test_id}/talks/{talk_id}")
def set_talk_mode(test_id: str, talk_id: str, body: TalkModeIn, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    if body.mode not in ("qa", "conversation"):
        raise HTTPException(400, "Mode must be qa or conversation.")
    talk = json.loads(_talk_file(t, talk_id).read_text())
    talk["mode"] = body.mode
    _save_talk(t, talk)
    return talk


@app.delete("/api/tests/{test_id}/talks/{talk_id}", status_code=204)
def delete_talk(test_id: str, talk_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    _talk_file(t, talk_id).unlink()


@app.post("/api/tests/{test_id}/talks/{talk_id}/ask")
def ask_talk(test_id: str, talk_id: str, body: TalkAskIn, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    talk = json.loads(_talk_file(t, talk_id).read_text())
    if body.use_suggestion:
        question = (talk.get("suggestion") or "").strip()
    else:
        question = (body.message or "").strip()[:2000]
    if not question:
        raise HTTPException(400, "Write a question first." if not body.use_suggestion else "No suggested question yet.")
    r = _result(t)
    by_id = {p["id"]: p for p in r["personas"]}
    members = [by_id[i] for i in talk["persona_ids"] if i in by_id]
    kf = r["analysis"]["keyframes"][len(r["analysis"]["keyframes"]) // 2] if r["analysis"].get("keyframes") else None
    transcript = r["analysis"].get("transcript")
    thread = list(talk["messages"])

    def sse(event, data):
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def answer(p, said):
        gz = [g for g in r["gaze"] if g["id"] == p["id"]]
        return talk_mod.reply(p, members, gz, transcript, kf, thread, question, said, talk["mode"])

    def stream():
        user_msg = {"role": "user", "content": question, "at": _iso()}
        talk["messages"].append(user_msg)
        talk["title"] = talk["title"] or question[:80]
        talk["suggestion"] = None
        _save_talk(t, talk)
        yield sse("user", {"content": question, "at": user_msg["at"]})

        def store(p, text):
            m = {"role": "persona", "persona_id": p["id"], "content": text, "at": _iso()}
            talk["messages"].append(m)
            _save_talk(t, talk)
            return sse("message", {k: m[k] for k in ("persona_id", "content", "at")})

        if talk["mode"] == "qa" or len(members) == 1:
            for p in members:
                yield sse("thinking", {"persona_id": p["id"]})
            with ThreadPoolExecutor(max_workers=6) as pool:
                futs = {pool.submit(answer, p, []): p for p in members}
                for fut in as_completed(futs):
                    p = futs[fut]
                    try:
                        yield store(p, fut.result())
                    except Exception as e:  # noqa: BLE001
                        yield sse("error", {"persona_id": p["id"], "detail": f"{p['name']} could not answer: {str(e)[:100]}"})
        else:
            said = []
            for p in members:
                yield sse("thinking", {"persona_id": p["id"]})
                try:
                    text = answer(p, list(said))
                    said.append((p, text))
                    yield store(p, text)
                except Exception as e:  # noqa: BLE001
                    yield sse("error", {"persona_id": p["id"], "detail": f"{p['name']} could not answer: {str(e)[:100]}"})
        try:
            talk["suggestion"] = talk_mod.suggest(talk["messages"], members)
        except Exception:  # noqa: BLE001
            talk["suggestion"] = None
        _save_talk(t, talk)
        yield sse("suggestion", {"content": talk["suggestion"]})
        yield sse("done", {})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
