"""Deploy the Next.js + FastAPI version of AdLens into one Daytona sandbox.

  python deploy_app.py            # build + run, print a signed preview URL
  python deploy_app.py --delete   # tear it down

Needs in .env (or the shell): ANTHROPIC_API_KEY, DAYTONA_API_KEY, OPENAI_API_KEY,
ADLENS_ADMIN_EMAIL + ADLENS_ADMIN_PASSWORD (the first account; at least 10 characters).
"""
import io
import os
import secrets
import sys
import tarfile
import time
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona, ListSandboxesQuery, SessionExecuteRequest
from dotenv import dotenv_values, load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
NAME = "adlens-app"
WEB_PORT = 3000
APP = "/home/daytona/adlens"
URL_TTL = 24 * 3600
SKIP = {"node_modules", ".next", ".git", "__pycache__", ".venv"}

daytona = Daytona()


def env(k):
    return (dotenv_values(ROOT / ".env").get(k) or os.getenv(k) or "").strip()


def bundle() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for top in ["backend", "core", "frontend", "reports", "requirements.txt"]:
            p = ROOT / top
            if not p.exists():
                continue
            for f in ([p] if p.is_file() else p.rglob("*")):
                if f.is_file() and not (SKIP & set(f.relative_to(ROOT).parts)):
                    tar.add(f, arcname=f.relative_to(ROOT).as_posix())
        for f in (ROOT / "cache" / "avatars").glob("*"):  # already drawn portraits
            tar.add(f, arcname=f.relative_to(ROOT).as_posix())
    return buf.getvalue()


def find_existing():
    return next(iter(daytona.list(ListSandboxesQuery(labels={"app": NAME}))), None)


def run(sb, cmd, timeout=900):
    r = sb.process.exec(cmd, timeout=timeout)
    if r.exit_code != 0:
        raise SystemExit(f"failed: {cmd[:80]}\n{r.result[-2000:]}")
    return r.result


def deploy():
    admin, admin_pw = env("ADLENS_ADMIN_EMAIL"), env("ADLENS_ADMIN_PASSWORD")
    if not admin or len(admin_pw) < 10:
        raise SystemExit("Set ADLENS_ADMIN_EMAIL and ADLENS_ADMIN_PASSWORD (10+ chars) in .env first.")
    keys = {k: env(k) for k in ("ANTHROPIC_API_KEY", "DAYTONA_API_KEY", "OPENAI_API_KEY") if env(k)}
    keys.update(SECRET_KEY=secrets.token_urlsafe(48), COOKIE_SECURE="1", ADLENS_DATA=f"{APP}/data")

    old = find_existing()
    if old:
        print("removing previous sandbox", old.id)
        daytona.delete(old)
    print("creating sandbox…")
    sb = daytona.create(CreateSandboxFromSnapshotParams(language="python", env_vars=keys,
                                                        labels={"app": NAME}, auto_stop_interval=0))
    print("sandbox", sb.id)
    run(sb, f"mkdir -p {APP}")
    sb.fs.upload_file(bundle(), f"{APP}/bundle.tgz")
    run(sb, f"cd {APP} && tar xzf bundle.tgz && rm bundle.tgz")
    print("installing python deps…")
    run(sb, f"cd {APP} && pip install -q -r requirements.txt")
    print("building frontend…")
    run(sb, f"cd {APP}/frontend && npm ci --no-audit --no-fund && npm run build", timeout=1200)

    # first account: password passed through the environment of a one-off command, never written to disk
    r = sb.process.exec(f"cd {APP} && python -m backend.manage create-user '{admin}' 'Admin' \"$ADLENS_ADMIN_PASSWORD\" "
                        f"&& python -m backend.manage import-legacy '{admin}'",
                        env={"ADLENS_ADMIN_PASSWORD": admin_pw}, timeout=300)
    print(r.result.strip())

    for sid, cmd in [("api", f"cd {APP} && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"),
                     ("web", f"cd {APP}/frontend && npm run start -- -p {WEB_PORT} -H 0.0.0.0")]:
        sb.process.create_session(sid)
        sb.process.execute_session_command(sid, SessionExecuteRequest(command=cmd, run_async=True))
    for _ in range(60):
        ok = sb.process.exec(f"curl -s -o /dev/null -w '%{{http_code}}' localhost:{WEB_PORT}/login").result.strip()
        if ok == "200":
            break
        time.sleep(2)
    else:
        raise SystemExit("the web app did not come up")
    url = sb.create_signed_preview_url(WEB_PORT, expires_in_seconds=URL_TTL)
    print(f"\n✅ AdLens is live (link valid {URL_TTL // 3600}h):\n{url.url}")


def delete():
    sb = find_existing()
    print(f"deleted {sb.id}" if sb and not daytona.delete(sb) else "nothing to delete")


if __name__ == "__main__":
    delete() if "--delete" in sys.argv else deploy()
