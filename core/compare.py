"""A/B comparison of two finished tests. All numbers are computed here, by code; the model only writes the verdict.

Fairness: when B reused A's exact panel ("New version, same panel"), every viewer is paired with themself and
the difference is tested per person (sign test + paired mean difference). With different panels the means are
compared as independent groups (Welch), and the page warns that who watched may explain part of the gap.
Simulated viewers also vary from run to run, so a small gap is called a tie rather than a win.
"""
from __future__ import annotations

import json
import math
import re
from statistics import mean, stdev

from core import llm

TIE_GAP = 0.2          # mean-interest gap (1-5 scale) below which we never call a winner
SEGMENTS = [("a1", lambda p: _age(p) < 25), ("a2", lambda p: 25 <= _age(p) < 35), ("a3", lambda p: 35 <= _age(p) < 45),
            ("a4", lambda p: _age(p) >= 45), ("F", lambda p: _sex(p) == "F"), ("M", lambda p: _sex(p) == "M")]
# two-sided 95% t critical values by degrees of freedom (normal beyond 30)
_T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26, 10: 2.23, 12: 2.18,
        15: 2.13, 20: 2.09, 25: 2.06, 30: 2.04}


def _age(p) -> int:
    try:
        return int(p.get("age") or 0)
    except (TypeError, ValueError):
        return 0


def _sex(p) -> str:
    g = str(p.get("gender", "")).strip().lower()
    return "F" if g in ("f", "female", "女性", "女") else "M" if g in ("m", "male", "男性", "男") else "?"


def _t95(df: float) -> float:
    if df >= 30:
        return 1.96 if df > 60 else 2.0
    keys = sorted(_T95)
    return _T95[max(k for k in keys if k <= max(1, int(df)))]


def _pair_key(p: dict) -> str:
    return str(p.get("source_id") or p.get("library_id") or f"{p.get('name')}|{p.get('age')}|{_sex(p)}")


def per_person(result: dict) -> dict[str, float]:
    by = {}
    for g in result.get("gaze") or []:
        by.setdefault(g["id"], []).append(g["interest"])
    return {k: mean(v) for k, v in by.items() if v}


def _sign_p(wins: int, losses: int) -> float:
    """Exact two-sided sign test (ties dropped)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _side(t: dict, result: dict) -> dict:
    s = result.get("summary") or {}
    a = result.get("analysis") or {}
    dur = a.get("duration") or 0
    curve = [{"x": round(c["t"] / dur, 4) if dur else 0, "t": c["t"], "avg": c["avg"]} for c in s.get("curve") or []]
    themes = [{"title": th.get("title"), "share": th.get("share", 0)} for th in (result.get("themes") or [])[:5]]
    return {**t, "engaged": s.get("engaged"), "total": s.get("total"), "avg_interest": s.get("avg_interest"),
            "low_t": s.get("low_t"), "top_focus": s.get("top_focus"), "duration": dur, "curve": curve, "themes": themes}


def compare(ta: dict, ra: dict, tb: dict, rb: dict, linked: bool) -> dict:
    """ta/tb: test summaries (id, name, media_kind, ...). ra/rb: result.json of each."""
    pa, pb = {p["id"]: p for p in ra["personas"]}, {p["id"]: p for p in rb["personas"]}
    ma, mb = per_person(ra), per_person(rb)
    keys_a = {_pair_key(p): i for i, p in pa.items()}
    keys_b = {_pair_key(p): i for i, p in pb.items()}
    if linked:   # B reused A's panel file: same order, same ids
        pairs = [(i, i) for i in pa if i in pb and i in ma and i in mb]
    else:
        pairs = [(keys_a[k], keys_b[k]) for k in keys_a if k in keys_b and keys_a[k] in ma and keys_b[k] in mb]
    same_panel = linked or (len(pairs) == len(pa) == len(pb) and len(pairs) > 0)

    va, vb = list(ma.values()), list(mb.values())
    diff = mean(vb) - mean(va) if va and vb else 0.0
    if same_panel and len(pairs) >= 2:
        d = [mb[j] - ma[i] for i, j in pairs]
        wins_b = sum(1 for x in d if x > 0.05)
        wins_a = sum(1 for x in d if x < -0.05)
        sd = stdev(d) if len(d) > 1 else 0.0
        se = sd / math.sqrt(len(d))
        half = _t95(len(d) - 1) * se
        half80 = half * 1.28 / 1.96
        p = _sign_p(wins_b, wins_a)
        test = {"kind": "paired", "n": len(d), "diff": round(mean(d), 2), "ci": [round(mean(d) - half, 2), round(mean(d) + half, 2)],
                "prefer_b": wins_b, "prefer_a": wins_a, "same": len(d) - wins_a - wins_b, "p": round(p, 4)}
        clear = abs(test["diff"]) >= TIE_GAP and (test["ci"][0] > 0 or test["ci"][1] < 0) and se > 0
        lean = abs(test["diff"]) >= TIE_GAP and abs(test["diff"]) > half80 and se > 0
    elif len(va) < 2 or len(vb) < 2:   # one viewer has no spread: nothing can be concluded
        test = {"kind": "independent", "n_a": len(va), "n_b": len(vb), "diff": round(diff, 2), "ci": None}
        clear = lean = False
    else:
        sa, sb = (stdev(va) if len(va) > 1 else 0.0), (stdev(vb) if len(vb) > 1 else 0.0)
        se = math.sqrt(sa ** 2 / len(va) + sb ** 2 / len(vb))
        df = (sa ** 2 / max(1, len(va)) + sb ** 2 / max(1, len(vb))) ** 2 / max(1e-12, (
            (sa ** 2 / max(1, len(va))) ** 2 / max(1, len(va) - 1) + (sb ** 2 / max(1, len(vb))) ** 2 / max(1, len(vb) - 1)))
        half = _t95(df) * se
        half80 = half * 1.28 / 1.96
        test = {"kind": "independent", "n_a": len(va), "n_b": len(vb), "diff": round(diff, 2),
                "ci": [round(diff - half, 2), round(diff + half, 2)]}
        clear = abs(test["diff"]) >= TIE_GAP and (test["ci"][0] > 0 or test["ci"][1] < 0) and se > 0
        lean = abs(test["diff"]) >= TIE_GAP and abs(test["diff"]) > half80 and se > 0
    leader = "B" if test["diff"] > 0 else "A" if test["diff"] < 0 else None
    # "clear": gap >= 0.2 and the 95% interval excludes zero; "lean": it clears an 80% interval; else a tie.
    # The sign test is shown as supporting evidence (with 5 viewers it can never go below p = 0.06).
    # A same-ad retest on the same panel moved the mean by ~0.4 with 5 viewers, so noise is real.
    outcome = "clear" if clear else "lean" if leader and lean else "tie"

    segments = []
    for key, fn in SEGMENTS:
        xa = [ma[i] for i, p in pa.items() if i in ma and fn(p)]
        xb = [mb[i] for i, p in pb.items() if i in mb and fn(p)]
        if xa or xb:
            segments.append({"key": key, "a": round(mean(xa), 2) if xa else None, "b": round(mean(xb), 2) if xb else None,
                             "n_a": len(xa), "n_b": len(xb)})

    movers = []
    if same_panel:
        def quote(result, pid, best):
            gs = [g for g in result["gaze"] if g["id"] == pid]
            if not gs:
                return None
            g = (max if best else min)(gs, key=lambda g: g["interest"])
            return {"t": g["t"], "interest": g["interest"], "thought": g.get("thought", ""), "thought_en": g.get("thought_en", "")}
        for i, j in sorted(pairs, key=lambda ij: -abs(mb[ij[1]] - ma[ij[0]]))[:6]:
            dlt = mb[j] - ma[i]
            if abs(dlt) < 0.3:
                continue
            p = pa[i]
            movers.append({"id_a": i, "id_b": j, "name": p.get("name"), "age": _age(p), "gender": _sex(p),
                           "a": round(ma[i], 2), "b": round(mb[j], 2),
                           "quote_a": quote(ra, i, best=dlt < 0), "quote_b": quote(rb, j, best=dlt > 0)})
    return {"a": _side(ta, ra), "b": _side(tb, rb), "same_panel": same_panel, "linked": linked,
            "test": test, "leader": leader, "outcome": outcome, "segments": segments, "movers": movers}


VERDICT_SYSTEM = """You are a senior advertising strategist reading an A/B test of two ad versions shown to the same
kind of simulated Japanese consumer panel. Decide which version to run and what to fix, in plain language.
Rules:
- Use only the numbers, themes and quotes given. Never invent a figure.
- Respect the statistics: if the outcome is "tie", do not declare a winner; if "lean", say it is a lean, not proof.
- If the panels differ, say that part of the gap may come from who watched.
- Panel members are simulated personas, not real people: say "panel", never "consumers said".
- Return ONLY JSON in the requested shape."""

VERDICT_SHAPE = """{"winner": "A|B|tie", "headline": "one sentence decision",
 "reasons": [{"point": "why", "evidence": "numbers or quote from the data"}],
 "fix": [{"version": "A|B", "action": "specific change"}],
 "caveat": "one sentence on how sure we can be"}"""


def _brief(side: dict, result: dict, label: str, lang: str) -> str:
    tr = " ".join(s.get("text", "") for s in (result.get("analysis") or {}).get("transcript") or [])[:600]
    key = "thought_en" if lang == "en" else "thought"
    quotes = sorted(result.get("gaze") or [], key=lambda g: -g["interest"])
    q = [f"{g.get(key) or g.get('thought')} ({g['interest']}/5)" for g in quotes[:3] + quotes[-3:]]
    themes = "; ".join(f"{t['title']} ({round((t['share'] or 0) * 100)}%)" for t in side["themes"])
    return (f"VERSION {label}: {side['name']}\nmedia: {side['media_kind']}, {round(side['duration'] or 0)} s\n"
            f"engaged {side['engaged']}/{side['total']}, mean interest {side['avg_interest']}/5, "
            f"lowest moment {side['low_t']}, eyes went most to: {side['top_focus']}\n"
            f"themes: {themes}\nspeech: {tr or '-'}\nquotes (3 highest, 3 lowest): " + " | ".join(q))


def verdict(cmp: dict, ra: dict, rb: dict, lang: str) -> dict:
    out_lang = "Japanese (日本語)" if lang == "ja" else "English"
    seg = "; ".join(f"{s['key']}: A {s['a']} vs B {s['b']}" for s in cmp["segments"])
    user = (f"Write all text in {out_lang}.\n\n{_brief(cmp['a'], ra, 'A', lang)}\n\n{_brief(cmp['b'], rb, 'B', lang)}\n\n"
            f"STATISTICS (B minus A, mean interest per viewer, 1-5 scale): {json.dumps(cmp['test'])}\n"
            f"outcome: {cmp['outcome']}, leader: {cmp['leader']}, same panel: {cmp['same_panel']}\n"
            f"segments (age bands a1 <25, a2 25-34, a3 35-44, a4 45+; F/M): {seg}\n\n"
            f"Return JSON exactly in this shape (2-4 reasons, 2-3 fixes):\n{VERDICT_SHAPE}")
    last = ""
    for _ in range(2):
        text, _usd = llm.call(model=llm.CHAT_MODEL, max_tokens=6000, system=VERDICT_SYSTEM, tag="compare-verdict",
                              messages=[{"role": "user", "content": user + last}])
        m = re.search(r"\{.*\}", text, re.S)
        try:
            v = json.loads(m.group(0)) if m else None
            if isinstance(v, dict) and v.get("headline") and v.get("winner") in ("A", "B", "tie"):
                if cmp["outcome"] == "tie":   # the statistics overrule the model
                    v["winner"] = "tie"
                v["lang"] = lang
                return v
        except json.JSONDecodeError:
            pass
        last = "\n\nYour previous answer was not valid JSON in the shape. Return only the JSON object."
    raise RuntimeError("could not write the verdict")
