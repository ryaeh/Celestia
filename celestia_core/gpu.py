"""Central GPU / model-residency control (Feature 11 substrate).

Serialises heavy GPU operations behind one process-wide lock so vision, STT,
background graph-extraction, and chat never load models concurrently and
oversubscribe VRAM (which can hang the Windows display driver). Also centralises
Ollama residency helpers.

Usage
-----
Foreground op (wait for the GPU)::

    with gpu_task("vision"):
        run_vision_model(...)

Background op (skip if the GPU is busy)::

    with gpu_task("graph-extract", blocking=False) as got:
        if not got:
            return  # something more important is using the GPU
        run_extraction(...)

Feature 11 (operating modes) sets policy on top of this — which models may be
resident and their keep_alive budgets; this module enforces serialisation.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

# Re-entrant so a heavy op can nest helper calls on the same thread without
# self-deadlocking. One lock = one GPU; cross-process coordination is left to
# Ollama's own request queue.
_gpu_lock = threading.RLock()

_state_lock = threading.Lock()
_current: str | None = None


def current_task() -> str | None:
    """Name of the GPU task currently holding the lock, or None if idle."""
    with _state_lock:
        return _current


def gpu_busy() -> bool:
    return current_task() is not None


@contextmanager
def gpu_task(
    name: str, *, blocking: bool = True, timeout: float | None = None
) -> Iterator[bool]:
    """Acquire exclusive GPU access for a heavy op.

    blocking=True  -> wait for the GPU (foreground: vision, STT).
    blocking=False -> skip if busy, yielding False (background: graph extract).

    Yields True if the lock was acquired (and is held for the block), else False.
    """
    global _current
    if blocking:
        acquired = _gpu_lock.acquire(timeout=-1 if timeout is None else timeout)
    else:
        acquired = _gpu_lock.acquire(blocking=False)

    if not acquired:
        yield False
        return

    with _state_lock:
        prev = _current
        _current = name
    try:
        yield True
    finally:
        with _state_lock:
            _current = prev
        _gpu_lock.release()


def unload_model(name: str) -> None:
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


def loaded_models() -> list[str]:
    """Names of models currently resident in Ollama (for diagnostics / a future
    GPU-status indicator). Returns [] if Ollama is unreachable.
    """
    try:
        import ollama

        ps = ollama.ps()
        models = ps.get("models", []) if isinstance(ps, dict) else getattr(ps, "models", [])
        out: list[str] = []
        for m in models or []:
            name = m.get("name") or m.get("model") if isinstance(m, dict) else getattr(m, "name", None)
            if name:
                out.append(name)
        return out
    except Exception:
        return []
