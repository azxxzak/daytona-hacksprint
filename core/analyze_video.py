"""Runs INSIDE a Daytona sandbox (also runnable locally as a fallback).

Usage: python analyze_video.py <input video/image> <output json>

Samples frames at ~2 fps and writes a small attention grid per frame plus a few keyframe JPEGs for the
persona-gaze step. The grid comes from the trained saliency model (UNISAL, core/attention.py) when its ONNX
files are present (ATTENTION_MODEL_DIR, baked into the worker snapshot); otherwise from a spectral-residual
map (Hou & Zhang 2007) with a mild centre bias, which is much weaker (see scripts/saliency_benchmark.py).
"""
import base64
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

GRID_W, GRID_H = 48, 27
SAMPLE_FPS = 2.0
MAX_FRAMES = 240          # 3-min video -> one heatmap every ~0.75 s
KEYFRAME_EVERY_S = 10     # persona gaze sampled every 10 s
MIN_KEYFRAMES, MAX_KEYFRAMES = 6, 18
MODEL_DIR = os.getenv("ATTENTION_MODEL_DIR", "/home/daytona/models")
MODEL_MAX_FRAMES = 540    # CPU budget for the video model (~6 fps for 90 s, fewer per second for longer ads)


def _grid(m: np.ndarray) -> np.ndarray:
    g = cv2.resize(m.astype(np.float32), (GRID_W, GRID_H), interpolation=cv2.INTER_AREA)
    g -= g.min()
    return g / (g.max() + 1e-8)


def load_model():
    if os.getenv("ATTENTION_MODEL", "unisal") != "unisal" or not Path(MODEL_DIR, "unisal_image.onnx").exists():
        return None
    try:
        from core.attention import Model
    except ImportError:   # run as a plain script next to attention.py
        from attention import Model
    try:
        return Model(MODEL_DIR)
    except Exception as e:  # noqa: BLE001 - never fail a test because of the model
        print("attention model unavailable:", e)
        return None


def model_maps(model, path: str, duration: float) -> list[tuple[float, np.ndarray]]:
    """Run the video model over the clip at up to 6 fps (state carried frame to frame) -> [(t, grid)]."""
    try:
        from core import attention as from_core
    except ImportError:
        import attention as from_core
    fps_want = min(from_core.VIDEO_FPS, MODEL_MAX_FRAMES / max(duration, 1e-6))
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / fps_want)))
    state = np.zeros(from_core.STATE_SHAPE, dtype=np.float32)
    out, idx = [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                s, state = model.vid.run(None, {"frame": from_core._prep(frame, from_core.VIDEO_SIZE), "state": state})
                out.append((idx / fps, _grid(s[0])))
        idx += 1
    cap.release()
    return out


def transcribe(src: str) -> list:
    """Speech-to-text with timestamps (Whisper, CPU). Returns [] if no speech or on failure."""
    try:
        import os

        from faster_whisper import WhisperModel
        import subprocess

        import imageio_ffmpeg
        # Decode audio with ffmpeg ourselves (avoids PyAV version issues): 16 kHz mono float32.
        raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-protocol_whitelist", "file", "-i", src, "-vn",
                              "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             capture_output=True, timeout=300).stdout
        audio = np.frombuffer(raw, dtype=np.float32)
        if audio.size < 16000:
            return []
        model = WhisperModel(os.getenv("WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio, vad_filter=True, beam_size=1)
        out = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
               for s in segments if s.text.strip()]
        print(f"speech language={info.language} p={info.language_probability:.2f}")
        return out
    except Exception as e:  # noqa: BLE001
        print("transcribe failed:", e)
        return []


def make_proxy(src: str, dst: str) -> bool:
    """Shrink to 480p H.264 + AAC so any browser can play it and the page stays light."""
    try:
        import subprocess

        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run([ff, "-y", "-loglevel", "error", "-protocol_whitelist", "file", "-i", src,
                            "-vf", "scale='min(854,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
                            "-movflags", "+faststart", dst], capture_output=True, text=True, timeout=600)
        return r.returncode == 0
    except Exception as e:  # noqa: BLE001
        print("proxy failed:", e)
        return False


def saliency(frame_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    small = cv2.resize(gray, (64, 36))
    f = np.fft.fft2(small)
    log_amp = np.log(np.abs(f) + 1e-8)
    phase = np.angle(f)
    residual = log_amp - cv2.blur(log_amp, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    sal = cv2.GaussianBlur(sal.astype(np.float32), (0, 0), 2.5)

    # People tend to look near the centre of the frame: blend a centre prior.
    ys, xs = np.mgrid[0:36, 0:64]
    center = np.exp(-(((xs - 32) / 22) ** 2 + ((ys - 18) / 13) ** 2))
    sal = sal / (sal.max() + 1e-8)
    sal = 0.75 * sal + 0.25 * center

    sal = cv2.resize(sal, (GRID_W, GRID_H), interpolation=cv2.INTER_AREA)
    sal -= sal.min()
    sal /= sal.max() + 1e-8
    return sal


def read_frames(path: str):
    img = cv2.imread(path)
    if img is not None:  # still image (banner)
        return [(0.0, img)], 0.0
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / fps if total else 0.0
    step = max(1, int(round(fps / SAMPLE_FPS)))
    if total and total / step > MAX_FRAMES:
        step = int(np.ceil(total / MAX_FRAMES))
    frames, idx = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            fh, fw = frame.shape[:2]
            s = 768 / max(fh, fw)
            if s < 1:  # keep memory low for long / 4K videos
                frame = cv2.resize(frame, (int(fw * s), int(fh * s)), interpolation=cv2.INTER_AREA)
            frames.append((idx / fps, frame))
        idx += 1
    cap.release()
    return frames, duration or (idx / fps)


def main(src: str, out: str):
    frames, duration = read_frames(src)
    if not frames:
        raise SystemExit("could not read any frames")
    h, w = frames[0][1].shape[:2]

    result = {"width": w, "height": h, "duration": duration,
              "grid": [GRID_W, GRID_H], "frames": [], "keyframes": [], "heat_model": "spectral"}
    model, mmaps = load_model(), []
    if model is not None:
        try:
            if duration > 0 and model.vid is not None:
                mmaps = model_maps(model, src, duration)
            else:
                mmaps = [(t, _grid(model.image(f))) for t, f in frames]
            result["heat_model"] = "unisal"
        except Exception as e:  # noqa: BLE001 - fall back to the spectral map
            print("attention model failed:", e)
            mmaps = []
    mtimes = np.array([t for t, _ in mmaps]) if mmaps else None
    for t, frame in frames:
        sal = mmaps[int(np.abs(mtimes - t).argmin())][1] if mmaps else saliency(frame)
        peak = np.unravel_index(np.argmax(sal), sal.shape)
        result["frames"].append({
            "t": round(t, 3),
            "heat": np.round(sal * 255).astype(np.uint8).flatten().tolist(),
            "peak": [round((peak[1] + 0.5) / GRID_W, 3), round((peak[0] + 0.5) / GRID_H, 3)],
        })

    n_kf = int(np.clip(duration / KEYFRAME_EVERY_S, MIN_KEYFRAMES, MAX_KEYFRAMES))
    picks = np.linspace(0, len(frames) - 1, min(n_kf, len(frames))).round().astype(int)
    for i in sorted(set(picks.tolist())):
        t, frame = frames[i]
        scale = 768 / max(w, h)
        thumb = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame
        ok, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
        result["keyframes"].append({"t": round(t, 3), "jpg_b64": base64.b64encode(buf).decode()})

    if duration > 0:
        result["transcript"] = transcribe(src)
        print(f"transcript segments={len(result['transcript'])}")

    with open(out, "w") as fh:
        json.dump(result, fh, ensure_ascii=False)
    print(f"ok frames={len(result['frames'])} keyframes={len(result['keyframes'])} heat={result['heat_model']}")
    if duration > 0:
        proxy = out.rsplit("/", 1)[0] + "/proxy.mp4" if "/" in out else "proxy.mp4"
        print("proxy", "ok" if make_proxy(src, proxy) else "failed")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
