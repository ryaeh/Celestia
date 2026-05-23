"""Localhost HTTP API for the Tauri desktop shell (127.0.0.1 only)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from celestia_core.config import ROOT, get, load_config

_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None


def _json_response(handler: BaseHTTPRequestHandler, code: int, body: dict[str, Any]) -> None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(data)


def tail_audit(n: int = 20) -> list[dict[str, Any]]:
    rel = get("security.audit_log", "logs/tool_audit.jsonl")
    path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"raw": line[:200]})
    return out


def build_status() -> dict[str, Any]:
    from celestia_core import security
    from celestia_core.preflight import (
        check_memory,
        check_ollama,
        check_security,
        check_vision,
        check_voice,
    )

    load_config()
    check_fns = [check_ollama, check_memory, check_security, check_voice]
    if get("vision.enabled", False):
        check_fns.append(check_vision)
    checks = [fn() for fn in check_fns]
    ollama_ok = True
    for ok, msg in checks:
        if "ollama" in msg.lower():
            ollama_ok = ok
            break

    return {
        "display_name": get("app.display_name", "Celestia"),
        "mode": security.get_mode(),
        "mode_label": security.armed_status_label(),
        "tray_max_mode": security.get_tray_max_mode(),
        "personality": get("personality.active", "default"),
        "ollama_ok": ollama_ok,
        "checks": [{"ok": ok, "message": msg} for ok, msg in checks],
    }


class _ShellHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _client_ok(self) -> bool:
        host = self.client_address[0]
        return host in ("127.0.0.1", "::1")

    def do_OPTIONS(self) -> None:
        if not self._client_ok():
            self.send_error(403)
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._client_ok():
            self.send_error(403)
            return
        path = urlparse(self.path).path
        if path == "/status":
            _json_response(self, 200, build_status())
            return
        if path == "/workspaces":
            from celestia_core.scope import list_workspaces

            ws = [str(p) for p in list_workspaces()]
            _json_response(self, 200, {"workspaces": ws})
            return
        if path == "/audit/tail":
            qs = parse_qs(urlparse(self.path).query)
            n = int(qs.get("n", ["20"])[0])
            _json_response(self, 200, {"entries": tail_audit(n)})
            return
        if path == "/chat/history":
            from celestia_core.shell_chat import get_active_session_id, get_history

            qs = parse_qs(urlparse(self.path).query)
            sid = qs.get("session", [None])[0]
            if not sid or sid == "default":
                sid = get_active_session_id()
            _json_response(self, 200, {"messages": get_history(sid), "session_id": sid})
            return
        if path == "/chat/sessions":
            from celestia_core.shell_chat import get_active_session_id, list_sessions

            _json_response(
                self,
                200,
                {"sessions": list_sessions(), "active_id": get_active_session_id()},
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if not self._client_ok():
            self.send_error(403)
            return
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid JSON"})
            return

        if path == "/mode":
            from celestia_core import security

            mode = str(body.get("mode", "")).lower()
            if mode not in ("safe", "scoped", "armed"):
                _json_response(self, 400, {"error": "mode must be safe, scoped, or armed"})
                return
            security.set_mode(mode)
            _json_response(
                self,
                200,
                {"ok": True, "mode": security.get_mode(), "label": security.armed_status_label()},
            )
            return
        if path == "/chat":
            from celestia_core.shell_chat import send_message

            msg = str(body.get("message", "")).strip()
            sid_raw = body.get("session_id")
            sid = str(sid_raw) if sid_raw else None
            result = send_message(msg, session_id=sid, source="shell")
            if "error" in result:
                _json_response(self, 400, result)
                return
            _json_response(self, 200, result)
            return
        if path == "/chat/new":
            from celestia_core.shell_chat import create_session

            sid = create_session()
            _json_response(self, 200, {"ok": True, "session_id": sid, "messages": []})
            return
        if path == "/chat/select":
            from celestia_core.shell_chat import get_history, set_active_session

            sid = str(body.get("session_id", "")).strip()
            if not sid or not set_active_session(sid):
                _json_response(self, 400, {"error": "invalid session_id"})
                return
            _json_response(
                self,
                200,
                {"ok": True, "session_id": sid, "messages": get_history(sid)},
            )
            return
        self.send_error(404)


def default_port() -> int:
    load_config()
    return int(get("ui.shell_port", 8765))


def start_server(port: int | None = None, *, daemon: bool = True) -> int:
    """Start background HTTP server; returns bound port."""
    global _server, _server_thread
    load_config()
    p = port if port is not None else default_port()
    if _server is not None:
        return p
    _server = ThreadingHTTPServer(("127.0.0.1", p), _ShellHandler)
    actual = _server.server_address[1]

    def _run() -> None:
        assert _server is not None
        _server.serve_forever(poll_interval=0.5)

    _server_thread = threading.Thread(target=_run, name="celestia-shell-api", daemon=daemon)
    _server_thread.start()
    return actual


def stop_server() -> None:
    global _server, _server_thread
    if _server is not None:
        _server.shutdown()
        _server = None
    _server_thread = None


def run_server_forever(port: int | None = None) -> None:
    load_config()
    p = port if port is not None else default_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", p), _ShellHandler)
    print(f"[shell] API http://127.0.0.1:{httpd.server_address[1]}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
