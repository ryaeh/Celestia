"""Tests for celestia_core/shell_server.py — auth, mode, and session routes (B-05).

The FastAPI app is exercised via Starlette's TestClient. Heavy paths (Ollama,
mem0) are avoided or stubbed: build_status is replaced so /status needs no
preflight deps, and all on-disk state (security mode, chat sessions) is
redirected to a tmp dir so tests never touch the user's real data.
"""

import pytest

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient

from celestia_core import shell_server
from celestia_core import security as sec
from celestia_core import shell_chat

LOCAL_CLIENT = ("127.0.0.1", 50000)
REMOTE_CLIENT = ("10.0.0.5", 40000)

_FAKE_STATUS = {
    "display_name": "Test",
    "mode": "safe",
    "mode_label": "safe",
    "tray_max_mode": None,
    "personality": "default",
    "ollama_ok": True,
    "checks": [],
}


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """Redirect security state + chat sessions to tmp and stub build_status."""
    # Security mode -> tmp, shared-state on.
    monkeypatch.setattr(sec, "_state_path", lambda: tmp_path / "security_state.json")
    monkeypatch.setattr(sec, "_state_lock_path", lambda: tmp_path / ".sec.lock")
    monkeypatch.setattr(sec, "_use_shared_state", lambda: True)
    monkeypatch.setattr(sec, "_state_cache", None, raising=False)
    monkeypatch.setattr(sec, "_session_mode", None, raising=False)
    # Chat sessions -> tmp (everything derives from _store_path).
    monkeypatch.setattr(
        shell_chat, "_store_path", lambda: tmp_path / "shell_chat" / "sessions.json"
    )
    # /status without preflight deps.
    monkeypatch.setattr(shell_server, "build_status", lambda: dict(_FAKE_STATUS))
    monkeypatch.setattr(shell_server, "_status_cache", None, raising=False)
    return tmp_path


@pytest.fixture()
def client(isolated):
    return TestClient(shell_server.app, client=LOCAL_CLIENT)


@pytest.fixture()
def token():
    return shell_server._API_TOKEN


def auth(token):
    return {"X-Celestia-Token": token}


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def test_status_is_token_exempt(client):
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["display_name"] == "Test"


def test_token_endpoint_is_exempt(client):
    r = client.get("/token")
    assert r.status_code == 200
    assert r.json()["token"] == shell_server._API_TOKEN


def test_protected_route_without_token_is_401(client):
    r = client.get("/workspaces")
    assert r.status_code == 401


def test_protected_route_with_wrong_token_is_401(client):
    r = client.get("/workspaces", headers={"X-Celestia-Token": "nope"})
    assert r.status_code == 401


def test_protected_route_with_valid_token_passes(client, token):
    r = client.get("/workspaces", headers=auth(token))
    assert r.status_code == 200
    assert "workspaces" in r.json()


def test_remote_client_is_forbidden(isolated, token):
    remote = TestClient(shell_server.app, client=REMOTE_CLIENT)
    r = remote.get("/workspaces", headers=auth(token))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Token persistence (B-02)
# ---------------------------------------------------------------------------

def test_token_reused_from_file(monkeypatch, tmp_path):
    path = tmp_path / ".api_token"
    path.write_text("deadbeefcafe", encoding="utf-8")
    monkeypatch.setattr(shell_server, "_TOKEN_PATH", path)
    assert shell_server._load_or_create_token() == "deadbeefcafe"


def test_token_generated_when_absent(monkeypatch, tmp_path):
    path = tmp_path / ".api_token"  # does not exist
    monkeypatch.setattr(shell_server, "_TOKEN_PATH", path)
    tok = shell_server._load_or_create_token()
    assert len(tok) == 64 and tok != ""  # fresh 32-byte hex


def test_token_regenerated_when_file_empty(monkeypatch, tmp_path):
    path = tmp_path / ".api_token"
    path.write_text("   \n", encoding="utf-8")  # blank/whitespace
    monkeypatch.setattr(shell_server, "_TOKEN_PATH", path)
    assert len(shell_server._load_or_create_token()) == 64


def test_write_token_file_round_trips(monkeypatch, tmp_path):
    path = tmp_path / ".api_token"
    monkeypatch.setattr(shell_server, "_TOKEN_PATH", path)
    monkeypatch.setattr(shell_server, "_API_TOKEN", "persisted-token-value")
    shell_server._write_token_file()
    assert path.read_text(encoding="utf-8") == "persisted-token-value"
    # Reusing the same file yields the same token (no rotation across restart).
    assert shell_server._load_or_create_token() == "persisted-token-value"


# ---------------------------------------------------------------------------
# /mode
# ---------------------------------------------------------------------------

def test_set_mode_round_trip(client, token):
    r = client.post("/mode", json={"mode": "scoped"}, headers=auth(token))
    assert r.status_code == 200
    assert r.json()["mode"] == "scoped"
    # Mode is persisted and observable through the security module.
    assert sec.get_mode() == "scoped"


def test_set_mode_rejects_invalid_value(client, token):
    r = client.post("/mode", json={"mode": "superuser"}, headers=auth(token))
    assert r.status_code == 400
    assert "error" in r.json()


# ---------------------------------------------------------------------------
# Session CRUD (no Ollama — a fresh session has no history to consolidate)
# ---------------------------------------------------------------------------

def test_create_and_list_sessions(client, token):
    created = client.post("/chat/new", headers=auth(token))
    assert created.status_code == 200
    sid = created.json()["session_id"]
    assert sid

    listed = client.get("/chat/sessions", headers=auth(token))
    assert listed.status_code == 200
    ids = [s["id"] for s in listed.json()["sessions"]]
    assert sid in ids


def test_select_session_round_trip(client, token):
    sid = client.post("/chat/new", headers=auth(token)).json()["session_id"]
    r = client.post("/chat/select", json={"session_id": sid}, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == sid
    assert body["messages"] == []


def test_select_unknown_session_is_400(client, token):
    r = client.post(
        "/chat/select", json={"session_id": "does-not-exist"}, headers=auth(token)
    )
    assert r.status_code == 400
    assert "error" in r.json()


def test_cancel_with_no_active_stream_is_noop(client, token):
    sid = client.post("/chat/new", headers=auth(token)).json()["session_id"]
    r = client.post("/chat/cancel", json={"session_id": sid}, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["cancelled"] is False  # nothing was streaming
    assert body["session_id"] == sid


# ---------------------------------------------------------------------------
# Live state push WebSocket (UI V2 / F3) — /ws/state
# ---------------------------------------------------------------------------

from starlette.websockets import WebSocketDisconnect  # noqa: E402

_FAKE_STATE = {
    "mode": "safe",
    "mode_label": "safe",
    "incognito": False,
    "gpu_busy": False,
    "gpu_task": None,
}


def test_ws_state_rejects_without_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/state"):
            pass


def test_ws_state_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/state?token=nope"):
            pass


def test_ws_state_rejects_remote_client(isolated, token):
    remote = TestClient(shell_server.app, client=REMOTE_CLIENT)
    with pytest.raises(WebSocketDisconnect):
        with remote.websocket_connect(f"/ws/state?token={token}"):
            pass


def test_ws_state_pushes_initial_snapshot(client, token, monkeypatch):
    monkeypatch.setattr(shell_server, "_collect_state", lambda: dict(_FAKE_STATE))
    with client.websocket_connect(f"/ws/state?token={token}") as ws:
        frame = ws.receive_json()
    assert frame["type"] == "state"
    # First frame is the full snapshot.
    for key, value in _FAKE_STATE.items():
        assert frame[key] == value


def test_ws_state_pushes_only_changed_keys(client, token, monkeypatch):
    states = iter([dict(_FAKE_STATE), {**_FAKE_STATE, "gpu_busy": True, "gpu_task": "chat"}])
    last = {"v": dict(_FAKE_STATE)}

    def fake_collect():
        try:
            last["v"] = next(states)
        except StopIteration:
            pass  # hold the last value
        return dict(last["v"])

    monkeypatch.setattr(shell_server, "_collect_state", fake_collect)
    monkeypatch.setattr(shell_server, "_WS_POLL_INTERVAL", 0.01)

    with client.websocket_connect(f"/ws/state?token={token}") as ws:
        first = ws.receive_json()
        second = ws.receive_json()

    assert set(_FAKE_STATE).issubset(first)  # full snapshot first
    # Second frame carries only the keys that changed — not the unchanged ones.
    assert second == {"type": "state", "gpu_busy": True, "gpu_task": "chat"}
