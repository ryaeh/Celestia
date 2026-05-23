"""
Orpheus TTS fully inside Atlas — no LM Studio, no uvicorn.
Uses llama-cpp-python (GGUF on GPU) + Orpheus-FastAPI tts_engine (SNAC decode only).
"""

from __future__ import annotations

import contextlib
import gc
import io
import os
import sys
import threading
import time
from pathlib import Path
from typing import Generator

from celestia_core.config import ROOT, get

_llama = None
_lock = threading.Lock()
_last_used = 0.0
_engine = None


def _idle_minutes() -> float:
    return float(get("voice.tts.orpheus.idle_shutdown_minutes", 5))


def _find_gguf() -> Path:
    rel = get("voice.tts.orpheus.model_gguf", "models/Orpheus-3b-FT-Q8_0.gguf")
    candidates = [
        Path(ROOT) / rel,
        Path(ROOT) / "Orpheus-FastAPI" / "models" / Path(rel).name,
        Path(ROOT) / "models" / Path(rel).name,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Orpheus GGUF not found. Put model in atlas/models/ or Orpheus-FastAPI/models/. "
        f"Run: .\\scripts\\setup.ps1"
    )


def _load_llama():
    global _llama
    with _lock:
        if _llama is not None:
            return _llama
        from llama_cpp import Llama

        path = _find_gguf()
        n_gpu = int(get("voice.tts.orpheus.n_gpu_layers", -1))
        n_ctx = int(get("voice.tts.orpheus.n_ctx", 8192))
        print(f"[tts] loading Orpheus GGUF on GPU: {path.name}...")
        _llama = Llama(
            model_path=str(path),
            n_gpu_layers=n_gpu,
            n_ctx=n_ctx,
            verbose=False,
        )
        print("[tts] Orpheus LLM ready (in-process)")
        return _llama


def _import_orpheus_engine():
    global _engine
    if _engine is not None:
        return _engine

    orp = Path(ROOT) / "Orpheus-FastAPI"
    if not orp.exists():
        raise FileNotFoundError("Orpheus-FastAPI folder required for SNAC audio decoder")

    os.environ.setdefault("ORPHEUS_API_URL", "http://127.0.0.1:1/v1/completions")
    os.environ.setdefault("ORPHEUS_MAX_TOKENS", str(get("voice.tts.orpheus.n_ctx", 8192)))
    os.environ["UVICORN_STARTED"] = "true"

    if str(orp) not in sys.path:
        sys.path.insert(0, str(orp))

    from tts_engine.inference import (
        REPETITION_PENALTY,
        TEMPERATURE,
        TOP_P,
        format_prompt,
        tokens_decoder_sync,
    )

    _engine = {
        "format_prompt": format_prompt,
        "tokens_decoder_sync": tokens_decoder_sync,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "repetition_penalty": REPETITION_PENALTY,
        "max_tokens": int(get("voice.tts.orpheus.max_tokens", 4096)),
    }
    return _engine


def _local_token_stream(prompt: str, voice: str) -> Generator[str, None, None]:
    eng = _import_orpheus_engine()
    llm = _load_llama()
    formatted = eng["format_prompt"](prompt, voice)
    print(f"[tts] generating tokens for: {formatted[:80]}...")

    stream = llm(
        formatted,
        max_tokens=eng["max_tokens"],
        temperature=eng["temperature"],
        top_p=eng["top_p"],
        repeat_penalty=eng["repetition_penalty"],
        stream=True,
    )
    for chunk in stream:
        text = chunk["choices"][0].get("text", "")
        if not text:
            continue
        for part in text.split(">"):
            if part:
                yield f"{part}>"


def force_unload() -> None:
    global _llama, _last_used
    with _lock:
        if _llama is not None:
            print("[tts] unloading Orpheus LLM")
            del _llama
            _llama = None
        _last_used = 0.0
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def unload_if_idle():
    global _llama, _last_used
    if _llama is None:
        return
    if (time.time() - _last_used) < _idle_minutes() * 60:
        return
    with _lock:
        if _llama is not None and (time.time() - _last_used) >= _idle_minutes() * 60:
            print("[tts] unloading Orpheus LLM (idle)")
            del _llama
            _llama = None
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass


def synthesize_wav(text: str) -> bytes:
    global _last_used
    # Fail before SNAC async thread if LLM cannot load
    _load_llama()
    eng = _import_orpheus_engine()
    voice = get("voice.tts.voice", "tara")
    out_dir = Path(ROOT) / "outputs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "celestia_last_reply.wav"

    # Orpheus inference prints emoji; Windows console (cp1254) can crash TTS
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
        io.StringIO()
    ):
        eng["tokens_decoder_sync"](
            _local_token_stream(text, voice),
            output_file=str(out_path),
        )
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError("Orpheus produced empty or invalid audio")

    _last_used = time.time()
    unload_if_idle()
    return out_path.read_bytes()
