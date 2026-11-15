"""Save every test run as a report on disk so it can be reopened later."""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "reports"


def save(report: dict, media: bytes) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^\w]+", "-", Path(report["name"]).stem)[:40].strip("-") or "ad"
    rid = f"{stamp}-{slug}"
    d = ROOT / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "media.bin").write_bytes(media)
    report = {**report, "id": rid, "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
    (d / "report.json").write_text(json.dumps(report, ensure_ascii=False, default=str))
    return rid


def update(rid: str, **fields):
    f = ROOT / rid / "report.json"
    data = json.loads(f.read_text())
    data.update(fields)
    f.write_text(json.dumps(data, ensure_ascii=False, default=str))


def load(rid: str) -> dict:
    d = ROOT / rid
    data = json.loads((d / "report.json").read_text())
    data["media"] = (d / "media.bin").read_bytes()
    return data


def list_all() -> list[dict]:
    out = []
    for f in sorted(ROOT.glob("*/report.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            out.append({"id": data["id"], "name": data["name"], "created": data["created"],
                        "viewers": len(data.get("personas", []))})
        except Exception:  # noqa: BLE001
            continue
    return out
