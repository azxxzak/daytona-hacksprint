"""Build benchmark manifests from downloaded eye-tracking datasets (fixation-point images -> pixel coordinates).

  .saliency/venv/bin/python scripts/benchmark_manifest.py mit1003 200
  .saliency/venv/bin/python scripts/benchmark_manifest.py ueyes 0 [1s|3s|7s]
"""
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / ".saliency" / "data"


def points(fix_img_path, img_shape) -> list[list[int]]:
    """Fixation-point image (white dots, maybe JPEG-blurred) -> one (x, y) per connected dot, image pixels."""
    m = cv2.imread(str(fix_img_path), cv2.IMREAD_GRAYSCALE)
    if m is None:
        return []
    h, w = img_shape[:2]
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
    n, _, _, cents = cv2.connectedComponentsWithStats((m > 127).astype(np.uint8), connectivity=8)
    return [[int(round(x)), int(round(y))] for x, y in cents[1:]]


def mit1003(n):
    img_dir, fix_dir = DATA / "mit1003/ALLSTIMULI", DATA / "mit1003/ALLFIXATIONMAPS"
    files = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in (".jpeg", ".jpg"))
    random.Random(0).shuffle(files)
    out = []
    for p in files[: n or None]:
        img = cv2.imread(str(p))
        pts = points(fix_dir / f"{p.stem}_fixPts.jpg", img.shape)
        if pts:
            out.append({"image": str(p), "width": img.shape[1], "height": img.shape[0], "fixations": pts})
    return out


def ueyes(n, dur="3s"):
    d = DATA / "ueyes"
    rows = [l.split(";") for l in (d / "image_types.csv").read_text().splitlines()[1:]]
    names = sorted(r[0] for r in rows if len(r) > 1 and r[1] == "poster")
    out = []
    for name in names:
        p = d / "images" / name
        stem = name.rsplit(".", 1)[0]
        fx = next((f for f in ((d / f"saliency_maps/fixmaps_{dur}" / f"{stem}{e}") for e in (".png", ".jpg")) if f.exists()), None)
        img = cv2.imread(str(p)) if p.exists() else None
        if img is None or fx is None:
            continue
        pts = points(fx, img.shape)
        if pts:
            out.append({"image": str(p), "width": img.shape[1], "height": img.shape[0], "fixations": pts})
    return out[: n or None]


if __name__ == "__main__":
    which, n = sys.argv[1], int(sys.argv[2])
    items = mit1003(n) if which == "mit1003" else ueyes(n, *(sys.argv[3:4] or ["3s"]))
    suffix = f"_{sys.argv[3]}" if which == "ueyes" and len(sys.argv) > 3 else ""
    dst = DATA / f"manifest_{which}{suffix}.json"
    dst.write_text(json.dumps(items))
    fx = [len(i["fixations"]) for i in items]
    print(f"{dst.name}: {len(items)} images, fixations per image median {int(np.median(fx)) if fx else 0}")
