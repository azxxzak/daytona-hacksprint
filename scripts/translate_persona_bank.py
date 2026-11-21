"""Fill persona_bank.profile_en with English profiles via the Message Batches API (resumable, ~$2-3 for 5,000).

    python -m scripts.translate_persona_bank            # submit what is missing, wait, store results
    python -m scripts.translate_persona_bank --collect msgbatch_...   # store the results of an existing batch

Uses the same prompt and validation as the on-demand path (core.localize).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from sqlmodel import select, update  # noqa: E402

from backend import db  # noqa: E402
from core import llm, localize  # noqa: E402
from core.persona_bank import PersonaBank  # noqa: E402

CHUNK = 1000
client = anthropic.Anthropic(max_retries=4, timeout=600)


def missing() -> list[str]:
    with db.session() as s:
        return list(s.exec(select(PersonaBank.id).where(PersonaBank.profile_en.is_(None)).order_by(PersonaBank.id)).all())


def submit(ids: list[str]) -> str:
    with db.session() as s:
        rows = s.exec(select(PersonaBank.id, PersonaBank.profile).where(PersonaBank.id.in_(ids))).all()
    reqs = [{"custom_id": i, "params": {"model": llm.FAST_MODEL, "max_tokens": 8000, "system": localize.TRANSLATE_SYSTEM,
                                        "messages": [{"role": "user", "content": localize.translate_user(p)}]}}
            for i, p in rows]
    b = client.messages.batches.create(requests=reqs)
    print(f"submitted {b.id}: {len(reqs)}", flush=True)
    return b.id


def collect(batch_id: str):
    while True:
        b = client.messages.batches.retrieve(batch_id)
        rc = b.request_counts
        print(f"  {batch_id} {b.processing_status}: ok={rc.succeeded} err={rc.errored} processing={rc.processing}", flush=True)
        if b.processing_status == "ended":
            break
        time.sleep(30)
    results = list(client.messages.batches.results(batch_id))
    with db.session() as s:
        orig = dict(s.exec(select(PersonaBank.id, PersonaBank.profile).where(
            PersonaBank.id.in_([r.custom_id for r in results]))).all())
    upd, bad, tin, tout = [], 0, 0, 0
    for r in results:
        if r.result.type != "succeeded" or r.custom_id not in orig:
            bad += 1
            continue
        m = r.result.message
        tin += m.usage.input_tokens
        tout += m.usage.output_tokens
        try:
            en = localize.parse_translation("".join(c.text for c in m.content if c.type == "text"), orig[r.custom_id])
        except (ValueError, KeyError) as e:  # noqa: PERF203
            bad += 1
            print(f"   {r.custom_id}: {str(e)[:80]}")
            continue
        upd.append({"id": r.custom_id, "profile_en": en})
    with db.session() as s:
        for k in range(0, len(upd), 500):
            s.execute(update(PersonaBank), upd[k:k + 500])
        s.commit()
    usd = (tin * llm.PRICES.get(llm.FAST_MODEL, (0.1, 0.5))[0] + tout * llm.PRICES.get(llm.FAST_MODEL, (0.1, 0.5))[1]) / 1e6 * 0.5
    print(f"  stored {len(upd)}, failed {bad}, batch cost ~${usd:.2f}", flush=True)


def main():
    db.init()
    if "--collect" in sys.argv:
        collect(sys.argv[sys.argv.index("--collect") + 1])
        return
    for attempt in (1, 2):
        todo = missing()
        print(f"attempt {attempt}: {len(todo)} profiles without English", flush=True)
        if not todo:
            break
        ids = [submit(todo[k:k + CHUNK]) for k in range(0, len(todo), CHUNK)]
        for bid in ids:
            collect(bid)
    print("still missing:", len(missing()))


if __name__ == "__main__":
    main()
