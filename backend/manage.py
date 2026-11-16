"""Admin CLI.

  python -m backend.manage create-user someone@example.com "Name"     # asks for the password
  python -m backend.manage import-legacy someone@example.com          # copy old Streamlit reports into this account
  python -m backend.manage migrate-sqlite                             # copy users + tests from data/adlens.db into DATABASE_URL
"""
import getpass
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import select

from backend import db, jobs
from backend.auth import hash_password
from backend.db import Test, User


def create_user(email: str, name: str = "", password: str | None = None):
    db.init()
    pw = password or getpass.getpass("Password (min 10 chars): ")
    if len(pw) < 10:
        sys.exit("Password must be at least 10 characters.")
    with db.session() as s:
        u = s.exec(select(User).where(User.email == email.lower())).first()
        if u:
            u.password_hash = hash_password(pw)
            print("updated password for", email)
        else:
            s.add(User(email=email.lower(), name=name, password_hash=hash_password(pw)))
            print("created", email)
        s.commit()


def import_legacy(email: str):
    """Old app saved reports/<id>/report.json + media.bin; convert them into tests for this user."""
    db.init()
    n = 0
    for f in sorted((db.ROOT / "reports").glob("*/report.json")):
        rep = json.loads(f.read_text())
        tid = __import__("hashlib").sha1(rep["id"].encode()).hexdigest()[:12]
        with db.session() as s:
            if s.get(Test, tid):
                continue
        d = db.test_dir(tid)
        shutil.copy(f.parent / "media.bin", d / "media.bin")
        a = rep["analysis"]
        if a.get("keyframes"):
            import base64
            (d / "thumb.jpg").write_bytes(base64.b64decode(a["keyframes"][0]["jpg_b64"]))
        summary = jobs.summarize(rep["gaze"])
        (d / "result.json").write_text(json.dumps(
            {"analysis": a, "gaze": rep["gaze"], "personas": rep["personas"], "summary": summary}, ensure_ascii=False))
        for pid, msgs in (rep.get("chats") or {}).items():
            (d / f"interview-{pid}.json").write_text(json.dumps(msgs, ensure_ascii=False))
        created = datetime.strptime(rep["created"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        with db.session() as s:
            s.add(Test(id=tid, owner=email.lower(), name=Path(rep["name"]).stem[:120], created_at=created,
                       status="done", step="done", percent=100, context=rep.get("context", ""),
                       media_kind="video" if rep["mime"].startswith("video") else "image", mime=rep["mime"],
                       viewers=len(rep["personas"]), where=rep.get("where"),
                       engaged=summary["engaged"] if summary else None,
                       avg_interest=summary["avg_interest"] if summary else None))
            s.commit()
        n += 1
    print("imported", n, "reports for", email)


def migrate_sqlite():
    """One-off: copy rows from the local SQLite file into the configured DATABASE_URL (e.g. Supabase)."""
    from sqlmodel import Session, create_engine
    src = create_engine(f"sqlite:///{db.DATA / 'adlens.db'}")
    if db.DB_URL.startswith("sqlite"):
        sys.exit("DATABASE_URL is not set to a different database.")
    db.init()
    n = {"users": 0, "tests": 0}
    with Session(src) as a, db.session() as b:
        for model, label in ((User, "users"), (Test, "tests")):
            for row in a.exec(select(model)).all():
                key = row.email if model is User else row.id
                exists = (b.exec(select(User).where(User.email == key)).first() if model is User else b.get(Test, key))
                if not exists:
                    data = row.model_dump()
                    if model is User:
                        data.pop("id", None)
                    b.add(model(**data))
                    n[label] += 1
        b.commit()
    print("migrated", n)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "create-user":
        create_user(*args)
    elif cmd == "import-legacy":
        import_legacy(*args)
    elif cmd == "migrate-sqlite":
        migrate_sqlite()
    else:
        print(__doc__)
