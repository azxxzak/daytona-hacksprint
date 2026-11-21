"""Object storage with a pathlib-like face.

`SPath("tests/abc/result.json").read_text()` reads Supabase Storage when SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY are set (Vercel, workers), and the local DATA folder otherwise (dev).
Only the subset of Path the app uses is implemented. Large media is never proxied through the API:
use signed_download_url() / signed_upload_url() so browsers and workers talk to Storage directly.
"""
import fnmatch
import os
import threading
from functools import lru_cache
from pathlib import Path, PurePosixPath

import httpx

URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = os.getenv("SUPABASE_BUCKET", "adlens")
REMOTE = bool(URL and KEY)
_ROOT = Path(__file__).resolve().parent.parent
LOCAL = Path(os.getenv("ADLENS_DATA") or ("/tmp/adlens-data" if os.getenv("VERCEL") else _ROOT / "data"))

_local = threading.local()


def _http() -> httpx.Client:
    c = getattr(_local, "client", None)
    if c is None:
        c = _local.client = httpx.Client(base_url=f"{URL}/storage/v1", timeout=60,
                                         headers={"Authorization": f"Bearer {KEY}", "apikey": KEY})
    return c


def _ctype(name: str) -> str:
    return {".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".md": "text/markdown",
            ".mp4": "video/mp4"}.get(PurePosixPath(name).suffix, "application/octet-stream")


class SPath:
    def __init__(self, key: str | PurePosixPath = ""):
        self.key = str(PurePosixPath(str(key))).lstrip("/") if str(key) else ""

    # --- path algebra ---
    def __truediv__(self, part):
        return SPath(f"{self.key}/{part}" if self.key else str(part))

    def __str__(self):
        return self.key

    def __repr__(self):
        return f"SPath({self.key!r})"

    def __eq__(self, other):
        return isinstance(other, SPath) and other.key == self.key

    def __hash__(self):
        return hash(self.key)

    name = property(lambda self: PurePosixPath(self.key).name)
    suffix = property(lambda self: PurePosixPath(self.key).suffix)
    stem = property(lambda self: PurePosixPath(self.key).stem)
    parent = property(lambda self: SPath(str(PurePosixPath(self.key).parent)))

    def with_suffix(self, s):
        return SPath(str(PurePosixPath(self.key).with_suffix(s)))

    def _lp(self) -> Path:
        return LOCAL / self.key

    # --- io ---
    def read_bytes(self) -> bytes:
        if not REMOTE:
            return self._lp().read_bytes()
        r = _http().get(f"/object/{BUCKET}/{self.key}")
        if r.status_code in (400, 404):
            raise FileNotFoundError(self.key)
        r.raise_for_status()
        return r.content

    def read_text(self, encoding="utf-8") -> str:
        return self.read_bytes().decode(encoding)

    def write_bytes(self, data: bytes):
        if not REMOTE:
            p = self._lp()
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)
            return len(data)
        r = _http().post(f"/object/{BUCKET}/{self.key}", content=data,
                         headers={"x-upsert": "true", "content-type": _ctype(self.key)})
        r.raise_for_status()
        return len(data)

    def write_text(self, s: str, encoding="utf-8"):
        return self.write_bytes(s.encode(encoding))

    def exists(self) -> bool:
        if not REMOTE:
            return self._lp().exists()
        r = _http().head(f"/object/{BUCKET}/{self.key}")
        if r.status_code == 200:
            return True
        return bool(_list_keys(self.key, limit=1))  # "folder" exists if it has objects

    def unlink(self, missing_ok=True):
        if not REMOTE:
            self._lp().unlink(missing_ok=missing_ok)
            return
        _http().request("DELETE", f"/object/{BUCKET}", json={"prefixes": [self.key]})

    def mkdir(self, *a, **kw):  # folders are implicit in object storage
        if not REMOTE:
            self._lp().mkdir(parents=True, exist_ok=True)

    def glob(self, pattern: str):
        """Supports patterns like '*.json' and '*/report.json' relative to this folder."""
        depth = pattern.count("/") + 1
        if not REMOTE:
            base = self._lp()
            return [SPath(str(PurePosixPath(self.key) / p.relative_to(base).as_posix()))
                    for p in base.glob(pattern) if p.is_file()] if base.exists() else []
        out = []
        for k in _list_keys(self.key, depth=depth):
            rel = k[len(self.key) + 1:] if self.key else k
            if fnmatch.fnmatch(rel, pattern):
                out.append(SPath(k))
        return out

    def rmtree(self):
        if not REMOTE:
            import shutil
            shutil.rmtree(self._lp(), ignore_errors=True)
            return
        keys = _list_keys(self.key, depth=8)
        for i in range(0, len(keys), 100):
            _http().request("DELETE", f"/object/{BUCKET}", json={"prefixes": keys[i:i + 100]})

    # --- direct transfer links ---
    def signed_download_url(self, expires=3600) -> str | None:
        if not REMOTE:
            return None
        r = _http().post(f"/object/sign/{BUCKET}/{self.key}", json={"expiresIn": expires})
        if r.status_code != 200:
            return None
        return f"{URL}/storage/v1{r.json()['signedURL']}"

    def signed_upload_url(self) -> str | None:
        if not REMOTE:
            return None
        r = _http().post(f"/object/upload/sign/{BUCKET}/{self.key}", headers={"x-upsert": "true"})
        r.raise_for_status()
        return f"{URL}/storage/v1{r.json()['url']}"


def _list_keys(prefix: str, depth=1, limit=None) -> list[str]:
    out, frontier = [], [(prefix.rstrip("/"), 1)]
    while frontier:
        folder, level = frontier.pop()
        offset = 0
        while True:
            r = _http().post(f"/object/list/{BUCKET}", json={"prefix": folder, "limit": 1000, "offset": offset})
            if r.status_code != 200:
                break
            items = r.json()
            for it in items:
                full = f"{folder}/{it['name']}" if folder else it["name"]
                if it.get("id") is None:
                    if level < depth:
                        frontier.append((full, level + 1))
                else:
                    out.append(full)
                    if limit and len(out) >= limit:
                        return out
            if len(items) < 1000:
                break
            offset += 1000
    return out


BUCKET_FILE_LIMIT = 500 * 1024 * 1024   # enforced by Storage itself, so a signed PUT cannot exceed it


def ensure_bucket():
    """Private bucket with a hard per-file size limit (the plan's own limit may be lower)."""
    if REMOTE:
        cfg = {"public": False, "file_size_limit": BUCKET_FILE_LIMIT}
        r = _http().post("/bucket", json={"id": BUCKET, "name": BUCKET, **cfg})
        if r.status_code >= 400:
            r = _http().put(f"/bucket/{BUCKET}", json={"id": BUCKET, "name": BUCKET, **cfg})
        return r.status_code


@lru_cache(maxsize=64)
def cached_json(key: str, version: str = "") -> str:
    """Small in-process cache for immutable blobs (results of finished tests). `version` busts it."""
    return SPath(key).read_text()
