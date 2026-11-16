"""Generate a portrait for each persona with the OpenAI Images API (cached on disk)."""
import base64
import hashlib
import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

CACHE = Path(__file__).resolve().parent.parent / "cache" / "avatars"
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2.6-sunburst")
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "medium")   # low | medium | high
PORTRAIT_VERSION = "v2"                                 # bump to redraw every portrait


def available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _prompt(p: dict) -> str:
    return (f"Photorealistic documentary-style portrait photo of a fictional {p.get('age')}-year-old Japanese "
            f"{str(p.get('gender', '')).lower()} who works as {p.get('occupation', 'an office worker')} "
            f"and lives in {p.get('region', 'Japan')}. Interests: {p.get('interests', '')}. "
            "Head and shoulders, facing the camera with a natural, relaxed expression. They are in a real setting "
            "that fits their life (their home, workplace or a place tied to their interests), softly out of focus "
            "behind them. Everyday clothing that suits their age and job. Natural window light, 50mm lens, "
            "realistic skin texture, sharp eyes, no retouching look. No text, no logos, no watermark.")


def key(p: dict) -> str:
    return hashlib.sha1((PORTRAIT_VERSION + IMAGE_MODEL + IMAGE_QUALITY + _prompt(p)).encode()).hexdigest()[:16]


def _thumb(png: bytes, size=768) -> bytes:
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.thumbnail((size, size))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, optimize=True, progressive=True)
    return buf.getvalue()


def cached(p: dict) -> bytes | None:
    f = CACHE / f"{key(p)}.jpg"
    return f.read_bytes() if f.exists() else None


def generate_one(p: dict) -> bytes:
    hit = cached(p)
    if hit:
        return hit
    from openai import OpenAI
    r = OpenAI().images.generate(model=IMAGE_MODEL, prompt=_prompt(p), size="1024x1024", quality=IMAGE_QUALITY, n=1)
    jpg = _thumb(base64.b64decode(r.data[0].b64_json))
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{key(p)}.jpg").write_bytes(jpg)
    return jpg


def generate_all(personas: list[dict], log=print, workers=6) -> dict[str, bytes]:
    """Returns {persona id: jpeg bytes}. Failures are skipped (persona keeps its colour dot)."""
    def job(p):
        try:
            return p["id"], generate_one(p)
        except Exception as e:  # noqa: BLE001
            log(f"avatar failed for {p['id']}: {e}")
            return p["id"], None

    out = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for pid, img in pool.map(job, personas):
            if img:
                out[pid] = img
    return out


def data_url(jpg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode()
