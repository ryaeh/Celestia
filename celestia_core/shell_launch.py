#!/usr/bin/env python3
"""Launch the Tauri desktop shell (starts localhost API if needed)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELL_DIR = ROOT / "shell"


def _npm_cmd() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def launch_shell_background(*, route: str = "home") -> int:
    """Start localhost API (if needed) and Tauri without blocking the caller."""
    if not (SHELL_DIR / "package.json").is_file():
        print("[shell] Missing shell/ — run: cd shell && npm install")
        return 1
    if not shutil.which(_npm_cmd().replace(".cmd", "")):
        print("[shell] npm not found — install Node.js 20+")
        return 1

    from celestia_core.shell_server import api_url, default_port, ping, start_server

    port = start_server(default_port())
    api = api_url(port)
    if ping(port):
        print(f"[shell] API already up at {api}")
    else:
        print(f"[shell] API {api}")

    env = os.environ.copy()
    env["CELESTIA_SHELL_API"] = api
    env["VITE_SHELL_API"] = api
    env["CELESTIA_SHELL_ROUTE"] = route
    env["VITE_SHELL_ROUTE"] = route

    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )

    subprocess.Popen(
        [_npm_cmd(), "run", "tauri", "dev"],
        cwd=str(SHELL_DIR),
        env=env,
        creationflags=flags,
        close_fds=True,
    )
    print("[shell] Opening desktop window — chat uses the same session as tray/voice.")
    return 0


def open_shell_chat() -> int:
    """Tray menu: open shell UI (shared chat session)."""
    from celestia_core.config import get, load_config

    load_config()
    if not get("ui.shell_settings", True):
        print("[shell] ui.shell_settings is false — enable it to use the desktop chat window.")
        return 1
    return launch_shell_background(route="home")


def launch_shell(*, route: str = "home", dev: bool = True) -> int:
    if not (SHELL_DIR / "package.json").is_file():
        print("[shell] Missing shell/ — run: cd shell && npm install")
        return 1
    if not shutil.which(_npm_cmd().replace(".cmd", "")):
        print("[shell] npm not found — install Node.js 20+")
        return 1

    from celestia_core.shell_server import default_port, start_server

    port = start_server(default_port())
    api = f"http://127.0.0.1:{port}"
    print(f"[shell] API {api}")

    env = os.environ.copy()
    env["CELESTIA_SHELL_API"] = api
    env["VITE_SHELL_API"] = api
    env["CELESTIA_SHELL_ROUTE"] = route
    env["VITE_SHELL_ROUTE"] = route

    if dev:
        cmd = [_npm_cmd(), "run", "tauri", "dev"]
    else:
        cmd = [_npm_cmd(), "run", "tauri", "build"]

    try:
        return subprocess.call(cmd, cwd=str(SHELL_DIR), env=env)
    except KeyboardInterrupt:
        return 0
    finally:
        from celestia_core.shell_server import stop_server

        stop_server()
