from __future__ import annotations

import json
from typing import Any

from celestia_core.config import ROOT, get

_memory = None
_init_error: str | None = None


def _vector_store_config() -> dict:
    backend = get("memory.vector_store", "chroma").lower()
    if backend == "qdrant":
        host = get("memory.qdrant.host", "localhost")
        port = get("memory.qdrant.port", get("docker.qdrant_port", 6333))
        return {"provider": "qdrant", "config": {"host": host, "port": port}}
    rel = get("memory.chroma.path", "data/chroma")
    path = __import__("pathlib").Path(rel)
    if not path.is_absolute():
        path = __import__("pathlib").Path(ROOT) / path
    path.mkdir(parents=True, exist_ok=True)
    return {"provider": "chroma", "config": {"path": str(path)}}


def _build_mem0():
    from mem0 import Memory

    ollama = get("llm.host", "http://127.0.0.1:11434")
    chat = get("llm.chat_model", "llama3.2:3b")
    embed = get("llm.embed_model", "nomic-embed-text")
    return Memory.from_config(
        {
            "vector_store": _vector_store_config(),
            "llm": {
                "provider": "ollama",
                "config": {"model": chat, "ollama_base_url": ollama},
            },
            "embedder": {
                "provider": "ollama",
                "config": {"model": embed, "ollama_base_url": ollama},
            },
        }
    )


def get_memory():
    global _memory, _init_error
    if not get("memory.enabled", True):
        return None
    if _memory is not None:
        return _memory
    if _init_error:
        raise RuntimeError(_init_error)
    try:
        _memory = _build_mem0()
        return _memory
    except Exception as e:
        _init_error = str(e)
        raise RuntimeError(f"Memory init failed: {e}") from e


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("results", payload)
    else:
        items = payload
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and (item.get("memory") or item.get("data") or item.get("content")):
            out.append(item)
    return out


def _extract_memories(payload: Any) -> list[str]:
    lines: list[str] = []
    for item in _extract_items(payload):
        text = item.get("memory") or item.get("data") or item.get("content")
        if text:
            lines.append(str(text).strip())
    return lines


# Assistant self-descriptions wrongly stored as "user" facts — skip in prompts
_SKIP_MEMORY_PATTERNS = (
    "i am atlas",
    "i am celestia",
    "jarvis-style assistant",
    "i am hearing from you",
)


def _should_skip_memory(text: str) -> bool:
    low = text.strip().lower()
    return any(p in low for p in _SKIP_MEMORY_PATTERNS)


def search(query: str, user_id: str, limit: int = 8) -> list[Any]:
    m = get_memory()
    if m is None:
        return []
    return m.search(query, user_id=user_id, limit=limit)


def add(content: str, user_id: str) -> dict[str, Any]:
    m = get_memory()
    if m is None:
        return {"error": "memory disabled"}
    # Store exact user words — no LLM rewrite (avoids losing "purple" etc.)
    return m.add(content, user_id=user_id, infer=False)


def get_all_entries(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    m = get_memory()
    if m is None:
        return []
    raw = m.get_all(user_id=user_id, limit=limit)
    entries = []
    for item in _extract_items(raw):
        mid = item.get("id")
        text = (item.get("memory") or item.get("data") or item.get("content") or "").strip()
        if mid and text:
            entries.append({"id": mid, "text": text})
    return entries


def get_all_texts(user_id: str, limit: int = 15) -> list[str]:
    return [e["text"] for e in get_all_entries(user_id, limit=limit)]


def build_context(query: str, user_id: str) -> str:
    """Recent facts + semantic search for the current question."""
    try:
        seen: set[str] = set()
        lines: list[str] = []
        for text in get_all_texts(user_id, limit=20):
            if text and text not in seen and not _should_skip_memory(text):
                seen.add(text)
                lines.append(f"- {text}")
        for text in _extract_memories(search(query, user_id, limit=8)):
            if text and text not in seen and not _should_skip_memory(text):
                seen.add(text)
                lines.append(f"- {text}")
        if not lines:
            return ""
        return "Stored facts about the user (trust these over guesses):\n" + "\n".join(lines[:25])
    except Exception:
        return ""


def search_json(query: str, user_id: str) -> str:
    try:
        hits = search(query, user_id)
        texts = _extract_memories(hits)
        return json.dumps({"memories": texts}, default=str)[:8000]
    except Exception as e:
        return f"Memory search failed: {e}"


def add_json(content: str, user_id: str) -> str:
    try:
        result = add(content, user_id)
        texts = _extract_memories(result)
        if texts:
            return f"Stored: {texts[0]}"
        return json.dumps(result, default=str)[:2000]
    except Exception as e:
        return f"Memory add failed: {e}"


def delete_by_id(memory_id: str) -> str:
    m = get_memory()
    if m is None:
        return "Memory disabled"
    m.delete(memory_id)
    return f"Deleted memory {memory_id[:8]}…"


def delete_matching(user_id: str, text: str) -> str:
    """Delete entries whose text contains the substring (case-insensitive)."""
    needle = text.strip().lower()
    if not needle:
        return "Nothing to delete (empty match)."
    removed = 0
    for entry in get_all_entries(user_id, limit=100):
        if needle in entry["text"].lower():
            delete_by_id(entry["id"])
            removed += 1
    if removed == 0:
        return f"No memories matched '{text}'"
    return f"Deleted {removed} memor{'y' if removed == 1 else 'ies'} matching '{text}'"


def update_by_id(memory_id: str, new_text: str) -> str:
    m = get_memory()
    if m is None:
        return "Memory disabled"
    new_text = new_text.strip()
    if not new_text:
        return "Empty text not allowed"
    m.update(memory_id, new_text)
    return f"Updated memory: {new_text[:80]}"


def format_list(user_id: str) -> str:
    entries = get_all_entries(user_id, limit=50)
    if not entries:
        return "No stored memories yet."
    lines = [f"Stored memories ({len(entries)}):"]
    for i, e in enumerate(entries, 1):
        lines.append(f"  {i}. [{e['id'][:8]}…] {e['text']}")
    return "\n".join(lines)


def clear_all(user_id: str) -> str:
    m = get_memory()
    if m is None:
        return "Memory disabled"
    m.delete_all(user_id=user_id)
    return f"Cleared all memories for {user_id}"
