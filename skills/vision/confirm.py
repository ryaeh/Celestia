from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from celestia_core.config import ROOT, get
from skills.vision.preview import open_preview


def _audit(event: str, **fields):
    rel = get("vision.audit_log", "logs/vision_audit.jsonl")
    path = Path(rel) if Path(rel).is_absolute() else Path(ROOT) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _confirm_mode() -> str:
    return get("vision.confirm_mode", "text").lower()


def _play_confirm_tts(prompt: str) -> None:
    try:
        from skills.tts.edge_backend import play_prompt

        play_prompt(prompt, wait_seconds=4.0)
    except Exception as e:
        print(f"[vision] confirm audio skipped: {e}")


def _text_confirm() -> bool:
    while True:
        ans = input("[vision] Send screenshot to AI? (yes/no): ").strip().lower()
        if ans in ("y", "yes", "ok", "send"):
            return True
        if ans in ("n", "no", "cancel"):
            return False
        print("Type yes or no.")


def _voice_confirm() -> bool | None:
    try:
        from skills.stt import record_and_transcribe

        print("[vision] Say yes or no (3s)...")
        text = record_and_transcribe(seconds=3.0).lower()
        if any(w in text for w in ("yes", "confirm", "yeah", "yep", "send", "ok")):
            return True
        if any(w in text for w in ("no", "cancel", "stop", "don't", "dont")):
            return False
        print(f"[vision] Heard: '{text}' — not clear.")
    except Exception as e:
        print(f"[vision] voice confirm failed: {e}")
    return None


def confirm_send(image_path: Path, mode: str) -> bool:
    if not get("vision.confirm_before_send", True):
        _audit("send_auto", mode=mode, image=str(image_path.name))
        return True

    prompt = get(
        "vision.tts_confirm_prompt",
        "Do you want me to send this screenshot for analysis?",
    )
    mode_confirm = _confirm_mode()
    if get("vision.allow_voice_confirm", False) and mode_confirm == "text":
        mode_confirm = "voice_or_text"
    print(f"[vision] {prompt}")
    print(f"[vision] Preview: {image_path}")

    preview = open_preview(image_path)
    try:
        _play_confirm_tts(prompt)

        if mode_confirm == "voice":
            voice = _voice_confirm()
            from skills.stt.engine import force_unload

            force_unload()
            if voice is None:
                print("[vision] Falling back to typing yes/no.")
                ok = _text_confirm()
            else:
                ok = voice
            _audit("confirm_voice", mode=mode, approved=ok)
            return ok

        if mode_confirm == "voice_or_text":
            voice = _voice_confirm()
            if voice is not None:
                from skills.stt.engine import force_unload

                force_unload()
                _audit("confirm_voice", mode=mode, approved=voice)
                return voice
            ok = _text_confirm()
            _audit("confirm_text_fallback", mode=mode, approved=ok)
            return ok

        ok = _text_confirm()
        _audit("confirm_text", mode=mode, approved=ok)
        return ok
    finally:
        if preview is not None:
            preview.close()
