"""Database models. SQLite by default; set DATABASE_URL for Postgres in production."""
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("ADLENS_DATA", ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)

def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{DATA / 'adlens.db'}"
    for old in ("postgres://", "postgresql://"):  # Supabase gives plain postgresql:// — use the psycopg 3 driver
        if url.startswith(old):
            return "postgresql+psycopg://" + url[len(old):]
    return url


DB_URL = _db_url()
engine = create_engine(DB_URL, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})


def now():
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str = ""
    password_hash: str
    created_at: datetime = Field(default_factory=now)


class Test(SQLModel, table=True):
    id: str = Field(primary_key=True)
    owner: str = Field(index=True)            # user email
    name: str
    created_at: datetime = Field(default_factory=now)
    status: str = "queued"                    # queued | running | done | failed
    step: str = "queued"                      # queued | sandbox | analysis | viewers | saving | done
    message: str = ""
    percent: int = 0
    error: str | None = None
    context: str = ""
    media_kind: str = "video"                 # video | image
    mime: str = "video/mp4"
    viewers: int = 0
    engaged: int | None = None
    avg_interest: float | None = None
    where: str | None = None


def init():
    SQLModel.metadata.create_all(engine)


def session():
    return Session(engine)


def test_dir(test_id: str) -> Path:
    d = DATA / "tests" / test_id
    if not d.exists():
        from core import blobstore
        blobstore.ensure_dir(d)  # restore a test that only exists in Supabase storage
    d.mkdir(parents=True, exist_ok=True)
    return d
