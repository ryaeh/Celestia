"""Linux path rules (stub until summer port)."""

from __future__ import annotations

import os
from pathlib import Path

PROTECTED_PREFIXES: tuple[str, ...] = (
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/boot",
    "/root",
)

BLOCKED_APP_NAMES = frozenset({"bash", "sh", "zsh", "sudo", "rm"})


def normalize(path: str | Path) -> Path | None:
    try:
        p = Path(path).expanduser().resolve()
        return p
    except (OSError, ValueError):
        return None


def is_protected(path: Path) -> bool:
    s = str(path)
    for prefix in PROTECTED_PREFIXES:
        if s == prefix or s.startswith(prefix + "/"):
            return True
    return False


def default_notepad_exe() -> Path:
    return Path("/usr/bin/notepad")  # placeholder


def system32_exe(name: str) -> Path:
    return Path("/usr/bin") / name


def find_builtin_exe(names: list[str]) -> Path | None:
    for name in names:
        p = Path("/usr/bin") / name
        if p.is_file():
            return p
    return None
