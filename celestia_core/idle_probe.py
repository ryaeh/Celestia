"""System idleness probes — is the *machine* free, not just Celestia?

The GPU-residency lock (`gpu.py`) only knows Celestia's own heavy ops; a game
or another app can be hammering the GPU while our lock is free. The idle
"tidying" daemon needs the whole-machine picture before it loads a big model:

- ``user_idle_seconds()``  — seconds since the last keyboard/mouse input
  (Windows ``GetLastInputInfo``; None elsewhere or on error).
- ``gpu_utilization()``    — system-wide GPU busy %, via nvidia-smi
  (None on non-NVIDIA machines).
- ``system_is_idle()``     — the combined gate the daemon polls.

This is also the first slice of the Feature 11 (operating modes) system probe.
"""

from __future__ import annotations

import subprocess
import sys


def user_idle_seconds() -> float | None:
    """Seconds since the last user input, or None when unknowable.

    Windows-only for now (``GetLastInputInfo``). GetTickCount wraps every ~49.7
    days; a wrap makes one reading look tiny, which only delays the daemon one
    cycle — acceptable for this use.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        tick = ctypes.windll.kernel32.GetTickCount()
        return max(0.0, (tick - info.dwTime) / 1000.0)
    except Exception:
        return None


def gpu_utilization() -> int | None:
    """System-wide GPU utilization percent via nvidia-smi, or None when
    unavailable. This sees *every* process (games, browsers), unlike
    ``gpu.gpu_busy()`` which only tracks Celestia's own lock."""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip().splitlines()[0].strip())
    except Exception:
        return None


def system_is_idle(*, min_afk_seconds: float, max_gpu_utilization: int) -> bool:
    """The daemon's gate: user AFK long enough AND the GPU quiet.

    Conservative on unknowns that must be known (no AFK reading → not idle),
    permissive on unknowns that can't be known (no NVIDIA GPU → utilization
    check is moot). Celestia's own foreground ops are covered separately by
    the non-blocking ``gpu_task`` acquire in the caller.
    """
    afk = user_idle_seconds()
    if afk is None or afk < min_afk_seconds:
        return False
    util = gpu_utilization()
    if util is not None and util > max_gpu_utilization:
        return False
    return True
