from __future__ import annotations

import requests

from celestia_core.config import ROOT, get, load_config
from pathlib import Path


def check_ollama() -> tuple[bool, str]:
    host = get("llm.host", "http://127.0.0.1:11434").rstrip("/")
    model = get("llm.chat_model", "llama3.2:3b")
    embed = get("llm.embed_model", "nomic-embed-text")
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        missing = []
        for want in (model, embed):
            base = want.split(":")[0]
            if not any(base in n for n in names):
                missing.append(want)
        if missing:
            return False, f"Ollama OK but missing: {', '.join(missing)} — ollama pull ..."
        return True, f"Ollama OK — {model}, {embed}"
    except requests.RequestException as e:
        return False, f"Ollama not reachable at {host} — {e}"


def check_memory() -> tuple[bool, str]:
    if not get("memory.enabled", True):
        return True, "Memory disabled in config"
    backend = get("memory.vector_store", "chroma").lower()
    if backend == "chroma":
        rel = get("memory.chroma.path", "data/chroma")
        path = Path(rel) if Path(rel).is_absolute() else Path(ROOT) / rel
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True, f"Memory: Chroma (local, no Docker) at {path}"
        except OSError as e:
            return False, f"Chroma path not writable: {e}"
    host = get("memory.qdrant.host", "localhost")
    port = get("memory.qdrant.port", get("docker.qdrant_port", 6333))
    try:
        r = requests.get(f"http://{host}:{port}/collections", timeout=5)
        if r.status_code == 200:
            return True, f"Memory: Qdrant at {host}:{port}"
        return False, f"Qdrant returned {r.status_code}"
    except requests.RequestException as e:
        return False, f"Qdrant not reachable — docker compose up -d qdrant ({e})"


def check_voice() -> tuple[bool, str]:
    if not get("voice.stt.enabled", False) and get("voice.tts.provider", "") != "orpheus":
        return True, "Voice: text-only mode"
    parts = []
    if get("voice.stt.enabled", False):
        parts.append("STT on")
    tts = get("voice.tts.provider", "edge")
    parts.append(f"TTS={tts}")
    if tts == "orpheus":
        backend = get("voice.tts.orpheus.backend", "local").lower()
        if backend == "local":
            try:
                import llama_cpp  # noqa: F401
                from skills.tts.orpheus_local import _find_gguf

                parts.append(f"Orpheus local OK — {_find_gguf().name}")
            except ImportError:
                return False, "llama-cpp-python missing — pip install llama-cpp-python (see scripts/setup.ps1)"
            except Exception as e:
                return False, f"Orpheus local: {e}"
        else:
            parts.append("Orpheus external backend (LM Studio / FastAPI)")
    return True, "Voice: " + ", ".join(parts)


def check_vision() -> tuple[bool, str]:
    if not get("vision.enabled", False):
        return True, "Vision disabled in config"
    host = get("llm.host", "http://127.0.0.1:11434").rstrip("/")
    want = []
    for key in ("llm.vision_model", "vision.text_model", "llm.vision_text_model"):
        m = get(key, "")
        if m and m not in want:
            want.append(m)
    if not want:
        want = ["llama3.2-vision:11b"]
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        missing = []
        for model in want:
            base = model.split(":")[0]
            if not any(base in n for n in names):
                missing.append(model)
        if missing:
            return False, f"Missing vision models — ollama pull {' '.join(missing)}"
        return True, f"Vision OK — {', '.join(want)}"
    except requests.RequestException as e:
        return False, f"Ollama not reachable for vision: {e}"


def check_security() -> tuple[bool, str]:
    from celestia_core import security

    personality = get("personality.active", "default")
    return True, f"Security: {security.armed_status_label()} (shared) | personality={personality}"


def run_checks() -> bool:
    load_config()
    ok = True
    checks = [check_ollama, check_memory, check_security, check_voice]
    if get("vision.enabled", False):
        checks.append(check_vision)
    for fn in checks:
        passed, msg = fn()
        tag = "ok" if passed else "FAIL"
        print(f"[{tag}] {msg}")
        if not passed:
            ok = False
    return ok
