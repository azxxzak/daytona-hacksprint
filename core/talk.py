"""Talks: one-to-one or group conversations between the user and the viewers of a finished test."""
import re

from core.gaze import CHAT_MODEL, FAST_MODEL, _text, client, transcript_text
from core.personas import describe


def _lang(text: str) -> str:
    return "Japanese" if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text or "") else "English"


def _render_thread(thread, personas_by_id, me_id):
    lines = []
    for m in thread:
        if m["role"] == "user":
            lines.append(f"Moderator: {m['content']}")
        else:
            who = "You" if m["persona_id"] == me_id else personas_by_id.get(m["persona_id"], {}).get("name", "Someone")
            lines.append(f"{who}: {m['content']}")
    return "\n".join(lines)


def reply(persona, members, gaze_points, transcript, keyframe, thread, question, said_this_turn, mode):
    """One viewer's answer. said_this_turn: [(persona, content)] already answered this question (conversation mode)."""
    by_id = {p["id"]: p for p in members}
    seen = "\n".join(f"- {g['t']:.0f}s: looked at {g['looking_at']} (interest {g['interest']}/5): {g['thought']}"
                     for g in gaze_points) or "(nothing recorded)"
    others = [p for p in members if p["id"] != persona["id"]]
    if others:
        room = ("You are in a group discussion (focus group) with: "
                + "; ".join(f"{p['name']} ({p['age']}, {p.get('occupation', '')})" for p in others) + ".")
    else:
        room = "This is a one-to-one interview."
    style = ""
    if mode == "conversation" and others:
        style = ("Speak to the room, not only the moderator: react to what the others just said, agree or push back, "
                 "and refer to them by name when it fits. Do not repeat a point someone already made.")
    system = (f"You are this person, a member of a consumer panel who just watched an advertisement.\n"
              f"Profile: {describe(persona)}\n"
              f"What you noticed while watching:\n{seen}\n"
              f"Everything said in the ad:\n{transcript_text(transcript) or '(no speech)'}\n\n"
              f"{room} {style}\n"
              "Stay in character with your own age, job, habits and values. Be candid; criticism and indifference are "
              "fine. Keep it to 2-4 short sentences, conversational, no lists. "
              f"The moderator's latest question is in {_lang(question)}: you MUST answer in {_lang(question)}, "
              "even if earlier messages or your notes are in another language.")
    parts = []
    if thread:
        parts.append("Conversation so far:\n" + _render_thread(thread, by_id, persona["id"]))
    parts.append(f"Moderator now asks: {question}")
    if said_this_turn:
        parts.append("Just now, others answered:\n" + "\n".join(f"{p['name']}: {c}" for p, c in said_this_turn))
    parts.append("Your answer:")
    content = [{"type": "text", "text": "\n\n".join(parts)}]
    if keyframe:
        content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                       "data": keyframe["jpg_b64"]}})
    msg = client().messages.create(model=CHAT_MODEL, max_tokens=2000, system=system,
                                   messages=[{"role": "user", "content": content}])
    return _text(msg).strip()


def suggest(thread, members):
    """Next moderator question, in the language of the last question."""
    if not thread:
        return None
    by_id = {p["id"]: p for p in members}
    convo = _render_thread(thread[-24:], by_id, me_id=None)
    last_q = next((m["content"] for m in reversed(thread) if m["role"] == "user"), "")
    msg = client().messages.create(
        model=FAST_MODEL, max_tokens=2000,  # leaves room for the model's thinking before the short answer
        messages=[{"role": "user", "content":
                   "You moderate a consumer focus group about an advertisement. Here is the discussion:\n\n"
                   f"{convo}\n\nWrite ONE next question that digs into the most interesting tension or vague point "
                   "you see (e.g. ask why, ask for a concrete example, contrast two people's views). Max 60 characters. "
                   f"Write it in {_lang(last_q)}. Output only the question."}])
    q = re.sub(r"^[\"'「『\s]+|[\"'」』\s]+$", "", _text(msg).strip().splitlines()[0] if _text(msg).strip() else "")
    return q or None
