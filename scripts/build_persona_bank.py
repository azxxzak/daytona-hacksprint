"""Build the persona bank with the Anthropic Message Batches API (resumable).

    python -m scripts.build_persona_bank --n 20          # pilot (first 20 seeds)
    python -m scripts.build_persona_bank --n 5000        # full build; re-run any time to continue
    python -m scripts.build_persona_bank --status        # progress + measured cost, no API calls that spend money
    python -m scripts.build_persona_bank --reset-profiles --n 20   # drop built rows (keep seeds) to re-run after a prompt change

State lives in Postgres (persona_bank_job / persona_bank_batch). A re-run first collects every uncollected
batch, then submits only seeds still `pending`, then re-batches failed seeds once (attempt 2).
Known gap: a crash after batches.create() returns but before the batch id is committed would orphan one batch
(the API has no idempotency key); the window is a single DB commit.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic  # noqa: E402
from sqlmodel import delete, func, select, update  # noqa: E402

from backend.db import engine, session  # noqa: E402
from core import persona_bank as pb  # noqa: E402
from core.persona_bank import PersonaBank, PersonaBankBatch, PersonaBankJob  # noqa: E402

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT, BATCH_DISCOUNT = 0.10, 0.50, 0.5   # USD per 1M tokens
MAX_TOKENS = 8000                                        # Haiku 5.5 thinks first
CHUNK = 1000                                             # requests per batch
MAX_ATTEMPTS = 2                                         # first pass + one re-batch

client = anthropic.Anthropic(max_retries=4, timeout=600)


def now():
    return pb._now()


def cost_now() -> tuple[int, int, float]:
    with session() as s:
        i, o = s.exec(select(func.coalesce(func.sum(PersonaBankJob.input_tokens), 0),
                             func.coalesce(func.sum(PersonaBankJob.output_tokens), 0))).one()
    return int(i), int(o), (i * PRICE_IN + o * PRICE_OUT) / 1e6 * BATCH_DISCOUNT


def seed_jobs(n: int):
    with session() as s:
        have = set(s.exec(select(PersonaBankJob.id)).all())
        new = [PersonaBankJob(id=pb.bank_id(i), seed=pb.make_seed(i)) for i in range(1, n + 1) if pb.bank_id(i) not in have]
        s.add_all(new)
        s.commit()
    print(f"seeds: {n - len(new)} existing, {len(new)} created")


def submit(job_ids: list[str], attempt: int):
    with session() as s:
        jobs = s.exec(select(PersonaBankJob).where(PersonaBankJob.id.in_(job_ids)).order_by(PersonaBankJob.id)).all()
    system = pb.build_system()
    reqs = [{"custom_id": j.id, "params": {"model": MODEL, "max_tokens": MAX_TOKENS, "system": system,
                                           "messages": [{"role": "user", "content": pb.build_user(j.seed)}]}} for j in jobs]
    batch = client.messages.batches.create(requests=reqs)
    register(batch.id, attempt, [j.id for j in jobs])
    print(f"submitted batch {batch.id}: {len(jobs)} requests (attempt {attempt})")


def register(batch_id: str, attempt: int, ids: list[str]):
    """One transaction, bulk statements (the DB link is ~0.8s per round-trip, so no per-row loops)."""
    with session() as s:
        s.add(PersonaBankBatch(batch_id=batch_id, attempt=attempt, size=len(ids)))
        s.exec(update(PersonaBankJob).where(PersonaBankJob.id.in_(ids)).values(
            status="submitted", batch_id=batch_id, attempt=attempt, updated_at=now()))
        s.commit()


def collect(batch_id: str, poll: int):
    while True:
        b = client.messages.batches.retrieve(batch_id)
        rc = b.request_counts
        print(f"  {batch_id} {b.processing_status}: ok={rc.succeeded} err={rc.errored} canceled={rc.canceled} "
              f"expired={rc.expired} processing={rc.processing}", flush=True)
        if b.processing_status == "ended":
            break
        time.sleep(poll)
    ok = bad = 0
    tin = tout = 0
    results = list(client.messages.batches.results(batch_id))
    with session() as s:
        jobs = {j.id: j for j in s.exec(select(PersonaBankJob).where(PersonaBankJob.id.in_([r.custom_id for r in results]))).all()}
        rows, upd = [], []
        for r in results:
            job = jobs.get(r.custom_id)
            if job is None or job.status == "done":
                continue
            err, prof, di, do = None, None, 0, 0
            if r.result.type != "succeeded":
                err = f"batch result {r.result.type}"
            else:
                m = r.result.message
                di, do = m.usage.input_tokens, m.usage.output_tokens
                tin += di
                tout += do
                text = "".join(c.text for c in m.content if c.type == "text")
                if m.stop_reason == "max_tokens":
                    err = "max_tokens before JSON finished"
                else:
                    try:
                        prof = pb.parse_profile(text)
                        err = pb.validate_profile(prof, job.seed)
                    except ValueError as e:
                        err = f"parse: {str(e)[:150]}"
            upd.append({"id": job.id, "status": "failed" if err else "done", "error": err, "updated_at": now(),
                        "input_tokens": job.input_tokens + di, "output_tokens": job.output_tokens + do})
            if err:
                bad += 1
            else:
                sd = job.seed
                rows.append(PersonaBank(id=job.id, age=sd["age"], gender=sd["gender"], region=sd["region"],
                                        area_type=sd["area_type"], occupation=sd["occupation"], employment=sd["employment"],
                                        marital=sd["marital"], household=sd["household"], income=sd["income"],
                                        segment_tags=sd["segment_tags"], profile=prof, seed=sd))
                ok += 1
        if rows:
            s.exec(delete(PersonaBank).where(PersonaBank.id.in_([r.id for r in rows])))   # idempotent re-collect
            s.add_all(rows)
        if upd:
            s.execute(update(PersonaBankJob), upd)   # ORM bulk update by primary key
        s.exec(update(PersonaBankBatch).where(PersonaBankBatch.batch_id == batch_id).values(
            collected_at=now(), input_tokens=tin, output_tokens=tout))
        s.commit()
    print(f"  collected {batch_id}: {ok} valid, {bad} failed validation/errored")


def pending_batches() -> list[str]:
    with session() as s:
        return list(s.exec(select(PersonaBankBatch.batch_id).where(PersonaBankBatch.collected_at.is_(None))).all())


def job_ids(n: int, status: str, max_attempt: int | None = None) -> list[str]:
    q = select(PersonaBankJob.id).where(PersonaBankJob.status == status, PersonaBankJob.id <= pb.bank_id(n))
    if max_attempt is not None:
        q = q.where(PersonaBankJob.attempt <= max_attempt)
    with session() as s:
        return list(s.exec(q.order_by(PersonaBankJob.id)).all())


def status(n: int):
    with session() as s:
        rows = s.exec(select(PersonaBankJob.status, func.count()).where(PersonaBankJob.id <= pb.bank_id(n))
                      .group_by(PersonaBankJob.status)).all()
        total = s.exec(select(func.count()).select_from(PersonaBank)).one()
    i, o, c = cost_now()
    print(f"jobs: {dict(rows)} | bank rows: {total} | tokens in={i:,} out={o:,} | measured batch cost ${c:.4f}")


def run(n: int, poll: int):
    t0 = time.time()
    pb.init_tables()
    seed_jobs(n)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for bid in pending_batches():          # resume: collect batches from earlier runs first
            collect(bid, poll)
        todo = job_ids(n, "pending") if attempt == 1 else job_ids(n, "failed", attempt - 1)
        # also anything 'submitted' without an open batch (should not happen) is treated as failed above
        if attempt == 1:
            todo += [i for i in job_ids(n, "failed", 0)]
        if not todo:
            print(f"attempt {attempt}: nothing to submit")
            continue
        print(f"attempt {attempt}: {len(todo)} personas to generate")
        for k in range(0, len(todo), CHUNK):
            submit(todo[k:k + CHUNK], attempt)
        for bid in pending_batches():
            collect(bid, poll)
        status(n)
    pb.invalidate()
    status(n)
    print(f"elapsed this run: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=pb.BANK_SIZE)
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--adopt", help="register an already-created batch id (e.g. after a crash between create and commit)")
    ap.add_argument("--reset-profiles", action="store_true", help="delete built rows + reset jobs to pending (seeds kept)")
    a = ap.parse_args()
    pb.init_tables()
    if a.reset_profiles:
        with session() as s:
            ids = pb.bank_id(a.n)
            s.exec(delete(PersonaBank).where(PersonaBank.id <= ids))
            for j in s.exec(select(PersonaBankJob).where(PersonaBankJob.id <= ids)).all():
                j.status, j.attempt, j.batch_id, j.error = "pending", 0, None, None
                j.seed = pb.make_seed(int(j.id.split("_")[1]))   # pick up sampler changes
                j.input_tokens = j.output_tokens = 0
                s.add(j)
            s.commit()
        print("reset done")
    elif a.adopt:
        register(a.adopt, 1, [])
        print("adopted; run the build again to collect it")
    elif a.status:
        status(a.n)
    else:
        run(a.n, a.poll)
