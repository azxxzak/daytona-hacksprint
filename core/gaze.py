"""Ask a vision model where each persona would look in each keyframe, and what they think."""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import anthropic

from core.personas import describe

FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-5-5")
CHAT_MODEL = os.getenv("CHAT_MODEL", "claude-sonnet-5-5")
CHUNK = 15  # personas per request

_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


PROMPT = """You simulate a consumer research panel watching an advertisement.
This is the frame at t={t:.1f}s{context}.

For EACH persona below, predict realistically where their eyes land first in this frame,
how interested they are, and a short inner thought IN JAPANESE (as that person would think it).
Be honest and varied: many people ignore ads, get bored, or dislike them. Do not be uniformly positive.
Different people notice different things (price, faces, product, text, logo, background).

Personas:
{personas}

Return ONLY a JSON array, one object per persona, in this exact shape:
[{{"id": "P001", "x": 0.0-1.0, "y": 0.0-1.0, "looking_at": "short English label",
   "interest": 1-5, "thought": "日本語の短い心の声"}}]
x,y are normalized image coordinates (0,0 = top-left)."""


def _text(msg):
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _parse(text):
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []


def _ask(keyframe, personas, context):
    lines = "\n".join(f"- {describe(p)}" for p in personas)
    msg = client().messages.create(
        model=FAST_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": keyframe["jpg_b64"]}},
            {"type": "text", "text": PROMPT.format(t=keyframe["t"], context=context, personas=lines)},
        ]}],
    )
    out = []
    for g in _parse(_text(msg)):
        try:
            out.append({"id": str(g["id"]), "t": keyframe["t"],
                        "x": min(max(float(g["x"]), 0), 1), "y": min(max(float(g["y"]), 0), 1),
                        "looking_at": g.get("looking_at", ""), "interest": int(g.get("interest", 3)),
                        "thought": g.get("thought", "")})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def persona_gaze(keyframes, personas, ad_context="", log=print):
    """Returns a flat list of gaze points for every (keyframe, persona)."""
    context = f" (ad context: {ad_context})" if ad_context else ""
    jobs = [(kf, personas[i:i + CHUNK]) for kf in keyframes for i in range(0, len(personas), CHUNK)]
    log(f"Asking {FAST_MODEL}: {len(jobs)} requests ({len(keyframes)} keyframes × {len(personas)} personas)")
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for chunk in pool.map(lambda j: _safe(j, context, log), jobs):
            results.extend(chunk)
    return results


def _safe(job, context, log):
    try:
        return _ask(job[0], job[1], context)
    except Exception as e:  # noqa: BLE001
        log(f"gaze request failed at t={job[0]['t']}: {e}")
        return []


def chat_with_persona(persona, gaze_points, history, user_msg, keyframe=None):
    seen = "\n".join(f"- t={g['t']:.1f}s looked at {g['looking_at']} (interest {g['interest']}/5): {g['thought']}"
                     for g in gaze_points)
    system = (f"You are this person, being interviewed after watching an ad in a consumer focus group.\n"
              f"Profile: {describe(persona)}\n"
              f"What you noticed while watching:\n{seen or '(nothing recorded)'}\n"
              "Stay in character. Be candid, including criticism. Keep answers short (2-4 sentences). "
              "Reply in the same language the interviewer uses (Japanese or English).")
    content = [{"type": "text", "text": user_msg}]
    if keyframe and not history:
        content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                       "data": keyframe["jpg_b64"]}})
    msgs = history + [{"role": "user", "content": content}]
    msg = client().messages.create(model=CHAT_MODEL, max_tokens=600, system=system, messages=msgs)
    return _text(msg)
