"""Tests for celestia_core/gpu.py — the GPU/model-residency manager."""

from __future__ import annotations

import threading

import pytest

import celestia_core.gpu as gpu


@pytest.fixture(autouse=True)
def _reset():
    # Ensure a clean lock state around each test.
    yield
    # If a test left the lock held on this thread, release defensively.
    try:
        gpu._gpu_lock.release()
    except RuntimeError:
        pass


def test_gpu_task_acquires_and_tracks_current() -> None:
    assert gpu.current_task() is None
    with gpu.gpu_task("vision") as got:
        assert got is True
        assert gpu.current_task() == "vision"
        assert gpu.gpu_busy() is True
    assert gpu.current_task() is None
    assert gpu.gpu_busy() is False


def test_gpu_task_reentrant_same_thread() -> None:
    with gpu.gpu_task("vision"):
        with gpu.gpu_task("stt", blocking=False) as got:
            assert got is True  # same thread re-enters the RLock
            assert gpu.current_task() == "stt"
        assert gpu.current_task() == "vision"  # restored on exit


def test_nonblocking_skips_when_held_by_other_thread() -> None:
    held = threading.Event()
    release = threading.Event()
    result: dict[str, bool] = {}

    def _holder():
        with gpu.gpu_task("vision"):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=_holder, daemon=True)
    t.start()
    assert held.wait(timeout=5)

    with gpu.gpu_task("graph-extract", blocking=False) as got:
        result["got"] = got

    assert result["got"] is False  # could not acquire — another thread holds it
    release.set()
    t.join(timeout=5)
    # Now free again.
    with gpu.gpu_task("late", blocking=False) as got:
        assert got is True


def test_blocking_waits_then_acquires() -> None:
    release = threading.Event()

    def _holder():
        with gpu.gpu_task("vision"):
            release.wait(timeout=5)

    t = threading.Thread(target=_holder, daemon=True)
    t.start()
    # Give the holder a moment to acquire, then release and confirm we can get it.
    release.set()
    t.join(timeout=5)
    with gpu.gpu_task("after", timeout=2) as got:
        assert got is True


def test_unload_model_no_ollama_is_safe(monkeypatch) -> None:
    import sys

    # Simulate ollama.generate raising — unload must swallow it.
    class _Boom:
        def generate(self, **kw):
            raise RuntimeError("no ollama")

    monkeypatch.setitem(sys.modules, "ollama", _Boom())
    gpu.unload_model("qwen2.5:7b")  # must not raise
    gpu.unload_model("")  # empty name → no-op


def test_loaded_models_parses_and_tolerates_errors(monkeypatch) -> None:
    import sys

    class _OK:
        def ps(self):
            return {"models": [{"name": "qwen2.5:7b"}, {"model": "moondream"}]}

    monkeypatch.setitem(sys.modules, "ollama", _OK())
    names = gpu.loaded_models()
    assert "qwen2.5:7b" in names

    class _Bad:
        def ps(self):
            raise RuntimeError("down")

    monkeypatch.setitem(sys.modules, "ollama", _Bad())
    assert gpu.loaded_models() == []
