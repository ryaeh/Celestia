"""Tests for the vision-analysis cancel path (UI V2 / F3) — skills/vision/analyze.py.

`ollama.chat` is monkeypatched on the module, so no Ollama / GPU is needed. The
cancel flag rides the shared stream_cancel registry under the fixed VISION_OP key.
"""

from __future__ import annotations

import pytest

from celestia_core import stream_cancel
import skills.vision.analyze as analyze


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    # Never leak an active/cancelled vision op into the next test.
    stream_cancel.end(stream_cancel.VISION_OP)


def _chunks(*pieces: str):
    for p in pieces:
        yield {"message": {"content": p}}


def test_stream_chat_accumulates_chunks(monkeypatch) -> None:
    monkeypatch.setattr(analyze.ollama, "chat", lambda **kw: _chunks("Hello", " world"))
    out = analyze._stream_chat("m", [{"role": "user", "content": "hi"}], options={})
    assert out == "Hello world"


def test_stream_chat_passes_stream_flag_and_keep_alive(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def _chat(**kw):
        seen.update(kw)
        return _chunks("ok")

    monkeypatch.setattr(analyze.ollama, "chat", _chat)
    analyze._stream_chat("m", [], options={"temperature": 0}, keep_alive="30s")
    assert seen["stream"] is True
    assert seen["keep_alive"] == "30s"


def test_stream_chat_raises_when_cancelled_mid_stream(monkeypatch) -> None:
    stream_cancel.begin(stream_cancel.VISION_OP)

    def _chat(**kw):
        def _gen():
            yield {"message": {"content": "first"}}
            # Cancel arrives while the model is still generating…
            stream_cancel.request_cancel(stream_cancel.VISION_OP)
            yield {"message": {"content": "second"}}
            # …so the third chunk must never be pulled.
            pytest.fail("stream should have been abandoned after cancel")
            yield {"message": {"content": "third"}}

        return _gen()

    monkeypatch.setattr(analyze.ollama, "chat", _chat)
    with pytest.raises(analyze.VisionCancelled):
        analyze._stream_chat("m", [], options={})


def test_analyze_image_registers_cancellable_op(monkeypatch, tmp_path) -> None:
    seen: dict[str, bool] = {}

    def _impl(path, question):
        # request_cancel returns True only for a registered (active) op.
        seen["active_during"] = stream_cancel.request_cancel(stream_cancel.VISION_OP)
        return "ok"

    monkeypatch.setattr(analyze, "_analyze_image_impl", _impl)
    img = tmp_path / "shot.png"
    img.write_bytes(b"png")

    assert analyze.analyze_image(img, "what is this?") == "ok"
    assert seen["active_during"] is True
    # Registration and any cancel flag are cleared once the op ends.
    assert stream_cancel.is_cancelled(stream_cancel.VISION_OP) is False
    assert stream_cancel.request_cancel(stream_cancel.VISION_OP) is False


def test_analyze_image_propagates_cancel(monkeypatch, tmp_path) -> None:
    def _impl(path, question):
        raise analyze.VisionCancelled("vision analysis cancelled")

    monkeypatch.setattr(analyze, "_analyze_image_impl", _impl)
    img = tmp_path / "shot.png"
    img.write_bytes(b"png")

    with pytest.raises(analyze.VisionCancelled):
        analyze.analyze_image(img, "q")
    assert stream_cancel.request_cancel(stream_cancel.VISION_OP) is False  # cleaned up


def test_cancel_is_not_a_runtime_error() -> None:
    # _two_pass_text failures fall back to single-pass via `except (ResponseError,
    # RuntimeError)`; a cancel must escape that net, not retry with another model.
    assert not issubclass(analyze.VisionCancelled, RuntimeError)
