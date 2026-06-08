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
    idle_limit = _idle_minutes() * 60
    now = time.time()
    if (now - _last_used) < idle_limit:
        return
    with _lock:
        if _model is not None and (now - _last_used) >= idle_limit:
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


def _preprocess_audio(audio: "np.ndarray", sample_rate: int) -> "np.ndarray":  # type: ignore[name-defined]
    """
    Clean up microphone audio before Whisper transcription.

    Steps (all pure numpy/scipy, no extra deps):
    1. High-pass filter at 80 Hz  — removes AC hum, low-frequency rumble and
       keyboard noise that would otherwise cause Whisper hallucinations.
    2. Noise gate                 — silence frames whose RMS is below a
       threshold; prevents Whisper from "hearing" background hiss.
    3. Peak normalise to 0.95    — ensures Whisper always receives a
       consistent loudness regardless of mic gain setting.
    """
    import numpy as np

    # ── 1. High-pass filter ──────────────────────────────────────────────────
    try:
        from scipy.signal import butter, sosfilt

        sos = butter(4, 80.0, btype="high", fs=sample_rate, output="sos")
        audio = sosfilt(sos, audio).astype(np.float32)
    except ImportError:
        pass  # scipy not installed — skip filter but still apply gate+norm

    # ── 2. Noise gate (25 ms frames) ────────────────────────────────────────
    frame_len = max(1, int(sample_rate * 0.025))
    gate_threshold = float(get("voice.stt.noise_gate_threshold", 0.005))
    if gate_threshold > 0:
        for start in range(0, len(audio) - frame_len, frame_len):
            frame = audio[start : start + frame_len]
            if np.sqrt(np.mean(frame ** 2)) < gate_threshold:
                audio[start : start + frame_len] = 0.0

    # ── 3. Peak normalise ────────────────────────────────────────────────────
    peak = float(np.max(np.abs(audio)))
    if peak > 0.01:
        audio = audio * (0.95 / peak)

    return audio


def transcribe_file(path: str) -> str:
    _touch()
    model = _load()
    vad = get("voice.stt.vad_filter", False)
    segments, _ = model.transcribe(path, vad_filter=bool(vad))
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
    """Record from the mic until stop_event is set or max_seconds elapses.

    CC-97: also auto-stops after voice.stt.silence_stop_seconds of silence
    once at least 1 s of audio has been recorded, so the user doesn't need
    to hold PTT for the full max_seconds after finishing speaking.
    """
    import queue

    import numpy as np
    import sounddevice as sd

    silence_stop = float(get("voice.stt.silence_stop_seconds", 1.5))
    gate_threshold = float(get("voice.stt.noise_gate_threshold", 0.005))

    print("[stt] listening… (release to send)")
    chunks: list = []
    q: queue.Queue = queue.Queue()

    def callback(indata, _frames, _time, status) -> None:
        if status:
            print(f"[stt] {status}")
        q.put(indata.copy())

    block = int(sample_rate * 0.1)  # 100 ms blocks
    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        blocksize=block,
        callback=callback,
    )
    started = time.time()
    silence_since: float | None = None  # timestamp when silence started
    stream.start()
    try:
        while not stop_event.is_set():
            elapsed = time.time() - started
            if elapsed >= max_seconds:
                break
            try:
                chunk = q.get(timeout=0.08)
            except queue.Empty:
                continue
            chunks.append(chunk)

            # Energy-based silence detection — only kicks in after min 1 s
            if elapsed >= 1.0 and silence_stop > 0:
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                now = time.time()
                if rms < gate_threshold:
                    if silence_since is None:
                        silence_since = now
                    elif (now - silence_since) >= silence_stop:
                        break  # auto-stop: enough silence after speech
                else:
                    silence_since = None  # speech detected, reset
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
    audio = _preprocess_audio(audio, sample_rate)
    audio_i16 = (np.clip(audio, -1.0, 1.0) * 32767).astype("int16")

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
