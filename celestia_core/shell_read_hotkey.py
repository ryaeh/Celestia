"""Global 'read screen' hotkey — capture → vision → inject into active chat (Feature 07)."""

from __future__ import annotations

import threading
from typing import Any

from celestia_core.config import get, load_config

_lock = threading.Lock()
_phase: str = "idle"  # idle | capturing
_listener_started = False


def _hotkey_spec() -> str | None:
    if not get("read_hotkey.enabled", True):
        return None
    raw = str(get("read_hotkey.hotkey", "ctrl+alt+space") or "").strip()
    return raw or None


def read_screen_status() -> dict[str, Any]:
    with _lock:
        return {"phase": _phase, "hotkey": _hotkey_spec()}


def trigger_read_screen(*, session_id: str | None = None) -> dict[str, Any]:
    """Capture active window → analyze → inject as chat turn. Thread-safe."""
    global _phase

    with _lock:
        if _phase != "idle":
            return {"error": "already capturing"}
        _phase = "capturing"

    try:
        if not get("vision.enabled", True):
            return {"error": "vision disabled in config"}

        scope = str(get("read_hotkey.scope", "active_window") or "active_window")
        question = str(
            get("read_hotkey.question", "What is on screen? Describe what you see concisely.")
            or "What is on screen? Describe what you see concisely."
        )
        speak = bool(get("read_hotkey.speak_answer", False))

        from skills.vision.capture import capture_active_window, capture_fullscreen
        from skills.vision.analyze import analyze_image
        from celestia_core.shell_chat import append_raw_turn
        from skills.memory.activity_feed import append_event

        image_path = capture_fullscreen() if scope == "fullscreen" else capture_active_window()

        try:
            answer = analyze_image(image_path, question)
        finally:
            try:
                image_path.unlink(missing_ok=True)
            except OSError:
                pass

        user_msg = f"[read screen] {question}"
        result = append_raw_turn(user_msg, answer, session_id=session_id)
        append_event(action="read_screen", text=answer[:200], kind="fact", source="read_hotkey")

        if speak:
            try:
                from skills.tts import speak as tts_speak
                tts_speak(answer[:600])
            except Exception:
                pass

        return result
    except Exception as e:
        return {"error": str(e)}
    finally:
        with _lock:
            _phase = "idle"


def _trigger_bg(session_id: str | None = None) -> None:
    threading.Thread(
        target=trigger_read_screen,
        kwargs={"session_id": session_id},
        name="read-screen",
        daemon=True,
    ).start()


def start_read_hotkey_listener() -> None:
    """Register the global read-screen hotkey. Called from shell_server.start_server()."""
    global _listener_started

    load_config()
    spec = _hotkey_spec()
    if not spec:
        return

    with _lock:
        if _listener_started:
            return
        _listener_started = True

    from celestia_core.shell_ptt import _parse_hotkey_parts, _key_token

    required_mods, main_key = _parse_hotkey_parts(spec)
    if not main_key:
        print(f"[read-screen] invalid hotkey spec: {spec}", flush=True)
        return

    pressed: set[str] = set()
    fired = False

    def on_press(key) -> None:
        nonlocal fired
        tok = _key_token(key)
        if tok:
            pressed.add(tok)
        if not fired:
            if required_mods and not required_mods.issubset(pressed):
                return
            if main_key in pressed:
                fired = True
                _trigger_bg()

    def on_release(key) -> None:
        nonlocal fired
        tok = _key_token(key)
        if tok:
            pressed.discard(tok)
        if fired:
            combo_still_down = main_key in pressed and (
                not required_mods or required_mods.issubset(pressed)
            )
            if not combo_still_down:
                fired = False

    def run() -> None:
        from pynput import keyboard
        print(f"[read-screen] hotkey: {spec}", flush=True)
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    threading.Thread(target=run, name="read-screen-hotkey", daemon=True).start()
