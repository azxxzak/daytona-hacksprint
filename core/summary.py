"""Panel summary numbers computed by code (never by the model)."""


def summarize(gaze: list[dict]) -> dict | None:
    if not gaze:
        return None
    per, curve, focus = {}, {}, {}
    for g in gaze:
        per.setdefault(g["id"], []).append(g["interest"])
        curve.setdefault(g["t"], []).append(g["interest"])
        k = (g.get("looking_at") or "").lower().strip()
        if k:
            focus[k] = focus.get(k, 0) + 1
    means = {k: sum(v) / len(v) for k, v in per.items()}
    pts = sorted((t, sum(v) / len(v)) for t, v in curve.items())
    low = min(pts, key=lambda p: p[1])[0] if len(pts) > 1 else None
    return {"engaged": sum(1 for m in means.values() if m >= 3.5), "total": len(means),
            "avg_interest": round(sum(g["interest"] for g in gaze) / len(gaze), 2),
            "low_t": low, "top_focus": max(focus, key=focus.get) if focus else None,
            "curve": [{"t": t, "avg": round(a, 2)} for t, a in pts]}
