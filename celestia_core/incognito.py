"""Incognito / pause-learning toggle.

A single global switch shared across tray / shell / CLI. When **on**, chat still
works normally, but every *recording* pass is skipped:

- session consolidation (typed long-term memory),
- knowledge-graph extraction,
- the memory activity feed.

State lives in ``data/incognito_state.json`` and is mtime-cached the same way the
security mode is, so the hot path can check it cheaply on every turn and all three
processes (tray, shell API, CLI) see the same value.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT
from celestia_core.file_utils import atomic_write_text, file_lock

# Cache of the parsed state file keyed on its mtime, mirroring security._read_state.
# is_on() is called on every consolidation check; re-parsing the JSON each time is
# wasteful, and the mtime key stays correct across processes (any write bumps it).
_state_cache: tuple[int, dict[str, Any]] | None = None


def _state_path() -> Path:
    return ROOT / "data" / "incognito_state.json"


def _state_lock_path() -> Path:
    return ROOT / "data" / ".incognito_state.lock"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_state() -> dict[str, Any]:
    global _state_cache
    path = _state_path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return {}
    if _state_cache is not None and _state_cache[0] == mtime:
        return _state_cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}
    _state_cache = (mtime, data)
    return data


def is_on() -> bool:
    """True when learning is paused (incognito)."""
    return bool(_read_state().get("on"))


def set_on(value: bool) -> bool:
    """Set incognito on/off. Returns the new state."""
    global _state_cache
    data = {"on": bool(value), "updated": _now_iso()}
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(_state_lock_path()):
        atomic_write_text(path, json.dumps(data, indent=2))
    _state_cache = None  # invalidate; next read re-stats the freshly written file
    return data["on"]


def toggle() -> bool:
    """Flip incognito. Returns the new state."""
    return set_on(not is_on())


def status_label() -> str:
    return "incognito (learning paused)" if is_on() else "learning on"
