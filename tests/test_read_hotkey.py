"""Tests for celestia_core/shell_read_hotkey.py — the universal read-screen trigger (Feature 07).

The vision capture/analyze modules import heavy native deps (mss, PIL, ollama) at
module top-level, so they are replaced with lightweight fakes injected into
sys.modules. shell_chat.append_raw_turn and activity_feed.append_event import
cheaply, so they are patched in place as spies. No Ollama / screen / GPU needed.
"""

from __future__ import annotations

import sys
import types

import pytest

import celestia_core.shell_read_hotkey as rh


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def read_env(tmp_path, monkeypatch):
    """Stub config + the lazily-imported vision/chat/activity/tts collaborators."""
    cfg: dict[str, object] = {
        "read_hotkey.enabled": True,
        "read_hotkey.hotkey": "ctrl+alt+space",
        "read_hotkey.scope": "active_window",
        "read_hotkey.question": "What is on screen?",
        "read_hotkey.speak_answer": False,
        "vision.enabled": True,
    }
    monkeypatch.setattr(rh, "load_config", lambda: None)
    monkeypatch.setattr(rh, "get", lambda key, default=None: cfg.get(key, default))

    calls: dict[str, list] = {"capture": [], "analyze": [], "events": [], "turns": [], "speak": []}

    def _make_capture(name: str):
        def _cap():
            p = tmp_path / f"{name}.png"
            p.write_bytes(b"fake-image")
            calls["capture"].append(name)
            return p
        return _cap

    # Fake skills.vision.capture / skills.vision.analyze (+ parent package stub)
    vision_pkg = types.ModuleType("skills.vision")
    vision_pkg.__path__ = []  # mark as a package

    cap_mod = types.ModuleType("skills.vision.capture")
    cap_mod.capture_active_window = _make_capture("active")
    cap_mod.capture_fullscreen = _make_capture("full")

    ana_mod = types.ModuleType("skills.vision.analyze")

    def _analyze(path, question):
        calls["analyze"].append((path, question))
        return "On screen: a code editor with an error."

    ana_mod.analyze_image = _analyze

    # Fake skills.tts (its __init__ would import the TTS backends)
    tts_mod = types.ModuleType("skills.tts")

    def _speak(text, **_kw):
        calls["speak"].append(text)

    tts_mod.speak = _speak

    monkeypatch.setitem(sys.modules, "skills.vision", vision_pkg)
    monkeypatch.setitem(sys.modules, "skills.vision.capture", cap_mod)
    monkeypatch.setitem(sys.modules, "skills.vision.analyze", ana_mod)
    monkeypatch.setitem(sys.modules, "skills.tts", tts_mod)

    # activity_feed + shell_chat import cheaply → patch attributes as spies.
    import skills.memory.activity_feed as af

    def _append_event(*, action, text, kind="fact", source="consolidate"):
        calls["events"].append({"action": action, "text": text, "kind": kind, "source": source})

    monkeypatch.setattr(af, "append_event", _append_event)

    import celestia_core.shell_chat as sc

    def _append_raw_turn(user_text, assistant_text, *, session_id=None):
        calls["turns"].append(
            {"user": user_text, "assistant": assistant_text, "session_id": session_id}
        )
        return {
            "session_id": session_id or "sid-1",
            "messages": [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ],
        }

    monkeypatch.setattr(sc, "append_raw_turn", _append_raw_turn)

    # Ensure a clean phase between tests.
    monkeypatch.setattr(rh, "_phase", "idle", raising=False)

    return rh, calls, cfg, ana_mod


# ---------------------------------------------------------------------------
# read_screen_status
# ---------------------------------------------------------------------------


def test_status_idle_reports_hotkey(read_env) -> None:
    mod, _, _, _ = read_env
    st = mod.read_screen_status()
    assert st["phase"] == "idle"
    assert st["hotkey"] == "ctrl+alt+space"


def test_status_hotkey_none_when_disabled(read_env) -> None:
    mod, _, cfg, _ = read_env
    cfg["read_hotkey.enabled"] = False
    assert mod.read_screen_status()["hotkey"] is None


# ---------------------------------------------------------------------------
# trigger_read_screen — happy path
# ---------------------------------------------------------------------------


def test_trigger_returns_messages(read_env) -> None:
    mod, calls, _, _ = read_env
    result = mod.trigger_read_screen(session_id="sid-1")
    assert "error" not in result
    assert result["session_id"] == "sid-1"
    roles = {m["role"] for m in result["messages"]}
    assert roles == {"user", "assistant"}


def test_trigger_passes_question_to_analyze(read_env) -> None:
    mod, calls, _, _ = read_env
    mod.trigger_read_screen()
    assert len(calls["analyze"]) == 1
    _path, question = calls["analyze"][0]
    assert question == "What is on screen?"


def test_trigger_uses_active_window_by_default(read_env) -> None:
    mod, calls, _, _ = read_env
    mod.trigger_read_screen()
    assert calls["capture"] == ["active"]


def test_trigger_fullscreen_scope(read_env) -> None:
    mod, calls, cfg, _ = read_env
    cfg["read_hotkey.scope"] = "fullscreen"
    mod.trigger_read_screen()
    assert calls["capture"] == ["full"]


def test_trigger_logs_activity_event(read_env) -> None:
    mod, calls, _, _ = read_env
    mod.trigger_read_screen()
    assert len(calls["events"]) == 1
    ev = calls["events"][0]
    assert ev["action"] == "read_screen"
    assert ev["source"] == "read_hotkey"
    assert "code editor" in ev["text"]


def test_trigger_persists_turn_with_prefix(read_env) -> None:
    mod, calls, _, _ = read_env
    mod.trigger_read_screen(session_id="abc")
    assert len(calls["turns"]) == 1
    turn = calls["turns"][0]
    assert turn["user"].startswith("[read screen]")
    assert turn["session_id"] == "abc"


def test_trigger_resets_phase_to_idle(read_env) -> None:
    mod, _, _, _ = read_env
    mod.trigger_read_screen()
    assert mod.read_screen_status()["phase"] == "idle"


# ---------------------------------------------------------------------------
# trigger_read_screen — speak option
# ---------------------------------------------------------------------------


def test_trigger_speaks_when_enabled(read_env) -> None:
    mod, calls, cfg, _ = read_env
    cfg["read_hotkey.speak_answer"] = True
    mod.trigger_read_screen()
    assert len(calls["speak"]) == 1
    assert "code editor" in calls["speak"][0]


def test_trigger_silent_by_default(read_env) -> None:
    mod, calls, _, _ = read_env
    mod.trigger_read_screen()
    assert calls["speak"] == []


# ---------------------------------------------------------------------------
# trigger_read_screen — guards & errors
# ---------------------------------------------------------------------------


def test_trigger_vision_disabled_returns_error(read_env) -> None:
    mod, calls, cfg, _ = read_env
    cfg["vision.enabled"] = False
    result = mod.trigger_read_screen()
    assert result["error"] == "vision disabled in config"
    assert calls["capture"] == []


def test_trigger_already_capturing_returns_error(read_env, monkeypatch) -> None:
    mod, calls, _, _ = read_env
    monkeypatch.setattr(mod, "_phase", "capturing", raising=False)
    result = mod.trigger_read_screen()
    assert result["error"] == "already capturing"
    assert calls["capture"] == []


def test_trigger_analyze_failure_returns_error_and_resets(read_env, monkeypatch) -> None:
    mod, calls, _, ana_mod = read_env

    def _boom(path, question):
        raise RuntimeError("vision model offline")

    monkeypatch.setattr(ana_mod, "analyze_image", _boom)
    result = mod.trigger_read_screen()
    assert "vision model offline" in result["error"]
    # Phase must be released even after a failure so the next trigger works.
    assert mod.read_screen_status()["phase"] == "idle"
    assert calls["turns"] == []
