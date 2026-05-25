"""Screenshot ring buffer for CC-49 (in-shell confirm) and CC-68 (history view).

Captures are stored as PNGs in  data/vision_history/<id>.png
An index is maintained at       data/vision_history/index.json
"""
from __future__ import annotations

import base64
import json
import shutil
import time
import uuid
from pathlib import Path

from celestia_core.config import ROOT

_HIST_DIR = ROOT / "data" / "vision_history"
_HIST_JSON = _HIST_DIR / "index.json"
MAX_ENTRIES = 20


def _load() -> list[dict]:
    if not _HIST_JSON.exists():
        return []
    try:
        return json.loads(_HIST_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    _HIST_DIR.mkdir(parents=True, exist_ok=True)
    _HIST_JSON.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def push(img_path: Path) -> str:
    """Copy *img_path* into the ring buffer. Returns the new entry id."""
    _HIST_DIR.mkdir(parents=True, exist_ok=True)
    entry_id = uuid.uuid4().hex[:12]
    dest = _HIST_DIR / f"{entry_id}.png"
    shutil.copy2(img_path, dest)

    entries = _load()
    entries.append({
        "id": entry_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "path": str(dest),
    })

    while len(entries) > MAX_ENTRIES:
        old = entries.pop(0)
        try:
            Path(old["path"]).unlink(missing_ok=True)
        except Exception:
            pass

    _save(entries)
    return entry_id


def get_path(entry_id: str) -> Path | None:
    for e in _load():
        if e["id"] == entry_id:
            p = Path(e["path"])
            return p if p.exists() else None
    return None


def list_entries(n: int = MAX_ENTRIES) -> list[dict]:
    """Return up to *n* most-recent captures (newest first) with base64 thumbnail."""
    entries = _load()[-n:]
    result: list[dict] = []
    for e in reversed(entries):
        p = Path(e.get("path", ""))
        if not p.exists():
            continue
        try:
            b64 = base64.b64encode(p.read_bytes()).decode()
        except Exception:
            b64 = ""
        result.append({
            "id": e["id"],
            "ts": e.get("ts", ""),
            "base64": b64,
        })
    return result
