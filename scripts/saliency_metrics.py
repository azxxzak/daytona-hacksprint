"""Standard saliency metrics (MIT/Tübingen benchmark definitions), numpy only.

All functions take a predicted map `s` (H×W, any scale) and ground truth at the SAME resolution:
  - `fix`: binary fixation map (1 where a human fixated), or
  - `dens`: continuous fixation density (fixations blurred with a Gaussian).
"""
from __future__ import annotations

import numpy as np

EPS = 1e-12


def _norm01(x):
    x = x.astype(np.float64)
    x = x - x.min()
    return x / (x.max() + EPS)


def cc(s, dens):
    a, b = s.astype(np.float64).ravel(), dens.astype(np.float64).ravel()
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + EPS))


def nss(s, fix):
    z = (s - s.mean()) / (s.std() + EPS)
    m = fix > 0
    return float(z[m].mean()) if m.any() else float("nan")


def sim(s, dens):
    a, b = s / (s.sum() + EPS), dens / (dens.sum() + EPS)
    return float(np.minimum(a, b).sum())


def kld(s, dens):
    q, p = s / (s.sum() + EPS), dens / (dens.sum() + EPS)
    return float((p * np.log(EPS + p / (q + EPS))).sum())


def auc_judd(s, fix):
    s = _norm01(s) + np.random.default_rng(0).uniform(0, 1e-7, s.shape)  # break ties
    m = fix > 0
    if not m.any():
        return float("nan")
    th = np.sort(s[m])[::-1]
    n_fix, n_pix = len(th), s.size
    tp, fp = [0.0], [0.0]
    flat = np.sort(s.ravel())[::-1]
    for i, t in enumerate(th):
        above = np.searchsorted(-flat, -t, side="right")   # pixels with value >= t
        tp.append((i + 1) / n_fix)
        fp.append((above - (i + 1)) / (n_pix - n_fix))
    tp.append(1.0)
    fp.append(1.0)
    return float(np.trapezoid(tp, fp))


def auc_shuffled(s, fix, other_fix, n_splits=20, rng=None):
    """Negatives are fixation locations from OTHER images: a centre blob scores ~0.5 here, so this measures
    what a model knows beyond 'people look at the middle'."""
    rng = rng or np.random.default_rng(0)
    s = _norm01(s)
    pos = s[fix > 0]
    neg_idx = np.flatnonzero(other_fix.ravel() > 0)
    if not len(pos) or not len(neg_idx):
        return float("nan")
    aucs = []
    for _ in range(n_splits):
        neg = s.ravel()[rng.choice(neg_idx, size=len(pos), replace=len(neg_idx) < len(pos))]
        th = np.linspace(0, 1, 101)[::-1]
        tp = np.array([(pos >= t).mean() for t in th])
        fp = np.array([(neg >= t).mean() for t in th])
        aucs.append(np.trapezoid(np.r_[0, tp, 1], np.r_[0, fp, 1]))
    return float(np.mean(aucs))


def center_bias(h, w, sigma_frac=0.25):
    ys, xs = np.mgrid[0:h, 0:w]
    return np.exp(-(((xs - (w - 1) / 2) / (sigma_frac * w)) ** 2 + ((ys - (h - 1) / 2) / (sigma_frac * h)) ** 2) / 2)


def blur_points(points, h, w, sigma_px, weights=None):
    """points: iterable of (x, y) in pixels -> density map (Gaussian per point)."""
    out = np.zeros((h, w))
    ys, xs = np.mgrid[0:h, 0:w]
    for i, (x, y) in enumerate(points):
        out += (1.0 if weights is None else weights[i]) * np.exp(-((xs - x) ** 2 + (ys - y) ** 2) / (2 * sigma_px ** 2))
    return out


def all_metrics(s, fix, dens, other_fix):
    s = np.clip(s.astype(np.float64), 0, None) + EPS
    return {"CC": cc(s, dens), "NSS": nss(s, fix), "AUC_J": auc_judd(s, fix), "sAUC": auc_shuffled(s, fix, other_fix),
            "SIM": sim(s, dens), "KLD": kld(s, dens)}
