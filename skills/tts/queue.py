"""Background TTS playback queue for pipelined sentence-streaming (CC-115).

Allows the LLM token generator and TTS engine to run concurrently:
while the model generates sentence N+1, sentence N is already playing.

Usage
-----
    from skills.tts.queue import SpeakQueue

    q = SpeakQueue()
    q.push("Hello, I am Celestia.")
    q.push("How can I help?")
    q.drain()   # block until both sentences finish playing
"""

from __future__ import annotations

import queue
import threading

_SENTINEL = object()


class SpeakQueue:
    """Thread-safe FIFO queue that speaks sentences on a single background thread.

    A new instance spawns exactly one daemon worker thread that calls
    ``skills.tts.manager.speak(sentence)`` in order.  The queue is
    joined via ``drain()`` which blocks until the last sentence finishes.
    """

    def __init__(self) -> None:
        self._q: queue.Queue[str | object] = queue.Queue()
        self._thread = threading.Thread(
            target=self._worker, name="tts-speak-queue", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def push(self, sentence: str) -> None:
        """Enqueue *sentence* for playback.  Non-blocking."""
        sentence = sentence.strip()
        if not sentence:
            return
        self._q.put(sentence)

    def drain(self, timeout: float = 120.0) -> None:
        """Block until every enqueued sentence has finished playing."""
        self._q.join()

    def clear(self) -> None:
        """Discard all pending (not yet started) sentences."""
        while not self._q.empty():
            try:
                self._q.get_nowait()
                self._q.task_done()
            except queue.Empty:
                break

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while True:
            item = self._q.get()
            if item is _SENTINEL:
                self._q.task_done()
                return
            try:
                from skills.tts.manager import speak

                speak(str(item))
            except Exception as e:
                print(f"[tts-queue] {e}")
            finally:
                self._q.task_done()


# ---------------------------------------------------------------------------
# Module-level shared queue
# One queue per process is fine for a single-user desktop companion.
# ---------------------------------------------------------------------------

_global: SpeakQueue | None = None
_global_lock = threading.Lock()


def get_global_queue() -> SpeakQueue:
    """Return the process-wide TTS playback queue, creating it on first call."""
    global _global
    if _global is None:
        with _global_lock:
            if _global is None:
                _global = SpeakQueue()
    return _global
