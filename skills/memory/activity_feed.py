"""Ring buffer of recent memory consolidation events (for shell Activity UI)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get

_lock = threading.Lock()
_MAX = 80


def _feed_path() -> Path:
    rel = get("memory.activity_feed_path", "data/memory/activity_feed.jsonl")
    path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_event(
    *,
    action: str,
    text: str,
    kind: str = "fact",
    source: str = "consolidate",
) -> None:
    row = {
        "ts": time.time(),
        "action": action,
        "kind": kind,
        "text": text[:500],
        "source": source,
    }
    with _lock:
        path = _feed_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        _trim_file(path)


def _trim_file(path: Path) -> None:
    if not path.is_file():
        return
    # Avoid reading and rewriting the file on every append. A JSONL line is
    # roughly 100–200 bytes; _MAX=80 lines ≈ 12 KB. Only bother trimming when
    # the file is meaningfully over budget.
    if path.stat().st_size < _MAX * 250:
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= _MAX:
        return
    path.write_text("\n".join(lines[-_MAX:]) + "\n", encoding="utf-8")


def tail(n: int = 30) -> list[dict[str, Any]]:
    path = _feed_path()
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out
