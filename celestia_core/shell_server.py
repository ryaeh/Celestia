"""Localhost HTTP API for the Tauri desktop shell (127.0.0.1 only).

CC-88: Migrated from ThreadingHTTPServer to FastAPI + uvicorn.
CC-89: SSE streaming endpoint POST /chat/stream added.
CC-114: Per-session API auth token (X-Celestia-Token header).
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Generator

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from celestia_core.config import ROOT, get, load_config
from celestia_core import faillog as _faillog

_faillog.setup()

# ---------------------------------------------------------------------------
# Auth token (CC-114)
# Session-scoped random token written to data/.api_token at startup.
# All endpoints except /status and /token require X-Celestia-Token header.
# ---------------------------------------------------------------------------

_API_TOKEN: str = secrets.token_hex(32)
_TOKEN_PATH: Path = ROOT / "data" / ".api_token"

# Endpoints that don't require the token:
#   /status  — health check used by ensure-api.mjs before the frontend loads
#   /token   — bootstrap endpoint that returns the token to the frontend
_TOKEN_EXEMPT = {"/status", "/token"}


def _write_token_file() -> None:
    try:
        _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_PATH.write_text(_API_TOKEN, encoding="utf-8")
        _TOKEN_PATH.chmod(0o600)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Celestia Shell API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Celestia-Token"],
    expose_headers=["X-Celestia-Token"],
)


@app.middleware("http")
async def localhost_only(request: Request, call_next):
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1"):
        return Response("Forbidden", status_code=403)
    return await call_next(request)


@app.middleware("http")
async def require_token(request: Request, call_next):
    if request.url.path in _TOKEN_EXEMPT or request.method == "OPTIONS":
        return await call_next(request)
    token = request.headers.get("X-Celestia-Token", "")
    if not secrets.compare_digest(token, _API_TOKEN):
        return JSONResponse(status_code=401, content={"error": "invalid token"})
    return await call_next(request)


# ---------------------------------------------------------------------------
# Bootstrap: write token, expose via /token
# ---------------------------------------------------------------------------

@app.get("/token")
def get_api_token():
    """Return the session token. Localhost-only (enforced by middleware)."""
    return {"token": _API_TOKEN}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ModeBody(BaseModel):
    mode: str


class ChatBody(BaseModel):
    message: str
    session_id: str | None = None


class SelectSessionBody(BaseModel):
    session_id: str


class MemoryBody(BaseModel):
    text: str
    kind: str = "fact"


class MemoryPatch(BaseModel):
    text: str | None = None
    kind: str | None = None


class PttStopBody(BaseModel):
    session_id: str | None = None


class WorkspaceBody(BaseModel):
    path: str


class PrefPatch(BaseModel):
    key: str
    value: Any


class VisionAnalyzeBody(BaseModel):
    capture_id: str
    question: str = "Describe this screenshot."
    session_id: str | None = None


# ---------------------------------------------------------------------------
# Shared helpers (unchanged from original)
# ---------------------------------------------------------------------------

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
        "vision_enabled": bool(get("vision.enabled", False)),
        "checks": [{"ok": ok, "message": msg} for ok, msg in checks],
    }


def _memory_user_id() -> str:
    return get("app.user_id", "atlas_user")


def _memory_list_payload() -> dict[str, Any]:
    from skills.memory.store import get_all_entries
    return {"entries": get_all_entries(_memory_user_id(), limit=200)}


def _memory_last_session_payload() -> dict[str, Any]:
    from skills.memory.last_session import read_note
    return read_note()


def _memory_activity_payload(n: int = 30) -> dict[str, Any]:
    from skills.memory.activity_feed import tail
    return {"events": tail(n)}


# ---------------------------------------------------------------------------
# Routes — GET
# ---------------------------------------------------------------------------

@app.get("/status")
def get_status():
    return build_status()


@app.get("/prefs")
def get_prefs():
    from celestia_core.config import MUTABLE_PREF_KEYS, get, get_all_prefs
    saved = get_all_prefs()
    effective = {k: get(k) for k in MUTABLE_PREF_KEYS}
    return {"prefs": effective, "saved": saved}


@app.patch("/prefs")
def patch_pref(body: PrefPatch):
    from celestia_core.config import set_pref
    msg = set_pref(body.key, body.value)
    if not msg.startswith("ok"):
        return JSONResponse(status_code=400, content={"error": msg})
    return {"ok": True, "key": body.key, "value": body.value}


@app.post("/vision/capture")
def post_vision_capture():
    """Take a full-screen screenshot, store in ring buffer, return base64."""
    if not get("vision.enabled", False):
        return JSONResponse(status_code=400, content={"error": "Vision is disabled in config.yaml"})
    try:
        from skills.vision.capture import capture_fullscreen
        from skills.vision.history import push
        import base64
        from PIL import Image

        path = capture_fullscreen()
        entry_id = push(path)
        b64 = base64.b64encode(path.read_bytes()).decode()
        with Image.open(path) as img:
            w, h = img.size
        return {"id": entry_id, "base64": b64, "width": w, "height": h}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/vision/analyze")
def post_vision_analyze(body: VisionAnalyzeBody):
    """Run vision analysis on a captured screenshot and persist to chat session."""
    if not get("vision.enabled", False):
        return JSONResponse(status_code=400, content={"error": "Vision is disabled in config.yaml"})
    from skills.vision.history import get_path
    path = get_path(body.capture_id)
    if path is None:
        return JSONResponse(status_code=404, content={"error": "Capture not found"})
    try:
        from skills.vision.analyze import analyze_image
        from celestia_core.shell_chat import append_raw_turn

        answer = analyze_image(path, body.question)
        user_msg = f"[screenshot] {body.question}"
        result = append_raw_turn(user_msg, answer, session_id=body.session_id)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/vision/history")
def get_vision_history(n: int = 20):
    """Return the most-recent n screenshots from the ring buffer."""
    from skills.vision.history import list_entries
    return {"entries": list_entries(n)}


@app.get("/workspaces")
def get_workspaces():
    from celestia_core.scope import list_workspaces
    return {"workspaces": [str(p) for p in list_workspaces()]}


@app.post("/workspaces/add")
def post_add_workspace(body: WorkspaceBody):
    from celestia_core.scope import add_workspace, list_workspaces
    msg = add_workspace(body.path)
    return {"message": msg, "workspaces": [str(p) for p in list_workspaces()]}


@app.post("/workspaces/remove")
def post_remove_workspace(body: WorkspaceBody):
    from celestia_core.scope import remove_workspace, list_workspaces
    msg = remove_workspace(body.path)
    return {"message": msg, "workspaces": [str(p) for p in list_workspaces()]}


@app.get("/audit/tail")
def get_audit_tail(n: int = 50):
    return {"entries": tail_audit(n)}


@app.get("/chat/history")
def get_chat_history(session: str | None = None):
    from celestia_core.shell_chat import get_active_session_id, get_history
    sid = session if session and session != "default" else get_active_session_id()
    return {"messages": get_history(sid), "session_id": sid}


@app.get("/chat/sessions")
def get_chat_sessions():
    from celestia_core.shell_chat import get_active_session_id, list_sessions
    return {"sessions": list_sessions(), "active_id": get_active_session_id()}


@app.get("/chat/ptt/status")
def get_ptt_status():
    from celestia_core.shell_ptt import ptt_status
    return ptt_status()


@app.get("/memory")
def get_memory():
    return _memory_list_payload()


@app.get("/memory/last-session")
def get_memory_last_session():
    return _memory_last_session_payload()


@app.get("/memory/activity")
def get_memory_activity(n: int = 30):
    return _memory_activity_payload(n)


@app.get("/memory/{memory_id}")
def get_memory_entry(memory_id: str):
    from skills.memory.store import get_all_entries
    entry = next(
        (e for e in get_all_entries(_memory_user_id(), 200) if e["id"] == memory_id),
        None,
    )
    if not entry:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return entry


# ---------------------------------------------------------------------------
# Routes — POST
# ---------------------------------------------------------------------------

@app.post("/mode")
def post_mode(body: ModeBody):
    from celestia_core import security
    if body.mode not in ("safe", "scoped", "armed"):
        return JSONResponse(status_code=400, content={"error": "mode must be safe, scoped, or armed"})
    security.set_mode(body.mode)
    return {"ok": True, "mode": security.get_mode(), "label": security.armed_status_label()}


@app.post("/chat")
def post_chat(body: ChatBody):
    from celestia_core.shell_chat import send_message
    msg = body.message.strip()
    try:
        result = send_message(msg, session_id=body.session_id, source="shell")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result


@app.post("/chat/stream")
def post_chat_stream(body: ChatBody):
    """SSE streaming endpoint (CC-89).

    Yields:
        data: {"token": "..."}      — one event per Ollama token chunk
        data: {"done": true, "reply": "...", "session_id": "...", "messages": [...]}
        data: {"error": "..."}      — on LLM failure
    """
    from celestia_core.shell_chat import send_message_stream

    def _generate() -> Generator[str, None, None]:
        try:
            for event in send_message_stream(
                body.message.strip(),
                session_id=body.session_id,
                source="shell",
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/chat/new")
def post_chat_new():
    from celestia_core.shell_chat import create_session
    sid = create_session()
    return {"ok": True, "session_id": sid, "messages": []}


@app.post("/chat/select")
def post_chat_select(body: SelectSessionBody):
    from celestia_core.shell_chat import get_history, set_active_session
    sid = body.session_id.strip()
    if not sid or not set_active_session(sid):
        return JSONResponse(status_code=400, content={"error": "invalid session_id"})
    return {"ok": True, "session_id": sid, "messages": get_history(sid)}


@app.post("/chat/ptt/start")
def post_ptt_start():
    from celestia_core.shell_ptt import ptt_start
    result = ptt_start()
    code = 400 if "error" in result else 200
    return JSONResponse(status_code=code, content=result)


@app.post("/chat/ptt/stop")
def post_ptt_stop(body: PttStopBody):
    from celestia_core.shell_ptt import ptt_finish
    try:
        result = ptt_finish(session_id=body.session_id)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    code = 400 if "error" in result else 200
    return JSONResponse(status_code=code, content=result)


@app.post("/chat/ptt/cancel")
def post_ptt_cancel():
    from celestia_core.shell_ptt import ptt_cancel
    return ptt_cancel()


@app.post("/memory")
def post_memory(body: MemoryBody):
    from skills.memory.activity_feed import append_event
    from skills.memory.store import add
    text = body.text.strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "text required"})
    try:
        add(text, _memory_user_id(), kind=body.kind)
        append_event(action="saved", text=text, kind=body.kind, source="manual")
        return {"ok": True, **_memory_list_payload()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/memory/last-session/refresh")
def post_memory_last_session_refresh():
    from celestia_core.shell_chat import get_active_session_id, get_history
    from skills.memory.last_session import update_from_messages
    hist = get_history(get_active_session_id())
    update_from_messages(hist)
    return {"ok": True, **_memory_last_session_payload()}


# ---------------------------------------------------------------------------
# Routes — PATCH / DELETE
# ---------------------------------------------------------------------------

@app.patch("/memory/{memory_id}")
def patch_memory(memory_id: str, body: MemoryPatch):
    from skills.memory.store import update_entry
    result = update_entry(
        memory_id,
        text=body.text.strip() if body.text else None,
        kind=body.kind.strip() if body.kind else None,
        user_id=_memory_user_id(),
    )
    if result == "Memory not found.":
        return JSONResponse(status_code=404, content={"error": result})
    return {"ok": True, "message": result, **_memory_list_payload()}


@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: str):
    from skills.memory.store import delete_by_id
    result = delete_by_id(memory_id)
    if "failed" in result.lower():
        return JSONResponse(status_code=400, content={"error": result})
    return {"ok": True, "message": result, **_memory_list_payload()}


# ---------------------------------------------------------------------------
# Server lifecycle (same public interface as before)
# ---------------------------------------------------------------------------

_uvicorn_server: uvicorn.Server | None = None
_server_thread: threading.Thread | None = None


def default_port() -> int:
    load_config()
    return int(get("ui.shell_port", 8765))


def api_url(port: int | None = None) -> str:
    p = port if port is not None else default_port()
    return f"http://127.0.0.1:{p}"


def ping(port: int | None = None, *, timeout: float = 0.4) -> bool:
    """True if the shell API responds on localhost."""
    import urllib.error
    import urllib.request

    url = f"{api_url(port)}/status"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def start_server(port: int | None = None, *, daemon: bool = True) -> int:
    """Start FastAPI server in a background thread; returns bound port."""
    global _uvicorn_server, _server_thread
    load_config()
    _write_token_file()
    p = port if port is not None else default_port()

    if _uvicorn_server is not None and _uvicorn_server.started:
        return p

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=p,
        log_level="error",
        access_log=False,
    )
    _uvicorn_server = uvicorn.Server(config)
    _server_thread = threading.Thread(
        target=_uvicorn_server.run,
        name="celestia-shell-api",
        daemon=daemon,
    )
    _server_thread.start()

    # Wait up to 5 s for uvicorn to become ready
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _uvicorn_server.started:
            break
        time.sleep(0.05)

    try:
        from celestia_core.shell_ptt import start_global_hotkey_listener
        start_global_hotkey_listener()
    except Exception as e:
        print(f"[shell-ptt] hotkey listener skipped: {e}")

    return p


def stop_server() -> None:
    global _uvicorn_server, _server_thread
    if _uvicorn_server is not None:
        _uvicorn_server.should_exit = True
    _uvicorn_server = None
    _server_thread = None


def run_server_forever(port: int | None = None) -> None:
    load_config()
    _write_token_file()
    p = port if port is not None else default_port()
    print(f"[shell] API http://127.0.0.1:{p}", flush=True)
    try:
        from celestia_core.shell_ptt import start_global_hotkey_listener
        start_global_hotkey_listener()
    except Exception as e:
        print(f"[shell-ptt] hotkey listener skipped: {e}")
    uvicorn.run(app, host="127.0.0.1", port=p, log_level="error", access_log=False)
