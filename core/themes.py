"""Theme summary of open-ended reactions (three stages, borrowed from a survey pipeline):

1. collect every inner thought (already generated in parallel during the run);
2. one call condenses them into 3-8 themes — segment labels are hidden so the model can't
   simply make one theme per segment;
3. assign every thought to a theme in batches of 40, re-asking for any id that came back missing,
   so each thought ends up in exactly one theme. Shares are computed by code.
"""
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor

from core import llm

BATCH = 40


def _segments(p):
    age = int(p.get("age") or 0)
    band = "<25" if age < 25 else "25-34" if age < 35 else "35-44" if age < 45 else "45+"
    g = str(p.get("gender", "")).lower()
    return [band, "Female" if g.startswith("f") else "Male"]


def _json(text, open_ch="["):
    m = re.search(r"\[.*\]" if open_ch == "[" else r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else ([] if open_ch == "[" else {})


def _condense(texts, lang):
    sample = random.Random(7).sample(texts, min(len(texts), 220))
    body = "\n".join(f"- {t}" for t in sample)
    out, _ = llm.call(model=llm.CHAT_MODEL, max_tokens=8000, tag="test-themes", cache=True, messages=[{
        "role": "user", "content":
        "These are inner thoughts of consumer-panel members while watching one advertisement.\n\n"
        f"{body}\n\nGroup them into 3 to 8 distinct themes that a marketer would act on (e.g. a reason for "
        "interest, a confusion, a doubt, an emotional reaction, indifference). Themes must not overlap. "
        f"Write titles and descriptions in {'Japanese' if lang == 'ja' else 'English'}.\n"
        'Return ONLY JSON: [{"id": "T1", "title": "<= 20 chars", "description": "one sentence"}]'}])
    themes = _json(out)
    return [{"id": str(t.get("id") or f"T{i + 1}"), "title": t.get("title", ""), "description": t.get("description", "")}
            for i, t in enumerate(themes)][:8]


def _assign(batch, themes):
    menu = "\n".join(f"{t['id']}: {t['title']} — {t['description']}" for t in themes)
    items = "\n".join(f"{i}: {t}" for i, t in batch)
    out, _ = llm.call(model=llm.FAST_MODEL, max_tokens=6000, tag="test-themes", cache=True, messages=[{
        "role": "user", "content":
        f"Themes:\n{menu}\n\nAssign each numbered thought to exactly one theme id (the closest one).\n\n{items}\n\n"
        'Return ONLY JSON: {"<number>": "<theme id>", ...} covering every number.'}])
    d = _json(out, "{")
    valid = {t["id"] for t in themes}
    return {int(k): v for k, v in d.items() if str(k).isdigit() and v in valid}


def summarize(gaze, personas, lang="ja") -> list[dict] | None:
    by_id = {p["id"]: p for p in personas}
    rows = [(i, g) for i, g in enumerate(g for g in gaze if (g.get("thought") or "").strip())]
    if len(rows) < 6:
        return None
    text_of = lambda g: (g.get("thought_en") or g["thought"]) if lang == "en" else g["thought"]  # noqa: E731
    themes = _condense([text_of(g) for _, g in rows], lang)
    if not themes:
        return None

    assigned: dict[int, str] = {}
    pending = [(i, text_of(g)) for i, g in rows]
    for _ in range(3):  # first pass + up to two re-asks for missing ids
        batches = [pending[k:k + BATCH] for k in range(0, len(pending), BATCH)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for got in pool.map(llm.bind(lambda b: _safe_assign(b, themes)), batches):
                assigned.update(got)
        pending = [(i, t) for i, t in pending if i not in assigned]
        if not pending:
            break

    gz = dict(rows)
    seg_tot, seg_hit = {}, {}
    for i, tid in assigned.items():
        for s in _segments(by_id.get(gz[i]["id"], {})):
            seg_tot[s] = seg_tot.get(s, 0) + 1
            seg_hit[(tid, s)] = seg_hit.get((tid, s), 0) + 1
    total = max(1, len(assigned))
    out = []
    for t in themes:
        members = [gz[i] for i, tid in assigned.items() if tid == t["id"]]
        if not members:
            continue
        ex = sorted(members, key=lambda g: -len(g.get("thought", "")))[:3]
        out.append({**t, "share": round(len(members) / total, 3),
                    "by_segment": [{"segment": s, "share": round(seg_hit.get((t["id"], s), 0) / n, 3)}
                                   for s, n in sorted(seg_tot.items())],
                    "examples": [{"persona_id": g["id"], "t": g["t"], "text": text_of(g)} for g in ex]})
    return sorted(out, key=lambda x: -x["share"])


def _safe_assign(batch, themes):
    try:
        return _assign(batch, themes)
    except Exception:  # noqa: BLE001
        return {}
