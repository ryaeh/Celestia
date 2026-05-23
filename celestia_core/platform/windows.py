"""Windows path normalization and protected prefixes."""

from __future__ import annotations

import os
from pathlib import Path

# Deny file/folder access under these (case-insensitive prefix match)
PROTECTED_PREFIXES: tuple[str, ...] = (
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
)

# Never launch these by nickname in scoped mode
BLOCKED_APP_NAMES = frozenset(
    {
        "cmd",
        "powershell",
        "pwsh",
        "regedit",
        "mmc",
        "wt",
        "windowsterminal",
    }
)


def normalize(path: str | Path) -> Path | None:
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        return Path(os.path.normpath(str(p.resolve())))
    except (OSError, ValueError):
        return None


def is_protected(path: Path) -> bool:
    s = str(path).lower()
    for prefix in PROTECTED_PREFIXES:
        if s.startswith(prefix.lower()):
            return True
    return False


def default_notepad_exe() -> Path:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return Path(root) / "System32" / "notepad.exe"


def system32_exe(name: str) -> Path:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return Path(root) / "System32" / name


def find_builtin_exe(names: list[str]) -> Path | None:
    """Try System32, Windows root, then WindowsApps aliases."""
    root = os.environ.get("SystemRoot", r"C:\Windows")
    search_dirs = [
        Path(root) / "System32",
        Path(root),
    ]
    apps = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps"
    if apps.is_dir():
        search_dirs.append(apps)
    for name in names:
        for base in search_dirs:
            p = base / name
            try:
                if p.is_file():
                    return p.resolve()
            except OSError:
                continue
    return None


def _install_roots() -> list[Path]:
    roots: list[Path] = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        val = os.environ.get(env, "")
        if val:
            roots.append(Path(val))
    return roots


def find_installed_exe(
    names: list[str],
    relative_paths: list[str] | None = None,
) -> Path | None:
    """System32/WindowsApps first, then Program Files style paths (Edge, Chrome, …)."""
    hit = find_builtin_exe(names)
    if hit:
        return hit
    for rel in relative_paths or []:
        for root in _install_roots():
            p = root / rel
            try:
                if p.is_file():
                    return p.resolve()
            except OSError:
                continue
    return None
