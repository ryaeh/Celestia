"""Memory entry kinds for Celestia v2."""

from __future__ import annotations

from typing import Literal

MemoryKind = Literal["fact", "instruction", "summary", "task"]

KINDS: tuple[MemoryKind, ...] = ("fact", "instruction", "summary", "task")

DEFAULT_KIND: MemoryKind = "fact"


def normalize_kind(raw: str | None) -> MemoryKind:
    k = (raw or DEFAULT_KIND).strip().lower()
    if k in KINDS:
        return k  # type: ignore[return-value]
    return DEFAULT_KIND


def kinds_enabled() -> list[MemoryKind]:
    from celestia_core.config import get

    raw = get("memory.kinds_enabled", list(KINDS))
    if not isinstance(raw, list):
        return list(KINDS)
    out: list[MemoryKind] = []
    for item in raw:
        k = normalize_kind(str(item))
        if k not in out:
            out.append(k)
    return out or list(KINDS)
