"""Ask a vision model where each persona would look in each keyframe, and what they think."""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from core import llm
from core.llm import CHAT_MODEL, FAST_MODEL, client  # noqa: F401  (re-exported for other modules)
from core.personas import describe

CHUNK = 15  # personas per request

REALISM = """Realism rules (important):
- People may be indifferent, bored, skeptical, confused or say no. Most ads get partial attention at best.
- Never turn a non-user into an eager buyer. If the product doesn't fit their life or budget, show that.
- React through their own profile (job, money, family, media habits, ad attitude), not as a marketer would.
- Plain everyday words, no polished marketing phrases."""

EVIDENCE = """Also say what each reaction rests on:
- "basis": "profile" if it follows a stated fact in their profile, "inferred" if it is a reasonable guess from it,
  "invented" if nothing in the profile supports it.
- "because": at most 60 characters (Japanese) naming that fact or reason."""

PROMPT = """You simulate a consumer research panel watching an advertisement.
This is the frame at t={t:.1f}s{context}.
{speech}
For EACH persona below, predict realistically where their eyes land first in this frame,
how interested they are, and a short inner thought IN JAPANESE (as that person would think it),
plus a natural English translation of that thought.
Different people notice different things (price, faces, product, text, logo, background).
If speech is given, react to the actual words too (a catchphrase, a claim, a price, an awkward line).

{realism}

{evidence}

Personas:
{personas}

Return ONLY a JSON array, one object per persona, in this exact shape:
[{{"id": "P001", "x": 0.0-1.0, "y": 0.0-1.0, "looking_at": "short English label",
   "interest": 1-5, "thought": "日本語の短い心の声", "thought_en": "the same thought in English",
   "basis": "profile|inferred|invented", "because": "根拠"}}]
x,y are normalized image coordinates (0,0 = top-left)."""


def _text(msg):
    return llm.text_of(msg)


def _parse(text):
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []


def speech_near(transcript, t0, t1):
    return " ".join(s["text"].strip() for s in transcript or [] if s["end"] >= t0 and s["start"] <= t1)


def transcript_text(transcript):
    return "\n".join(f"[{s['start']:.0f}-{s['end']:.0f}s] {s['text'].strip()}" for s in transcript or [])


def _ask(keyframe, personas, context, speech=""):
    lines = "\n".join(f"- {describe(p)}" for p in personas)
    text, _ = llm.call(
        model=FAST_MODEL, max_tokens=8000, cache=True, tag="test-gaze",
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": keyframe["jpg_b64"]}},
            {"type": "text", "text": PROMPT.format(
                t=keyframe["t"], context=context, personas=lines, realism=REALISM, evidence=EVIDENCE,
                speech=f'Audio heard around this moment: "{speech}"\n' if speech else "")},
        ]}],
    )
    out = []
    for g in _parse(text):
        try:
            out.append({"id": str(g["id"]), "t": keyframe["t"],
                        "x": min(max(float(g["x"]), 0), 1), "y": min(max(float(g["y"]), 0), 1),
                        "looking_at": g.get("looking_at", ""), "interest": int(g.get("interest", 3)),
                        "thought": g.get("thought", ""), "thought_en": g.get("thought_en", ""),
                        "basis": g.get("basis") if g.get("basis") in ("profile", "inferred", "invented") else None,
                        "because": str(g.get("because") or "")[:120]})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def persona_gaze(keyframes, personas, ad_context="", log=print, transcript=None):
    """Returns a flat list of gaze points for every (keyframe, persona)."""
    context = f" (ad context: {ad_context})" if ad_context else ""
    ts = [kf["t"] for kf in keyframes]
    windows = {kf["t"]: speech_near(transcript, (ts[i - 1] if i else 0) - 1, kf["t"] + 4)
               for i, kf in enumerate(keyframes)}
    jobs = [(kf, personas[i:i + CHUNK], windows[kf["t"]])
            for kf in keyframes for i in range(0, len(personas), CHUNK)]
    log(f"Asking {FAST_MODEL}: {len(jobs)} requests ({len(keyframes)} keyframes × {len(personas)} personas)")
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:  # the shared limiter decides real concurrency
        for chunk in pool.map(llm.bind(lambda j: _safe(j, context, log)), jobs):
            results.extend(chunk)
    return results


def _safe(job, context, log):
    try:
        return _ask(job[0], job[1], context, job[2])
    except Exception as e:  # noqa: BLE001
        log(f"gaze request failed at t={job[0]['t']}: {e}")
        return []


def chat_with_persona(persona, gaze_points, history, user_msg, keyframe=None, transcript=None):
    """Legacy one-to-one interview (v1 endpoints)."""
    seen = "\n".join(f"- t={g['t']:.1f}s looked at {g['looking_at']} (interest {g['interest']}/5): {g['thought']}"
                     for g in gaze_points)
    system = (f"You are this person, being interviewed after watching an ad in a consumer focus group.\n"
              f"Profile: {describe(persona)}\n"
              f"What you noticed while watching:\n{seen or '(nothing recorded)'}\n"
              f"Everything said in the ad (transcript with timestamps):\n{transcript_text(transcript) or '(no speech)'}\n"
              "If asked about specific words or lines, quote them and give your honest reaction.\n"
              f"{REALISM}\n"
              "Stay in character. Keep answers short (2-4 sentences). "
              "Reply in the same language the interviewer uses (Japanese or English).")
    content = [{"type": "text", "text": user_msg}]
    if keyframe and not history:
        content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                       "data": keyframe["jpg_b64"]}})
    text, _ = llm.call(model=CHAT_MODEL, max_tokens=4000, system=system, tag="talk-legacy",
                       messages=history + [{"role": "user", "content": content}])
    return text
