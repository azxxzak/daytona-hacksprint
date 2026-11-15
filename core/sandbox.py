"""Run the video saliency analysis inside an isolated Daytona sandbox."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from daytona import Daytona

SCRIPT = Path(__file__).with_name("analyze_video.py")
REMOTE_DIR = "/tmp/adlab"


def analyze_in_daytona(media: bytes, filename: str, log=print) -> dict:
    daytona = Daytona()  # DAYTONA_API_KEY from env
    log("Creating Daytona sandbox… / サンドボックス作成中")
    sandbox = daytona.create()
    try:
        ext = Path(filename).suffix or ".mp4"
        src, out = f"{REMOTE_DIR}/input{ext}", f"{REMOTE_DIR}/result.json"
        sandbox.process.exec(f"mkdir -p {REMOTE_DIR}")
        log("Uploading media + analysis script… / アップロード中")
        sandbox.fs.upload_file(media, src)
        sandbox.fs.upload_file(SCRIPT.read_bytes(), f"{REMOTE_DIR}/analyze_video.py")

        log("Installing OpenCV in sandbox… / 環境構築中")
        r = sandbox.process.exec("pip install -q opencv-python-headless numpy imageio-ffmpeg faster-whisper",
                                 timeout=400)
        if r.exit_code != 0:
            raise RuntimeError(f"pip failed: {r.result[-500:]}")

        log("Heatmaps + Whisper speech-to-text… / ヒートマップ・音声書き起こし中")
        r = sandbox.process.exec(f"python {REMOTE_DIR}/analyze_video.py {src} {out}", timeout=600)
        if r.exit_code != 0:
            raise RuntimeError(f"analysis failed: {r.result[-800:]}")
        log(f"Sandbox: {r.result.strip()}")
        result = json.loads(sandbox.fs.download_file(out))
        if "proxy ok" in r.result:
            result["proxy"] = sandbox.fs.download_file(f"{REMOTE_DIR}/proxy.mp4")
            log(f"Browser-friendly 480p proxy: {len(result['proxy']) / 1e6:.1f} MB")
        return result
    finally:
        daytona.delete(sandbox)
        log("Sandbox deleted. / サンドボックス削除")


def analyze_locally(media: bytes, filename: str, log=print) -> dict:
    """Fallback so the demo never dies if the network/sandbox is down."""
    log("⚠️ Using local fallback / ローカル実行")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "input" + (Path(filename).suffix or ".mp4"))
        out = os.path.join(d, "result.json")
        Path(src).write_bytes(media)
        r = subprocess.run([sys.executable, str(SCRIPT), src, out], check=True, capture_output=True, text=True)
        result = json.loads(Path(out).read_text())
        if "proxy ok" in r.stdout:
            result["proxy"] = Path(d, "proxy.mp4").read_bytes()
        return result


def analyze(media: bytes, filename: str, log=print) -> tuple[dict, str]:
    try:
        return analyze_in_daytona(media, filename, log), "daytona"
    except Exception as e:  # noqa: BLE001 - keep the demo alive
        log(f"Daytona error: {e}")
        return analyze_locally(media, filename, log), "local"
