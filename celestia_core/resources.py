"""Free GPU/RAM before heavy Ollama vision loads."""

from __future__ import annotations

import gc


def free_for_vision() -> None:
    """Unload voice models loaded during confirm (Orpheus + Whisper)."""
    try:
        from skills.tts.orpheus_local import force_unload

        force_unload()
    except Exception:
        pass
    try:
        from skills.stt.engine import force_unload

        force_unload()
    except Exception:
        pass
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    print("[vision] freed voice models for analysis")
