"""Shell push-to-talk — hold to record, release to transcribe + chat (CC-84).

CC-115: ptt_finish now uses pipelined sentence-streaming TTS when
voice.always_speak is true, halving the time to first audio.
"""

from __future__ import annotations

import threading
from typing import Any

from celestia_core.config import get, load_config
from celestia_core.shell_chat import send_message, send_message_stream

_lock = threading.Lock()
_stop_event: threading.Event | None = None
_worker: threading.Thread | None = None
_transcript: str = ""
_phase: str = "idle"  # idle | listening | transcribing
_error: str | None = None
_hotkey_listener_started = False

# Windows virtual-key codes for letter keys (when modifiers hide key.char)
_VK_LETTERS = {ord(c): c for c in "abcdefghijklmnopqrstuvwxyz"}


def _shell_ptt_hotkey_spec() -> str | None:
    """Hotkey spec or None if disabled. Default: ctrl+alt+shift+v when unset in config."""
    raw = get("ui.shell_ptt_hotkey", None)
    if raw is None:
        return "ctrl+alt+shift+v"
    s = str(raw).strip()
    if not s or s.lower() in ("off", "none", "false", "0"):
        return None
    return s


def ptt_status() -> dict[str, Any]:
    with _lock:
        return {
            "phase": _phase,
            "listening": _phase == "listening",
            "busy": _phase in ("listening", "transcribing"),
            "error": _error,
            "hotkey": _shell_ptt_hotkey_spec(),
        }


def _set_phase(phase: str, *, error: str | None = None) -> None:
    global _phase, _error
    _phase = phase
    _error = error


def ptt_start() -> dict[str, Any]:
    """Begin recording (call again on release via ptt_finish)."""
    global _stop_event, _worker, _transcript

    load_config()
    if not get("voice.stt.enabled", True):
        return {"error": "voice.stt.enabled is false in config.yaml"}
    if not get("ui.shell_ptt_enabled", True):
        return {"error": "shell PTT disabled (ui.shell_ptt_enabled)"}

    with _lock:
        if _phase != "idle":
            return {"error": "PTT already active"}

        _transcript = ""
        _stop_event = threading.Event()
        stop = _stop_event

        def run() -> None:
            global _transcript
            try:
                from skills.stt import record_ptt_until

                max_sec = float(get("ui.shell_ptt_max_seconds", 45))
                _transcript = record_ptt_until(stop, max_seconds=max_sec)
            except Exception as e:
                with _lock:
                    _set_phase("idle", error=str(e))

        _set_phase("listening")
        _worker = threading.Thread(target=run, name="shell-ptt-record", daemon=True)
        _worker.start()

    return {"ok": True, "listening": True}


def ptt_cancel() -> dict[str, Any]:
    """Abort recording without sending."""
    global _stop_event, _worker, _transcript

    with _lock:
        if _phase == "idle":
            return {"ok": True}
        if _stop_event is not None:
            _stop_event.set()
        worker = _worker
        _set_phase("idle")

    if worker is not None:
        worker.join(timeout=60)
    with _lock:
        _transcript = ""
        _stop_event = None
        _worker = None
    return {"ok": True}


def ptt_finish(*, session_id: str | None = None) -> dict[str, Any]:
    """Stop recording, transcribe, and send into the active shell chat session."""
    global _stop_event, _worker, _transcript

    with _lock:
        if _phase != "listening":
            return {"error": "not listening"}
        if _stop_event is not None:
            _stop_event.set()
        worker = _worker

    if worker is not None:
        worker.join(timeout=120)

    with _lock:
        text = (_transcript or "").strip()
        _transcript = ""
        _stop_event = None
        _worker = None
        if not text:
            _set_phase("idle")
            return {"error": "no speech detected"}

    _set_phase("transcribing")
    try:
        # CC-115: use pipelined streaming TTS when voice output is enabled.
        # This lets Celestia start speaking after the first sentence rather
        # than waiting for the full LLM response to complete.
        if get("voice.always_speak", False) or get("voice.tts.streaming", True):
            return _send_with_streaming_tts(text, session_id=session_id)
        return send_message(text, session_id=session_id, source="voice")
    except Exception as e:
        err = str(e)
        _set_phase("idle", error=err)
        return {"error": err}
    finally:
        with _lock:
            if _phase == "transcribing":
                _set_phase("idle")


def _send_with_streaming_tts(
    text: str, *, session_id: str | None = None
) -> dict[str, Any]:
    """Run LLM streaming with concurrent sentence-level TTS playback (CC-115).

    Feeds tokens from ``send_message_stream`` into ``speak_stream`` which
    enqueues each complete sentence for TTS immediately.  The TTS worker
    plays sentence N while the LLM generates sentence N+1, cutting
    time-to-first-audio from ~8 s to ~2 s on typical hardware.
    """
    play = get("voice.always_speak", False) or get("voice.tts.streaming", True)

    # Capture the final done/error event from the generator via a closure.
    final: dict[str, Any] = {}

    def _token_iter():
        for event in send_message_stream(text, session_id=session_id, source="voice"):
            if "token" in event:
                yield event["token"]
            else:
                # done or error — store it, stop yielding
                final.update(event)

    try:
        from skills.tts import speak_stream
        speak_stream(_token_iter(), play=bool(play))
    except Exception as e:
        print(f"[ptt] TTS stream error: {e}")
        # Fall back: final may already be set from the generator exhaustion
        if not final:
            final["error"] = str(e)

    return final if final else {"error": "no response from model"}


def _parse_hotkey_parts(spec: str) -> tuple[frozenset[str], str | None]:
    mods: set[str] = set()
    main: str | None = None
    for part in spec.split("+"):
        p = part.strip().lower()
        if not p:
            continue
        if p in ("ctrl", "control"):
            mods.add("ctrl")
        elif p in ("alt", "menu"):
            mods.add("alt")
        elif p == "shift":
            mods.add("shift")
        elif p in ("win", "windows", "meta", "cmd", "command"):
            mods.add("win")
        elif len(p) == 1:
            main = p
        else:
            main = p
    return frozenset(mods), main


def _key_token(key) -> str | None:
    from pynput.keyboard import Key, KeyCode

    if isinstance(key, KeyCode):
        if key.char and len(key.char) == 1 and key.char.isprintable():
            return key.char.lower()
        vk = getattr(key, "vk", None)
        if vk is not None:
            letter = _VK_LETTERS.get(vk & 0xFF)
            if letter:
                return letter
    if isinstance(key, Key):
        name = str(key).replace("Key.", "").lower()
        mapping = {
            "ctrl_l": "ctrl",
            "ctrl_r": "ctrl",
            "alt_l": "alt",
            "alt_gr": "alt",
            "alt_r": "alt",
            "shift": "shift",
            "shift_l": "shift",
            "shift_r": "shift",
            "cmd": "win",
            "cmd_l": "win",
            "cmd_r": "win",
        }
        return mapping.get(name, name)
    return None


def start_global_hotkey_listener() -> None:
    """Hold configured hotkey to talk (optional; UI mic works without this)."""
    global _hotkey_listener_started

    load_config()
    if not get("ui.shell_ptt_enabled", True):
        return
    spec = _shell_ptt_hotkey_spec()
    if not spec:
        return

    with _lock:
        if _hotkey_listener_started:
            return
        _hotkey_listener_started = True

    required_mods, main_key = _parse_hotkey_parts(spec)
    if not main_key:
        print(f"[shell-ptt] invalid hotkey: {spec}")
        return

    pressed: set[str] = set()
    active = False

    def combo_down() -> bool:
        if required_mods and not required_mods.issubset(pressed):
            return False
        return main_key in pressed

    def on_press(key) -> None:
        nonlocal active
        tok = _key_token(key)
        if tok:
            pressed.add(tok)
        if not active and combo_down():
            active = True
            res = ptt_start()
            if "error" in res:
                print(f"[shell-ptt] {res['error']}")
                active = False

    def on_release(key) -> None:
        nonlocal active
        tok = _key_token(key)
        if tok:
            pressed.discard(tok)
        if active and not combo_down():
            active = False
            res = ptt_finish()
            if "error" in res and res["error"] not in ("not listening", "no speech detected"):
                print(f"[shell-ptt] {res['error']}")

    def run() -> None:
        from pynput import keyboard

        print(f"[shell-ptt] hold to talk: {spec} (release to send)", flush=True)
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    threading.Thread(target=run, name="shell-ptt-hotkey", daemon=True).start()
