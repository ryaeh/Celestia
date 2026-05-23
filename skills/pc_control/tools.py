from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

BLOCKED_PS = re.compile(
    r"(Remove-Item\s+-Recurse|Format-Volume|Clear-Content|Stop-Computer|Restart-Computer|"
    r"shutdown|diskpart|reg\s+delete|Invoke-Expression|iex\b|DownloadString|"
    r"Start-Process\s+.*powershell|-EncodedCommand)",
    re.IGNORECASE,
)

BLOCKED_OPEN = re.compile(
    r"(cmd|command\s*prompt|powershell|terminal|conhost|www\.example\.com|example\.com)",
    re.IGNORECASE,
)

BLOCKED_URL_HOSTS = (
    "example.com",
    "example.org",
    "test.com",
    "localhost",
    "127.0.0.1",
)

PC_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": "Run a safe PowerShell command. Prefer Get-* cmdlets.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_path",
            "description": (
                "Open a file, folder, or app. For Notepad use path 'notepad' or 'not defteri' "
                "(classic System32 editor). Never use write.exe — it is not installed on Windows 11."
            ),
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a URL in the browser. Only when user gave a real URL to open.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "CPU, RAM, disk, and uptime summary.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": "Top processes by memory use.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
]

MEMORY_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search stored facts about the user.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_add",
            "description": (
                "Store a fact about the USER only (preferences, name, habits). "
                "Never store assistant identity or 'I am Celestia'. Use user's exact wording."
            ),
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list",
            "description": "List all stored user memories (ids and text).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Delete one memory by id, or delete all matching a text snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "UUID from memory_list"},
                    "match_text": {
                        "type": "string",
                        "description": "Delete entries containing this text",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_edit",
            "description": "Update an existing memory by id (from memory_list).",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "new_text": {"type": "string", "description": "Replacement fact text"},
                },
                "required": ["memory_id", "new_text"],
            },
        },
    },
]


def _run_ps(command: str, timeout: int = 30) -> str:
    if BLOCKED_PS.search(command):
        return "Blocked: command matches safety denylist."
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return f"Exit {proc.returncode}\n{err or out}"
    return out or "(no output)"


def _system32_exe(name: str) -> Path:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return Path(root) / "System32" / name


def _app_alias(name: str) -> tuple[str, str | None]:
    """Map friendly names; optional note when substituting."""
    from celestia_core.config import get

    aliases = get("pc_control.app_aliases") or {}
    key = name.lower().strip().removesuffix(".exe")
    if key in aliases:
        target = str(aliases[key])
        return target, f" (alias: {name} → {target})"
    return name, None


_NOTEPAD_NAMES = frozenset(
    {
        "notepad",
        "notepad.exe",
        "not defteri",
        "notdefteri",
        "write",       # old WordPad fallback — not on Win11; use classic Notepad
        "write.exe",
    }
)


def _open_notepad() -> str:
    """Launch classic Notepad (Not Defteri) — not the Store WinUI 'Notepad' app."""
    from celestia_core.config import get

    if get("pc_control.app_aliases", {}).get("notepad"):
        launch, note = _app_alias("notepad")
        _launch_via_shell(launch)
        return f"Opened: {launch}{note or ''}"

    classic = _system32_exe("notepad.exe")
    if not classic.is_file():
        return "Classic notepad.exe not found in System32."

    # Direct launch — avoids PATH alias to WindowsApps\\Notepad (broken DLL on many PCs).
    subprocess.Popen(
        [str(classic)],
        cwd=str(classic.parent),
        close_fds=True,
    )
    return (
        f"Opened classic Notepad (Not Defteri): {classic}. "
        "Do not use the separate Store app named 'Notepad' - that one often shows "
        "Microsoft.UI.Windowing.Core.dll errors."
    )


def _launch_via_shell(target: str) -> None:
    flags = 0
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags = subprocess.CREATE_NO_WINDOW
    subprocess.run(
        ["cmd", "/c", "start", "", target],
        check=False,
        timeout=15,
        creationflags=flags,
    )


def _open_path(path: str) -> str:
    from celestia_core.security import get_mode

    path = path.strip().strip('"')
    if not path or BLOCKED_OPEN.search(path):
        return "Blocked: cannot open terminals or placeholder paths."

    if get_mode() == "scoped":
        from celestia_core.scope import check_open_path

        err = check_open_path(path)
        if err:
            return err

    if "/" not in path and "\\" not in path and ":" not in path:
        from celestia_core.scope import resolve_launchable_exe

        exe, err = resolve_launchable_exe(path)
        if err:
            return err
        if exe:
            subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
            return f"Opened: {exe}"
        if path.lower().strip().removesuffix(".exe") in _NOTEPAD_NAMES:
            return _open_notepad()
        launch, note = _app_alias(path)
        if launch.endswith(".exe") or "\\" in launch or "/" in launch:
            exe = Path(launch) if Path(launch).is_absolute() else _system32_exe(launch)
            if launch.endswith(".exe") and not exe.is_file():
                return f"Failed: {launch} not found on this PC."
        try:
            _launch_via_shell(launch)
            return f"Opened: {launch}{note or ''}"
        except OSError as e:
            return f"Failed to open '{path}': {e}"

    target = Path(path)
    if not target.exists():
        return f"Blocked: path not found: {path}"
    os.startfile(str(target))
    return f"Opened: {target}"


def _open_url(url: str) -> str:
    url = url.strip()
    lower = url.lower()
    if not lower.startswith(("http://", "https://")):
        url = "https://" + url
        lower = url.lower()
    if any(host in lower for host in BLOCKED_URL_HOSTS):
        return f"Blocked: refusing URL '{url}'"
    webbrowser.open(url)
    return f"Opened URL: {url}"


def execute_pc(name: str, arguments: dict[str, Any]) -> str:
    if name == "run_powershell":
        return _run_ps(arguments["command"])
    if name == "open_path":
        return _open_path(arguments["path"])
    if name == "open_url":
        return _open_url(arguments["url"])
    if name == "get_system_status":
        cmd = (
            "$os = Get-CimInstance Win32_OperatingSystem; "
            "$cpu = (Get-CimInstance Win32_Processor).LoadPercentage; "
            "$ram = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1MB, 1); "
            "$ramTotal = [math]::Round($os.TotalVisibleMemorySize/1MB, 1); "
            "$disk = Get-CimInstance Win32_LogicalDisk -Filter \"DriveType=3\" | "
            "ForEach-Object { \"$($_.DeviceID) $([math]::Round(($_.Size-$_.FreeSpace)/1GB,1))/$([math]::Round($_.Size/1GB,1)) GB used\" }; "
            "$uptime = (Get-Date) - $os.LastBootUpTime; "
            "\"CPU: ${cpu}% | RAM: ${ram}/${ramTotal} GB | Uptime: $($uptime.Days)d $($uptime.Hours)h $($uptime.Minutes)m | Disk: $($disk -join '; ')\""
        )
        return _run_ps(cmd)
    if name == "list_processes":
        limit = int(arguments.get("limit") or 15)
        cmd = (
            f"Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First {limit} "
            "Name, @{N='MB';E={[math]::Round($_.WorkingSet/1MB,1)}} | Format-Table -AutoSize | Out-String"
        )
        return _run_ps(cmd)
    return f"Unknown PC tool: {name}"
