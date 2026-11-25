"""Ask the AdLens persona panel (same prompt and model as a real test) where they look on benchmark images.

  .venv/bin/python scripts/benchmark_persona_gaze.py manifest.json out_cache.json [--n 10] [--limit 0]

Writes {image_path: [[x_norm, y_norm], ...]} for scripts/saliency_benchmark.py --personas. Results are cached
by core/llm (cache=True), so a rerun costs nothing.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from core import gaze, llm  # noqa: E402
from core.personas import sample_personas, with_colors  # noqa: E402


def keyframe(path: str) -> dict:
    img = cv2.imread(path)
    h, w = img.shape[:2]
    s = 768 / max(h, w)
    if s < 1:   # same size the worker sends
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return {"t": 0.0, "jpg_b64": base64.b64encode(buf).decode()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    items = json.loads(Path(a.manifest).read_text())
    if a.limit:
        items = items[:a.limit]
    panel = with_colors(sample_personas(a.n, (20, 64), ["F", "M"], seed=7))
    panel = [{**p, "id": f"P{i + 1:03d}"} for i, p in enumerate(panel)]
    out = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else {}
    todo = [it for it in items if it["image"] not in out]
    print(f"{len(todo)} images to ask ({len(out)} cached), panel of {len(panel)}", flush=True)

    def ask(it):
        for _ in range(3):   # an occasional malformed JSON reply: ask again (the real worker skips the frame)
            try:
                pts = gaze._ask(keyframe(it["image"]), panel, "", "", "ja")
                return it["image"], [[g["x"], g["y"]] for g in pts]
            except ValueError:
                continue
        return it["image"], []

    with ThreadPoolExecutor(8) as ex:
        for k, (img, pts) in enumerate(ex.map(ask, todo)):
            if pts:
                out[img] = pts
            if k % 25 == 0:
                Path(a.out).write_text(json.dumps(out))
                print(f"  {k + 1}/{len(todo)}  spent ${llm.TOTALS['usd']:.3f}", flush=True)
    Path(a.out).write_text(json.dumps(out))
    print(f"done: {len(out)} images, spent ${llm.TOTALS['usd']:.3f}")


if __name__ == "__main__":
    main()
