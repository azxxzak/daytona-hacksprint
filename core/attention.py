"""Predicted human attention from a trained saliency model (UNISAL, ONNX), for still images and video.

Runs in the Daytona worker with only onnxruntime + numpy + OpenCV. Model files come from
scripts/export_saliency_model.py: unisal_image.onnx (stills) and unisal_video.onnx (one frame + recurrent state).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
VIDEO_SIZE = (224, 384)      # (h, w) the video model was trained at
VIDEO_FPS = 6.0              # DHF1K training used every 5th frame of 30 fps video
STATE_SHAPE = (1, 256, 7, 12)


def _prep(img_bgr: np.ndarray, size_hw: tuple[int, int]) -> np.ndarray:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, (size_hw[1], size_hw[0]), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    return ((rgb - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)


def image_size(h: int, w: int) -> tuple[int, int]:
    """UNISAL's rule for stills: a 32-multiple grid of ~100-120 cells closest to the image's aspect ratio."""
    ar, best = h / w, None
    for n1 in range(7, 14):
        for n2 in range(7, 14):
            if 100 <= n1 * n2 <= 120:
                r = min(ar, n1 / n2) / max(ar, n1 / n2)
                if best is None or r > best[0]:
                    best = (r, n1, n2)
    return best[1] * 32, best[2] * 32


class Model:
    def __init__(self, folder: str | Path, providers=("CPUExecutionProvider",)):
        import onnxruntime as ort
        folder = Path(folder)
        if folder.suffix == ".onnx":
            folder = folder.parent
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.img = ort.InferenceSession(str(folder / "unisal_image.onnx"), opts, providers=list(providers))
        vid = folder / "unisal_video.onnx"
        self.vid = ort.InferenceSession(str(vid), opts, providers=list(providers)) if vid.exists() else None

    def image(self, img_bgr: np.ndarray) -> np.ndarray:
        """-> attention map (H×W of the model input, float, max 1)."""
        h, w = img_bgr.shape[:2]
        x = _prep(img_bgr, image_size(h, w))
        s = self.img.run(None, {"image": x})[0][0]
        return s / (s.max() + 1e-12)

    def video(self, frames_bgr: list[np.ndarray]) -> list[np.ndarray]:
        """Frames in time order, ideally ~6 fps -> one map per frame (224×384, max 1). Falls back to stills."""
        if self.vid is None:
            return [self.image(f) for f in frames_bgr]
        state = np.zeros(STATE_SHAPE, dtype=np.float32)
        out = []
        for f in frames_bgr:
            s, state = self.vid.run(None, {"frame": _prep(f, VIDEO_SIZE), "state": state})
            s = s[0]
            out.append(s / (s.max() + 1e-12))
        return out


def hotspots(m: np.ndarray, k: int = 5, min_rel: float = 0.35, radius: float = 0.09) -> list[list[float]]:
    """Strongest separate peaks of an attention map -> [[x, y, strength 0-1], ...] in normalised image coordinates.
    Peaks closer than `radius` (share of the larger side) to a stronger one are dropped."""
    m = np.asarray(m, dtype=np.float32)
    h, w = m.shape
    top = float(m.max())
    if top <= 0:
        return []
    work = m.copy()
    ys, xs = np.mgrid[0:h, 0:w]
    r = radius * max(h, w)
    out = []
    for _ in range(k):
        y, x = np.unravel_index(int(np.argmax(work)), work.shape)
        v = float(work[y, x])
        if v < min_rel * top:
            break
        out.append([round((x + 0.5) / w, 3), round((y + 0.5) / h, 3), round(v / top, 2)])
        work[(xs - x) ** 2 + (ys - y) ** 2 <= r * r] = 0
    return out
