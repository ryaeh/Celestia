"""Faillog — write ERROR+ to data/logs/errors.log (rotating 2 MB × 3).

Call ``setup()`` once near the entry-point.  All Python ERROR/CRITICAL
messages (including uvicorn ASGI exceptions and uncaught thread errors)
then go to the log file in addition to stderr.

Check the log any time without pasting errors back into chat:
    notepad data\\logs\\errors.log
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
_LOG_PATH = _LOG_DIR / "errors.log"
_setup_done = False


def setup() -> None:
    """Install rotating file handler + exception hooks.  Safe to call twice."""
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        _LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setLevel(logging.ERROR)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.getLogger().addHandler(handler)

    # --- Unhandled main-thread exceptions ---
    _orig_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            _orig_excepthook(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("celestia.crash").critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
        )
        _orig_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # --- Uncaught exceptions in non-main threads (Python 3.8+) ---
    _orig_thread_hook = threading.excepthook

    def _thread_hook(args):
        logging.getLogger("celestia.thread").error(
            "Uncaught exception in thread '%s'",
            getattr(args.thread, "name", str(args.thread)),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        _orig_thread_hook(args)

    threading.excepthook = _thread_hook

    print(f"[faillog] Errors → {_LOG_PATH}", file=sys.stderr)


def path() -> Path:
    """Return the absolute path to the current error log."""
    return _LOG_PATH
