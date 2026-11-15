"""Runs INSIDE a Daytona sandbox (also runnable locally as a fallback).

Usage: python analyze_video.py <input video/image> <output json>

Samples frames at ~2 fps, computes a spectral-residual saliency map per frame
(Hou & Zhang 2007) with a mild center bias, and writes a small JSON grid per
frame plus a few keyframe JPEGs for the persona-gaze step.
"""
import base64
import json
import sys

import cv2
import numpy as np

GRID_W, GRID_H = 48, 27
SAMPLE_FPS = 2.0
MAX_FRAMES = 90
N_KEYFRAMES = 6


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
              "grid": [GRID_W, GRID_H], "frames": [], "keyframes": []}
    for t, frame in frames:
        sal = saliency(frame)
        peak = np.unravel_index(np.argmax(sal), sal.shape)
        result["frames"].append({
            "t": round(t, 3),
            "heat": np.round(sal * 255).astype(np.uint8).flatten().tolist(),
            "peak": [round((peak[1] + 0.5) / GRID_W, 3), round((peak[0] + 0.5) / GRID_H, 3)],
        })

    picks = np.linspace(0, len(frames) - 1, min(N_KEYFRAMES, len(frames))).round().astype(int)
    for i in sorted(set(picks.tolist())):
        t, frame = frames[i]
        scale = 768 / max(w, h)
        thumb = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame
        ok, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
        result["keyframes"].append({"t": round(t, 3), "jpg_b64": base64.b64encode(buf).decode()})

    with open(out, "w") as fh:
        json.dump(result, fh)
    print(f"ok frames={len(result['frames'])} keyframes={len(result['keyframes'])}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
