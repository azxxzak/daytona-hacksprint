"""Market context for a test: live web research (Gemini + Google Search) joined to the panel's reactions (Claude).

Step 1 — research (Gemini with the google_search tool): identify the product/brand/category from the ad (context,
          transcript, what viewers looked at) and collect current Japanese market facts, competitors, trends,
          prices. Grounding metadata gives the web sources; we number them and mark each supported sentence [n].
Step 2 — synthesis (Claude): set the research against the panel (themes, segment engagement, quotes) and return
          structured JSON. Every market fact must cite source numbers; nothing may be invented. Prose is written
          in the test's language.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

import httpx

from core import llm

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_FALLBACK = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-pro-latest")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# rough list prices (USD) for the usage log: per 1M input / output tokens, plus one grounded search request
GEMINI_PRICE = (0.30, 2.50, 0.035)


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


# ----------------------------------------------------------------------------- inputs

def _brief(test_name: str, context: str, result: dict) -> str:
    a = result.get("analysis") or {}
    transcript = " ".join(s.get("text", "").strip() for s in a.get("transcript") or [])[:1500]
    looked = {}
    for g in result.get("gaze") or []:
        k = (g.get("looking_at") or "").strip().lower()
        if k:
            looked[k] = looked.get(k, 0) + 1
    top_looks = ", ".join(k for k, _ in sorted(looked.items(), key=lambda x: -x[1])[:12])
    themes = "; ".join(f"{t.get('title')} ({round(t.get('share', 0) * 100)}%)" for t in result.get("themes") or [])
    s = result.get("summary") or {}
    return (f"Test name: {test_name or '-'}\nAdvertiser's note about the ad: {context or '-'}\n"
            f"Media: {'video, ' + str(round(a.get('duration') or 0)) + ' s' if a.get('duration') else 'image'}\n"
            f"Speech in the ad (auto-transcribed, may contain errors): {transcript or '-'}\n"
            f"What viewers' eyes went to most: {top_looks or '-'}\n"
            f"Panel: {s.get('total', '?')} simulated Japanese viewers, average interest {s.get('avg_interest', '?')}/5.\n"
            f"Main reaction themes: {themes or '-'}")


RESEARCH_PROMPT = """You are a senior market analyst for the Japanese market. Use Google Search. Write a factual
research brief in English for a marketer who is testing the ad below with a consumer panel.

{brief}

Cover, each as its own section:
1. Product identification: the most likely product, brand and category, and your confidence (high/medium/low).
   If this is a known campaign, name it and when it ran.
2. Market: size and recent direction of this category in Japan (latest figures, with the year).
3. Competitors: 3-5 main competing products/brands and how they position and advertise.
4. Consumer trends in Japan that bear on how this ad lands (prices, habits, demographics, regional factors).
5. Price points, deals and financing norms customers compare against.
6. Recent news, campaigns or controversies about this brand/product.
Rules: every figure must come from a source you found, with its year. Prefer Japanese official/industry sources.
If you cannot find something, say "not found" instead of guessing."""


# ----------------------------------------------------------------------------- step 1: Gemini research

def _gemini(prompt: str, model: str) -> dict:
    r = httpx.post(GEMINI_URL.format(model=model), timeout=200,
                   headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                   json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                         "tools": [{"google_search": {}}],
                         "generationConfig": {"temperature": 0.2}})
    if r.status_code != 200:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:200]}")
    return r.json()


def research(brief: str, user: str = "system") -> dict:
    """-> {text (with [n] markers), sources [{id, title, url}], queries, model}."""
    last = None
    for model in dict.fromkeys([GEMINI_MODEL, GEMINI_FALLBACK]):
        try:
            d = _gemini(RESEARCH_PROMPT.format(brief=brief), model)
            break
        except Exception as e:  # noqa: BLE001 - try the fallback model once
            last = e
    else:
        raise RuntimeError(f"web research failed: {last}")
    cand = (d.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    gm = cand.get("groundingMetadata") or {}
    chunks = gm.get("groundingChunks") or []
    sources, idx_of = [], {}
    for i, ch in enumerate(chunks):
        w = ch.get("web") or {}
        if not w.get("uri"):
            continue
        idx_of[i] = len(sources) + 1
        sources.append({"id": len(sources) + 1, "title": w.get("title") or "source", "url": w["uri"]})
    # mark each grounded sentence with its source numbers so the synthesis can cite them
    marked, pos = text, 0
    for sup in gm.get("groundingSupports") or []:
        seg = (sup.get("segment") or {}).get("text") or ""
        ids = sorted({idx_of[i] for i in sup.get("groundingChunkIndices") or [] if i in idx_of})
        if not seg or not ids:
            continue
        at = marked.find(seg, pos)
        if at < 0:
            at = marked.find(seg)
        if at < 0:
            continue
        end = at + len(seg)
        tag = "[" + ",".join(str(i) for i in ids) + "]"
        marked = marked[:end] + " " + tag + marked[end:]
        pos = end + len(tag) + 1
    u = d.get("usageMetadata") or {}
    tin, tout = u.get("promptTokenCount", 0), (u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0))
    usd = (tin * GEMINI_PRICE[0] + tout * GEMINI_PRICE[1]) / 1e6 + GEMINI_PRICE[2]
    try:
        llm.record_usage(user, "market-research", model, tin, tout, usd)
    except Exception:  # noqa: BLE001 - usage logging must never break the feature
        pass
    return {"text": marked, "sources": sources, "queries": gm.get("webSearchQueries") or [], "model": model}


# ----------------------------------------------------------------------------- step 2: Claude synthesis

SYNTH_SYSTEM = """You are a strategy consultant. You join live market research to a simulated consumer panel's
reactions to one ad, for the advertiser. Be concrete and decision-oriented, plain language, no hype.
Hard rules:
- Market facts and figures come ONLY from the research brief. Cite them with the brief's source numbers in "src".
  Never invent a figure, a competitor or a campaign. If the brief says "not found", leave it out.
- Panel facts come ONLY from the panel data given (themes, shares, segment numbers, quotes).
- Panel members are simulated personas, not real survey respondents: say "panel", never "consumers said".
- Return ONLY JSON, exactly the requested shape."""

SHAPE = """{
  "product": {"name": "", "brand": "", "category": "", "confidence": "high|medium|low", "campaign": "known campaign or empty"},
  "headline": "one sentence: what the market reality means for this ad",
  "market": [{"point": "fact with its figure and year", "src": [1]}],
  "competitors": [{"name": "", "positioning": "how they position/advertise", "vs_ad": "how this ad compares", "src": [2]}],
  "trends": [{"trend": "", "so_what": "what it means for this ad", "src": [3]}],
  "fit": [{"market": "what the market says", "panel": "what the panel did/said", "verdict": "aligned|gap|risk"}],
  "recommendations": [{"action": "specific change to the ad or media plan", "why": "market + panel reason", "src": [1]}]
}"""


def _panel_digest(result: dict, lang: str) -> str:
    from core.decision_report import compute_numbers
    nums = compute_numbers(result, lang)
    lines = [f"- {n.get('label', n['key'])}: {n['value']}" for n in nums[:40]]
    th = []
    for t in result.get("themes") or []:
        ex = " / ".join(e.get("text", "")[:140] for e in (t.get("examples") or [])[:2])
        th.append(f"- {t.get('title')} ({round(t.get('share', 0) * 100)}%): {t.get('description', '')} Quotes: {ex}")
    return "Numbers:\n" + "\n".join(lines) + "\n\nThemes:\n" + "\n".join(th)


def synthesize(brief: str, res: dict, result: dict, lang: str) -> dict:
    out_lang = "Japanese (日本語)" if lang == "ja" else "English"
    user = (f"Write all text in {out_lang} (brand and product names as usually written).\n\n"
            f"AD AND PANEL OVERVIEW\n{brief}\n\nPANEL DATA\n{_panel_digest(result, lang)}\n\n"
            f"RESEARCH BRIEF (source numbers in [brackets])\n{res['text']}\n\n"
            f"SOURCES\n" + "\n".join(f"[{s['id']}] {s['title']}" for s in res["sources"]) +
            f"\n\nReturn JSON in exactly this shape (3-5 items per list, 3-4 recommendations):\n{SHAPE}")
    last = None
    for attempt in range(2):
        text, _ = llm.call(model=llm.CHAT_MODEL, max_tokens=12000, system=SYNTH_SYSTEM, tag="market-synthesis",
                           budget_s=200, messages=[{"role": "user", "content": user + (last or "")}])
        try:
            m = re.search(r"\{.*\}", text, re.S)
            v = json.loads(m.group(0)) if m else None
            if not isinstance(v, dict) or not v.get("headline"):
                raise ValueError("missing headline")
            return _clean(v, {s["id"] for s in res["sources"]})
        except (ValueError, json.JSONDecodeError) as e:
            last = f"\n\nYour previous answer was not valid ({e}). Return only the JSON object."
    raise RuntimeError("could not structure the market analysis")


def _clean(v: dict, ids: set[int]) -> dict:
    def src(x):
        return [int(i) for i in (x or []) if str(i).isdigit() and int(i) in ids]
    for key in ("market", "competitors", "trends", "recommendations"):
        v[key] = [{**it, "src": src(it.get("src"))} for it in (v.get(key) or []) if isinstance(it, dict)][:6]
    v["fit"] = [it for it in (v.get("fit") or []) if isinstance(it, dict)][:6]
    for it in v["fit"]:
        if it.get("verdict") not in ("aligned", "gap", "risk"):
            it["verdict"] = "gap"
    # a market fact without any source is dropped: it cannot be checked
    v["market"] = [it for it in v["market"] if it["src"]]
    return v


def generate(test_name: str, context: str, result: dict, lang: str, user: str = "system") -> dict:
    t0 = time.time()
    brief = _brief(test_name, context, result)
    res = research(brief, user)
    out = synthesize(brief, res, result, "ja" if lang == "ja" else "en")
    out.update(sources=res["sources"], queries=res["queries"], research_model=res["model"],
               synthesis_model=llm.CHAT_MODEL, lang=lang, seconds=round(time.time() - t0),
               generated_at=datetime.now(timezone.utc).isoformat())
    return out
