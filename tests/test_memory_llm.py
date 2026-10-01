"""skills/memory/llm.py — the background memory passes' chat helper (think flag)."""

from __future__ import annotations

import ollama
import pytest

import skills.memory.llm as mllm


@pytest.fixture
def calls(monkeypatch):
    seen: list[dict] = []

    def fake_chat(**kw):
        seen.append(kw)
        return {"message": {"content": "{}"}}

    monkeypatch.setattr(ollama, "chat", fake_chat)
    return seen


def _cfg(monkeypatch, value):
    monkeypatch.setattr(mllm, "get", lambda k, d=None: value if k == "memory.background_think" else d)


def test_think_off_by_default(monkeypatch, calls) -> None:
    _cfg(monkeypatch, False)
    mllm.background_chat(model="m", messages=[])
    assert calls[-1]["think"] is False


def test_default_leaves_model_behaviour(monkeypatch, calls) -> None:
    _cfg(monkeypatch, "default")
    mllm.background_chat(model="m", messages=[])
    assert "think" not in calls[-1]


def test_model_without_thinking_switch_is_retried_plainly(monkeypatch) -> None:
    _cfg(monkeypatch, False)
    seen: list[dict] = []

    def fake_chat(**kw):
        seen.append(kw)
        if "think" in kw:
            raise RuntimeError('"qwen2.5:3b" does not support thinking')
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(ollama, "chat", fake_chat)
    assert mllm.background_chat(model="qwen2.5:3b", messages=[])["message"]["content"] == "ok"
    assert "think" in seen[0] and "think" not in seen[1]


def test_other_errors_propagate(monkeypatch) -> None:
    _cfg(monkeypatch, False)

    def boom(**kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ollama, "chat", boom)
    with pytest.raises(RuntimeError, match="connection refused"):
        mllm.background_chat(model="m", messages=[])
