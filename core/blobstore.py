"""Durable file storage on Supabase Storage, with the local data folder as a working copy.

The app keeps reading and writing plain files under DATA (and cache/avatars). This module makes them
durable without touching every write site:
- start(): make sure the private bucket exists, restore every small file that is missing locally
  (results, talks, reports, profiles, portraits); large media is fetched lazily with ensure_local();
- a watcher thread uploads any file whose size+mtime changed and stayed stable for one scan;
- delete_prefix() removes objects when a test or talk is deleted.
Without SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY everything is a no-op (local development).
"""
import logging
import mimetypes
import os
import threading
import time
from pathlib import Path

import httpx

from core.llm import DATA, ROOT

log = logging.getLogger("adlens.blobs")
URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = os.getenv("SUPABASE_BUCKET", "adlens")
ENABLED = bool(URL and KEY)

# local root -> object key prefix
ROOTS = [(DATA, "data/"), (ROOT / "cache" / "avatars", "avatars/")]
SKIP_NAMES = {"upload.bin", "adlens.db", ".secret_key"}
LAZY_NAMES = {"media.bin"}
SKIP_SUFFIXES = {".lock", ".tmp", ".db-journal", ".db-wal", ".db-shm"}

_http = None
_seen: dict[str, tuple] = {}


def _client():
    global _http
    if _http is None:
        _http = httpx.Client(base_url=f"{URL}/storage/v1", timeout=120,
                             headers={"Authorization": f"Bearer {KEY}", "apikey": KEY})
    return _http


def key_for(path: Path) -> str | None:
    path = Path(path).resolve()
    for root, prefix in ROOTS:
        try:
            return prefix + path.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return None


def path_for(key: str) -> Path | None:
    for root, prefix in ROOTS:
        if key.startswith(prefix):
            return root / key[len(prefix):]
    return None


def _skip(path: Path) -> bool:
    return path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES or path.name.startswith(".")


def upload(path: Path):
    k = key_for(path)
    if not ENABLED or not k or _skip(path) or not path.exists():
        return
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    r = _client().post(f"/object/{BUCKET}/{k}", content=path.read_bytes(),
                       headers={"x-upsert": "true", "content-type": ctype})
    if r.status_code >= 300:
        raise RuntimeError(f"upload {k}: {r.status_code} {r.text[:200]}")


def download(key: str) -> bool:
    p = path_for(key)
    if not ENABLED or not p:
        return False
    r = _client().get(f"/object/{BUCKET}/{key}")
    if r.status_code != 200:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(r.content)
    tmp.replace(p)
    st = p.stat()
    _seen[str(p)] = (st.st_size, st.st_mtime, "uploaded")
    return True


def list_keys(prefix: str) -> list[str]:
    """Recursive listing of object keys under prefix (folder-style)."""
    out, stack = [], [prefix.rstrip("/")]
    while stack:
        folder = stack.pop()
        offset = 0
        while True:
            r = _client().post(f"/object/list/{BUCKET}",
                               json={"prefix": folder, "limit": 1000, "offset": offset})
            if r.status_code != 200:
                break
            items = r.json()
            for it in items:
                full = f"{folder}/{it['name']}" if folder else it["name"]
                (stack.append(full) if it.get("id") is None else out.append(full))
            if len(items) < 1000:
                break
            offset += 1000
    return out


def ensure_local(path: Path) -> bool:
    """Fetch one file from storage if it is missing locally (used for large media)."""
    path = Path(path)
    if path.exists():
        return True
    k = key_for(path)
    return bool(k) and download(k)


def ensure_dir(path: Path):
    """Restore a whole folder (e.g. one test) if it is missing locally; media stays lazy."""
    path = Path(path)
    k = key_for(path)
    if not ENABLED or not k or (path.exists() and any(path.iterdir())):
        return
    for key in list_keys(k):
        if Path(key).name not in LAZY_NAMES and not (path_for(key) or Path("/nonexistent")).exists():
            download(key)


def delete_prefix(path: Path):
    k = key_for(path)
    if not ENABLED or not k:
        return
    keys = list_keys(k) if Path(path).suffix == "" else [k]
    for i in range(0, len(keys), 100):
        _client().request("DELETE", f"/object/{BUCKET}", json={"prefixes": keys[i:i + 100]})
    for root, _ in ROOTS:
        for p in list(_seen):
            if p.startswith(str(Path(path))):
                _seen.pop(p, None)


def _scan_once():
    for root, _ in ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or _skip(p):
                continue
            st = p.stat()
            sig = (st.st_size, st.st_mtime)
            prev = _seen.get(str(p))
            if prev and prev[:2] == sig and prev[2] == "uploaded":
                continue
            if prev and prev[:2] == sig and prev[2] == "pending":  # unchanged for one scan -> stable
                try:
                    upload(p)
                    _seen[str(p)] = (*sig, "uploaded")
                except Exception as e:  # noqa: BLE001
                    log.warning("sync failed for %s: %s", p, e)
            else:
                _seen[str(p)] = (*sig, "pending")


def _watch(every=4.0):
    while True:
        try:
            _scan_once()
        except Exception as e:  # noqa: BLE001
            log.warning("sync scan failed: %s", e)
        time.sleep(every)


def flush():
    """Upload everything that changed, now (two scans so new files count as stable)."""
    if ENABLED:
        _scan_once()
        _scan_once()


def start():
    if not ENABLED:
        log.info("Supabase storage not configured; files stay local")
        return
    r = _client().post("/bucket", json={"id": BUCKET, "name": BUCKET, "public": False})
    if r.status_code not in (200, 201) and "already exists" not in r.text.lower() and r.status_code != 409:
        log.warning("bucket check: %s %s", r.status_code, r.text[:200])
    restored = 0
    for _, prefix in ROOTS:
        for key in list_keys(prefix.rstrip("/")):
            p = path_for(key)
            if p and Path(key).name not in LAZY_NAMES and not p.exists():
                restored += download(key)
    # everything already on disk counts as uploaded only after the first scans confirm it
    log.info("restored %d files from Supabase storage", restored)
    threading.Thread(target=_watch, daemon=True, name="blob-sync").start()
