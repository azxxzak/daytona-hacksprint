"""Decision report: numbers are computed in code, the LLM only writes prose with {{key}} tokens.

Number guard: the model never types digits. It writes {{key}} tokens; after parsing we
  1. scan every prose field (tokens removed) for digits / % -> offenders,
  2. retry once with the offending snippets listed,
  3. if still dirty, drop the offending sentences,
  4. finally replace tokens with the display values from `numbers`.
"""
from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from datetime import datetime, timezone

from core import llm
from core.llm import CHAT_MODEL

ENGAGED_AT = 3.5
SEGMENTS = [("<25", "lt25"), ("25-34", "25_34"), ("35-44", "35_44"), ("45+", "45plus"),
            ("Female", "female"), ("Male", "male")]
TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
DIGITS = re.compile(r"[0-9０-９%％]")
SENT_SPLIT = re.compile(r"(?<=[。.!?！？\n])")
LLM_TIMEOUT = 240

CARD_LABELS = {
    "en": ["Primary segment", "Key tension", "Primary driver", "Biggest friction"],
    "ja": ["主要セグメント", "最大の葛藤", "主な推進要因", "最大の障壁"],
}


# ----------------------------------------------------------------------------- numbers

def _mmss(t: float) -> str:
    t = int(round(t))
    return f"{t // 60}:{t % 60:02d}"


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def segment_of(p: dict) -> list[str]:
    age = p.get("age") or 0
    band = "<25" if age < 25 else "25-34" if age < 35 else "35-44" if age < 45 else "45+"
    out = [band]
    if p.get("gender") in ("Female", "Male"):
        out.append(p["gender"])
    return out


def persona_means(result: dict) -> dict[str, float]:
    acc = defaultdict(list)
    for g in result.get("gaze", []):
        acc[g["id"]].append(g["interest"])
    return {k: sum(v) / len(v) for k, v in acc.items() if v}


def compute_numbers(result: dict, lang: str = "en") -> list[dict]:
    ja = lang == "ja"
    L = (lambda ja_, en_: ja_ if ja else en_)
    personas = result.get("personas", [])
    means = persona_means(result)
    nums: list[dict] = []

    def add(key, label, value):
        nums.append({"key": key, "label": label, "value": str(value)})

    total = len(personas)
    engaged = sum(1 for p in personas if means.get(p["id"], 0) >= ENGAGED_AT)
    allvals = [v for v in means.values()]
    avg = sum(allvals) / len(allvals) if allvals else 0.0
    add("panel_size", L("パネル人数", "Panel size"), total)
    add("engaged_count", L("関心が高い人数", "Engaged viewers"), f"{engaged} / {total}")
    add("engaged_share", L("関心が高い割合", "Engaged share"), _pct(engaged / total) if total else "0%")
    add("avg_interest", L("平均関心度 (1-5)", "Average interest (1-5)"), f"{avg:.1f}")

    curve = (result.get("summary") or {}).get("curve") or []
    if curve:
        lo = min(curve, key=lambda c: c["avg"])
        hi = max(curve, key=lambda c: c["avg"])
        add("low_time", L("関心が最も低い時点", "Lowest-interest moment"), _mmss(lo["t"]))
        add("low_value", L("最低時点の平均関心度", "Interest at lowest moment"), f"{lo['avg']:.1f}")
        add("high_time", L("関心が最も高い時点", "Highest-interest moment"), _mmss(hi["t"]))
        add("high_value", L("最高時点の平均関心度", "Interest at highest moment"), f"{hi['avg']:.1f}")

    for name, slug in SEGMENTS:
        members = [p for p in personas if name in segment_of(p) and p["id"] in means]
        if not members:
            continue
        m = [means[p["id"]] for p in members]
        eng = sum(1 for x in m if x >= ENGAGED_AT)
        add(f"seg_{slug}_n", L(f"{name} 人数", f"{name} panel size"), len(members))
        add(f"seg_{slug}_avg", L(f"{name} 平均関心度", f"{name} average interest"), f"{sum(m) / len(m):.1f}")
        add(f"seg_{slug}_engaged", L(f"{name} 関心が高い割合", f"{name} engaged share"),
            _pct(eng / len(members)))

    gaze = result.get("gaze", [])
    counts: dict[str, int] = defaultdict(int)
    for g in gaze:
        lab = (g.get("looking_at") or "").strip().lower()
        if lab:
            counts[lab] += 1
    n = sum(counts.values())
    for i, (lab, c) in enumerate(sorted(counts.items(), key=lambda kv: -kv[1])[:5], 1):
        add(f"focus_{i}_share", L(f"注視先: {lab}", f"Looking at: {lab}"), _pct(c / n))

    for th in result.get("themes") or []:
        tid = re.sub(r"[^A-Za-z0-9_]", "_", str(th.get("id", "")))
        if tid and "share" in th:
            add(f"theme_{tid}_share", L(f"テーマ: {th.get('title', tid)}", f"Theme: {th.get('title', tid)}"),
                _pct(float(th["share"])))

    add("transcript_lines", L("書き起こし行数", "Transcript lines"),
        len((result.get("analysis") or {}).get("transcript") or []))
    return nums


# ----------------------------------------------------------------------------- prompt

def _digest(result: dict, lang: str, cap: int = 60) -> str:
    rng = random.Random(7)
    pmap = {p["id"]: p for p in result.get("personas", [])}
    by_seg: dict[str, list] = defaultdict(list)
    for g in result.get("gaze", []):
        p = pmap.get(g["id"])
        txt = (g.get("thought_en") if lang == "en" and g.get("thought_en") else g.get("thought")) or ""
        if not p or not txt:
            continue
        for s in segment_of(p):
            by_seg[s].append((g, txt))
    per = max(3, cap // max(1, len(by_seg)))
    lines = []
    for name, _ in SEGMENTS:
        items = by_seg.get(name, [])
        rng.shuffle(items)
        if not items:
            continue
        lines.append(f"[{name}]")
        for g, txt in sorted(items[:per], key=lambda x: x[0]["t"]):
            lines.append(f"- (interest {g['interest']}, seeing: {g.get('looking_at', '')}) {txt[:160]}")
    return "\n".join(lines)


def _transcript(result: dict, cap=3500) -> str:
    tr = (result.get("analysis") or {}).get("transcript") or []
    return " / ".join(x["text"] for x in tr)[:cap]


SYSTEM = """You are a senior consumer-insight strategist writing a decision report from an AI panel pre-screen of an advertisement.
The panel is simulated (AI personas), so this is a directional pre-screen, not real research. Never claim real-world effects (sales, conversion, lift). Be honest: state weaknesses plainly, and flag where evidence is thin.

HARD RULE ON NUMBERS: never type a digit or a percent sign yourself, anywhere in prose. When you need a number, write its token from the NUMBERS table, e.g. {{engaged_share}}. Use only keys that exist. If no key fits, describe it in words without a number (e.g. "most", "a minority"). Do not write persona ids, times, ages or counts as digits; use tokens or words. Segment names (<25, 25-34, 35-44, 45+, Female, Male) may appear verbatim in the "segment" fields and in prose.

Output JSON only (no markdown fences, no commentary)."""

SCHEMA = """{
 "candidates": [  // exactly 10 candidate insights, each scored 1-5 (integers) on impact, gap, explainability, actionability, robustness
   {"title": str, "evidence": str, "so_what": str, "now_what": str,
    "scores": {"impact": int, "gap": int, "explainability": int, "actionability": int, "robustness": int}}
 ],
 "thesis": str,                                   // one line
 "cards": [                                       // exactly 4, in this order: primary segment, key tension, primary driver, biggest friction
   {"value": str /* short phrase */, "note": str}
 ],
 "segments": [{"segment": str /* one of the segment names given */, "verdict": "win"|"grow"|"deprioritize", "why": str}],  // one per segment listed
 "tensions": [{"tension": str, "strategy": str}],   // up to 3
 "actions": [{"horizon": "48h"|"2w"|"6w", "action": str, "kpi": str}]   // exactly 3 per horizon (9 total); kpi may use number tokens or words
}"""


def _user_prompt(result, test_name, context, question, lang, numbers, feedback=""):
    out_lang = "Japanese (日本語)" if lang == "ja" else "English"
    segs = [n for n, slug in SEGMENTS if any(x["key"] == f"seg_{slug}_n" for x in numbers)]
    nums = "\n".join(f"{n['key']}: {n['label']} = {n['value']}" for n in numbers)
    themes = result.get("themes") or []
    th = "\n".join(f"- {t.get('title')}: {t.get('description', '')}" for t in themes) or "(none)"
    return f"""Write all prose in {out_lang}.
Ad / test name: {test_name}
Context from the requester: {context or '(none)'}
Decision question: {question or '(none given - infer the most useful decision: should this creative go forward, and for whom?)'}
Segments present: {', '.join(segs)}

NUMBERS (computed by code; reference by {{{{key}}}} only):
{nums}

THEMES:
{th}

TRANSCRIPT (audio of the ad):
{_transcript(result) or '(none)'}

WHAT THE PANEL THOUGHT (sample, grouped by segment):
{_digest(result, lang)}

Draft 10 candidate insights, score them honestly, then fill the rest. Include at least one weakness / negative finding. Return JSON of this shape:
{SCHEMA}
{feedback}"""


# ----------------------------------------------------------------------------- parse / validate

def _json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[i:j + 1])


def _s(x) -> str:
    return str(x).strip() if x is not None else ""


DIMS = ("impact", "gap", "explainability", "actionability", "robustness")


def _validate(raw: dict, segments: list[str]) -> dict:
    cands = raw.get("candidates")
    if not isinstance(cands, list) or len(cands) < 3:
        raise ValueError("candidates must be a list of 10 insights")
    scored = []
    for c in cands:
        sc = c.get("scores") or {}
        total = sum(min(5, max(1, int(sc.get(d, 1)))) for d in DIMS)
        scored.append({"title": _s(c.get("title")), "evidence": _s(c.get("evidence")),
                       "so_what": _s(c.get("so_what")), "now_what": _s(c.get("now_what")), "score": total})
    scored = [c for c in scored if c["title"] and c["evidence"]]
    if len(scored) < 3:
        raise ValueError("fewer than 3 usable insights")
    insights = sorted(scored, key=lambda c: -c["score"])[:5]

    cards = raw.get("cards")
    if not isinstance(cards, list) or len(cards) != 4:
        raise ValueError("cards must have exactly 4 entries")
    cards = [{"value": _s(c.get("value")), "note": _s(c.get("note"))} for c in cards]

    segs = []
    for s in raw.get("segments") or []:
        v = _s(s.get("verdict")).lower()
        if _s(s.get("segment")) in segments and v in ("win", "grow", "deprioritize"):
            segs.append({"segment": _s(s["segment"]), "verdict": v, "why": _s(s.get("why"))})
    if not segs:
        raise ValueError("segments missing or invalid")

    tensions = [{"tension": _s(t.get("tension")), "strategy": _s(t.get("strategy"))}
                for t in (raw.get("tensions") or [])[:3] if _s(t.get("tension"))]

    actions = []
    for h in ("48h", "2w", "6w"):
        got = [a for a in (raw.get("actions") or []) if _s(a.get("horizon")) == h and _s(a.get("action"))]
        if not got:
            raise ValueError(f"no actions for horizon {h}")
        actions += [{"horizon": h, "action": _s(a["action"]), "kpi": _s(a.get("kpi"))} for a in got[:3]]
    if not _s(raw.get("thesis")):
        raise ValueError("thesis missing")
    return {"thesis": _s(raw["thesis"]), "cards": cards, "insights": insights, "segments": segs,
            "tensions": tensions, "actions": actions}


# ----------------------------------------------------------------------------- number guard

_SEG_WHITELIST = re.compile(r"<25|25-34|35-44|45\+")


def _prose_fields(rep: dict):
    """Yield (container, key) for every prose string. segment names/horizons are structural."""
    yield rep, "thesis"
    for c in rep["headline_cards"]:
        yield c, "value"
        yield c, "note"
    for i in rep["insights"]:
        for k in ("title", "evidence", "so_what", "now_what"):
            yield i, k
    for s in rep["segments"]:
        yield s, "why"
    for t in rep["tensions"]:
        yield t, "tension"
        yield t, "strategy"
    for a in rep["actions"]:
        yield a, "action"
        yield a, "kpi"


def _offenders(text: str, keys: set[str]) -> list[str]:
    bad = []
    for m in TOKEN.finditer(text):
        if m.group(1) not in keys:
            bad.append(m.group(0))
    stripped = _SEG_WHITELIST.sub("", TOKEN.sub(" ", text))
    for m in DIGITS.finditer(stripped):
        a, b = max(0, m.start() - 8), min(len(stripped), m.end() + 8)
        bad.append(stripped[a:b].strip())
    return bad


def scan(rep: dict, keys: set[str]) -> list[str]:
    out = []
    for d, k in _prose_fields(rep):
        out += _offenders(d[k], keys)
    return out


def _strip_sentences(rep: dict, keys: set[str]):
    for d, k in _prose_fields(rep):
        if not _offenders(d[k], keys):
            continue
        kept = [s for s in SENT_SPLIT.split(d[k]) if s and not _offenders(s, keys)]
        d[k] = "".join(kept).strip() or "—"


def _fill(rep: dict, values: dict[str, str]):
    for d, k in _prose_fields(rep):
        d[k] = TOKEN.sub(lambda m: values.get(m.group(1), ""), d[k])


# ----------------------------------------------------------------------------- generate

def generate(result: dict, test_name: str, context: str, decision_question: str, lang: str) -> dict:
    lang = "ja" if lang == "ja" else "en"
    numbers = compute_numbers(result, lang)
    keys = {n["key"] for n in numbers}
    values = {n["key"]: n["value"] for n in numbers}
    segs = [n for n, slug in SEGMENTS if f"seg_{slug}_n" in keys]

    feedback = ""
    rep = None
    for attempt in range(2):
        # through core.llm so the call is rate-limited, retried and billed to the user like every other
        text, _ = llm.call(model=CHAT_MODEL, max_tokens=12000, system=SYSTEM, tag="report", budget_s=LLM_TIMEOUT,
                           messages=[{"role": "user", "content": _user_prompt(
                               result, test_name, context, decision_question, lang, numbers, feedback)}])
        try:
            v = _validate(_json(text), segs)
        except (ValueError, json.JSONDecodeError, TypeError, AttributeError) as e:
            if attempt == 1:
                if rep is not None:  # attempt 0 parsed but had stray digits: keep it, strip below
                    _strip_sentences(rep, keys)
                    break
                raise RuntimeError(f"model returned invalid report JSON: {e}") from e
            feedback = f"\nYour previous answer was rejected: {e}. Return valid JSON only, exactly the shape above."
            continue
        rep = {
            "decision_question": decision_question or "",
            "thesis": v["thesis"],
            "headline_cards": [{"label": CARD_LABELS[lang][i], **c} for i, c in enumerate(v["cards"])],
            "insights": v["insights"], "segments": v["segments"],
            "tensions": v["tensions"], "actions": v["actions"],
        }
        bad = scan(rep, keys)
        if not bad:
            break
        if attempt == 1:
            _strip_sentences(rep, keys)
            break
        feedback = ("\nYour previous answer contained digits/percent signs or unknown tokens in prose. "
                    "Rewrite using {{key}} tokens or words only. Offending snippets: "
                    + json.dumps(bad[:30], ensure_ascii=False))
    _fill(rep, values)
    rep["numbers"] = numbers
    rep["generated_at"] = datetime.now(timezone.utc).isoformat()
    rep["lang"] = lang
    return rep
