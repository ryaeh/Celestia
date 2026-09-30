"""One chat call helper for the background memory passes (consolidation,
last-session note, graph extraction).

These passes can run on a different model than chat (``memory.session_consolidate_model``,
``memory.graph.extraction_model``). Reasoning models such as Qwen3/3.5 think by
default, which makes them slow and is not what the Gate A extraction eval
measured (thinking off). ``memory.background_think`` (default false) is passed as
Ollama's ``think`` flag; a model without a thinking switch gets the call retried
without it, so the setting is safe for any model.
"""

from __future__ import annotations

from typing import Any

import ollama

from celestia_core.config import get


def background_think() -> bool | None:
    """The configured think flag: False/True, or None to leave the model's default."""
    raw = get("memory.background_think", False)
    if raw is None or str(raw).strip().lower() in ("default", "none", ""):
        return None
    return bool(raw)


def background_chat(**kwargs: Any) -> Any:
    """``ollama.chat(**kwargs)`` with ``think`` set per ``memory.background_think``."""
    think = background_think()
    if think is None:
        return ollama.chat(**kwargs)
    try:
        return ollama.chat(**kwargs, think=think)
    except Exception as e:  # noqa: BLE001 — only the "no thinking switch" case is retried
        if "think" not in str(e).lower():
            raise
        return ollama.chat(**kwargs)
