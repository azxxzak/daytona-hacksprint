"""Persona panel: load from a People-Model-style CSV, or sample synthetically.

CSV columns recognised (any subset; extra columns are kept as traits):
  id, name, age, gender, region, occupation, income, interests, media, values
"""
import random

import csv
import io

FIRST = {"F": ["Yui", "Haruka", "Aoi", "Sakura", "Mei", "Yoko", "Keiko", "Naomi", "Rin", "Emi"],
         "M": ["Haruto", "Ren", "Sota", "Takumi", "Kenji", "Hiroshi", "Daiki", "Yuto", "Kaito", "Shin"]}
REGIONS = [("Tokyo", .30), ("Osaka", .15), ("Kanagawa", .12), ("Aichi", .10), ("Fukuoka", .08),
           ("Hokkaido", .08), ("Kyoto", .07), ("Rural town", .10)]
OCCUPATIONS = {(15, 22): ["University student", "High-school student", "Part-time worker"],
               (23, 39): ["Office worker", "Engineer", "Designer", "Nurse", "Sales", "Freelancer"],
               (40, 64): ["Manager", "Civil servant", "Shop owner", "Teacher", "Homemaker"],
               (65, 99): ["Retired", "Part-time worker", "Volunteer"]}
INTERESTS = ["anime", "gaming", "fashion", "beauty", "cooking", "travel", "fitness", "investing",
             "cars", "camping", "K-pop", "baseball", "soccer", "coffee", "tech gadgets", "pets",
             "parenting", "gardening", "photography", "sustainability"]
MEDIA = ["TikTok", "Instagram", "YouTube", "X (Twitter)", "LINE", "TV", "Newspaper", "Podcasts"]
TRAITS = ["skeptical of ads", "impulsive buyer", "price-sensitive", "brand-loyal",
          "values quality", "trend follower", "busy, skims quickly", "detail-oriented",
          "eco-conscious", "easily bored"]
COLORS = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0",
          "#f032e6", "#bcf60c", "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8"]


def _weighted(options):
    names, weights = zip(*options)
    return random.choices(names, weights)[0]


def _occupation(age):
    for (lo, hi), jobs in OCCUPATIONS.items():
        if lo <= age <= hi:
            return random.choice(jobs)
    return "Office worker"


def sample_personas(n, age_range, genders, seed=42):
    random.seed(seed)
    out = []
    for i in range(n):
        g = random.choice(genders)
        age = random.randint(*age_range)
        income = random.choice(["<3M JPY", "3-5M JPY", "5-8M JPY", "8M+ JPY"] if age >= 23 else ["<1M JPY"])
        out.append({
            "id": f"P{i + 1:03d}",
            "name": random.choice(FIRST[g]),
            "age": age,
            "gender": "Female" if g == "F" else "Male",
            "region": _weighted(REGIONS),
            "occupation": _occupation(age),
            "income": income,
            "interests": ", ".join(random.sample(INTERESTS, 3)),
            "media": ", ".join(random.sample(MEDIA, 2)),
            "values": ", ".join(random.sample(TRAITS, 2)),
        })
    return out


def load_csv(data, age_range, genders) -> list[dict]:
    """Customer CSV -> persona dicts. `data` is bytes, str or a file object. Unknown columns are kept as traits."""
    if hasattr(data, "read"):
        data = data.read()
    text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]
    wanted = {"F": ("f", "female", "女性", "女"), "M": ("m", "male", "男性", "男")}
    ok_gender = {v for g in genders for v in wanted[g]}
    out = []
    for r in rows:
        if r.get("age"):
            try:
                r["age"] = int(float(r["age"]))
            except ValueError:
                continue
            if not age_range[0] <= r["age"] <= age_range[1]:
                continue
        if r.get("gender") and r["gender"].lower() not in ok_gender:
            continue
        out.append(r)
    for i, r in enumerate(out):
        r.setdefault("id", f"P{i + 1:03d}")
        r.setdefault("name", r["id"])
    return out


def with_colors(personas: list[dict]) -> list[dict]:
    return [{**p, "color": COLORS[i % len(COLORS)]} for i, p in enumerate(personas)]


def describe(p: dict) -> str:
    skip = {"color", "profile", "_seed", "avatar_url", "has_deep_profile"}
    base = "; ".join(f"{k}: {v}" for k, v in p.items()
                     if k not in skip and not isinstance(v, (dict, list)) and v not in (None, ""))
    if p.get("profile"):
        from core.persona_profile import compact
        base += f"; profile: {compact(p)}"
    return base
