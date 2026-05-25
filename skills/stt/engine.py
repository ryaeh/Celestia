from __future__ import annotations

import threading
import time

from celestia_core.config import get

_model = None
_lock = threading.Lock()
_last_used = 0.0


def _idle_minutes() -> float:
    return float(get("voice.stt.idle_unload_minutes", 10))


def _touch():
    global _last_used
    _last_used = time.time()


def force_unload() -> None:
    global _model, _last_used
    with _lock:
        if _model is not None:
            print("[stt] unloading whisper")
            _model = None
        _last_used = 0.0
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _maybe_unload():
    global _model, _last_used
    if _model is None:
        return
    if (time.time() - _last_used) < _idle_minutes() * 60:
        return
    with _lock:
        if _model is not None and (time.time() - _last_used) >= _idle_minutes() * 60:
            _model = None
            print("[stt] model unloaded (idle)")


def _load():
    global _model
    with _lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        device = get("voice.stt.device", "cuda")
        compute = get("voice.stt.compute_type", "float16")
        name = get("voice.stt.model", "large-v3")
        print(f"[stt] loading {name} on {device}...")
        _model = WhisperModel(name, device=device, compute_type=compute)
        print("[stt] ready")
        return _model


def transcribe_file(path: str) -> str:
    _touch()
    model = _load()
    segments, _ = model.transcribe(path)
    text = " ".join(s.text.strip() for s in segments).strip()
    _touch()
    return text


def record_ptt_until(
    stop_event: threading.Event,
    *,
    max_seconds: float = 45.0,
    sample_rate: int = 16000,
    min_seconds: float = 0.35,
) -> str:
    """Record from the mic until stop_event is set or max_seconds elapses."""
    import queue

    import numpy as np
    import sounddevice as sd

    print("[stt] listening… (release to send)")
    chunks: list = []
    q: queue.Queue = queue.Queue()

    def callback(indata, _frames, _time, status) -> None:
        if status:
            print(f"[stt] {status}")
        q.put(indata.copy())

    block = int(sample_rate * 0.1)
    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        blocksize=block,
        callback=callback,
    )
    started = time.time()
    stream.start()
    try:
        while not stop_event.is_set():
            if time.time() - started >= max_seconds:
                break
            try:
                chunks.append(q.get(timeout=0.08))
            except queue.Empty:
                pass
    finally:
        stream.stop()
        stream.close()

    elapsed = time.time() - started
    if elapsed < min_seconds:
        print("[stt] too short — hold a little longer")
        _maybe_unload()
        return ""

    if not chunks:
        _maybe_unload()
        return ""

    import os
    import tempfile
    import wave

    audio = np.concatenate(chunks, axis=0).flatten()
    audio_i16 = (audio * 32767).astype("int16")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = f.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_i16.tobytes())

    try:
        print(f"[stt] transcribing ({elapsed:.1f}s)…")
        return transcribe_file(path)
    finally:
        os.unlink(path)
        _maybe_unload()


def record_and_transcribe(seconds: float = 5.0, sample_rate: int = 16000) -> str:
    import numpy as np
    import sounddevice as sd
    import wave
    import tempfile
    import os

    print(f"[stt] recording {seconds}s — speak now...")
    audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    audio = (audio.flatten() * 32767).astype("int16")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = f.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())

    try:
        return transcribe_file(path)
    finally:
        os.unlink(path)
        _maybe_unload()
