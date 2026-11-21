"""Draw a portrait for every persona-bank person who has none yet (resumable: re-run to continue).

    python -m scripts.draw_bank_portraits             # all missing
    python -m scripts.draw_bank_portraits --limit 12  # a small trial

Uses exactly the same prompt/key as the on-demand path (core.avatars), so the app finds them at once.
Concurrency is modest and 429s back off, so it stays inside the OpenAI image rate limit.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import avatars, persona_bank  # noqa: E402
from core.store import _list_keys  # noqa: E402

WORKERS = 6
PRICE = {"low": 0.011, "medium": 0.042, "high": 0.167}   # approx. USD per 1024x1024 image


def missing() -> list[dict]:
    ids = [r[0] for r in persona_bank._index()]
    have = {k.rsplit("/", 1)[-1][:-4] for k in _list_keys("avatars", depth=1) if k.endswith(".jpg")}
    out = []
    for i in range(0, len(ids), 500):
        for p in persona_bank.get(ids[i:i + 500]):
            if avatars.key(p) not in have:
                out.append(p)
    return out


def draw(p: dict) -> tuple[str, str | None]:
    for attempt in range(6):
        try:
            avatars.generate_one(p)
            return p["id"], None
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "429" in msg or "rate" in msg.lower() or "timeout" in msg.lower() or "502" in msg or "503" in msg:
                time.sleep(min(90, 10 * (attempt + 1)))
                continue
            return p["id"], msg[:160]
    return p["id"], "gave up after retries"


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    todo = missing()
    if limit:
        todo = todo[:limit]
    print(f"to draw: {len(todo)} (quality {avatars.IMAGE_QUALITY}, ~${len(todo) * PRICE.get(avatars.IMAGE_QUALITY, 0.042):.0f})", flush=True)
    t0, done, failed = time.time(), 0, []
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = [ex.submit(draw, p) for p in todo]
        for f in as_completed(futs):
            pid, err = f.result()
            done += 1
            if err:
                failed.append((pid, err))
            if done % 25 == 0 or done == len(todo):
                rate = done / max(1, time.time() - t0) * 60
                eta = (len(todo) - done) / max(rate, 0.1)
                print(f"{done}/{len(todo)} drawn, {len(failed)} failed, {rate:.1f}/min, ~{eta:.0f} min left", flush=True)
    for pid, err in failed[:20]:
        print("  failed:", pid, err)
    print(f"finished in {(time.time() - t0) / 60:.1f} min; failed {len(failed)}")


if __name__ == "__main__":
    main()
