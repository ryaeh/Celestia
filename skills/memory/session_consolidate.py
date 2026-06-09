"""Summarize chat session → typed long-term memory (v2 auto-save)."""

from __future__ import annotations

import json
import re
from typing import Any

import ollama

from celestia_core.config import get
from skills.memory.activity_feed import append_event
from skills.memory.store import _should_skip_memory, add, get_all_entries
from skills.memory.types import KINDS, MemoryKind, normalize_kind

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")

_REMEMBER_HINTS = re.compile(
    r"\b(remember|memorize|memorise|don't forget|dont forget|do not forget|"
    r"keep in mind|save this|note that|store this|never forget)\b",
    re.I,
)

_INFERENCE_MARKERS = re.compile(
    r"\b(helps in|useful for|understanding user|scheduling|inferred|likely|probably|"
    r"may help|could help|suggests that|it seems)\b",
    re.I,
)

_KIND_KEYS: dict[str, MemoryKind] = {
    "facts": "fact",
    "instructions": "instruction",
    "summaries": "summary",
    "tasks": "task",
}


def _dialog_excerpt(messages: list[dict[str, Any]], start_index: int) -> str:
    lines: list[str] = []
    for m in messages[start_index:]:
        role = m.get("role")
        if role == "user":
            lines.append(f"User: {m.get('content', '')}")
        elif role == "assistant":
            text = (m.get("content") or "").strip()
            if text:
                lines.append(f"Assistant: {text[:400]}")
    return "\n".join(lines[-30:])


def _user_turns_since(messages: list[dict[str, Any]], start_index: int) -> int:
    return sum(1 for m in messages[start_index:] if m.get("role") == "user")


def _user_asked_to_remember(messages: list[dict[str, Any]], start_index: int) -> bool:
    for m in messages[start_index:]:
        if m.get("role") != "user":
            continue
        if _REMEMBER_HINTS.search(m.get("content") or ""):
            return True
    return False


def consolidate_mode() -> str:
    """off | explicit | auto."""
    raw = str(get("memory.session_consolidate_mode", "auto") or "auto").lower()
    if raw in ("off", "false", "0", "none"):
        return "off"
    if raw in ("explicit", "manual"):
        return "explicit"
    return "auto"


def should_run_consolidation(
    messages: list[dict[str, Any]],
    *,
    start_index: int,
    end: bool = False,
) -> bool:
    if not get("memory.enabled", True):
        return False
    if not get("memory.session_consolidate", True):
        return False

    mode = consolidate_mode()
    if mode == "off":
        return False
    if mode == "explicit":
        if end and get("memory.session_consolidate_on_end", True):
            return _user_asked_to_remember(messages, start_index)
        return _user_asked_to_remember(messages, start_index)

    if end:
        return bool(get("memory.session_consolidate_on_end", True))

    min_users = int(get("memory.session_consolidate_min_user_turns", 2))
    if _user_turns_since(messages, start_index) < min_users:
        return False

    return True


def _parse_typed(raw: str) -> dict[MemoryKind, list[str]]:
    raw = raw.strip()
    match = _JSON_BLOCK.search(raw)
    if not match:
        return {k: [] for k in KINDS}
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return {k: [] for k in KINDS}

    out: dict[MemoryKind, list[str]] = {k: [] for k in KINDS}
    for key, kind in _KIND_KEYS.items():
        items = data.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = str(item.get("text") or item.get("fact") or "").strip()
            else:
                continue
            if text:
                out[kind].append(text)
    return out


def _normalize_fact(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _is_duplicate(text: str, existing: list[str]) -> bool:
    low = _normalize_fact(text)
    words = _word_set(text)
    for ex in existing:
        ex_low = _normalize_fact(ex)
        if low == ex_low:
            return True
        if len(low) > 12 and (low in ex_low or ex_low in low):
            return True
        ex_words = _word_set(ex)
        if words and ex_words:
            overlap = len(words & ex_words) / min(len(words), len(ex_words))
            if overlap >= 0.72:
                return True
    return False


def _reject_entry(text: str, kind: MemoryKind) -> str | None:
    if _should_skip_memory(text):
        return "assistant/self text"
    if len(text) < 6:
        return "too short"
    if kind != "summary" and _INFERENCE_MARKERS.search(text):
        return "inferred/meta"
    if text.strip().endswith("?"):
        return "question"
    low = text.lower()
    if low.startswith(("the user asked", "the assistant", "celestia ", "atlas ")):
        return "meta narration"
    return None


def consolidate_session_messages(
    messages: list[dict[str, Any]],
    user_id: str,
    *,
    start_index: int = 0,
    extract_graph: bool = True,
    end: bool = False,
) -> tuple[int, list[str]]:
    """
    Store typed memories. Returns (new_start_index, lines for optional verbose log).

    ``extract_graph`` runs the knowledge-graph relation pass (an extra LLM call).
    ``end`` applies end-of-session consolidation rules (e.g. consolidate even on
    a short session). Both the typed and graph passes are meant to run off the
    chat hot-path (background thread), never blocking new-chat / switch-chat.
    """
    if not should_run_consolidation(messages, start_index=start_index, end=end):
        return len(messages), []

    excerpt = _dialog_excerpt(messages, start_index)
    if not excerpt.strip() or len(excerpt) < 30:
        return len(messages), []

    # One fetch of the recent entries, grouped by kind — equivalent to calling
    # get_entries_by_kind(limit=40) per kind but without the repeated get_all scan.
    recent = get_all_entries(user_id, limit=40)
    existing_by_kind: dict[MemoryKind, list[str]] = {
        kind: [e["text"] for e in recent if e["kind"] == kind] for kind in KINDS
    }
    known_blocks: list[str] = []
    for kind in KINDS:
        texts = existing_by_kind[kind]
        if texts:
            known_blocks.append(f"{kind.upper()}:\n" + "\n".join(f"- {t}" for t in texts[:20]))
    known_block = "\n\n".join(known_blocks) if known_blocks else "(none yet)"

    model = get("memory.session_consolidate_model") or get("llm.chat_model", "llama3.2:3b")
    max_per_kind = int(get("memory.session_consolidate_max_facts", 3))

    prompt = (
        "Review this chat excerpt. Extract durable memories in four categories.\n"
        "Rules:\n"
        "- 0 items per category is valid.\n"
        "- NEVER duplicate items under KNOWN MEMOS.\n"
        "- facts: user-stated preferences, projects, names, habits\n"
        "- instructions: standing rules the user wants you to follow\n"
        "- summaries: brief recap of what was discussed (1-2 lines max)\n"
        "- tasks: open todos or things the user plans to do\n"
        "- Do NOT store greetings, assistant opinions, 'helps with X' reasoning, or guesses.\n"
        "JSON only:\n"
        '{"facts":[{"text":"..."}],"instructions":[{"text":"..."}],'
        '"summaries":[{"text":"..."}],"tasks":[{"text":"..."}]}\n\n'
        f"KNOWN:\n{known_block}\n\n--- Excerpt ---\n{excerpt}"
    )

    try:
        resp = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 512, "temperature": 0.1},
        )
        raw = (resp.get("message") or {}).get("content") or ""
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump().get("content", "") or str(raw)
    except Exception as e:
        return len(messages), [f"consolidate skipped: {e}"]

    typed = _parse_typed(str(raw))
    stored_lines: list[str] = []

    for kind in KINDS:
        existing = existing_by_kind[kind]
        for text in typed[kind][:max_per_kind]:
            text = text.strip()
            reject = _reject_entry(text, kind)
            if reject:
                continue
            if _is_duplicate(text, existing):
                continue
            try:
                add(text, user_id, kind=kind)
                existing.append(text)
                append_event(action="saved", text=text, kind=kind)
                if get("memory.session_consolidate_verbose", False):
                    stored_lines.append(f"[{kind}] {text}")
            except Exception as e:
                stored_lines.append(f"(failed [{kind}] '{text[:40]}': {e})")

    # Feature 10 — deep background pass: extract relations into the temporal
    # knowledge graph. Gated and isolated so it never affects typed-memory flow,
    # and skipped on the synchronous finalize path (extract_graph=False) so
    # creating/switching a chat never blocks on the extra LLM call.
    if extract_graph and get("memory.graph.enabled", False) and str(get("memory.graph.deep_pass", "background")) != "off":
        try:
            from skills.memory.graph_extract import extract_and_store

            stored_lines += extract_and_store(excerpt, user_id=user_id, source="chat", model=model)
        except Exception as e:
            stored_lines.append(f"(graph extract failed: {e})")

    return len(messages), stored_lines
