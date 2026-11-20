"""Build the Daytona snapshot every test worker starts from (deps + Whisper model baked in).

  python scripts/build_worker_snapshot.py            # builds `adlens-worker-v1` if it does not exist
Bump SNAPSHOT when the worker's dependencies change (and set WORKER_SNAPSHOT for the API).
"""
import sys

from daytona import CreateSnapshotParams, Daytona, Image
from dotenv import load_dotenv

load_dotenv()
SNAPSHOT = "adlens-worker-v1"

image = (
    Image.debian_slim("3.12")
    .pip_install(["opencv-python-headless", "numpy", "imageio-ffmpeg", "faster-whisper", "anthropic", "httpx"])
    .run_commands(
        # bake the ffmpeg binary and the Whisper "base" model into the image so a test starts in seconds
        "python -c \"import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())\"",
        "python -c \"from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')\"",
    )
    .workdir("/home/daytona")
)

if __name__ == "__main__":
    d = Daytona()
    try:
        s = d.snapshot.get(SNAPSHOT)
        print("exists:", s.name, getattr(s, "state", ""))
        sys.exit(0)
    except Exception:  # noqa: BLE001 - not found -> build
        pass
    snap = d.snapshot.create(CreateSnapshotParams(name=SNAPSHOT, image=image), on_logs=lambda line: print(line, flush=True))
    print("built:", snap.name, getattr(snap, "state", ""))
