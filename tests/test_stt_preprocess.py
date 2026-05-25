"""Tests for STT audio preprocessing (force_unload, _preprocess_audio).

These tests run offline — no Whisper model loaded, no microphone required.
"""
from __future__ import annotations

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# _preprocess_audio
# ---------------------------------------------------------------------------

def _import_preprocess():
    from skills.stt.engine import _preprocess_audio
    return _preprocess_audio


def test_preprocess_returns_same_length():
    """Output array must have same length as input."""
    preprocess = _import_preprocess()
    data = np.random.uniform(-0.1, 0.1, 16000).astype(np.float32)
    out = preprocess(data, 16000)
    assert len(out) == len(data)


def test_preprocess_normalises_loud_signal():
    """Peak normalisation should bring a loud signal below ≈ 1.0."""
    preprocess = _import_preprocess()
    data = np.ones(4096, dtype=np.float32) * 3.0  # amplitude > 1
    out = preprocess(data, 16000)
    assert np.max(np.abs(out)) <= 1.0 + 1e-6


def test_preprocess_preserves_loud_frames():
    """A reasonably loud signal must survive without being zeroed."""
    preprocess = _import_preprocess()
    data = np.ones(4096, dtype=np.float32) * 0.5
    out = preprocess(data, 16000)
    assert np.any(out != 0.0)


def test_preprocess_output_dtype():
    preprocess = _import_preprocess()
    data = np.random.uniform(-0.1, 0.1, 8000).astype(np.float32)
    out = preprocess(data, 16000)
    assert out.dtype == np.float32


# ---------------------------------------------------------------------------
# force_unload
# ---------------------------------------------------------------------------

def test_force_unload_clears_model():
    """force_unload should set the global model to None."""
    import skills.stt.engine as eng
    eng._model = object()
    from skills.stt.engine import force_unload
    force_unload()
    assert eng._model is None
