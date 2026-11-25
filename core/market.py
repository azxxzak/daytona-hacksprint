"""Market context for a test: live web research joined to the panel's reactions. Both steps run on Claude.

Step 1 — research (Claude with the web_search server tool): identify the product/brand/category from the ad
          (context, transcript, what viewers looked at) and collect current Japanese market facts, competitors,
          trends, prices. Every sentence Claude bases on a page carries citations; we number the pages and mark
          each cited sentence [n].
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

import anthropic

from core import llm

RESEARCH_MODEL = os.getenv("RESEARCH_MODEL", llm.CHAT_MODEL)
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8,
                   "user_location": {"type": "approximate", "country": "JP", "timezone": "Asia/Tokyo"}}
SEARCH_USD = 0.01          # list price: $10 per 1,000 searches


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


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


RESEARCH_PROMPT = """You are a senior market analyst for the Japanese market. Use the web search tool (search in Japanese
and in English; up to 8 searches, so plan them). Write a factual research brief in English for a marketer who is testing the ad below with a consumer panel.

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


# ----------------------------------------------------------------------------- step 1: web research

def _research_call(messages: list, deadline: float):
    """One streamed request with retries on overload/5xx; the limiter sees every attempt."""
    attempt = 0
    while True:
        try:
            with llm.limiter:
                with llm.client().messages.stream(model=RESEARCH_MODEL, max_tokens=16000, tools=[WEB_SEARCH_TOOL],
                                                  messages=messages, timeout=max(10.0, deadline - time.time())) as st:
                    msg = st.get_final_message()
            llm.limiter.success()
            return msg
        except anthropic.RateLimitError as e:
            llm.limiter.busy()
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code < 500:
                raise
            last = e
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            last = e
        attempt += 1
        delay = min(20.0, 2 ** attempt)
        if time.time() + delay > deadline:
            raise last
        time.sleep(delay)


def research(brief: str, user: str = "system") -> dict:
    """-> {text (with [n] markers), sources [{id, title, url}], queries, model}."""
    llm.check_budget(user)
    messages = [{"role": "user", "content": RESEARCH_PROMPT.format(brief=brief)}]
    # 170 s for research leaves room for the synthesis call inside Vercel's 300 s function limit
    deadline, blocks, usd, searches, tin, tout = time.time() + 170, [], 0.0, 0, 0, 0
    stop = None
    try:
        for _ in range(4):   # server-side tool loops may pause; send the turn back to let it continue
            if time.time() > deadline:
                raise RuntimeError("web research ran out of time")
            msg = _research_call(messages, deadline)
            u = msg.usage
            n = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0
            searches += n
            tin += getattr(u, "input_tokens", 0) or 0
            tout += getattr(u, "output_tokens", 0) or 0
            usd += llm.cost_usd(RESEARCH_MODEL, u) + n * SEARCH_USD
            blocks.extend(msg.content)
            stop = msg.stop_reason
            if stop != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": msg.content}]
    finally:   # money already spent is always counted, even when a later turn fails
        try:
            llm.record_usage(user, "market-research", RESEARCH_MODEL, tin, tout, round(usd, 6))
        except Exception:  # noqa: BLE001 - usage logging must never break the feature
            pass
    if stop == "pause_turn":
        raise RuntimeError("web research did not finish")
    sources, idx, queries, parts = [], {}, [], []

    def num(url, title):
        if url not in idx:
            idx[url] = len(sources) + 1
            sources.append({"id": idx[url], "title": title or url, "url": url})
        return idx[url]

    for b in blocks:
        kind = getattr(b, "type", "")
        if kind == "server_tool_use" and getattr(b, "name", "") == "web_search":
            q = (getattr(b, "input", None) or {}).get("query")
            if q:
                queries.append(q)
        elif kind == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            for r in b.content:
                if getattr(r, "url", None):
                    num(r.url, getattr(r, "title", ""))
        elif kind == "text":
            ids = sorted({num(c.url, getattr(c, "title", "")) for c in (getattr(b, "citations", None) or [])
                          if getattr(c, "url", None)})
            parts.append(b.text + (" [" + ",".join(map(str, ids)) + "]" if ids else ""))
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("web research returned no text")
    return {"text": text, "sources": sources, "queries": queries, "model": RESEARCH_MODEL, "searches": searches}


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
