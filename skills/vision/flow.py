from __future__ import annotations

from pathlib import Path

from celestia_core.config import get
from skills.vision import analyze, capture, confirm, selector


def parse_screen_command(line: str) -> tuple[str | None, str]:
    """
    Parse REPL/tray line like 'screen fullscreen read text'.
    Returns (mode, question). mode None = use vision.default_mode from config.
    """
    low = line.strip().lower()
    if low == "screen":
        return None, ""
    if not low.startswith("screen "):
        return None, line.strip()

    rest = line.strip()[7:].strip()
    if not rest:
        return None, ""

    aliases = {
        "window": "active_window",
        "active": "active_window",
        "full": "fullscreen",
        "fullscreen": "fullscreen",
        "region": "region",
        "active_window": "active_window",
    }
    parts = rest.split(maxsplit=1)
    first = parts[0].lower()
    if first in aliases:
        mode = aliases[first]
        question = parts[1].strip() if len(parts) > 1 else ""
        return mode, question
    return None, rest


def run_screen_ask(
    question: str,
    *,
    mode: str | None = None,
    speak: bool = True,
) -> str:
    if not get("vision.enabled", True):
        raise RuntimeError("Vision disabled in config.yaml")

    mode = (mode or get("vision.default_mode", "region")).lower()
    question = question.strip() or input("What should I look for on screen? ").strip()
    if not question:
        raise ValueError("No question provided")

    capture.cleanup_old_files()
    image_path: Path

    print(f"[vision] capture mode: {mode}")
    if mode == "fullscreen":
        image_path = capture.capture_fullscreen()
    elif mode == "active_window":
        image_path = capture.capture_active_window()
    else:
        x, y, w, h = selector.select_region()
        image_path = capture.capture_bbox(x, y, w, h)

    if not confirm.confirm_send(image_path, mode):
        print("[vision] Cancelled — image not sent.")
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            pass
        return "Cancelled."

    try:
        answer = analyze.analyze_image(image_path, question)
        print(f"\n[vision]\n{answer}\n")
        if speak:
            try:
                from skills.tts import speak as tts_speak

                # Speak the short tail if long; full text otherwise
                spoken = answer
                if len(answer) > 600 and "summary" in answer.lower():
                    parts = answer.split("\n")
                    spoken = parts[-1] if parts else answer[-600:]
                tts_speak(spoken[:800])
            except Exception as e:
                print(f"[warn] TTS: {e}")
        return answer
    finally:
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            pass
        capture.cleanup_old_files()
