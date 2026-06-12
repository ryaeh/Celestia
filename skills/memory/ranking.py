"""Memory ranking: importance, access stats, and the blended recall score.

Step 1-2 of the memory lifecycle. The hot path stays cheap:

- **Importance** is assigned at write time, heuristically by kind (a smarter
  offline pass — the idle "tidying" job — can re-score it later).
- **Access stats** (recall_count, last_recalled) live in a small JSON sidecar
  keyed by memory id, so bumping them on recall never rewrites a vector.
- **rank_order()** blends similarity (the order mem0 already returned) with
  importance, how often an entry is recalled, and recency — so one-off lookups
  sink out of injection while genuinely useful memories float up.

Nothing here deletes anything; decay-delete is a later step that consumes the
same importance + recall signals.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get
from celestia_core.file_utils import atomic_write_text, file_lock
from skills.memory.types import KINDS, MemoryKind, normalize_kind

# Starting importance per kind. Instructions are standing rules (never decay);
# facts are durable; tasks are often time-bound; summaries are the most
# ephemeral (the main over-save vector). 0..1.
DEFAULT_IMPORTANCE: dict[MemoryKind, float] = {
    "instruction": 1.0,
    "fact": 0.7,
    "task": 0.4,
    "summary": 0.3,
}


def default_importance(kind: str | None) -> float:
    return DEFAULT_IMPORTANCE.get(normalize_kind(kind), 0.5)


# ---------------------------------------------------------------------------
# Access-stat sidecar
# ---------------------------------------------------------------------------


def _stats_path() -> Path:
    return ROOT / "data" / "memory" / "recall_stats.json"


def _lock_path() -> Path:
    return ROOT / "data" / "memory" / "recall_stats.lock"


def load_stats() -> dict[str, dict[str, Any]]:
    """Read the full {memory_id: {"count": int, "last": float}} map."""
    path = _stats_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def recall_for(stats: dict[str, dict[str, Any]], memory_id: str) -> tuple[int, float]:
    rec = stats.get(memory_id) or {}
    try:
        return int(rec.get("count", 0)), float(rec.get("last", 0.0))
    except (TypeError, ValueError):
        return 0, 0.0


def bump_recall(memory_ids: list[str], *, now: float | None = None) -> None:
    """Record that these memories were just recalled. Atomic + cross-process."""
    ids = [m for m in memory_ids if m]
    if not ids:
        return
    ts = time.time() if now is None else now
    path = _stats_path()
    with file_lock(_lock_path()):
        stats = load_stats()
        for mid in ids:
            rec = stats.get(mid) or {}
            rec["count"] = int(rec.get("count", 0)) + 1
            rec["last"] = ts
            stats[mid] = rec
        atomic_write_text(path, json.dumps(stats, ensure_ascii=False, indent=2))


def prune_stats(valid_ids: set[str]) -> None:
    """Keep only stats whose memory id is in ``valid_ids`` (whole-universe prune).

    Caller must pass the *complete* set of live ids — use ``drop_stats`` instead
    when you only know which ids were removed.
    """
    with file_lock(_lock_path()):
        stats = load_stats()
        trimmed = {mid: rec for mid, rec in stats.items() if mid in valid_ids}
        if len(trimmed) != len(stats):
            atomic_write_text(
                _stats_path(), json.dumps(trimmed, ensure_ascii=False, indent=2)
            )


def is_kept(stats: dict[str, dict[str, Any]], memory_id: str) -> bool:
    """True if the user pinned this memory as a keeper (never decays)."""
    return bool((stats.get(memory_id) or {}).get("keep"))


def set_keep(memory_id: str, keep: bool) -> None:
    """Pin/unpin a memory as a keeper. Stored alongside recall stats so it
    survives without rewriting the vector or changing the memory id."""
    if not memory_id:
        return
    with file_lock(_lock_path()):
        stats = load_stats()
        rec = stats.get(memory_id) or {}
        if keep:
            rec["keep"] = True
        else:
            rec.pop("keep", None)
        if rec:
            stats[memory_id] = rec
        else:
            stats.pop(memory_id, None)
        atomic_write_text(_stats_path(), json.dumps(stats, ensure_ascii=False, indent=2))


def drop_stats(memory_ids: list[str]) -> None:
    """Remove access stats for specific deleted memory ids (decay cleanup)."""
    ids = {m for m in memory_ids if m}
    if not ids:
        return
    with file_lock(_lock_path()):
        stats = load_stats()
        trimmed = {mid: rec for mid, rec in stats.items() if mid not in ids}
        if len(trimmed) != len(stats):
            atomic_write_text(
                _stats_path(), json.dumps(trimmed, ensure_ascii=False, indent=2)
            )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _weights() -> dict[str, float]:
    return {
        "similarity": float(get("memory.ranking.weight_similarity", 0.5)),
        "importance": float(get("memory.ranking.weight_importance", 0.25)),
        "recall": float(get("memory.ranking.weight_recall", 0.15)),
        "recency": float(get("memory.ranking.weight_recency", 0.10)),
    }


def rank_score(
    *,
    idx: int,
    total: int,
    importance: float,
    recall_count: int,
    last_recalled: float,
    created_at: float,
    now: float,
    weights: dict[str, float],
    halflife_days: float = 30.0,
) -> float:
    """Blend the signals into one score. Higher = inject sooner.

    - similarity: mem0 already returned entries best-first, so position is the
      proxy (top = 1.0, last → 0.0).
    - importance: the 0..1 durability score.
    - recall: saturating at 5 recalls — being useful keeps a memory alive.
    - recency: exponential decay on the freshest of created/last-recalled.
    """
    sim = 1.0 - (idx / total) if total > 1 else 1.0
    recall = min(max(recall_count, 0), 5) / 5.0
    fresh = max(created_at, last_recalled)
    if fresh > 0 and halflife_days > 0:
        age_days = max(now - fresh, 0.0) / 86400.0
        recency = math.exp(-age_days * math.log(2) / halflife_days)
    else:
        recency = 0.0
    return (
        weights["similarity"] * sim
        + weights["importance"] * max(0.0, min(importance, 1.0))
        + weights["recall"] * recall
        + weights["recency"] * recency
    )


def rank_order(entries: list[dict[str, Any]], *, now: float | None = None) -> list[dict[str, Any]]:
    """Re-order similarity-ranked entries by the blended score (stable on ties)."""
    if len(entries) < 2:
        return entries
    ts = time.time() if now is None else now
    stats = load_stats()
    weights = _weights()
    halflife = float(get("memory.ranking.recency_halflife_days", 30.0))
    total = len(entries)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for idx, e in enumerate(entries):
        rc, last = recall_for(stats, str(e.get("id", "")))
        score = rank_score(
            idx=idx,
            total=total,
            importance=float(e.get("importance", 0.5)),
            recall_count=rc,
            last_recalled=last,
            created_at=float(e.get("created_at", 0.0)),
            now=ts,
            weights=weights,
            halflife_days=halflife,
        )
        scored.append((score, idx, e))
    # Highest score first; original index breaks ties so similarity order holds.
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [e for _, _, e in scored]


# Re-exported so callers don't import KINDS just to iterate importance defaults.
__all__ = [
    "DEFAULT_IMPORTANCE",
    "KINDS",
    "default_importance",
    "load_stats",
    "recall_for",
    "bump_recall",
    "prune_stats",
    "drop_stats",
    "is_kept",
    "set_keep",
    "rank_score",
    "rank_order",
]
