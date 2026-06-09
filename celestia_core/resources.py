"""Free GPU/RAM before heavy Ollama vision loads."""

from __future__ import annotations

import gc


def unload_ollama_model(name: str) -> None:
    """Ask Ollama to drop a model from VRAM now (keep_alive=0, empty prompt).

    No-op / harmless if the model isn't loaded or Ollama is unreachable.
    """
    if not name:
        return
    try:
        import ollama

        ollama.generate(model=name, prompt="", keep_alive=0)
    except Exception:
        pass


def free_for_vision() -> None:
    """Free VRAM before a vision load so the vision model does not stack on top
    of resident models and oversubscribe the GPU (which can hang the display
    driver). Unloads the voice models *and* the chat LLM.
    """
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

    # Critical: the chat model (e.g. qwen2.5:7b ~5 GB) lingers in VRAM for
    # Ollama's default keep_alive (5 min). Loading a 7-11B vision model on top
    # can exceed VRAM and freeze the desktop. Drop it first; it reloads on the
    # next chat turn.
    try:
        from celestia_core.config import get

        if get("vision.unload_chat_model", True):
            unload_ollama_model(str(get("llm.chat_model", "qwen2.5:7b")))
    except Exception:
        pass

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    print("[vision] freed voice + chat models for analysis")
