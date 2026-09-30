"""Companion overlay bubble — server side (the bubble itself is a Tauri window).

The bubble is a second, always-on-top Tauri window (``?view=overlay``). It
mirrors ``/ws/state``, so the server only needs to publish two things:

* ``overlay_seq`` — a counter bumped by :func:`request_toggle` (global hotkey
  ``ui.overlay_hotkey`` or ``POST /overlay/toggle``, e.g. from the tray). The
  overlay window watches it and shows/hides itself on each change, which works
  even while the main window is hidden.
* ``busy`` — whether any chat turn / vision op is running (the Aura "thinking"
  state), from :mod:`celestia_core.stream_cancel`.
"""

from __future__ import annotations

import threading

from celestia_core.config import get, load_config

_lock = threading.Lock()
_seq = 0
_listener_started = False


def toggle_seq() -> int:
    with _lock:
        return _seq


def request_toggle() -> int:
    """Ask the overlay window to flip visibility. Returns the new sequence."""
    global _seq
    with _lock:
        _seq += 1
        return _seq


def _hotkey_spec() -> str | None:
    if not get("ui.overlay_enabled", True):
        return None
    raw = str(get("ui.overlay_hotkey", "ctrl+alt+o") or "").strip()
    return raw or None


def start_overlay_hotkey_listener() -> None:
    """Register the global show/hide-bubble hotkey (pynput). Called at shell start."""
    global _listener_started

    load_config()
    spec = _hotkey_spec()
    if not spec:
        return
    with _lock:
        if _listener_started:
            return
        _listener_started = True

    from celestia_core.shell_ptt import _key_token, _parse_hotkey_parts

    required_mods, main_key = _parse_hotkey_parts(spec)
    if not main_key:
        print(f"[overlay] invalid hotkey spec: {spec}", flush=True)
        return

    pressed: set[str] = set()
    fired = False

    def on_press(key) -> None:
        nonlocal fired
        tok = _key_token(key)
        if tok:
            pressed.add(tok)
        if fired or (required_mods and not required_mods.issubset(pressed)):
            return
        if main_key in pressed:
            fired = True  # one toggle per press, not per key-repeat
            request_toggle()

    def on_release(key) -> None:
        nonlocal fired
        tok = _key_token(key)
        if tok:
            pressed.discard(tok)
        if fired and main_key not in pressed:
            fired = False

    def run() -> None:
        from pynput import keyboard
        print(f"[overlay] bubble hotkey: {spec}", flush=True)
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    threading.Thread(target=run, name="overlay-hotkey", daemon=True).start()
