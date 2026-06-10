"""Cross-process file primitives shared by tray, shell API, and CLI.

Extracted from shell_chat.py (F-01) so every cross-process JSON writer can use
the same exclusive lock and atomic-write pattern instead of a bare write_text
that can corrupt a file on crash or lose a write under a concurrent writer.
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    """Exclusive advisory lock shared across processes, keyed on a lock file.

    Uses msvcrt on Windows and fcntl elsewhere. The lock file itself is never
    read from or written to — it is only the handle the OS locks. Callers hold
    the lock for the duration of their read-modify-write.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as lock_file:
        if sys.platform == "win32":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write text to ``path`` atomically.

    Writes to a temp file in the same directory, flushes + fsyncs it, then
    os.replace()s it onto the target. A crash mid-write leaves the original
    file intact instead of a half-written, JSON-corrupt one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
