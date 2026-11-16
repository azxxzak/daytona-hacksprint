"""One door for every Claude call: adaptive concurrency, retries, usage/cost accounting, optional disk cache.

- Concurrency limit adapts (AIMD): a 429/529 halves it, a run of successes raises it by one.
- Retries with jittered exponential backoff on rate limits, overloaded and 5xx.
- Every call records tokens and USD (price table below) against the user in `current_user` and
  in an append-only usage log, so the UI can show spend and estimates can be measured.
- cache=True stores the text result on disk keyed by a hash of the request, so a retried job
  returns finished work instantly.
"""
import contextvars
import hashlib
import json
import os
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

FAST_MODEL = os.getenv("FAST_MODEL", "claude-haiku-5-5")
CHAT_MODEL = os.getenv("CHAT_MODEL", "claude-sonnet-5-5")

# USD per 1M tokens (input, output). Anthropic first-party list prices; keep in sync with the pricing page.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("ADLENS_DATA", ROOT / "data"))
CACHE_DIR = ROOT / "cache" / "llm"
USAGE_LOG = DATA / "usage.jsonl"

current_user: contextvars.ContextVar[str] = contextvars.ContextVar("adlens_user", default="system")
current_tag: contextvars.ContextVar[str] = contextvars.ContextVar("adlens_tag", default="")

_client = None
_log_lock = threading.Lock()


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=0)  # retries are ours, so the limiter sees every 429
    return _client


class AdaptiveLimiter:
    def __init__(self, start=8, low=1, high=24):
        self.limit, self.low, self.high = start, low, high
        self.active, self.ok_streak = 0, 0
        self.cv = threading.Condition()

    def __enter__(self):
        with self.cv:
            while self.active >= self.limit:
                self.cv.wait()
            self.active += 1

    def __exit__(self, *exc):
        with self.cv:
            self.active -= 1
            self.cv.notify_all()

    def success(self):
        with self.cv:
            self.ok_streak += 1
            if self.ok_streak >= 10 and self.limit < self.high:
                self.limit += 1
                self.ok_streak = 0
                self.cv.notify_all()

    def busy(self):
        with self.cv:
            self.limit = max(self.low, self.limit // 2)
            self.ok_streak = 0


limiter = AdaptiveLimiter(start=int(os.getenv("LLM_CONCURRENCY", "8")))


def cost_usd(model, usage) -> float:
    pin, pout = PRICES.get(model, PRICES[CHAT_MODEL])
    inp = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25 \
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.1
    return round((inp * pin + (getattr(usage, "output_tokens", 0) or 0) * pout) / 1e6, 6)


def _record(model, usage, usd, tag):
    entry = {"at": datetime.now(timezone.utc).isoformat(), "user": current_user.get(), "tag": tag or current_tag.get(),
             "model": model, "in": getattr(usage, "input_tokens", 0), "out": getattr(usage, "output_tokens", 0),
             "usd": usd}
    with _log_lock:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")


def text_of(msg) -> str:
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def call(*, model=None, messages, system=None, max_tokens=4000, cache=False, tag="", budget_s=240) -> tuple[str, float]:
    """Returns (text, usd). Raises the last API error if the time budget runs out."""
    model = model or CHAT_MODEL
    req = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        req["system"] = system
    key = None
    if cache:
        key = hashlib.sha256(json.dumps(req, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        hit = CACHE_DIR / f"{key}.json"
        if hit.exists():
            return json.loads(hit.read_text())["text"], 0.0
    deadline, attempt = time.time() + budget_s, 0
    while True:
        try:
            with limiter:
                msg = client().messages.create(**req)
            limiter.success()
            usd = cost_usd(model, msg.usage)
            _record(model, msg.usage, usd, tag)
            text = text_of(msg)
            if key and text:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (CACHE_DIR / f"{key}.json").write_text(json.dumps({"text": text}, ensure_ascii=False))
            return text, usd
        except anthropic.RateLimitError as e:
            limiter.busy()
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code < 500:
                raise
            if e.status_code == 529:
                limiter.busy()
            last = e
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            last = e
        attempt += 1
        delay = min(30.0, (2 ** attempt) + random.uniform(0, 1))
        if time.time() + delay > deadline:
            raise last
        time.sleep(delay)


def bind(fn):
    """Carry the current user into worker threads (thread pools don't inherit context vars)."""
    user = current_user.get()

    def run(*a, **kw):
        current_user.set(user)
        return fn(*a, **kw)
    return run


def month_usage(user: str) -> dict:
    """Spend this calendar month for one user, from the usage log."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    usd, n = 0.0, {"test": 0, "talk": 0}
    if USAGE_LOG.exists():
        for line in USAGE_LOG.open():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("user") == user and e.get("at", "").startswith(month):
                usd += e.get("usd", 0)
                for k in n:
                    if e.get("tag", "").startswith(k):
                        n[k] += 1
    return {"month_usd": round(usd, 4), "calls": n}
