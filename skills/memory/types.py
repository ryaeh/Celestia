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


# ---------------------------------------------------------------------------
# Origin + trust (T04 — memory-poisoning defense)
# ---------------------------------------------------------------------------
# Every memory records where it came from. Text that reached the model from
# outside the trust boundary (files, web pages, clipboard, screen, MCP servers)
# can be *stored*, but never as an instruction and never live: it's quarantined
# until the user approves it on the Memory page.

ORIGIN_USER = "user"                    # typed by the user (Memory page, API)
ORIGIN_ASSISTANT = "assistant"          # the model called memory_add
ORIGIN_SCREEN = "screen"                # OCR / UI text from the screen
ORIGIN_CONSOLIDATION = "consolidation"  # background distillation of chat
ORIGIN_UNKNOWN = "unknown"              # written before origins existed
_ORIGINS = {ORIGIN_USER, ORIGIN_ASSISTANT, ORIGIN_SCREEN, ORIGIN_CONSOLIDATION, ORIGIN_UNKNOWN}


def normalize_origin(raw: str | None) -> str:
    """One of the fixed origins, or ``tool:<name>``; anything else → unknown."""
    o = (raw or "").strip().lower()
    if o in _ORIGINS:
        return o
    if o.startswith("tool:") and len(o) > 5:
        return o
    return ORIGIN_UNKNOWN


def trust_policy(kind: MemoryKind, *, untrusted: bool) -> tuple[MemoryKind, bool]:
    """``(stored_kind, quarantined)`` for a memory about to be written.

    Untrusted provenance → stored as a quarantined *fact*, whatever kind was
    asked for: injected text must never become a standing instruction (or a
    task Celestia acts on) without the user's say-so.
    """
    if not untrusted:
        return kind, False
    return "fact", True
