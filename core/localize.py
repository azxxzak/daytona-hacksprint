"""English view of Japanese data.

The UI language reaches the API as the `X-Lang` header (or the `adlens_lang` cookie); backend.main stores it in
LANG for the request. Everything that leaves the API in a persona goes through `persona()`:

- short categorical fields (occupation, prefecture, income band, marital status, ...) use fixed dictionaries,
  so facets, filters and cards always agree;
- the free-text profile is translated once by Claude and cached: bank personas keep it in
  persona_bank.profile_en (filled in bulk by scripts/translate_persona_bank.py), every other persona in storage
  under i18n/profile_en/<hash>.json (translated on first view).
"""
import contextvars
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

from core import llm
from core.store import SPath

LANG: contextvars.ContextVar[str] = contextvars.ContextVar("adlens_lang", default="ja")


def lang() -> str:
    return LANG.get()


def is_en() -> bool:
    return LANG.get() == "en"


# ----------------------------------------------------------------------------------------------- dictionaries
OCCUPATION_EN = {
    "年金生活者（退職後）": "Retired (pension)", "専業主婦": "Homemaker", "専業主夫": "Homemaker (male)",
    "製造・生産職（正社員）": "Manufacturing worker (full-time)", "事務職（正社員）": "Office clerk (full-time)",
    "パート・アルバイト（小売・販売）": "Part-time (retail)", "高校生": "High-school student",
    "無職（求職中・休職中）": "Unemployed (job seeking / on leave)", "管理職（課長以上）": "Manager (section chief+)",
    "営業職（正社員）": "Sales (full-time)", "大学生": "University student",
    "販売・サービス職（正社員）": "Retail & service (full-time)", "公務員": "Civil servant",
    "建設・技能職（正社員）": "Construction & trades (full-time)", "パート・アルバイト（飲食・接客）": "Part-time (food service)",
    "ITエンジニア（正社員）": "IT engineer (full-time)", "無職": "Not working",
    "運輸・物流（正社員）": "Transport & logistics (full-time)", "パート・アルバイト（製造・軽作業）": "Part-time (factory / light work)",
    "医療職（看護師・薬剤師など）": "Healthcare (nurse, pharmacist, etc.)", "パート・アルバイト（事務）": "Part-time (office)",
    "金融・保険（正社員）": "Finance & insurance (full-time)", "パート・アルバイト（物流・配送）": "Part-time (logistics / delivery)",
    "契約社員・派遣社員（小売・販売）": "Contract / agency (retail)", "パート・アルバイト（清掃・警備）": "Part-time (cleaning / security)",
    "個人事業主（飲食・小売）": "Small business owner (food / retail)", "専門職・研究職（正社員）": "Specialist / researcher (full-time)",
    "自営（サービス業）": "Self-employed (services)", "介護・福祉職（正社員）": "Care & welfare worker (full-time)",
    "建設職人・一人親方": "Independent tradesperson", "教員・保育士": "Teacher / childcare worker",
    "フリーランス（クリエイティブ・IT）": "Freelancer (creative / IT)", "パート・アルバイト（医療・介護）": "Part-time (healthcare / care)",
    "パート・アルバイト（教育・塾）": "Part-time (education / cram school)", "契約社員・派遣社員（飲食・接客）": "Contract / agency (food service)",
    "農業": "Farmer", "契約社員・派遣社員（製造・軽作業）": "Contract / agency (factory / light work)",
    "専門学校生": "Vocational school student", "士業・開業医・専門職": "Licensed professional / physician",
    "教員（正社員）": "Teacher (full-time)", "パート・アルバイト（コールセンター）": "Part-time (call center)",
    "契約社員・派遣社員（事務）": "Contract / agency (office)", "家業手伝い・自営": "Family business",
    "運転手・個人運送": "Driver / owner-operator", "契約社員・派遣社員（医療・介護）": "Contract / agency (healthcare / care)",
    "医療職（正社員）": "Healthcare (full-time)", "契約社員・派遣社員（物流・配送）": "Contract / agency (logistics / delivery)",
    "契約社員・派遣社員（清掃・警備）": "Contract / agency (cleaning / security)",
    "契約社員・派遣社員（コールセンター）": "Contract / agency (call center)",
    "契約社員・派遣社員（教育・塾）": "Contract / agency (education)", "大学院生": "Graduate student",
}
INCOME_EN = {
    "収入なし": "No income", "〜100万円": "Under ¥1M", "100〜200万円": "¥1–2M", "200〜300万円": "¥2–3M",
    "300〜400万円": "¥3–4M", "400〜500万円": "¥4–5M", "500〜700万円": "¥5–7M", "700〜1000万円": "¥7–10M",
    "1000万円以上": "¥10M+",
}
MARITAL_EN = {"既婚": "Married", "未婚": "Single", "離別": "Divorced", "死別": "Widowed"}
EMPLOYMENT_EN = {
    "正社員": "Full-time", "パート・アルバイト": "Part-time", "退職・年金生活": "Retired", "専業主婦(夫)": "Homemaker",
    "学生": "Student", "自営・フリーランス": "Self-employed / freelance", "無職": "Not working", "契約・派遣": "Contract / agency",
}
HOUSEHOLD_EN = {
    "親と同居": "Lives with parents", "夫婦のみ": "Couple only", "単身世帯（一人暮らし）": "Lives alone",
    "夫婦と子ども（子1人）": "Couple with 1 child", "夫婦と子ども（子2人）": "Couple with 2 children",
    "夫婦と子ども（子3人）": "Couple with 3 children", "三世代同居": "Three generations",
    "夫婦と子ども（成人した子1人と同居）": "Couple with 1 adult child", "夫婦と子ども（成人した子2人と同居）": "Couple with 2 adult children",
    "夫婦と子ども（成人した子3人と同居）": "Couple with 3 adult children", "夫婦と親": "Couple with parent(s)",
    "子ども世帯と同居": "Lives with adult child's family", "ひとり親と子ども（子1人）": "Single parent, 1 child",
    "ひとり親と子ども（子2人）": "Single parent, 2 children", "ひとり親と子ども（子3人）": "Single parent, 3 children",
}
TAG_EN = {
    "都市部": "Urban", "郊外": "Suburban", "地方": "Rural", "シニア": "Senior", "プレシニア": "Pre-senior",
    "一人暮らし": "Lives alone", "低所得・節約志向": "Budget-minded", "子育て世帯": "Raising kids",
    "若手社会人": "Young professional", "専業主婦(夫)": "Homemaker", "学生": "Student", "高所得層": "High income",
    "DINKs・子なし夫婦": "DINKs", "既婚者": "Married",
    **{f"{d}代": f"{d}s" for d in range(10, 90, 10)},
}


def _pref_en() -> dict:
    from core.persona_bank import PREF_EN
    return PREF_EN


def short(value, table: dict) -> str:
    v = "" if value is None else str(value)
    return table.get(v, v)


def region(value) -> str:
    v = "" if value is None else str(value)
    return _pref_en().get(v, v)


def occupation(value) -> str:
    return short(value, OCCUPATION_EN)


def label(kind: str, value: str) -> str:
    """Facet label for `kind` in the current language (filters keep using the Japanese value)."""
    if not is_en():
        return value
    return {"region": region, "occupation": occupation}.get(kind, lambda v: v)(value)


# ----------------------------------------------------------------------------------------------- profiles
TRANSLATE_SYSTEM = """You translate Japanese consumer-persona profiles (JSON) into natural English for a marketing tool.

Rules:
- Return ONLY the JSON object, with exactly the same keys, nesting and list lengths. Numbers stay unchanged.
- full_name: the person's name romanized as "Given Family" (e.g. 野口 楓（のぐち かえで） -> "Kaede Noguchi"), no kana.
- meta: short English like "20s / Female / Job seeker / Single".
- Place names romanized (長崎県 -> Nagasaki Prefecture). Services as known in English (LINE, X (Twitter), YouTube).
- Keep the person's voice: plain, concrete, unpolished. Do not add praise, marketing words or new facts.
- speech_style: describe the style in English, then give the typical phrases as English renderings with the
  original Japanese in parentheses.
- Japanese-specific things (konbini, hyakkin, furusato nozei, ...) may stay romanized with a 2-3 word gloss."""


def translate_user(profile: dict) -> str:
    return "Translate this profile:\n" + json.dumps(profile, ensure_ascii=False)


def parse_translation(text: str, original: dict) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    out = json.loads(m.group(0))
    missing = [k for k in original if k not in out]
    if missing:
        raise ValueError(f"missing keys: {missing[:5]}")
    rest = json.dumps({k: v for k, v in out.items() if k != "speech_style"}, ensure_ascii=False)
    rest = re.sub(r"[（(][^）)]{0,40}[）)]", "", rest)  # a Japanese term in brackets next to its English is fine
    if len(re.findall(r"[\u3040-\u30ff]", rest)) > 12:
        raise ValueError("untranslated Japanese left outside speech_style")
    return out


def _key(profile: dict) -> str:
    return hashlib.sha1(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def _cache(profile: dict) -> SPath:
    return SPath(f"i18n/profile_en/{_key(profile)}.json")


def _has_japanese(profile: dict) -> bool:
    return bool(re.search(r"[぀-ヿ一-鿿]", json.dumps(profile, ensure_ascii=False)))


def translate_profile(profile: dict) -> dict:
    """English profile (cached in storage). Falls back to the original on any failure."""
    if not profile or not _has_japanese(profile):
        return profile
    f = _cache(profile)
    try:
        if f.exists():
            return json.loads(f.read_text())
    except Exception:  # noqa: BLE001
        pass
    for _ in range(2):
        try:
            out, _u = llm.call(model=llm.FAST_MODEL, max_tokens=8000, tag="translate-profile", cache=True,
                               system=TRANSLATE_SYSTEM, messages=[{"role": "user", "content": translate_user(profile)}])
            en = parse_translation(out, profile)
            f.write_text(json.dumps(en, ensure_ascii=False))
            return en
        except Exception:  # noqa: BLE001 - try once more, then show the original
            continue
    return profile


def _bank_id(p: dict) -> str | None:
    for k in ("source_id", "id"):
        v = str(p.get(k) or "")
        if v.startswith("bank_"):
            return v
    return None


def _bank_en(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    try:
        from core.persona_bank import _fetch
        return {i: r.profile_en for i, r in _fetch(ids).items() if getattr(r, "profile_en", None)}
    except Exception:  # noqa: BLE001
        return {}


def prefetch(personas: list[dict]) -> dict[int, dict]:
    """English profiles for a list of personas: bank ones from the DB, the rest translated in parallel."""
    if not is_en():
        return {}
    bank = _bank_en([b for b in (_bank_id(p) for p in personas) if b])
    out, todo = {}, []
    for i, p in enumerate(personas):
        b = _bank_id(p)
        if b and b in bank:
            out[i] = bank[b]
        elif p.get("profile"):
            todo.append(i)
    if todo:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i, en in zip(todo, pool.map(llm.bind(lambda i: translate_profile(personas[i]["profile"])), todo)):
                out[i] = en
    return out


def persona(p: dict, profile_en: dict | None = None) -> dict:
    """English copy of a persona dict (same keys). No-op in Japanese."""
    if not is_en():
        return p
    q = dict(p)
    q["occupation"] = occupation(p.get("occupation"))
    q["region"] = region(p.get("region"))
    q["income"] = short(p.get("income"), INCOME_EN)
    q["marital"] = short(p.get("marital"), MARITAL_EN)
    if p.get("segment"):
        q["segment"] = ", ".join(TAG_EN.get(s.strip(), s.strip()) for s in str(p["segment"]).split(","))
    prof = profile_en if profile_en is not None else (translate_profile(p["profile"]) if p.get("profile") else None)
    if prof:
        q["profile"] = prof
        # free-text fields (library personas) that no dictionary covers: take them from the English profile
        meta = [x.strip() for x in str(prof.get("meta") or "").split("/")]
        for k, alt in (("region", prof.get("region")), ("income", prof.get("income")),
                       ("occupation", meta[2] if len(meta) > 2 else None)):
            if alt and _has_japanese({"v": q.get(k, "")}):
                q[k] = alt
        if prof.get("full_name") and _has_japanese({"n": p.get("name", "")}):
            q["name"] = re.sub(r"\s*[（(].*?[）)]", "", prof["full_name"]).strip()
        if _bank_id(p) or _has_japanese({"x": p.get("interests", "")}):
            q["interests"] = ", ".join(str(x) for x in (prof.get("purchase_drivers") or [])[:3])
            q["values"] = ", ".join(str(x) for x in (prof.get("values_top") or []))
            q["media"] = ", ".join(str(m).split(":")[0].strip() for m in (prof.get("media") or [])[:4])
    return q


def personas(ps: list[dict]) -> list[dict]:
    if not is_en():
        return ps
    en = prefetch(ps)
    return [persona(p, en.get(i)) for i, p in enumerate(ps)]
