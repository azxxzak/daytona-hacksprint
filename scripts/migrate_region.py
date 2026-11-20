"""Copy everything from one Supabase project to another (e.g. Sydney -> Tokyo).

.env must hold the NEW project as DATABASE_URL / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY and the old one as
OLD_DATABASE_URL / OLD_SUPABASE_URL / OLD_SUPABASE_SERVICE_ROLE_KEY.

    python -m scripts.migrate_region            # copy tables + storage (safe to re-run: skips what exists)
    python -m scripts.migrate_region --check    # only compare counts

Never prints keys, passwords or row contents.
"""
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx
from dotenv import load_dotenv

load_dotenv()
import os  # noqa: E402

from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from backend import db  # noqa: E402,F401 - registers User/Test/Usage
from core import persona_bank  # noqa: E402,F401 - registers the bank tables

BUCKET = os.getenv("SUPABASE_BUCKET", "adlens")
SKIP_KEYS = {"dev_user.txt"}


def engine(raw):
    url = db._db_url(raw)
    args = {"prepare_threshold": None} if ":6543/" in url else {}
    return create_engine(url, connect_args=args)


def storage(url, key):
    return httpx.Client(base_url=url.rstrip("/") + "/storage/v1", timeout=120,
                        headers={"Authorization": f"Bearer {key}", "apikey": key})


def list_all(cli, prefix=""):
    out, frontier = [], [prefix]
    while frontier:
        folder = frontier.pop()
        offset = 0
        while True:
            r = cli.post(f"/object/list/{BUCKET}", json={"prefix": folder, "limit": 1000, "offset": offset})
            r.raise_for_status()
            items = r.json()
            for it in items:
                full = f"{folder}/{it['name']}" if folder else it["name"]
                if it.get("id") is None:
                    frontier.append(full)
                else:
                    out.append(full)
            if len(items) < 1000:
                break
            offset += 1000
    return out


def tables():
    return [t for t in SQLModel.metadata.sorted_tables]


def counts(eng):
    out = {}
    with eng.connect() as c:
        for t in tables():
            try:
                out[t.name] = c.execute(select(func.count()).select_from(t)).scalar()
            except Exception:  # noqa: BLE001 - table missing
                c.rollback()
                out[t.name] = None
    return out


def copy_tables(src, dst):
    SQLModel.metadata.create_all(dst)
    for t in tables():
        pk = [c.name for c in t.primary_key.columns]
        with src.connect() as a, dst.begin() as b:
            have = {tuple(r) for r in b.execute(select(*[t.c[k] for k in pk]))}
            rows = [dict(r._mapping) for r in a.execute(select(t))]
            new = [r for r in rows if tuple(r[k] for k in pk) not in have]
            for i in range(0, len(new), 500):
                b.execute(t.insert(), new[i:i + 500])
            # keep integer id sequences ahead of the copied ids
            for col in t.primary_key.columns:
                if col.autoincrement is True or (col.type.python_type is int and col.name == "id"):
                    b.execute(text(f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', '{col.name}'), "
                                   f"COALESCE((SELECT MAX({col.name}) FROM \"{t.name}\"), 1))"))
        print(f"  {t.name}: {len(rows)} rows, {len(new)} copied")


def copy_storage(old, new):
    new.post("/bucket", json={"id": BUCKET, "name": BUCKET, "public": False})  # 409 if it exists
    keys = [k for k in list_all(old) if k.split("/")[-1] not in SKIP_KEYS]
    have = set(list_all(new))
    todo = [k for k in keys if k not in have]
    print(f"  storage: {len(keys)} objects, {len(todo)} to copy")

    def one(k):
        for attempt in range(3):
            try:
                r = old.get(f"/object/{BUCKET}/{k}")
                r.raise_for_status()
                w = new.post(f"/object/{BUCKET}/{k}", content=r.content, headers={
                    "content-type": r.headers.get("content-type", "application/octet-stream"), "x-upsert": "true"})
                w.raise_for_status()
                return None
            except httpx.HTTPError as e:
                err = e
        return f"{k}: {type(err).__name__}"

    with ThreadPoolExecutor(8) as ex:
        fails = [f for f in ex.map(one, todo) if f]
    print(f"  storage: {len(todo) - len(fails)} copied, {len(fails)} failed")
    for f in fails[:10]:
        print("   ", f)
    return keys


def main():
    need = ["OLD_DATABASE_URL", "OLD_SUPABASE_URL", "OLD_SUPABASE_SERVICE_ROLE_KEY",
            "DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    missing = [k for k in need if not os.getenv(k)]
    if missing:
        sys.exit(f"missing in .env: {', '.join(missing)}")
    if os.getenv("OLD_SUPABASE_URL").rstrip("/") == os.getenv("SUPABASE_URL").rstrip("/"):
        sys.exit("OLD_SUPABASE_URL and SUPABASE_URL are the same project.")
    src, dst = engine(os.getenv("OLD_DATABASE_URL")), engine(os.getenv("DATABASE_URL"))
    old = storage(os.getenv("OLD_SUPABASE_URL"), os.getenv("OLD_SUPABASE_SERVICE_ROLE_KEY"))
    new = storage(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    if "--check" not in sys.argv:
        print("tables:")
        copy_tables(src, dst)
        print("storage:")
        copy_storage(old, new)
    a, b = counts(src), counts(dst)
    sa, sb = len([k for k in list_all(old) if k.split("/")[-1] not in SKIP_KEYS]), len(list_all(new))
    print("\ncheck (old -> new):")
    for k in a:
        print(f"  {k:22} {a[k]!s:>6} -> {b[k]!s:>6}  {'OK' if a[k] == b[k] else 'DIFF'}")
    print(f"  {'storage objects':22} {sa:>6} -> {sb:>6}  {'OK' if sa <= sb else 'DIFF'}")


if __name__ == "__main__":
    main()
