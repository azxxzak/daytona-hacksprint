"""Email + password accounts with a signed, httpOnly session cookie."""
import os
import secrets
import time
from collections import defaultdict

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlmodel import select

from backend.db import DATA, User, session

COOKIE = "adlens_session"
MAX_AGE = 14 * 24 * 3600


def _secret() -> str:
    s = os.getenv("SECRET_KEY")
    if s:
        return s
    f = DATA / ".secret_key"  # dev: persist a random key so sessions survive restarts
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48))
        f.chmod(0o600)
    return f.read_text().strip()


_signer = URLSafeTimedSerializer(_secret(), salt="adlens-session")
_attempts: dict[str, list[float]] = defaultdict(list)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def rate_limit(key: str, limit=8, window=600):
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < window]
    if len(_attempts[key]) >= limit:
        raise HTTPException(429, "Too many sign-in attempts. Try again in a few minutes.")
    _attempts[key].append(now)


def login(email: str, password: str, request: Request, response: Response) -> User:
    rate_limit(f"{request.client.host if request.client else '?'}:{email.lower()}")
    with session() as s:
        user = s.exec(select(User).where(User.email == email.lower().strip())).first()
    if not user or not check_password(password, user.password_hash):
        raise HTTPException(401, "Email or password is not correct.")
    response.set_cookie(COOKIE, _signer.dumps(user.email), max_age=MAX_AGE, httponly=True,
                        samesite="lax", secure=os.getenv("COOKIE_SECURE", "0") == "1")
    return user


def logout(response: Response):
    response.delete_cookie(COOKIE)


def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    try:
        email = _signer.loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Your session has expired. Sign in again.") from None
    with session() as s:
        user = s.exec(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    return user


CurrentUser = Depends(current_user)
