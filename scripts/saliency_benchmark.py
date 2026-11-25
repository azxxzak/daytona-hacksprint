"""Benchmark AdLens attention maps against real human eye-tracking.

Input: a manifest (JSON list) of {"image": path, "width": W, "height": H, "fixations": [[x, y], ...] in pixels}.
Methods compared on every image (maps resized to a common evaluation width):
  center   - a centre Gaussian: the baseline every model must beat
  spectral - AdLens' old map (spectral residual + centre prior, core/analyze_video.py)
  model    - the trained saliency model (ONNX, see scripts/export_saliency_model.py)
  personas - where the AI personas say they look (Claude, one point per persona) blurred into a map
  blend    - model + personas
Run (saliency venv):  .saliency/venv/bin/python scripts/saliency_benchmark.py manifest.json out_dir [--personas cache.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import saliency_metrics as M  # noqa: E402

EVAL_W = 256
GT_SIGMA = 0.03       # ground-truth blur, share of image width (about one degree of visual angle)
PERSONA_SIGMA = 0.05  # one persona point -> Gaussian of this width share (matches the report heatmap)
BLEND_W = 0.25


def spectral(img_bgr):
    from core.analyze_video import saliency
    return saliency(img_bgr)


def load_model(path):
    from core import attention
    return attention.Model(path) if path else None


def bootstrap_ci(v, n=2000, rng=np.random.default_rng(0)):
    v = np.asarray([x for x in v if np.isfinite(x)])
    if not len(v):
        return float("nan"), float("nan"), float("nan")
    means = rng.choice(v, size=(n, len(v)), replace=True).mean(1)
    return float(v.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--model", default=str(ROOT / ".saliency" / "unisal_image.onnx"))
    ap.add_argument("--personas", default=None, help="JSON cache {image: [[x_norm, y_norm], ...]}")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    items = json.loads(Path(a.manifest).read_text())
    if a.limit:
        items = items[:a.limit]
    persona_pts = json.loads(Path(a.personas).read_text()) if a.personas else {}
    model = load_model(a.model) if Path(a.model).exists() else None
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # every image's fixations at eval resolution (for the shuffled AUC negatives)
    prepared = []
    for it in items:
        img = cv2.imread(it["image"])
        if img is None:
            continue
        H, W = img.shape[:2]
        h = max(8, round(EVAL_W * H / W))
        sx, sy = EVAL_W / W, h / H
        fix = np.zeros((h, EVAL_W))
        pts = []
        for x, y in it["fixations"]:
            xi, yi = int(np.clip(x * sx, 0, EVAL_W - 1)), int(np.clip(y * sy, 0, h - 1))
            fix[yi, xi] = 1
            pts.append((x * sx, y * sy))
        if not pts:
            continue
        dens = M.blur_points(pts, h, EVAL_W, GT_SIGMA * EVAL_W)
        prepared.append((it, img, fix, dens))
    print(f"{len(prepared)} images", flush=True)

    rows = []
    for i, (it, img, fix, dens) in enumerate(prepared):
        h, w = fix.shape
        # negatives for sAUC: fixations of up to 30 other images, resized to this image's grid
        other = np.zeros((h, w))
        for j in np.random.default_rng(i).choice(len(prepared), size=min(30, len(prepared) - 1), replace=False):
            if j == i:
                continue
            o = prepared[j][2]
            other = np.maximum(other, cv2.resize(o, (w, h), interpolation=cv2.INTER_NEAREST))
        maps = {"center": M.center_bias(h, w),
                "spectral": cv2.resize(spectral(img).astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)}
        if model is not None:
            maps["model"] = cv2.resize(model.image(img), (w, h), interpolation=cv2.INTER_LINEAR)
        pp = persona_pts.get(it["image"])
        if pp:
            maps["personas"] = M.blur_points([(x * w, y * h) for x, y in pp], h, w, PERSONA_SIGMA * w) + 1e-6
            if "model" in maps:
                m = maps["model"] / (maps["model"].max() + 1e-9)
                p = maps["personas"] / (maps["personas"].max() + 1e-9)
                maps["blend"] = (1 - BLEND_W) * m + BLEND_W * p
        for name, s in maps.items():
            rows.append({"image": it["image"], "method": name, **M.all_metrics(s, fix, dens, other)})
        if i % 20 == 0:
            print(f"  {i + 1}/{len(prepared)}", flush=True)

    (out / "rows.json").write_text(json.dumps(rows))
    methods = list(dict.fromkeys(r["method"] for r in rows))
    summary = {}
    for mth in methods:
        rs = [r for r in rows if r["method"] == mth]
        summary[mth] = {"n": len(rs), **{k: bootstrap_ci([r[k] for r in rs]) for k in ("CC", "NSS", "AUC_J", "sAUC", "SIM", "KLD")}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print("\nmethod      n    CC            NSS           AUC-J   sAUC    SIM     KLD")
    for mth, s in summary.items():
        f = lambda k: f"{s[k][0]:.3f}"  # noqa: E731
        print(f"{mth:10s} {s['n']:4d}  {f('CC')} [{s['CC'][1]:.2f},{s['CC'][2]:.2f}]  {f('NSS')} [{s['NSS'][1]:.2f},{s['NSS'][2]:.2f}]"
              f"  {f('AUC_J')}  {f('sAUC')}  {f('SIM')}  {f('KLD')}")


if __name__ == "__main__":
    main()
