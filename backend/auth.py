"""Email + password accounts with a signed, httpOnly session cookie.

- Sign-in attempts are counted in Postgres (per email and per client IP), so the limit holds across every
  serverless instance; unknown emails cost a bcrypt check too, so timing does not reveal which accounts exist.
- The session payload carries a fingerprint of the password hash: changing a password ends every old session.
"""
import hashlib
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlmodel import Field, SQLModel, select

from backend.db import DATA, User, session

COOKIE = "adlens_session"
MAX_AGE = 7 * 24 * 3600
WINDOW_S = 600
LIMIT_PER_EMAIL = 8
LIMIT_PER_IP = 30
SECURE_COOKIE = os.getenv("COOKIE_SECURE", "1" if os.getenv("VERCEL") else "0") == "1"


def _secret() -> str:
    s = os.getenv("SECRET_KEY")
    if s:
        return s
    if os.getenv("VERCEL"):
        raise RuntimeError("SECRET_KEY must be set in production.")
    f = DATA / ".secret_key"  # dev: persist a random key so sessions survive restarts
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48))
        f.chmod(0o600)
    return f.read_text().strip()


_signer = URLSafeTimedSerializer(_secret(), salt="adlens-session")
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt()).decode()
_mem_attempts: dict[str, list[float]] = defaultdict(list)  # fallback only if the database is unreachable


class LoginAttempt(SQLModel, table=True):
    __tablename__ = "login_attempt"
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True)            # "e:<email>" or "ip:<address>"
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() or request.headers.get("x-real-ip") or
            (request.client.host if request.client else "?"))[:64]


def rate_limit(email: str, ip: str):
    """Raise 429 when this email or this IP made too many attempts in the window; then record the attempt."""
    keys = {f"e:{email}": LIMIT_PER_EMAIL, f"ip:{ip}": LIMIT_PER_IP}
    since = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_S)
    try:
        from sqlalchemy import delete, func
        with session() as s:
            for k, limit in keys.items():
                n = s.exec(select(func.count()).select_from(LoginAttempt)
                           .where(LoginAttempt.key == k, LoginAttempt.at >= since)).one()
                if n >= limit:
                    raise HTTPException(429, "Too many sign-in attempts. Try again in a few minutes.")
            s.add_all([LoginAttempt(key=k) for k in keys])
            s.exec(delete(LoginAttempt).where(LoginAttempt.at < since - timedelta(days=1)))
            s.commit()
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - database trouble: fall back to the per-process counter
        now = time.time()
        for k, limit in keys.items():
            _mem_attempts[k] = [t for t in _mem_attempts[k] if now - t < WINDOW_S]
            if len(_mem_attempts[k]) >= limit:
                raise HTTPException(429, "Too many sign-in attempts. Try again in a few minutes.") from None
            _mem_attempts[k].append(now)


def _fingerprint(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def login(email: str, password: str, request: Request, response: Response) -> User:
    email = normalize_email(email)
    rate_limit(email, _client_ip(request))
    with session() as s:
        user = s.exec(select(User).where(User.email == email)).first()
    ok = check_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(401, "Email or password is not correct.")
    response.set_cookie(COOKIE, _signer.dumps([user.email, _fingerprint(user)]), max_age=MAX_AGE, httponly=True,
                        samesite="lax", secure=SECURE_COOKIE, path="/")
    return user


def logout(response: Response):
    response.delete_cookie(COOKIE, path="/", samesite="lax", secure=SECURE_COOKIE, httponly=True)


def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    try:
        payload = _signer.loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Your session has expired. Sign in again.") from None
    if not (isinstance(payload, list) and len(payload) == 2):   # pre-fingerprint cookies: sign in again
        raise HTTPException(401, "Your session has expired. Sign in again.")
    email, fp = payload
    with session() as s:
        user = s.exec(select(User).where(User.email == email)).first()
    if not user or not secrets.compare_digest(fp, _fingerprint(user)):
        raise HTTPException(401, "Your session has expired. Sign in again.")
    return user


CurrentUser = Depends(current_user)
