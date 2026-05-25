from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from celestia_core.config import ROOT, get

# Matches sentence-ending punctuation followed by a space/newline.
# Excludes common decimal patterns (3.14) by requiring the character before
# the punctuation not to be a digit.
_SENTENCE_END = re.compile(r"(?<!\d)[.!?]+(?=\s|$)")


def speak(text: str, *, play: bool = True) -> Path:
    text = text.strip()
    if not text:
        raise ValueError("empty text")

    out_dir = Path(ROOT) / "outputs"
    out_dir.mkdir(exist_ok=True)
    wav_path = out_dir / "celestia_last_reply.wav"

    provider = get("voice.tts.provider", "orpheus").lower()
    backend = get("voice.tts.orpheus.backend", "local").lower()
    data: bytes | None = None

    if provider == "orpheus":
        try:
            if backend == "local":
                from skills.tts import orpheus_local

                data = orpheus_local.synthesize_wav(text)
            else:
                from skills.tts import orpheus_backend

                data = orpheus_backend.synthesize_wav(text)
                orpheus_backend.stop_if_idle()
        except Exception as e:
            print(f"[tts] Orpheus failed ({e}), using edge-tts")

    if data is None:
        from skills.tts import edge_backend

        edge_backend.speak_to_file(text, wav_path)
    else:
        wav_path.write_bytes(data)

    if play:
        _play(wav_path)
    return wav_path


def speak_stream(
    token_iter: Iterable[str],
    *,
    play: bool = True,
    min_sentence_chars: int = 12,
    drain: bool = True,
) -> str:
    """Pipeline LLM token streaming with TTS playback (CC-115).

    Accepts any iterable of string tokens (e.g. from ``run_turn_stream``),
    accumulates them into sentence-sized chunks, and enqueues each chunk for
    TTS as soon as a sentence boundary is detected.  The TTS worker plays
    sentences concurrently while the LLM continues generating the next one.

    Returns the full assembled reply string.

    Parameters
    ----------
    token_iter:
        Iterable of string tokens from the LLM.
    play:
        If False, accumulate and return the text without synthesising audio.
    min_sentence_chars:
        Don't flush a chunk unless it has at least this many non-whitespace
        characters.  Prevents speaking isolated punctuation artifacts.
    """
    from skills.tts.queue import get_global_queue

    q = get_global_queue() if play else None

    buffer = ""
    full_text = ""

    def _try_flush(buf: str, *, final: bool = False) -> str:
        """Flush complete sentences from *buf* to the TTS queue.  Returns remainder."""
        while True:
            m = _SENTENCE_END.search(buf)
            if not m:
                break
            end = m.end()
            sentence = buf[:end].strip()
            remainder = buf[end:]
            # Skip flush if there's nothing after and this is mid-stream —
            # the dot might be a decimal or abbreviation; wait for more context.
            if not final and not remainder.strip():
                break
            if sentence and len(sentence.replace(" ", "")) >= min_sentence_chars:
                if q:
                    q.push(sentence)
            buf = remainder.lstrip()
        return buf

    for token in token_iter:
        buffer += token
        full_text += token
        buffer = _try_flush(buffer)

    # Final flush: speak whatever remains
    buffer = _try_flush(buffer, final=True)
    if buffer.strip():
        if q:
            q.push(buffer.strip())

    # Block until every sentence has finished playing.
    # Pass drain=False from PTT path so the HTTP response returns immediately
    # and TTS continues playing in the background daemon thread.
    if q and drain:
        q.drain()

    return full_text.strip()


def _play(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'(New-Object Media.SoundPlayer "{path}").PlaySync()',
            ],
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0,
        )
