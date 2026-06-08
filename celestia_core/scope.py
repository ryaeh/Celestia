"""Scoped PC access — protected paths, workspaces, app allowlist (Phase 3a/3b)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from celestia_core.config import ROOT, get, load_config
from celestia_core.platform import get_platform

_NOTEPAD_NAMES = frozenset({"notepad", "notepad.exe", "not defteri", "notdefteri"})

# Nickname -> exe filenames to search (System32 first)
_BUILTIN_EXE: dict[str, list[str]] = {
    "calc": ["calc.exe"],
    "calculator": ["calc.exe"],
    "mspaint": ["mspaint.exe"],
    "paint": ["mspaint.exe"],
    "snippingtool": ["SnippingTool.exe", "ScreenClippingHost.exe"],
    "magnify": ["magnify.exe"],
    "control": ["control.exe"],
    "controlpanel": ["control.exe"],
    "write": ["write.exe"],
    "wordpad": ["write.exe"],
    "explorer": ["explorer.exe"],
    "fileexplorer": ["explorer.exe"],
    "msedge": ["msedge.exe"],
    "edge": ["msedge.exe"],
    "chrome": ["chrome.exe"],
    "firefox": ["firefox.exe"],
    "taskmgr": ["Taskmgr.exe"],
    "taskmanager": ["Taskmgr.exe"],
}

# Program Files paths when exe is not in System32 / WindowsApps
_INSTALLED_REL: dict[str, list[str]] = {
    "msedge": ["Microsoft/Edge/Application/msedge.exe"],
    "edge": ["Microsoft/Edge/Application/msedge.exe"],
    "chrome": [
        "Google/Chrome/Application/chrome.exe",
    ],
    "firefox": ["Mozilla Firefox/firefox.exe"],
}

_extra_workspaces_path = ROOT / "data" / "scope_workspaces.json"

# Cache of the parsed extra-workspaces file, keyed on its mtime. list_workspaces()
# runs on every scoped file check; re-reading + parsing each time is wasteful.
# Any write below bumps the mtime and forces a re-read (safe across processes).
_extra_workspaces_cache: tuple[int, list[str]] | None = None


def _plat():
    return get_platform()


def _config_workspaces() -> list[Path]:
    raw = get("security.workspaces") or []
    out: list[Path] = []
    for item in raw:
        p = _plat().normalize(item)
        if p:
            out.append(p)
    return out


def _read_extra_workspace_paths() -> list[str]:
    """Raw workspace path strings from disk, cached on the file's mtime."""
    global _extra_workspaces_cache
    path = _extra_workspaces_path
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return []
    if _extra_workspaces_cache is not None and _extra_workspaces_cache[0] == mtime:
        return _extra_workspaces_cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        paths = data.get("workspaces", [])
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(paths, list):
        paths = []
    _extra_workspaces_cache = (mtime, paths)
    return paths


def _load_extra_workspaces() -> list[Path]:
    out: list[Path] = []
    for item in _read_extra_workspace_paths():
        p = _plat().normalize(item)
        if p:
            out.append(p)
    return out


def list_workspaces() -> list[Path]:
    seen: set[str] = set()
    merged: list[Path] = []
    for p in _config_workspaces() + _load_extra_workspaces():
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            merged.append(p)
    if not merged:
        for candidate in (
            Path.home() / "Documents" / "Celestia",
            Path.home() / "Projects",
            Path.home() / "Documents",
            ROOT,
        ):
            if candidate.is_dir():
                k = str(candidate).lower()
                if k not in seen:
                    seen.add(k)
                    merged.append(candidate)
    return merged


def add_workspace(path: str) -> str:
    p = _plat().normalize(path)
    if not p:
        return f"Invalid path: {path}"
    if not p.is_dir():
        return f"Not a directory: {p}"
    extras = [str(x) for x in _load_extra_workspaces()]
    key = str(p)
    if key in extras or any(str(w).lower() == key.lower() for w in _config_workspaces()):
        return f"Already in workspaces: {p}"
    extras.append(key)
    _extra_workspaces_path.parent.mkdir(parents=True, exist_ok=True)
    _extra_workspaces_path.write_text(
        json.dumps({"workspaces": extras}, indent=2),
        encoding="utf-8",
    )
    global _extra_workspaces_cache
    _extra_workspaces_cache = None
    return f"Added workspace: {p}"


def remove_workspace(path: str) -> str:
    p = _plat().normalize(path)
    if not p:
        return f"Invalid path: {path}"
    extras = [str(x) for x in _load_extra_workspaces()]
    key = str(p)
    new = [e for e in extras if e.lower() != key.lower()]
    if len(new) == len(extras):
        return f"Not in runtime workspaces (check config.yaml): {path}"
    _extra_workspaces_path.write_text(
        json.dumps({"workspaces": new}, indent=2),
        encoding="utf-8",
    )
    global _extra_workspaces_cache
    _extra_workspaces_cache = None
    return f"Removed workspace: {p}"


def _app_allowlist() -> set[str]:
    apps = get("security.app_allowlist") or [
        "notepad",
        "notepad.exe",
        "not defteri",
        "notdefteri",
        "calc",
        "calculator",
        "mspaint",
        "paint",
        "snippingtool",
    ]
    return {a.lower().strip() for a in apps}


def _find_app_exe(key: str, names: list[str]) -> Path | None:
    plat = _plat()
    rel = _INSTALLED_REL.get(key, [])
    finder = getattr(plat, "find_installed_exe", plat.find_builtin_exe)
    return finder(names, rel)


def _resolve_app_nickname(name: str) -> Path | None:
    plat = _plat()
    key = name.lower().strip().removesuffix(".exe")
    if key in plat.BLOCKED_APP_NAMES:
        return None
    aliases = get("pc_control.app_aliases") or {}
    if key in aliases:
        p = plat.normalize(aliases[key])
        return p if p and p.is_file() else None
    if key in _NOTEPAD_NAMES:
        exe = plat.default_notepad_exe()
        return exe if exe.is_file() else None
    if key in _BUILTIN_EXE:
        return _find_app_exe(key, _BUILTIN_EXE[key])
    if key in _app_allowlist():
        if name.lower().endswith(".exe"):
            p = plat.normalize(name)
            return p if p and p.is_file() else None
        if key in _BUILTIN_EXE:
            return _find_app_exe(key, _BUILTIN_EXE[key])
    return None


def _allowed_executables() -> set[str]:
    plat = _plat()
    out: set[str] = set()
    for item in get("security.allowed_executables") or []:
        p = plat.normalize(item)
        if p and p.is_file():
            out.add(str(p).lower())
    for app in _app_allowlist():
        exe = _resolve_app_nickname(app)
        if exe and exe.is_file():
            out.add(str(exe).lower())
    for key in _BUILTIN_EXE:
        exe = _resolve_app_nickname(key)
        if exe and exe.is_file():
            out.add(str(exe).lower())
    return out


def resolve_launchable_exe(name: str) -> tuple[Path | None, str | None]:
    """Resolve app nickname; return (exe, error_message)."""
    load_config()
    key = name.lower().strip().removesuffix(".exe")
    if key not in _app_allowlist() and key not in _NOTEPAD_NAMES:
        return None, (
            f"Blocked: '{name}' is not on app_allowlist. "
            "Add to app_allowlist in security.policy.yaml."
        )
    exe = _resolve_app_nickname(name)
    if not exe or not exe.is_file():
        return None, f"Blocked: app not found on this PC: {name}"
    if str(exe).lower() not in _allowed_executables():
        return None, f"Blocked: executable not allowlisted: {exe}"
    return exe, None


def _is_under_workspace(path: Path) -> bool:
    workspaces = list_workspaces()
    if not workspaces:
        return False
    p = str(path).lower()
    for root in workspaces:
        r = str(root).lower()
        if p == r or p.startswith(r + os.sep):
            return True
    return False


def _can_launch_executable(exe: Path) -> tuple[bool, str]:
    key = str(exe).lower()
    if key in _allowed_executables():
        return True, ""
    return False, f"Executable not on allowlist: {exe}"


def check_open_path(path: str) -> str | None:
    """Return error message if blocked in scoped mode; None if allowed."""
    load_config()
    plat = _plat()
    raw = path.strip().strip('"')
    if not raw:
        return "Blocked: empty path."

    if "/" not in raw and "\\" not in raw and ":" not in raw:
        key = raw.lower().removesuffix(".exe")
        if key in plat.BLOCKED_APP_NAMES:
            return f"Blocked: '{raw}' is not allowed in scoped mode."
        _, err = resolve_launchable_exe(raw)
        return err

    resolved = plat.normalize(raw)
    if not resolved:
        return f"Blocked: invalid path: {raw}"

    if resolved.is_file():
        if resolved.suffix.lower() == ".exe":
            ok, msg = _can_launch_executable(resolved)
            return msg if not ok else None
        if plat.is_protected(resolved):
            return f"Blocked: cannot open files under protected system paths: {resolved}"
        if not _is_under_workspace(resolved):
            return (
                f"Blocked: file outside workspaces: {resolved}. "
                "Use 'scope add <folder>' or arm for full access."
            )
        return None

    if resolved.is_dir():
        if plat.is_protected(resolved):
            return f"Blocked: cannot open protected folders (e.g. System32): {resolved}"
        if not _is_under_workspace(resolved):
            return f"Blocked: folder outside workspaces: {resolved}"
        return None

    return f"Blocked: path not found: {resolved}"


def check_file_write(path: str) -> str | None:
    """Scoped: workspace files only. Armed: any non-protected path."""
    from celestia_core.security import get_mode

    load_config()
    plat = _plat()
    mode = get_mode()
    if mode == "safe":
        return "Blocked: file_write requires scoped or armed mode."

    resolved = plat.normalize(path)
    if not resolved:
        return f"Blocked: invalid path: {path}"
    if resolved.exists() and resolved.is_dir():
        return f"Blocked: path is a directory: {resolved}"
    if plat.is_protected(resolved):
        return f"Blocked: cannot write protected path: {resolved}"
    parent = resolved.parent
    if parent and plat.is_protected(parent) and not _is_under_workspace(resolved):
        return f"Blocked: cannot write under protected path: {resolved}"

    if mode == "scoped" and not _is_under_workspace(resolved):
        return (
            f"Blocked: file outside workspaces: {resolved}. "
            "Use scope add <folder> or arm for full access."
        )
    return None


def check_file_read(path: str) -> str | None:
    """Scoped: workspace files only. Armed: any non-protected file."""
    from celestia_core.security import get_mode

    load_config()
    plat = _plat()
    mode = get_mode()
    if mode == "safe":
        return "Blocked: file_read requires scoped or armed mode."

    resolved = plat.normalize(path)
    if not resolved:
        return f"Blocked: invalid path: {path}"
    if not resolved.is_file():
        return f"Blocked: not a file: {resolved}"
    if plat.is_protected(resolved):
        return f"Blocked: cannot read protected path: {resolved}"

    if mode == "scoped" and not _is_under_workspace(resolved):
        return (
            f"Blocked: file outside workspaces: {resolved}. "
            "Use scope add <folder> or arm for full access."
        )
    return None


def _url_host(url: str) -> str:
    from urllib.parse import urlparse

    u = url.strip()
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    try:
        return (urlparse(u).hostname or "").lower()
    except Exception:
        return ""


def check_open_url(url: str) -> str | None:
    """Scoped: allow only hosts in security.url_allowlist (empty list = block all)."""
    from celestia_core.security import get_mode
    from celestia_core.url_policy import host_matches_allowlist

    load_config()
    mode = get_mode()
    if mode != "scoped":
        return None

    allowlist = [str(x) for x in (get("security.url_allowlist") or []) if x]
    if not allowlist:
        return (
            "Blocked in scoped mode: URLs need armed mode, or add hosts to "
            "url_allowlist in security.policy.yaml."
        )

    host = _url_host(url)
    if not host:
        return f"Blocked: invalid URL: {url}"

    if host_matches_allowlist(host, allowlist):
        return None

    return f"Blocked: URL host '{host}' not in url_allowlist (security.policy.yaml)."


def format_status() -> str:
    from celestia_core.security import get_mode

    mode = get_mode()
    lines = [f"Security mode: {mode.upper()}"]
    lines.append("Workspaces:")
    ws = list_workspaces()
    if ws:
        for p in ws:
            lines.append(f"  - {p}")
    else:
        lines.append("  (none — add with: scope add C:\\Your\\Folder)")
    lines.append("App allowlist: " + ", ".join(sorted(_app_allowlist())))
    lines.append("Allowed executables (auto-resolved):")
    for a in sorted(_allowed_executables()):
        lines.append(f"  - {a}")
    urls = get("security.url_allowlist") or []
    if urls:
        lines.append("URL allowlist (scoped): " + ", ".join(str(u) for u in urls))
    else:
        lines.append("URL allowlist (scoped): (empty — all URLs blocked until armed)")
    lines.append("Protected: Windows, Program Files, ProgramData, …")
    return "\n".join(lines)


def print_pick_workspace_hint() -> None:
    """CLI wizard: paths to paste into config.yaml."""
    print("=== Celestia workspace picker ===\n")
    print("Add folders under security.workspaces in config.yaml, for example:\n")
    print("security:")
    print("  workspaces:")
    for p in list_workspaces():
        print(f'    - "{p}"')
    print("\nSuggested folders (create if missing):")
    for candidate in (
        ROOT,
        Path.home() / "Projects",
        Path.home() / "Documents" / "Celestia",
        Path.home() / "Documents",
    ):
        mark = "exists" if candidate.is_dir() else "missing"
        print(f'  - "{candidate}"  ({mark})')
    print("\nRuntime add without editing config:  scope add C:\\Your\\Folder")
