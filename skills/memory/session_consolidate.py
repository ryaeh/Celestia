"""Summarize chat session → long-term memory (no user confirm)."""

from __future__ import annotations

import json
import re
from typing import Any

import ollama

from celestia_core.config import get
from skills.memory.store import _should_skip_memory, add, get_all_texts

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


def _dialog_excerpt(messages: list[dict[str, Any]], start_index: int) -> str:
    lines: list[str] = []
    for m in messages[start_index:]:
        role = m.get("role")
        if role == "user":
            lines.append(f"User: {m.get('content', '')}")
        elif role == "assistant":
            text = (m.get("content") or "").strip()
            if text:
                lines.append(f"Assistant: {text[:500]}")
        elif role == "tool":
            name = m.get("name", "tool")
            body = str(m.get("content", ""))[:200]
            lines.append(f"[{name}: {body}]")
    return "\n".join(lines[-40:])


def _parse_facts(raw: str) -> list[dict[str, str]]:
    raw = raw.strip()
    match = _JSON_BLOCK.search(raw)
    if not match:
        return []
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return []
    facts = data.get("facts") or []
    if not isinstance(facts, list):
        return []
    out: list[dict[str, str]] = []
    for item in facts:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("fact") or "").strip()
        if not text:
            continue
        reason = str(item.get("reason") or item.get("why") or "session summary").strip()
        out.append({"text": text, "reason": reason})
    return out


def _is_duplicate(text: str, existing: list[str]) -> bool:
    low = text.lower()
    for ex in existing:
        if low == ex.lower() or low in ex.lower() or ex.lower() in low:
            return True
    return False


def consolidate_session_messages(
    messages: list[dict[str, Any]],
    user_id: str,
    *,
    start_index: int = 0,
) -> tuple[int, list[str]]:
    """
    Analyze new session messages; store 0–3 user facts in long-term memory.
    Returns (new_start_index, human-readable lines about what was stored).
    """
    if not get("memory.enabled", True):
        return len(messages), []
    if not get("memory.session_consolidate", True):
        return len(messages), []

    excerpt = _dialog_excerpt(messages, start_index)
    if not excerpt.strip() or len(excerpt) < 40:
        return len(messages), []

    model = get("memory.session_consolidate_model") or get("llm.chat_model", "llama3.2:3b")
    prompt = (
        "You review a chat between a user and an assistant. "
        "Pick 0–3 durable facts about THE USER ONLY that would help in future conversations.\n"
        "Store: preferences, names, projects, habits, stated goals.\n"
        "Do NOT store: greetings, one-off tasks, assistant identity, tool errors, "
        "file paths unless the user said they always use that location.\n"
        "Respond with JSON only:\n"
        '{"facts":[{"text":"short fact in third person about user","reason":"why it matters"}]}\n'
        "If nothing is worth long-term memory, return: {\"facts\":[]}\n\n"
        f"--- Chat excerpt ---\n{excerpt}"
    )

    try:
        resp = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 512, "temperature": 0.2},
        )
        raw = (resp.get("message") or {}).get("content") or ""
    except Exception as e:
        return len(messages), [f"[memory] consolidate skipped: {e}"]

    facts = _parse_facts(raw)
    if not facts:
        return len(messages), []

    existing = get_all_texts(user_id, limit=30)
    stored_lines: list[str] = []
    max_facts = int(get("memory.session_consolidate_max_facts", 3))

    for item in facts[:max_facts]:
        text = item["text"]
        reason = item["reason"]
        if _should_skip_memory(text):
            continue
        if _is_duplicate(text, existing):
            continue
        try:
            add(text, user_id)
            existing.append(text)
            stored_lines.append(f"{text} — {reason}")
        except Exception as e:
            stored_lines.append(f"(failed to store '{text[:40]}': {e})")

    return len(messages), stored_lines
