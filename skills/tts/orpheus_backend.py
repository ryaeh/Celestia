from __future__ import annotations

import subprocess
import time
from pathlib import Path

import requests

from celestia_core.config import ROOT, get

_fastapi_proc: subprocess.Popen | None = None
_last_used = 0.0


def _fastapi_dir() -> Path:
    for name in ("Orpheus-FastAPI", "legacy/Orpheus-FastAPI"):
        p = Path(ROOT) / name
        if (p / "app.py").exists():
            return p
    raise FileNotFoundError("Orpheus-FastAPI folder not found")


def _idle_minutes() -> float:
    return float(get("voice.tts.orpheus.idle_shutdown_minutes", 5))


def _api_up() -> bool:
    try:
        r = requests.get("http://127.0.0.1:5006/v1/audio/voices", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


def ensure_fastapi() -> bool:
    global _fastapi_proc
    if _api_up():
        return True

    mode = get("voice.tts.orpheus.mode", "on_demand")
    if mode == "lmstudio_manual":
        if not _lm_studio_up():
            print("[tts] Load Orpheus in LM Studio, start server :1234, then Orpheus-FastAPI on :5006")
            return False

    if mode not in ("on_demand", "lmstudio_manual"):
        return False

    print("[tts] starting Orpheus-FastAPI (first run may take a minute)...")
    import sys

    py = sys.executable
    cwd = _fastapi_dir()
    _fastapi_proc = subprocess.Popen(
        [py, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "5006"],
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    for _ in range(120):
        if _api_up():
            print("[tts] Orpheus-FastAPI ready on :5006")
            return True
        time.sleep(1)
    print("[tts] Orpheus-FastAPI failed to start")
    return False


def _lm_studio_up() -> bool:
    try:
        r = requests.get("http://127.0.0.1:1234/v1/models", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


def stop_if_idle():
    global _fastapi_proc, _last_used
    if _fastapi_proc is None:
        return
    if (time.time() - _last_used) < _idle_minutes() * 60:
        return
    if _fastapi_proc.poll() is None:
        _fastapi_proc.terminate()
        try:
            _fastapi_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _fastapi_proc.kill()
    _fastapi_proc = None
    print("[tts] Orpheus-FastAPI stopped (idle)")


def synthesize_wav(text: str) -> bytes:
    global _last_used
    if not ensure_fastapi():
        raise RuntimeError("Orpheus TTS unavailable")
    voice = get("voice.tts.voice", "tara")
    r = requests.post(
        "http://127.0.0.1:5006/v1/audio/speech",
        json={"input": text, "voice": voice},
        timeout=600,
    )
    r.raise_for_status()
    _last_used = time.time()
    return r.content
