"""Two-tier persona profiles.

Tier 1 (`profile`): a compact structured profile (~1.5k chars) generated for every persona. It grounds
every later reaction and answer, so it deliberately includes friction, indifference and non-use.
Tier 2 (`deep`): a long markdown report (insights, contradictions, communication analysis), only on request.
"""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import llm

DIR = llm.DATA / "profiles"

PROFILE_RULES = """Rules for realism (important):
- Make each person specific and a little inconsistent, like a real person. Give them real friction: budget limits,
  habits, things they ignore, brands they dislike, things they do NOT use.
- Never turn a non-user into a user. If a category or product doesn't fit their life, say they don't use it.
- Ad attitudes must vary across people: many skip ads, distrust them, or barely notice them.
- No marketing language, no flattery. Plain everyday Japanese.
- Stay consistent with the given attributes (age, gender, job, region, segment)."""

SCHEMA = """{
  "full_name": "姓 名（よみがな）",
  "meta": "20代/女性/大学生/未婚",
  "headline": "one short identity line in Japanese",
  "household": "", "income": "", "region": "",
  "daily_life": "2-3 sentences",
  "media": ["channel: how they use it", "..."],
  "ad_attitude": "1-2 sentences",
  "purchase_drivers": ["...", "..."], "purchase_barriers": ["...", "..."],
  "values_top": ["", "", ""], "values_low": ["", "", ""],
  "big_five": {"openness": 0, "conscientiousness": 0, "extraversion": 0, "agreeableness": 0, "neuroticism": 0},
  "speech_style": "how they talk + 2-3 typical phrases",
  "insights": [{"title": "", "body": "2 sentences"}, {"title": "", "body": ""}]
}"""


def seed_key(p: dict) -> str:
    """Stable id of the persona's *original* attributes. Stored on the dict as `_seed`, because
    ensure_profiles later rewrites name/media/values from the generated profile."""
    if p.get("_seed"):
        return p["_seed"]
    base = {k: p.get(k) for k in ("id", "age", "gender", "occupation", "region", "income", "interests", "media",
                                   "values", "segment", "marital")}
    p["_seed"] = hashlib.sha1(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return p["_seed"]


def _seed_text(p: dict) -> str:
    parts = [f"age {p.get('age')}", f"gender {p.get('gender')}", f"job {p.get('occupation')}",
             f"region {p.get('region')}"]
    for k in ("marital", "income", "interests", "media", "values", "segment", "seed_note"):
        if p.get(k):
            parts.append(f"{k}: {p[k]}")
    return "; ".join(str(x) for x in parts)


def _parse_list(text):
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []


def cached(p: dict) -> dict | None:
    f = DIR / f"{seed_key(p)}.json"
    return json.loads(f.read_text()) if f.exists() else None


def _generate_batch(batch, model):
    lines = "\n".join(f"{i + 1}. {_seed_text(p)}" for i, p in enumerate(batch))
    text, _ = llm.call(model=model, max_tokens=12000, tag="profile", cache=True, messages=[{"role": "user", "content":
        f"Create consumer-research persona profiles for these {len(batch)} people living in Japan.\n\n{lines}\n\n"
        f"{PROFILE_RULES}\n\nWrite all text fields in Japanese. Big Five scores are integers 0-100.\n"
        f"Return ONLY a JSON array with {len(batch)} objects in the same order, each exactly in this shape:\n{SCHEMA}"}])
    out = _parse_list(text)
    if len(out) != len(batch):
        raise ValueError(f"expected {len(batch)} profiles, got {len(out)}")
    return out


def ensure_profiles(personas: list[dict], model=None, log=print, batch_size=4) -> list[dict]:
    """Adds `profile` to each persona (in place, cached on disk) and refreshes the derived short fields."""
    DIR.mkdir(parents=True, exist_ok=True)
    todo = [p for p in personas if not cached(p)]
    batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]

    def run(b):
        for attempt in (1, 2):
            try:
                for p, prof in zip(b, _generate_batch(b, model or llm.FAST_MODEL)):
                    (DIR / f"{seed_key(p)}.json").write_text(json.dumps(prof, ensure_ascii=False))
                return
            except Exception as e:  # noqa: BLE001
                log(f"profile batch failed (attempt {attempt}): {str(e)[:120]}")

    if batches:
        log(f"Writing profiles for {len(todo)} viewers")
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(llm.bind(run), batches))
    for p in personas:
        prof = cached(p)
        if prof:
            p["profile"] = prof
            p["name"] = re.sub(r"[（(].*?[）)]", "", prof.get("full_name") or p.get("name", "")).strip() or p.get("name")
            if prof.get("media"):
                p["media"] = ", ".join(m.split(":")[0].split("：")[0].strip() for m in prof["media"][:4])
            if prof.get("values_top"):
                p["values"] = ", ".join(prof["values_top"])
    return personas


def compact(p: dict) -> str:
    """Profile text used inside prompts (keeps tokens modest)."""
    prof = p.get("profile")
    if not prof:
        return ""
    keep = {k: prof.get(k) for k in ("meta", "headline", "household", "income", "daily_life", "media",
                                      "ad_attitude", "purchase_drivers", "purchase_barriers", "values_top",
                                      "values_low", "speech_style")}
    return json.dumps(keep, ensure_ascii=False)


# ---------------- tier 2 ----------------
DEEP_PROMPT = """Write a deep persona report in Japanese for this person, for marketers and planners. Use markdown.
Base everything on the profile below; you may add plausible detail, but never contradict it, and keep their
friction, non-use and ad indifference intact.

Sections (use these exact ### headings):
### ペルソナレポート — name, age, job, income, household, personality and values, daily life (weekday / weekend),
information behaviour and media, attitude to ads, consumption and money, health, relationships, outlook.
### インサイト — 3 insights. For each: **インサイト** (one bold line), **本音** (a first-person quote, 3-5 sentences in
their own voice), **理由** (why, 1 paragraph), **示唆** (what it means for brands/ads).
### 矛盾 — 3 contradictions in their values or behaviour; for each the contradiction, the insight that resolves it,
and a short 本音 quote.
### 詳細な人格 — Big Five (each 0-100 with one sentence), values (TOP3 / BOTTOM3 with a line each), speech style with
typical phrases, knowledge depth (deep / shallow / none), information gathering and sharing habits.
### 消費行動 — categories, motives, barriers, brand choice, purchase flow.
### 深層心理 — secrets they would not say, best and worst traits, goals, motto, three formative past experiences.
### コミュニケーション分析 — 3-4 paragraphs on how they talk with friends, family, strangers and brands, and why.

Profile:
{profile}
Attributes: {seed}"""


def deep_path(p: dict) -> Path:
    return DIR / f"{seed_key(p)}.deep.md"


def deep_status(p: dict) -> str:
    if deep_path(p).exists():
        return "ready"
    if (DIR / f"{seed_key(p)}.deep.lock").exists():
        return "generating"
    return "none"


def generate_deep(p: dict):
    lock = DIR / f"{seed_key(p)}.deep.lock"
    DIR.mkdir(parents=True, exist_ok=True)
    lock.write_text("1")
    try:
        text, _ = llm.call(model=llm.CHAT_MODEL, max_tokens=16000, tag="profile-deep", budget_s=600,
                           messages=[{"role": "user", "content": DEEP_PROMPT.format(
                               profile=json.dumps(p.get("profile") or {}, ensure_ascii=False), seed=_seed_text(p))}])
        deep_path(p).write_text(text)
    finally:
        lock.unlink(missing_ok=True)
