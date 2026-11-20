"""AdLens API. Run: .venv/bin/uvicorn backend.main:app --port 8000"""
import base64
import hashlib
import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile  # noqa: E402
from fastapi.responses import RedirectResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlmodel import select  # noqa: E402

from backend import auth, db, worker_ctl  # noqa: E402
from backend.db import Test, User  # noqa: E402
from core import avatars, library, llm, persona_profile, store, themes as themes_mod  # noqa: E402
from core import talk as talk_mod  # noqa: E402
from core.gaze import chat_with_persona  # noqa: E402
from core.personas import load_csv, sample_personas, with_colors  # noqa: E402
from core.store import SPath  # noqa: E402

try:  # 5,000-person bank (Supabase); falls back to synthetic sampling until it is built
    from core import persona_bank
except Exception:  # noqa: BLE001
    persona_bank = None

logging.basicConfig(level=logging.INFO)
db.init()
app = FastAPI(title="AdLens API", docs_url="/api/docs", openapi_url="/api/openapi.json")

MAX_UPLOAD = 500 * 1024 * 1024
MEDIA_TYPES = {".mp4": ("video", "video/mp4"), ".mov": ("video", "video/quicktime"), ".webm": ("video", "video/webm"),
               ".png": ("image", "image/png"), ".jpg": ("image", "image/jpeg"), ".jpeg": ("image", "image/jpeg")}
UPLOAD_ID = re.compile(r"[a-f0-9]{24}\.(mp4|mov|webm|png|jpg|jpeg|csv)")


# ---------------- helpers ----------------
def _gender(p):
    g = str(p.get("gender", "")).strip().lower()
    return "Female" if g in ("f", "female", "女性", "女") else "Male" if g in ("m", "male", "男性", "男") else p.get("gender", "")


def avatar_url(p: dict) -> str:
    src = p.get("source_id") or p.get("library_id") or (p["id"] if str(p.get("id", "")).startswith(("bank_", "lib_")) else "")
    if src:
        return f"/api/avatars/p/{src}.jpg"
    return f"/api/avatars/{avatars.key(p)}.jpg"


def register_portraits(personas: list[dict]):
    """Personas that are not in the bank/library get an index file so their portrait can be drawn later."""
    for p in personas:
        if not (p.get("source_id") or p.get("library_id")):
            (avatars.CACHE / f"{avatars.key(p)}.json").write_text(json.dumps(p, ensure_ascii=False, default=str))


def persona_out(p: dict, with_deep=False) -> dict:
    fields = ("id", "name", "age", "gender", "region", "occupation", "income", "interests", "media", "values", "color")
    out = {f: p.get(f, "") for f in fields}
    out["age"] = int(p.get("age") or 0)
    out["gender"] = _gender(p)
    out["avatar_url"] = avatar_url(p)
    if p.get("profile"):
        out["profile"] = p["profile"]
        if with_deep:
            out["has_deep_profile"] = persona_profile.deep_status(p) == "ready"
    return out


def _genders(genders) -> list[str]:
    gs = [g for g in (genders.split(",") if isinstance(genders, str) else genders) if g in ("F", "M")]
    if not gs:
        raise HTTPException(400, "Pick at least one gender.")
    return gs


def bank_panel(age_min, age_max, genders, count, regions=None, occupations=None, seed=None):
    if age_min > age_max or not (5 <= count <= 60):
        raise HTTPException(400, "Age range or viewer count is out of bounds.")
    gs = _genders(genders)
    if persona_bank is not None:
        try:
            ps, matched = persona_bank.sample(age_min, age_max, gs, count, regions=regions or None,
                                              occupations=occupations or None, seed=seed)
            if ps:
                return with_colors(ps), matched
        except Exception as e:  # noqa: BLE001
            logging.getLogger("adlens").warning("persona bank unavailable: %s", e)
    return with_colors(sample_personas(count, (age_min, age_max), gs, seed=seed or 42)), None


def csv_panel(csv_bytes, age_min, age_max, genders, count):
    ps = load_csv(csv_bytes, (age_min, age_max), _genders(genders))[:count]
    if not ps:
        raise HTTPException(400, "No one in the CSV matches this age range and gender.")
    return with_colors(ps)


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
            "thumb_url": f"/api/tests/{t.id}/thumb.jpg" if t.status == "done" else None,
            "engaged": t.engaged, "avg_interest": t.avg_interest}


def _owner_tag(user: User) -> str:
    return hashlib.sha1(user.email.encode()).hexdigest()[:12]


def _upload_key(user: User, upload_id: str) -> str:
    if not UPLOAD_ID.fullmatch(upload_id or ""):
        raise HTTPException(400, "Unknown upload.")
    return f"uploads/{_owner_tag(user)}/{upload_id}"


def _redirect(path: SPath, expires=3600, cache=True) -> Response:
    url = path.signed_download_url(expires=expires)
    if not url:
        raise HTTPException(404, "Not found.")
    headers = {"Cache-Control": f"private, max-age={expires - 120}"} if cache else {}
    return RedirectResponse(url, status_code=302, headers=headers)


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
            regions: str = "", occupations: str = "", seed: int | None = None, user: User = auth.CurrentUser):
    ps, matched = bank_panel(age_min, age_max, genders, count, _csv_list(regions), _csv_list(occupations), seed)
    return {"personas": [persona_out(p) for p in ps], "matched": matched}


def _csv_list(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


@app.get("/api/audience/facets")
def facets(user: User = auth.CurrentUser):
    if persona_bank is None:
        return {"total": 0, "regions": [], "occupations": [], "age_bands": []}
    return persona_bank.facets()


def _persona_by_source(pid: str) -> dict | None:
    if pid.startswith("lib_"):
        return library.all_personas().get(pid)
    if pid.startswith("bank_") and persona_bank is not None:
        got = persona_bank.get([pid])
        return got[0] if got else None
    return None


def _serve_portrait(p: dict) -> Response:
    jpg = avatars.CACHE / f"{avatars.key(p)}.jpg"
    if avatars.cached(p) is None:
        if not avatars.available():
            raise HTTPException(404, "Portrait not available.")
        try:
            avatars.generate_one(p)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Could not draw the portrait: {str(e)[:120]}") from None
    return _redirect(jpg, expires=24 * 3600)


@app.get("/api/avatars/p/{pid}.jpg")
def avatar_by_persona(pid: str, user: User = auth.CurrentUser):
    if not re.fullmatch(r"(lib|bank)_[A-Za-z0-9_]{1,40}", pid):
        raise HTTPException(404, "Not found.")
    p = _persona_by_source(pid)
    if not p:
        raise HTTPException(404, "Persona not found.")
    return _serve_portrait(p)


@app.get("/api/avatars/{key}.jpg")
def avatar(key: str, user: User = auth.CurrentUser):
    if not re.fullmatch(r"[a-f0-9]{16}", key):
        raise HTTPException(404, "Not found.")
    if avatars._cached_key(key) is not None:
        return _redirect(avatars.CACHE / f"{key}.jpg", expires=24 * 3600)
    idx = avatars.CACHE / f"{key}.json"
    try:
        p = json.loads(idx.read_text())
    except (FileNotFoundError, OSError, ValueError):
        raise HTTPException(404, "Portrait not available.") from None
    return _serve_portrait(p)


# ---------------- uploads (browser -> Supabase Storage directly) ----------------
class UploadIn(BaseModel):
    filename: str
    size: int = 0
    content_type: str = ""


@app.post("/api/uploads")
def create_upload(body: UploadIn, user: User = auth.CurrentUser):
    ext = PurePosixPath(body.filename).suffix.lower()
    if ext not in MEDIA_TYPES and ext != ".csv":
        raise HTTPException(400, "Upload an MP4, MOV, WEBM, PNG, JPG or CSV file.")
    if body.size > MAX_UPLOAD:
        raise HTTPException(413, "The file is larger than 500 MB.")
    upload_id = f"{uuid.uuid4().hex[:24]}{ext}"
    url = SPath(_upload_key(user, upload_id)).signed_upload_url()
    if not url:
        raise HTTPException(501, "Direct uploads need Supabase storage to be configured.")
    ctype = body.content_type or ("text/csv" if ext == ".csv" else MEDIA_TYPES[ext][1])
    return {"upload_id": upload_id, "upload_url": url, "method": "PUT",
            "headers": {"content-type": ctype, "x-upsert": "true"}}


# ---------------- tests ----------------
class PanelIn(BaseModel):
    source: str = "bank"
    age_min: int = 20
    age_max: int = 45
    genders: list[str] = ["F", "M"]
    count: int = 20
    regions: list[str] = []
    occupations: list[str] = []
    seed: int | None = None
    persona_ids: list[str] = []
    csv_upload_id: str = ""


class NewTestIn(BaseModel):
    upload_id: str
    name: str = ""
    context: str = ""
    lang: str = "ja"
    panel: PanelIn = PanelIn()


def _panel_from(body: NewTestIn, user: User) -> list[dict]:
    pn = body.panel
    if pn.source == "library":
        lib = library.all_personas()
        ids = list(dict.fromkeys(pn.persona_ids))
        if not (1 <= len(ids) <= 60) or any(i not in lib for i in ids):
            raise HTTPException(400, "Pick between 1 and 60 personas from the library.")
        return [{**lib[i], "library_id": i, "source_id": i, "id": f"P{n + 1:03d}"} for n, i in enumerate(ids)]
    if pn.source == "csv":
        try:
            raw = SPath(_upload_key(user, pn.csv_upload_id)).read_bytes()
        except FileNotFoundError:
            raise HTTPException(400, "The CSV upload was not found. Upload it again.") from None
        ps = csv_panel(raw, pn.age_min, pn.age_max, pn.genders, pn.count)
    else:
        ps, _ = bank_panel(pn.age_min, pn.age_max, pn.genders, pn.count, pn.regions, pn.occupations, pn.seed)
    out = []
    for n, p in enumerate(ps):
        src = p["id"] if str(p.get("id", "")).startswith("bank_") else None
        out.append({**p, "id": f"P{n + 1:03d}", **({"source_id": src} if src else {})})
    return out


@app.post("/api/tests", status_code=201)
def create_test(body: NewTestIn, user: User = auth.CurrentUser):
    media_key = _upload_key(user, body.upload_id)
    ext = PurePosixPath(body.upload_id).suffix.lower()
    if ext not in MEDIA_TYPES:
        raise HTTPException(400, "Upload an MP4, MOV, WEBM, PNG or JPG file.")
    if not SPath(media_key).exists():
        raise HTTPException(400, "The upload did not finish. Upload the file again.")
    personas = _panel_from(body, user)
    register_portraits(personas)
    kind, mime = MEDIA_TYPES[ext]
    test_id = uuid.uuid4().hex[:12]
    (db.test_dir(test_id) / "personas.json").write_text(json.dumps(personas, ensure_ascii=False, default=str))
    with db.session() as s:
        t = Test(id=test_id, owner=user.email, name=(body.name.strip() or "Untitled test")[:120],
                 context=body.context[:500], media_kind=kind, mime=mime, viewers=len(personas),
                 message="Waiting to start")
        s.add(t)
        s.commit()
        s.refresh(t)
    try:
        worker_ctl.start(t, personas, media_key, body.upload_id, mime, body.lang)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("adlens").exception("worker start failed")
        with db.session() as s:
            row = s.get(Test, test_id)
            row.status, row.error = "failed", f"Could not start the analysis: {str(e)[:200]}"
            s.add(row)
            s.commit()
    return {"id": test_id}


@app.get("/api/tests")
def list_tests(user: User = auth.CurrentUser):
    with db.session() as s:
        rows = s.exec(select(Test).where(Test.owner == user.email).order_by(Test.created_at.desc())).all()
    rows = [worker_ctl.poll(t) if t.status in ("queued", "running") else t for t in rows]
    return {"tests": [summary_out(t) for t in rows]}


def _result_text(t: Test) -> str:
    return store.cached_json(f"tests/{t.id}/result.json", version=f"{t.status}:{t.percent}")


def _result(t: Test) -> dict:
    if t.status != "done":
        raise HTTPException(409, "The test has not finished yet.")
    try:
        return json.loads(_result_text(t))
    except FileNotFoundError:
        raise HTTPException(409, "The test result is missing.") from None


@app.get("/api/tests/{test_id}")
def get_test(test_id: str, user: User = auth.CurrentUser):
    t = worker_ctl.poll(own_test(test_id, user))
    out = {**summary_out(t), "context": t.context,
           "progress": {"step": t.step, "message": t.message, "percent": t.percent},
           "error": t.error, "where": t.where, "media_url": f"/api/tests/{t.id}/media",
           "duration": 0, "width": 0, "height": 0, "grid": [48, 27], "frames": [], "transcript": [],
           "personas": [], "gaze": [], "summary": None, "themes": None}
    if t.status == "done":
        r = _result(t)
        a = r["analysis"]
        out.update(duration=a.get("duration", 0), width=a.get("width", 0), height=a.get("height", 0),
                   grid=a.get("grid", [48, 27]), frames=[{"t": x["t"], "heat": x["heat"]} for x in a["frames"]],
                   transcript=a.get("transcript", []), personas=[persona_out(p) for p in r["personas"]],
                   gaze=[{**g, "thought_en": g.get("thought_en", "")} for g in r["gaze"]], summary=r["summary"],
                   themes=r.get("themes"))
    elif t.status in ("queued", "running"):
        try:  # the panel is known from the start, so the progress view can show who is watching
            out["personas"] = [persona_out(p) for p in json.loads((db.test_dir(t.id) / "personas.json").read_text())]
        except (FileNotFoundError, ValueError):
            pass
    return out


@app.delete("/api/tests/{test_id}", status_code=204)
def delete_test(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    if t.status in ("queued", "running"):
        raise HTTPException(409, "This test is still running. Delete it when it has finished.")
    with db.session() as s:
        s.delete(s.get(Test, t.id))
        s.commit()
    db.test_dir(t.id).rmtree()


@app.get("/api/tests/{test_id}/media")
def media(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    if t.status != "done":
        raise HTTPException(404, "Media is not ready yet.")
    return _redirect(db.test_dir(t.id) / "media.bin", expires=6 * 3600)


@app.get("/api/tests/{test_id}/thumb.jpg")
def thumb(test_id: str, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    return _redirect(db.test_dir(t.id) / "thumb.jpg", expires=24 * 3600)


# ---------------- interviews (v1, kept for old clients) ----------------
class AskIn(BaseModel):
    message: str


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
    if people_csv is None:
        ps, matched = bank_panel(age_min, age_max, genders, count)
        return {"personas": [persona_out(p) for p in ps], "matched": matched}
    ps = csv_panel(await people_csv.read(), age_min, age_max, genders, count)
    return {"personas": [persona_out(p) for p in ps], "matched": len(ps)}


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
    f = _talk_file(t, talk_id)
    f.unlink()


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

    owner = user.email

    def answer(p, said):
        llm.current_user.set(owner)
        gz = [g for g in r["gaze"] if g["id"] == p["id"]]
        return talk_mod.reply(p, members, gz, transcript, kf, thread, question, said, talk["mode"])

    def stream():
        llm.current_user.set(owner)
        user_msg = {"role": "user", "content": question, "at": _iso()}
        talk["messages"].append(user_msg)
        talk["title"] = talk["title"] or question[:80]
        talk["suggestion"] = None
        _save_talk(t, talk)
        yield sse("user", {"content": question, "at": user_msg["at"]})

        def store(p, rep):
            m = {"role": "persona", "persona_id": p["id"], "content": rep["content"], "at": _iso(),
                 "basis": rep.get("basis"), "because": rep.get("because", ""), "usd": rep.get("usd", 0)}
            talk["messages"].append(m)
            _save_talk(t, talk)
            return sse("message", {k: m[k] for k in ("persona_id", "content", "at", "basis", "because")})

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
                    rep = answer(p, list(said))
                    said.append((p, rep["content"]))
                    yield store(p, rep)
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
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


# ---------------- v3: library, deep profiles, themes, cost ----------------
@app.get("/api/library")
def get_library(user: User = auth.CurrentUser):
    ps = library.all_personas()
    groups = []
    for gid, name, name_en, desc, _ in library.GROUPS:
        members = [persona_out(p) for p in ps.values() if p["group"] == gid]
        groups.append({"id": gid, "name": name, "name_en": name_en, "description": desc, "personas": members})
    return {"groups": groups}


@app.get("/api/library/personas/{pid}")
def get_library_persona(pid: str, user: User = auth.CurrentUser):
    p = library.all_personas().get(pid)
    if not p:
        raise HTTPException(404, "Persona not found.")
    return persona_out(p)


def _global_persona(pid: str, user: User) -> dict:
    """lib_*/bank_* -> library or bank persona; '<test_id>:<persona_id>' -> a viewer of one of the user's tests."""
    if pid.startswith(("lib_", "bank_")):
        p = _persona_by_source(pid)
    elif ":" in pid:
        test_id, local = pid.split(":", 1)
        r = _result(own_test(test_id, user))
        p = next((x for x in r["personas"] if x["id"] == local), None)
    else:
        p = None
    if not p:
        raise HTTPException(404, "Persona not found.")
    if not p.get("profile"):
        llm.current_user.set(user.email)
        persona_profile.ensure_profiles([p])
    return p


@app.get("/api/personas/{pid}/deep")
def get_deep(pid: str, user: User = auth.CurrentUser):
    p = _global_persona(pid, user)
    status = persona_profile.deep_status(p)
    md = persona_profile.deep_path(p).read_text() if status == "ready" else None
    return {"status": status, "markdown": md}


@app.post("/api/personas/{pid}/deep")
def make_deep(pid: str, user: User = auth.CurrentUser):
    """Writes the long profile inside the request (serverless: no background work) and returns it."""
    p = _global_persona(pid, user)
    if persona_profile.deep_status(p) != "ready":
        llm.current_user.set(user.email)
        try:
            persona_profile.generate_deep(p)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"The full profile could not be written: {str(e)[:120]}") from None
    return get_deep(pid, user)


@app.post("/api/tests/{test_id}/themes")
def recompute_themes(test_id: str, lang: str = "ja", user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    r = _result(t)
    llm.current_user.set(user.email)
    r["themes"] = themes_mod.summarize(r["gaze"], r["personas"], "en" if lang == "en" else "ja")
    (db.test_dir(t.id) / "result.json").write_text(json.dumps(r, ensure_ascii=False))
    store.cached_json.cache_clear()
    return {"status": "ready", "themes": r["themes"]}


class EstimateIn(BaseModel):
    rounds: int = 1


# list-price upper bound for one viewer reply (image + profile + thread in, short JSON answer + thinking out)
_REPLY_TOKENS = (6000, 1500)


@app.post("/api/tests/{test_id}/talks/{talk_id}/estimate")
def estimate_talk(test_id: str, talk_id: str, body: EstimateIn, user: User = auth.CurrentUser):
    t = own_test(test_id, user)
    talk = json.loads(_talk_file(t, talk_id).read_text())
    rounds = max(1, min(body.rounds, 20))
    paid = [m["usd"] for m in talk["messages"] if m.get("role") == "persona" and m.get("usd")]
    pin, pout = llm.PRICES[llm.CHAT_MODEL]
    bound = (_REPLY_TOKENS[0] * pin + _REPLY_TOKENS[1] * pout) / 1e6
    per_reply, basis = (sum(paid[-12:]) / len(paid[-12:]), "measured") if paid else (bound, "price_list")
    sp, sout = llm.PRICES[llm.FAST_MODEL]
    per_round = per_reply * len(talk["persona_ids"]) + (2000 * sp + 600 * sout) / 1e6  # + follow-up suggestion
    return {"usd": round(per_round * rounds, 4), "per_round_usd": round(per_round, 4), "basis": basis}


@app.get("/api/usage")
def usage(user: User = auth.CurrentUser):
    u = llm.month_usage(user.email)
    with db.session() as s:
        n_tests = len(s.exec(select(Test).where(Test.owner == user.email)).all())
    return {"month_usd": u["month_usd"], "tests": n_tests, "talk_messages": u["calls"]["talk"]}


try:  # decision report + exports (separate module)
    from backend.report_routes import router as report_router  # noqa: E402
    app.include_router(report_router)
except ImportError as e:  # pragma: no cover
    logging.getLogger("adlens").warning("decision report routes not loaded: %s", e)
