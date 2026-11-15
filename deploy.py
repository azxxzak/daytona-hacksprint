"""Deploy AdLens itself into a Daytona sandbox and print a shareable signed preview URL.

  python deploy.py            # deploy (or redeploy) and print URL
  python deploy.py --delete   # tear the demo sandbox down
"""
import sys
import time
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona, ListSandboxesQuery, SessionExecuteRequest
from dotenv import dotenv_values, load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
FILES = ["app.py", "requirements.txt", "core/__init__.py", "core/analyze_video.py", "core/gaze.py",
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
    old = find_existing()
    if old:
        print("removing previous demo sandbox", old.id)
        daytona.delete(old)

    secrets = {k: v for k, v in dotenv_values(ROOT / ".env").items()
               if k in ("ANTHROPIC_API_KEY", "DAYTONA_API_KEY") and v}
    print("creating sandbox…")
    sb = daytona.create(CreateSandboxFromSnapshotParams(
        language="python", env_vars=secrets, labels={"app": NAME}, auto_stop_interval=0))
    print("sandbox", sb.id)

    sb.process.exec(f"mkdir -p {APP_DIR}/core")
    for f in FILES:
        p = ROOT / f
        sb.fs.upload_file(p.read_bytes() if p.exists() else b"", f"{APP_DIR}/{f}")
    print("uploaded", len(FILES), "files; installing deps…")
    r = sb.process.exec(f"cd {APP_DIR} && pip install -q -r requirements.txt", timeout=600)
    if r.exit_code != 0:
        raise SystemExit(r.result[-1500:])

    sb.process.create_session("web")
    sb.process.execute_session_command("web", SessionExecuteRequest(
        command=(f"cd {APP_DIR} && python -m streamlit run app.py --server.port {PORT} "
                 "--server.address 0.0.0.0 --server.headless true --server.maxUploadSize 100 "
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
