"""Memory decay-delete (lifecycle step 3).

Removes memories that earned no keep: low importance, never recalled, and older
than the TTL. Protected kinds (instructions) are never touched, and any memory
that was *ever* recalled is exempt — being useful is how a memory survives.

Destructive, so OFF by default — opt in via ``memory.decay.enabled``. Runs at
most once per ``min_interval_hours`` on the background session-finalize path, and
on demand via POST /memory/decay (which can ``dry_run`` to preview).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get
from celestia_core.file_utils import atomic_write_text
from skills.memory.ranking import drop_stats, is_kept, load_stats, recall_for
from skills.memory.types import normalize_kind


def _protect_kinds() -> set[str]:
    raw = get("memory.decay.protect_kinds", ["instruction"])
    if not isinstance(raw, list):
        return {"instruction"}
    return {normalize_kind(str(k)) for k in raw}


def decay_candidates(
    entries: list[dict[str, Any]],
    stats: dict[str, dict[str, Any]],
    *,
    now: float,
    ttl_days: float,
    min_importance: float,
    protect_kinds: set[str],
) -> list[str]:
    """Pure: ids eligible for decay. A memory decays only if it is unprotected,
    below the importance floor, never recalled, and older than the TTL."""
    cutoff = now - ttl_days * 86400.0
    out: list[str] = []
    for e in entries:
        mid = str(e.get("id", ""))
        if not mid:
            continue
        if is_kept(stats, mid):  # user-pinned keeper
            continue
        if normalize_kind(e.get("kind")) in protect_kinds:
            continue
        if float(e.get("importance", 0.5)) >= min_importance:
            continue
        recall_count, _ = recall_for(stats, mid)
        if recall_count > 0:  # ever recalled → earned its place
            continue
        created = float(e.get("created_at", 0.0))
        if created <= 0.0:  # unknown age → never delete
            continue
        if created > cutoff:  # too young
            continue
        out.append(mid)
    return out


# ---------------------------------------------------------------------------
# Throttle marker
# ---------------------------------------------------------------------------


def _last_sweep_path() -> Path:
    return ROOT / "data" / "memory" / "decay_last.txt"


def _seconds_since_last_sweep() -> float:
    path = _last_sweep_path()
    if not path.is_file():
        return float("inf")
    try:
        return time.time() - float(path.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return float("inf")


def _mark_swept() -> None:
    try:
        atomic_write_text(_last_sweep_path(), str(time.time()))
    except OSError:
        pass


def should_sweep_now() -> bool:
    """True if decay is enabled and the throttle window has elapsed."""
    if not get("memory.decay.enabled", False):
        return False
    interval_h = float(get("memory.decay.min_interval_hours", 24))
    return _seconds_since_last_sweep() >= interval_h * 3600.0


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def sweep_decay(
    user_id: str | None = None, *, dry_run: bool = False, force: bool = False
) -> dict[str, Any]:
    """Delete decayed memories for ``user_id``.

    ``dry_run`` returns the candidate ids without deleting (for a preview UI).
    ``force`` bypasses the time throttle (manual trigger); ``enabled`` is always
    respected. Returns ``{enabled, scanned, deleted, ids, ...}``.
    """
    if not get("memory.decay.enabled", False):
        return {"enabled": False, "deleted": 0, "ids": []}
    if not dry_run and not force and not should_sweep_now():
        return {"enabled": True, "throttled": True, "deleted": 0, "ids": []}

    uid = user_id or get("app.user_id", "atlas_user")
    from skills.memory.store import delete_by_id, get_all_entries

    entries = get_all_entries(uid, limit=int(get("memory.decay.scan_limit", 500)))
    ids = decay_candidates(
        entries,
        load_stats(),
        now=time.time(),
        ttl_days=float(get("memory.decay.ttl_days", 30)),
        min_importance=float(get("memory.decay.min_importance", 0.5)),
        protect_kinds=_protect_kinds(),
    )

    if dry_run:
        return {
            "enabled": True,
            "dry_run": True,
            "scanned": len(entries),
            "deleted": 0,
            "ids": ids,
        }

    deleted = 0
    for mid in ids:
        try:
            delete_by_id(mid)
            deleted += 1
        except Exception:
            pass
    if deleted:
        drop_stats(ids)
    _mark_swept()
    return {"enabled": True, "scanned": len(entries), "deleted": deleted, "ids": ids}
