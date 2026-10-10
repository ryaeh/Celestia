"""Ollama lifecycle for the shell's launch gate: probe, start, and pull models.

Celestia talks to Ollama over HTTP and never owns it. We only *launch* ``ollama
serve`` (detached, so it outlives Celestia and stays shared with other tools) when
the user asks, and pull the models the config needs. None of this is an LLM tool —
it is reachable only from the token-guarded shell API and the CLI prompt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from celestia_core.config import get

DEFAULT_HOST = "http://127.0.0.1:11434"
DOWNLOAD_URL = "https://ollama.com/download"

# What to do at launch when Ollama is off. Stored as a UI pref (data/ui_prefs.json),
# so changing it never touches config.yaml or its integrity hash.
PREF_ON_LAUNCH = "llm.ollama_on_launch"
ON_LAUNCH_CHOICES = ("ask", "start", "skip")

DOWN_MESSAGE = (
    "Ollama isn't running. Use the Start Ollama button in the app "
    "(or run `ollama serve`), then try again."
)

# (connect, read) seconds. On Windows a refused localhost connection doesn't fail
# fast — it hangs until the connect timeout — so every "Ollama is off" probe costs
# the full connect timeout. A listening local server accepts instantly, so keep
# that short and give the read (a busy server) real slack to avoid false "down".
_PROBE_TIMEOUT_LOCAL = (0.6, 3.0)
_PROBE_TIMEOUT_REMOTE = (2.0, 3.0)
_STATUS_TTL = 1.0  # several windows poll status — share one probe per second
_START_POLL = 0.5  # seconds between probes while waiting for `serve` to come up
_DEFAULT_START_TIMEOUT = 25.0


class OllamaError(RuntimeError):
    """A start/pull request that can't be honoured (the message is user-facing)."""


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def host() -> str:
    return str(get("llm.host", DEFAULT_HOST)).rstrip("/")


def _host_parts(h: str) -> tuple[str, int]:
    parsed = urlparse(h if "://" in h else f"http://{h}")
    return (parsed.hostname or "127.0.0.1"), (parsed.port or 11434)


def is_local(h: str | None = None) -> bool:
    """True when ``llm.host`` points at this PC — the only case we may start Ollama."""
    name, _ = _host_parts(h or host())
    return name in ("127.0.0.1", "localhost", "::1", "0.0.0.0")


def chat_model() -> str:
    return str(get("llm.chat_model", "llama3.2:3b") or "").strip()


def required_models() -> list[str]:
    """Models chat + memory need. (Vision models stay with ``check_vision``.)"""
    out: list[str] = []
    for m in (chat_model(), str(get("llm.embed_model", "nomic-embed-text") or "").strip()):
        if m and m not in out:
            out.append(m)
    return out


def on_launch() -> str:
    """ask | start | skip — what the shell does at launch when Ollama is off."""
    v = str(get(PREF_ON_LAUNCH, "ask") or "ask").strip().lower()
    return v if v in ON_LAUNCH_CHOICES else "ask"


def _norm(name: str) -> str:
    """Ollama treats a bare ``nomic-embed-text`` as ``nomic-embed-text:latest``."""
    n = name.strip().lower()
    return n if ":" in n.rsplit("/", 1)[-1] else f"{n}:latest"


def find_exe() -> Path | None:
    """Locate ollama.exe: ``llm.ollama_path`` override, PATH, then the default installs."""
    override = str(get("llm.ollama_path", "") or "").strip()
    if override:
        p = Path(override).expanduser()
        if p.is_file():
            return p
    found = shutil.which("ollama")
    if found:
        return Path(found)
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base:
            candidates.append(Path(base) / "Ollama" / "ollama.exe")
    return next((c for c in candidates if c.is_file()), None)


def is_connection_error(exc: BaseException | None) -> bool:
    """True when ``exc`` (or its cause chain) means "couldn't reach the server"."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, (ConnectionError, requests.ConnectionError)):
            return True
        try:
            import httpx

            if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                return True
        except ImportError:  # pragma: no cover - httpx ships with the ollama client
            pass
        exc = exc.__cause__ or exc.__context__
    return False


# ---------------------------------------------------------------------------
# Probe + status
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_probe_cache: tuple[float, tuple[set[str] | None, str | None]] | None = None
_start: dict[str, Any] = {"active": False, "error": None}
_start_thread: threading.Thread | None = None


def _idle_pull() -> dict[str, Any]:
    return {
        "active": False,
        "models": [],
        "current": None,
        "index": 0,
        "status": "",
        "completed": 0,
        "total": 0,
        "error": None,
        "finished": False,
        "cancelled": False,
    }


_pull: dict[str, Any] = _idle_pull()
_pull_thread: threading.Thread | None = None


def _probe() -> tuple[set[str] | None, str | None]:
    """(installed model names, None) when reachable, else (None, error text)."""
    h = host()
    try:
        r = requests.get(
            f"{h}/api/tags",
            timeout=_PROBE_TIMEOUT_LOCAL if is_local(h) else _PROBE_TIMEOUT_REMOTE,
        )
        r.raise_for_status()
        names: set[str] = set()
        for m in r.json().get("models", []):
            for key in ("name", "model"):
                if m.get(key):
                    names.add(_norm(str(m[key])))
        return names, None
    except (requests.RequestException, ValueError) as e:
        return None, str(e)


def invalidate() -> None:
    """Drop the cached probe (after a start/pull so the next status is fresh)."""
    global _probe_cache
    _probe_cache = None


def _probe_cached(use_cache: bool) -> tuple[set[str] | None, str | None]:
    global _probe_cache
    now = time.monotonic()
    if _probe_cache is not None:
        fresh = now - _probe_cache[0] < _STATUS_TTL
        # While a start is in flight the worker is already probing — and a server
        # that is still initialising accepts connections but won't answer /api/tags
        # for seconds, so a second prober would just block a request thread.
        if (use_cache and fresh) or _start["active"]:
            return _probe_cache[1]
    result = _probe()
    _probe_cache = (now, result)
    return result


def _pull_view(p: dict[str, Any]) -> dict[str, Any]:
    out = dict(p)
    total = int(p.get("total") or 0)
    out["percent"] = min(100, int(100 * int(p.get("completed") or 0) / total)) if total else None
    return out


def status(*, use_cache: bool = True) -> dict[str, Any]:
    """Everything the shell needs to render the launch gate / banner / settings row.

    ``state`` is one of: running · missing_models · starting · down · not_installed.
    """
    names, err = _probe_cached(use_cache)
    h = host()
    required = required_models()
    local = is_local(h)
    reachable = names is not None
    missing = [m for m in required if reachable and _norm(m) not in names]  # type: ignore[operator]
    exe = None if reachable else find_exe()

    with _lock:
        starting = bool(_start["active"])
        start_error = None if reachable else _start["error"]
        pull = _pull_view(_pull)

    if reachable:
        state = "missing_models" if missing else "running"
    elif starting:
        state = "starting"
    elif local and exe is None:
        state = "not_installed"
    else:
        state = "down"

    chat = chat_model()
    messages = {
        "running": f"Ollama is running — {', '.join(required)}",
        "missing_models": f"Ollama is running but missing: {', '.join(missing)}",
        "starting": "Starting Ollama…",
        "not_installed": "Ollama isn't installed on this PC.",
        "down": "Ollama isn't running." if local else f"Can't reach Ollama at {h}.",
    }
    return {
        "state": state,
        "reachable": reachable,
        "host": h,
        "local": local,
        "can_start": (not reachable) and local and exe is not None and not starting,
        "required": required,
        "missing": missing,
        "chat_ready": reachable and bool(chat) and _norm(chat) in names,  # type: ignore[operator]
        "message": messages[state],
        "error": err,
        "start_error": start_error,
        "pull": pull,
        "on_launch": on_launch(),
        "download_url": DOWNLOAD_URL,
    }


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def _spawn(exe: Path) -> None:
    """Launch ``ollama serve`` detached: no window, and it survives Celestia exiting."""
    env = os.environ.copy()
    name, port = _host_parts(host())
    env["OLLAMA_HOST"] = f"{name}:{port}"  # bind where Celestia will look for it
    kwargs: dict[str, Any] = {
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0x08000000
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([str(exe), "serve"], **kwargs)


def _start_worker(exe: Path, timeout: float) -> None:
    global _probe_cache
    error: str | None = None
    try:
        _spawn(exe)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = _probe()
            _probe_cache = (time.monotonic(), result)  # status() reads this while we're starting
            if result[0] is not None:
                break
            time.sleep(_START_POLL)
        else:
            error = (
                f"Ollama didn't answer within {int(timeout)}s. "
                "Run `ollama serve` in a terminal to see why."
            )
    except OSError as e:
        error = f"Couldn't launch Ollama: {e}"
    finally:
        with _lock:
            _start["active"] = False
            _start["error"] = error
        invalidate()


def start(*, block: bool = False, timeout: float | None = None) -> dict[str, Any]:
    """Start ``ollama serve`` if nothing is answering. Idempotent; returns ``status()``.

    Non-blocking by default — callers poll ``status()`` (``state == "starting"``
    until the server answers). A port already in use (the Ollama tray app got there
    first) is fine: the probe loop just sees the other server come up.
    """
    global _start_thread
    st = status(use_cache=False)
    if st["reachable"]:
        return st
    if not st["local"]:
        raise OllamaError(f"Ollama is set to {st['host']}, not this PC — start it there.")
    exe = find_exe()
    if exe is None:
        raise OllamaError(f"Ollama isn't installed — get it from {DOWNLOAD_URL}")

    limit = timeout if timeout is not None else float(
        get("llm.ollama_start_timeout_seconds", _DEFAULT_START_TIMEOUT) or _DEFAULT_START_TIMEOUT
    )
    with _lock:
        launch = not _start["active"]
        if launch:
            _start["active"] = True
            _start["error"] = None
    if launch:
        _start_thread = threading.Thread(
            target=_start_worker, args=(exe, limit), daemon=True, name="ollama-start"
        )
        _start_thread.start()
    if block and _start_thread is not None:
        _start_thread.join()
    return status(use_cache=False)


# ---------------------------------------------------------------------------
# Pull
# ---------------------------------------------------------------------------

def _field(chunk: Any, key: str) -> Any:
    return chunk.get(key) if isinstance(chunk, dict) else getattr(chunk, key, None)


def _set_pull(**fields: Any) -> None:
    with _lock:
        _pull.update(fields)


def _pull_worker(models: list[str]) -> None:
    error: str | None = None
    try:
        import ollama

        client = ollama.Client(host=host(), timeout=None)  # downloads take minutes
        for i, model in enumerate(models):
            _set_pull(current=model, index=i, status="starting", completed=0, total=0)
            layers: dict[str, tuple[int, int]] = {}
            stream = client.pull(model, stream=True)
            try:
                for chunk in stream:
                    if _pull["cancelled"]:
                        break
                    digest = str(_field(chunk, "digest") or "")
                    if digest:
                        layers[digest] = (
                            int(_field(chunk, "completed") or 0),
                            int(_field(chunk, "total") or 0),
                        )
                    _set_pull(
                        status=str(_field(chunk, "status") or ""),
                        completed=sum(c for c, _ in layers.values()),
                        total=sum(t for _, t in layers.values()),
                    )
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
            if _pull["cancelled"]:
                break
    except Exception as e:  # noqa: BLE001 — surfaced to the UI, never raised
        error = DOWN_MESSAGE if is_connection_error(e) else f"Pull failed: {e}"
    finally:
        with _lock:
            _pull.update(active=False, finished=True, error=error)
        invalidate()


def start_pull(models: list[str] | None = None) -> dict[str, Any]:
    """Pull the missing required models (or the named subset). Idempotent; non-blocking."""
    global _pull_thread
    names, _ = _probe()
    if names is None:
        raise OllamaError("Ollama isn't running — start it first.")
    required = required_models()
    if models:
        bad = [m for m in models if m not in required]
        if bad:
            raise OllamaError(f"Not a model Celestia is configured to use: {', '.join(bad)}")
    missing = [m for m in required if _norm(m) not in names]
    wanted = [m for m in missing if not models or m in models]
    with _lock:
        busy = bool(_pull["active"])
        if not busy:
            if not wanted:
                raise OllamaError("Nothing to pull — the required models are already installed.")
            _pull.clear()
            _pull.update(_idle_pull())
            _pull.update(active=True, models=wanted, current=wanted[0])
    if not busy:  # status() takes the lock itself, so never call it from inside
        _pull_thread = threading.Thread(
            target=_pull_worker, args=(wanted,), daemon=True, name="ollama-pull"
        )
        _pull_thread.start()
    return status(use_cache=False)


def cancel_pull() -> dict[str, Any]:
    """Stop an in-flight pull (Ollama keeps the partial download, so it resumes)."""
    with _lock:
        if _pull["active"]:
            _pull["cancelled"] = True
    return status(use_cache=False)


# ---------------------------------------------------------------------------
# CLI prompt (terminal entry points; the shell has its own dialog)
# ---------------------------------------------------------------------------

def cli_gate() -> bool:
    """Terminal counterpart of the shell's launch dialog. True = carry on.

    Honours the same remembered choice: ``start`` starts without asking, ``skip``
    continues without Ollama, ``ask`` prompts — but only on a real terminal, so
    scripts and pipes are never blocked.
    """
    st = status(use_cache=False)
    if st["state"] == "running":
        return True
    choice = on_launch()
    if choice == "ask":
        if not (sys.stdin and sys.stdin.isatty()):
            return True
        print(f"[ollama] {st['message']}")
        options = "[S]tart Ollama / [C]ontinue without / [Q]uit" if st["can_start"] else "[C]ontinue without / [Q]uit"
        while True:
            try:
                answer = input(f"[ollama] {options}: ").strip().lower()
            except EOFError:  # stdin closed — nobody can answer, so behave as before the prompt existed
                return True
            except KeyboardInterrupt:
                return False
            if answer in ("q", "quit"):
                return False
            if answer in ("c", "continue", ""):
                return True
            if answer in ("s", "start") and st["can_start"]:
                choice = "start"
                break
    if choice == "skip" or not st["can_start"]:
        print(f"[ollama] {st['message']} Continuing without it — chat and memory are paused.")
        return True
    print("[ollama] starting…")
    after = start(block=True)
    print(f"[ollama] {after['message']}" if after["state"] != "running" else "[ollama] up.")
    if after["start_error"]:
        print(f"[ollama] {after['start_error']}")
    return True
