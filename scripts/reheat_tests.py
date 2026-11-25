"""Recompute the attention heatmap of finished tests with the trained model (no LLM calls, nothing else changes).

  .venv/bin/python scripts/reheat_tests.py [test_id ...]      # default: every finished test still on the old map

For each test: back up result.json to result.spectral.json (once), recompute analysis.frames[].heat/peak with
UNISAL from the stored media, set analysis.heat_model = "unisal". Persona gaze, themes and reports are kept.
Restore one test:  copy tests/<id>/result.spectral.json back over result.json.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
os.environ.setdefault("ATTENTION_MODEL_DIR", str(ROOT / ".saliency"))
from sqlmodel import select  # noqa: E402

from backend import db  # noqa: E402
from core import analyze_video as av  # noqa: E402


def reheat(test_id: str, model) -> str:
    d = db.test_dir(test_id)
    res = json.loads((d / "result.json").read_text())
    a = res["analysis"]
    if a.get("heat_model") == "unisal":
        return "already"
    if not (d / "result.spectral.json").exists():
        (d / "result.spectral.json").write_text(json.dumps(res, ensure_ascii=False))
    with tempfile.TemporaryDirectory() as tmp:
        ext = ".png" if not a.get("duration") else ".mp4"
        src = Path(tmp) / f"media{ext}"
        src.write_bytes((d / "media.bin").read_bytes())
        if a.get("duration"):
            maps = av.model_maps(model, str(src), a["duration"])
        else:
            img = cv2.imread(str(src))
            maps = [(0.0, av._grid(model.image(img)))]
    if not maps:
        return "no frames"
    times = np.array([t for t, _ in maps])
    gw, gh = a.get("grid", [av.GRID_W, av.GRID_H])
    for fr in a["frames"]:
        g = maps[int(np.abs(times - fr["t"]).argmin())][1]
        if g.shape != (gh, gw):
            g = cv2.resize(g, (gw, gh), interpolation=cv2.INTER_AREA)
        peak = np.unravel_index(np.argmax(g), g.shape)
        fr["heat"] = np.round(g * 255).astype(np.uint8).flatten().tolist()
        fr["peak"] = [round((peak[1] + 0.5) / gw, 3), round((peak[0] + 0.5) / gh, 3)]
    a["heat_model"] = "unisal"
    (d / "result.json").write_text(json.dumps(res, ensure_ascii=False))
    return f"ok ({len(a['frames'])} frames)"


def main():
    model = av.load_model()
    assert model is not None, "model files missing in .saliency/"
    ids = sys.argv[1:]
    if not ids:
        with db.session() as s:
            ids = [t.id for t in s.exec(select(db.Test).where(db.Test.status == "done")).all()]
    for tid in ids:
        try:
            print(tid, reheat(tid, model), flush=True)
        except Exception as e:  # noqa: BLE001
            print(tid, "FAILED", type(e).__name__, str(e)[:120], flush=True)


if __name__ == "__main__":
    main()
