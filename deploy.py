"""Deploy AdLens itself into a Daytona sandbox and print a shareable signed preview URL.

  python deploy.py            # deploy (or redeploy) and print URL
  python deploy.py --delete   # tear the demo sandbox down
"""
import os
import sys
import time
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona, ListSandboxesQuery, SessionExecuteRequest
from dotenv import dotenv_values, load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
FILES = ["app.py", "requirements.txt", "core/__init__.py", "core/avatars.py", "core/ui.py", "core/reports.py", "core/i18n.py", "core/auth.py", ".streamlit/config.toml", "core/analyze_video.py", "core/gaze.py",
         "core/personas.py", "core/player.py", "core/sandbox.py"]
NAME = "adlens-demo"
PORT = 8501
APP_DIR = "/home/daytona/adlens"
URL_TTL = 6 * 3600  # signed link valid for 6 hours

daytona = Daytona()


def find_existing():
    return next(iter(daytona.list(ListSandboxesQuery(labels={"app": NAME}))), None)


def delete():
    sb = find_existing()
    if sb:
        daytona.delete(sb)
        print("deleted", sb.id)
    else:
        print("nothing to delete")


def deploy():
    wanted = ("ANTHROPIC_API_KEY", "DAYTONA_API_KEY", "OPENAI_API_KEY",
              "APP_PASSWORD", "ALLOWED_EMAILS", "ALLOWED_DOMAINS")
    env_file = dotenv_values(ROOT / ".env")
    # .env first, then the shell environment (so `APP_PASSWORD=... python deploy.py` also works)
    secrets = {k: v for k in wanted if (v := (env_file.get(k) or os.getenv(k) or "").strip())}
    if not (secrets.get("APP_PASSWORD") or (ROOT / ".streamlit" / "secrets.toml").exists()):
        raise SystemExit("Refusing to deploy without sign-in: set APP_PASSWORD in .env "
                         "or configure Google sign-in in .streamlit/secrets.toml")

    old = find_existing()  # only tear down the old demo once we know the new one can be deployed
    if old:
        print("removing previous demo sandbox", old.id)
        daytona.delete(old)
    print("creating sandbox…")
    sb = daytona.create(CreateSandboxFromSnapshotParams(
        language="python", env_vars=secrets, labels={"app": NAME}, auto_stop_interval=0))
    print("sandbox", sb.id)

    sb.process.exec(f"mkdir -p {APP_DIR}/core {APP_DIR}/.streamlit")
    for f in FILES:
        p = ROOT / f
        sb.fs.upload_file(p.read_bytes() if p.exists() else b"", f"{APP_DIR}/{f}")
    if (ROOT / ".streamlit" / "secrets.toml").exists():  # Google sign-in config (redirect_uri must be the deploy URL)
        sb.fs.upload_file((ROOT / ".streamlit" / "secrets.toml").read_bytes(), f"{APP_DIR}/.streamlit/secrets.toml")
    faces = sorted((ROOT / "cache" / "avatars").glob("*.jpg"))
    if faces:  # ship already-generated portraits so the demo doesn't pay for them twice
        sb.process.exec(f"mkdir -p {APP_DIR}/cache/avatars")
        for f in faces:
            sb.fs.upload_file(f.read_bytes(), f"{APP_DIR}/cache/avatars/{f.name}")
    saved = [f for f in (ROOT / "reports").glob("*/*") if f.is_file()]
    for f in saved:  # ship saved reports so the demo link opens with them
        rel = f.relative_to(ROOT).as_posix()
        sb.process.exec(f"mkdir -p '{APP_DIR}/{Path(rel).parent.as_posix()}'")
        sb.fs.upload_file(f.read_bytes(), f"{APP_DIR}/{rel}")
    print("uploaded", len(FILES), "files +", len(faces), "portraits +", len(saved), "report files; installing deps…")
    r = sb.process.exec(f"cd {APP_DIR} && pip install -q -r requirements.txt", timeout=600)
    if r.exit_code != 0:
        raise SystemExit(r.result[-1500:])

    sb.process.create_session("web")
    sb.process.execute_session_command("web", SessionExecuteRequest(
        command=(f"cd {APP_DIR} && python -m streamlit run app.py --server.port {PORT} "
                 "--server.address 0.0.0.0 --server.headless true --server.maxUploadSize 500 "
                 "--server.enableCORS false --server.enableXsrfProtection false"),
        run_async=True))

    for _ in range(30):
        r = sb.process.exec(f"curl -s -o /dev/null -w '%{{http_code}}' localhost:{PORT}/_stcore/health")
        if r.result.strip() == "200":
            break
        time.sleep(2)
    else:
        raise SystemExit("streamlit did not come up")

    url = sb.create_signed_preview_url(PORT, expires_in_seconds=URL_TTL)
    print("\n✅ AdLens is live (link valid 6h):\n" + url.url)


if __name__ == "__main__":
    delete() if "--delete" in sys.argv else deploy()
