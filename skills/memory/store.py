"""Long-term memory via mem0 + Chroma (typed entries, budgeted inject)."""

from __future__ import annotations

import re
import threading
import time
from typing import Any

from celestia_core.config import get

from skills.memory.last_session import context_block as last_session_block, is_greeting
from skills.memory.types import DEFAULT_KIND, MemoryKind, normalize_kind

_memory = None
_lock = threading.Lock()

# Instruction entries change rarely — cache them to avoid a full get_all_entries
# scan on every conversation turn.
_INSTRUCTION_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_INSTRUCTION_CACHE_TTL = 60.0  # seconds


def _get_cached_instructions(user_id: str) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached = _INSTRUCTION_CACHE.get(user_id)
    if cached and now - cached[0] < _INSTRUCTION_CACHE_TTL:
        return cached[1]
    all_entries = get_all_entries(user_id, limit=100)
    instructions = [e for e in all_entries if e["kind"] == "instruction"]
    _INSTRUCTION_CACHE[user_id] = (now, instructions)
    return instructions


def _invalidate_instruction_cache(user_id: str | None = None) -> None:
    if user_id:
        _INSTRUCTION_CACHE.pop(user_id, None)
    else:
        _INSTRUCTION_CACHE.clear()


def _get_memory():
    global _memory
    if _memory is None:
        with _lock:
            if _memory is None:
                from mem0 import Memory
                from pathlib import Path
                from celestia_core.config import ROOT, get

                host = get("llm.host", "http://127.0.0.1:11434").rstrip("/")
                embed_model = get("llm.embed_model", "nomic-embed-text")
                chat_model = get("llm.chat_model", "llama3.2:3b")
                chroma_path = str(ROOT / "data" / "memory" / "chroma")

                _memory = Memory.from_config(
                    {
                        "embedder": {
                            "provider": "ollama",
                            "config": {
                                "model": embed_model,
                                "ollama_base_url": host,
                            },
                        },
                        "vector_store": {
                            "provider": "chroma",
                            "config": {
                                "collection_name": "celestia_memories",
                                "path": chroma_path,
                            },
                        },
                        "llm": {
                            "provider": "ollama",
                            "config": {
                                "model": chat_model,
                                "ollama_base_url": host,
                            },
                        },
                    }
                )
    return _memory


def _extract_text(item: dict) -> str:
    return (item.get("memory") or item.get("text") or "").strip()


def _extract_kind(item: dict) -> MemoryKind:
    meta = item.get("metadata") or {}
    if isinstance(meta, dict):
        return normalize_kind(meta.get("kind"))
    return DEFAULT_KIND


def _extract_updated(item: dict) -> float:
    ts = item.get("updated_at") or item.get("created_at") or ""
    if not ts:
        return 0.0
    try:
        from datetime import datetime

        if isinstance(ts, (int, float)):
            return float(ts)
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


def _entry_from_item(item: dict) -> dict[str, Any]:
    return {
        "id": item.get("id", ""),
        "text": _extract_text(item),
        "kind": _extract_kind(item),
        "updated_at": _extract_updated(item),
    }


def get_all_entries(user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    m = _get_memory()
    try:
        raw = m.get_all(user_id=user_id, limit=limit)
        items = raw.get("results", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        out = [_entry_from_item(it) for it in items if _extract_text(it)]
        out.sort(key=lambda e: e["updated_at"], reverse=True)
        return out
    except Exception:
        return []


def add(
    content: str,
    user_id: str = "default",
    *,
    kind: str | MemoryKind = DEFAULT_KIND,
    infer: bool = False,
) -> dict[str, Any]:
    m = _get_memory()
    k = normalize_kind(str(kind))
    result = m.add(
        content,
        user_id=user_id,
        metadata={"kind": k},
        infer=infer,
    )
    if k == "instruction":
        _invalidate_instruction_cache(user_id)
    return result


def get_entries_by_kind(user_id: str, kind: str, limit: int = 50) -> list[dict[str, Any]]:
    k = normalize_kind(kind)
    return [e for e in get_all_entries(user_id, limit) if e["kind"] == k]


_ASSISTANT_MARKERS = re.compile(
    r"\b(i am|i'm)\s+(celestia|atlas|your assistant|an ai)\b|"
    r"\b(celestia|atlas)\s+(said|replied|assistant)\b",
    re.I,
)


def _should_skip_memory(text: str) -> bool:
    t = text.strip()
    if not t or len(t) < 4:
        return True
    if _ASSISTANT_MARKERS.search(t):
        return True
    low = t.lower()
    if low.startswith(("celestia ", "atlas ", "the assistant ")):
        return True
    return False


def add_json(content: str, user_id: str = "default", kind: str = DEFAULT_KIND) -> str:
    try:
        add(content, user_id, kind=kind)
        return f"Saved ({normalize_kind(kind)}): {content[:80]}"
    except Exception as e:
        return f"Memory save failed: {e}"


def search(query: str, user_id: str = "default", limit: int = 5) -> list[dict]:
    m = _get_memory()
    try:
        raw = m.search(query, user_id=user_id, limit=limit)
        items = raw.get("results", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        return [_entry_from_item(it) for it in items if _extract_text(it)]
    except Exception:
        return []


def search_json(query: str, user_id: str = "default") -> str:
    hits = search(query, user_id)
    if not hits:
        return "No matching memories."
    lines = [f"- [{h['kind']}] {h['text']}" for h in hits[:10]]
    return "Relevant memories:\n" + "\n".join(lines)


def delete_by_id(memory_id: str) -> str:
    m = _get_memory()
    try:
        m.delete(memory_id)
        _invalidate_instruction_cache()
        return "Deleted."
    except Exception as e:
        return f"Delete failed: {e}"


def delete_matching(user_id: str, match_text: str) -> str:
    needle = match_text.lower()
    removed = 0
    for entry in get_all_entries(user_id, limit=200):
        if needle in entry["text"].lower():
            delete_by_id(entry["id"])
            removed += 1
    return f"Removed {removed} matching memories." if removed else "No matching memories found."


def edit_json(memory_id: str, new_text: str, user_id: str = "default", kind: str | None = None) -> str:
    return update_entry(memory_id, text=new_text, kind=kind)


def clear_all(user_id: str = "default") -> str:
    entries = get_all_entries(user_id, limit=500)
    n = 0
    for e in entries:
        try:
            _get_memory().delete(e["id"])
            n += 1
        except Exception:
            pass
    _invalidate_instruction_cache(user_id)
    return f"Cleared {n} memories."


def _known_user_ids() -> list[str]:
    return [
        get("memory.user_id", "default"),
        "atlas_user",
        "default",
    ]


def _find_entry(memory_id: str) -> tuple[str | None, dict[str, Any] | None]:
    """Locate the (user_id, entry) owning a memory id in a single pass per user."""
    m = _get_memory()
    for uid in _known_user_ids():
        try:
            raw = m.get_all(user_id=uid, limit=200)
            items = raw.get("results", raw) if isinstance(raw, dict) else raw
            if isinstance(items, list):
                for it in items:
                    if it.get("id") == memory_id and _extract_text(it):
                        return uid, _entry_from_item(it)
        except Exception:
            continue
    return None, None


def update_entry(
    memory_id: str,
    *,
    text: str | None = None,
    kind: str | None = None,
    user_id: str | None = None,
) -> str:
    # Resolve the entry. With a known user_id, one scan finds it; otherwise
    # _find_entry locates the owning user and entry together in a single pass.
    if user_id:
        entry = next(
            (e for e in get_all_entries(user_id, 200) if e["id"] == memory_id), None
        )
        uid = user_id if entry else None
    else:
        uid, entry = _find_entry(memory_id)
    if not uid or not entry:
        return "Memory not found."

    new_text = (text or entry["text"]).strip()
    new_kind = normalize_kind(kind) if kind else entry["kind"]
    m = _get_memory()

    # In-place text update is atomic — no window where the memory is deleted but
    # not yet re-added. A kind change touches metadata (not updatable in place),
    # so it still requires a rewrite.
    if new_kind == entry["kind"] and hasattr(m, "update"):
        try:
            m.update(memory_id, data=new_text)
            _invalidate_instruction_cache(uid)
            return "Updated."
        except Exception:
            return "Update failed."

    try:
        m.delete(memory_id)
    except Exception:
        pass
    add(new_text, uid, kind=new_kind)
    _invalidate_instruction_cache(uid)
    return "Updated."


def format_list(user_id: str = "default", *, kind: str | None = None) -> str:
    entries = get_all_entries(user_id, limit=50)
    if kind:
        k = normalize_kind(kind)
        entries = [e for e in entries if e["kind"] == k]
    if not entries:
        return "No memories stored yet."
    lines = [f"- [{e['kind']}] {e['text'][:120]}" for e in entries[:25]]
    return "Stored memories:\n" + "\n".join(lines)


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = re.sub(r"\s+", " ", line.lower().strip())
        if key and key not in seen:
            seen.add(key)
            out.append(line)
    return out


def build_context(query: str, user_id: str = "default") -> str:
    """Budgeted memory block injected into each turn.

    Per-turn cost: one vector search (Chroma) + cached instruction lookup.
    The old approach did get_all_entries (100-row scan) + search every turn;
    instructions are now served from a 60-second in-process cache instead.
    """
    if not get("memory.enabled", True):
        return ""

    mode = get("memory.inject", "always_budgeted")
    if mode == "off":
        return ""

    max_lines = int(get("memory.inject_max_lines", 8))
    max_chars = int(get("memory.inject_max_chars", 1200))

    if mode == "smart" and not _needs_memory_smart(query):
        return ""

    lines: list[str] = []
    seen: set[str] = set()

    if is_greeting(query):
        block = last_session_block()
        if block:
            lines.append(block)
            seen.add(block)

    # Pinned instructions — served from cache, no full scan per turn
    for e in _get_cached_instructions(user_id)[:2]:
        line = f"[instruction] {e['text']}"
        if line not in seen:
            lines.append(line)
            seen.add(line)

    # Semantic search covers facts, tasks, summaries, and relevant instructions
    if query.strip():
        hits = search(query, user_id, limit=6)
        for h in hits[:4]:
            line = f"[{h['kind']}] {h['text']}"
            if line not in seen:
                lines.append(line)
                seen.add(line)

    # Feature 10 — structural recall: walk the knowledge graph from entities
    # named in the query and inject connected facts (hybrid with similarity).
    # Off by default; entity resolution is alias lookups, no LLM on the hot path.
    if get("memory.graph.enabled", False) and query.strip():
        try:
            from skills.memory import graph_store as _graph

            hops = int(get("memory.graph.walk_hops", 2))
            for ln in _graph.recall_from_text(query, hops=hops, max_lines=4):
                line = f"[graph] {ln}"
                if line not in seen:
                    lines.append(line)
                    seen.add(line)
        except Exception:
            pass

    lines = _dedupe_lines(lines)[:max_lines]
    if not lines:
        return ""

    body = "Relevant context from memory:\n" + "\n".join(f"- {ln}" for ln in lines)
    if len(body) > max_chars:
        body = body[: max_chars - 3] + "..."
    return body


def _needs_memory_smart(query: str) -> bool:
    q = query.strip().lower()
    if is_greeting(q):
        return True
    if len(q) < 4:
        return False
    triggers = (
        "remember",
        "recall",
        "last time",
        "you know",
        "my name",
        "about me",
        "what did",
        "when did",
        "schedule",
        "usually",
        "prefer",
    )
    return any(t in q for t in triggers)
