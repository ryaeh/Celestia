"""Shell API for the Ollama launch gate — /ollama/*, /status, and the friendly 503.

The service itself is covered in test_ollama_service.py; here ``ollama_service`` is
stubbed so these tests only check the HTTP layer: auth, status codes, body shapes.
"""

import pytest

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient

from celestia_core import ollama_service, shell_server

LOCAL_CLIENT = ("127.0.0.1", 50000)

# Captured at import, before any test can monkeypatch it.
_REAL_BUILD_STATUS = shell_server.build_status


def _status(state="down", **over):
    base = {
        "state": state,
        "reachable": state in ("running", "missing_models"),
        "host": "http://127.0.0.1:11434",
        "local": True,
        "can_start": state == "down",
        "required": ["qwen2.5:3b", "nomic-embed-text"],
        "missing": [],
        "chat_ready": state == "running",
        "message": state,
        "error": None,
        "start_error": None,
        "pull": {"active": False},
        "on_launch": "ask",
        "download_url": "https://ollama.com/download",
    }
    base.update(over)
    return base


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(shell_server, "_status_cache", None, raising=False)
    return TestClient(shell_server.app, client=LOCAL_CLIENT)


@pytest.fixture()
def hdr():
    return {"X-Celestia-Token": shell_server._API_TOKEN}


# ---------------------------------------------------------------------------
# /ollama/status
# ---------------------------------------------------------------------------


def test_ollama_status_requires_the_token(client):
    assert client.get("/ollama/status").status_code == 401


def test_ollama_status_returns_the_service_status(client, hdr, monkeypatch):
    monkeypatch.setattr(ollama_service, "status", lambda **kw: _status("down"))
    r = client.get("/ollama/status", headers=hdr)
    assert r.status_code == 200
    assert r.json()["state"] == "down"
    assert r.json()["can_start"] is True


# ---------------------------------------------------------------------------
# /ollama/start
# ---------------------------------------------------------------------------


def test_start_requires_the_token(client):
    assert client.post("/ollama/start").status_code == 401


def test_start_returns_the_new_status(client, hdr, monkeypatch):
    monkeypatch.setattr(ollama_service, "start", lambda **kw: _status("starting", can_start=False))
    r = client.post("/ollama/start", headers=hdr)
    assert r.status_code == 200
    assert r.json()["state"] == "starting"


def test_start_refusal_is_a_400_with_the_reason(client, hdr, monkeypatch):
    def refuse(**kw):
        raise ollama_service.OllamaError("Ollama isn't installed — get it from https://ollama.com/download")

    monkeypatch.setattr(ollama_service, "start", refuse)
    r = client.post("/ollama/start", headers=hdr)
    assert r.status_code == 400
    assert "isn't installed" in r.json()["error"]


def test_start_clears_the_cached_status(client, hdr, monkeypatch):
    shell_server._status_cache = (1e12, {"stale": True})
    monkeypatch.setattr(ollama_service, "start", lambda **kw: _status("starting"))
    client.post("/ollama/start", headers=hdr)
    assert shell_server._status_cache is None


# ---------------------------------------------------------------------------
# /ollama/pull
# ---------------------------------------------------------------------------


def test_pull_defaults_to_every_missing_model(client, hdr, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ollama_service, "start_pull", lambda models=None: seen.append(models) or _status("missing_models")
    )
    r = client.post("/ollama/pull", headers=hdr, json={})
    assert r.status_code == 200
    assert seen == [None]


def test_pull_passes_the_requested_models(client, hdr, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ollama_service, "start_pull", lambda models=None: seen.append(models) or _status("missing_models")
    )
    client.post("/ollama/pull", headers=hdr, json={"models": ["nomic-embed-text"]})
    assert seen == [["nomic-embed-text"]]


def test_pull_refusal_is_a_400(client, hdr, monkeypatch):
    def refuse(models=None):
        raise ollama_service.OllamaError("Not a model Celestia is configured to use: gpt-oss:120b")

    monkeypatch.setattr(ollama_service, "start_pull", refuse)
    r = client.post("/ollama/pull", headers=hdr, json={"models": ["gpt-oss:120b"]})
    assert r.status_code == 400
    assert "configured to use" in r.json()["error"]


def test_pull_cancel(client, hdr, monkeypatch):
    monkeypatch.setattr(ollama_service, "cancel_pull", lambda: _status("missing_models"))
    r = client.post("/ollama/pull/cancel", headers=hdr)
    assert r.status_code == 200
    assert r.json()["state"] == "missing_models"


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state, ok", [("running", True), ("down", False), ("starting", False), ("missing_models", False)]
)
def test_build_status_derives_ollama_ok_from_the_service_state(monkeypatch, state, ok):
    from celestia_core import preflight, security

    # Hermetic: a developer's config.yaml may enable vision, which would probe a real Ollama.
    monkeypatch.setattr(shell_server, "load_config", lambda *a, **k: {})
    monkeypatch.setattr(shell_server, "get", lambda key, default=None: default)
    monkeypatch.setattr(ollama_service, "status", lambda **kw: _status(state))
    monkeypatch.setattr(preflight, "check_ollama", lambda: (ok, "Ollama"))
    monkeypatch.setattr(preflight, "check_memory", lambda: (True, "Memory"))
    monkeypatch.setattr(preflight, "check_security", lambda: (True, "Security"))
    monkeypatch.setattr(preflight, "check_voice", lambda: (True, "Voice"))
    monkeypatch.setattr(preflight, "check_vision", lambda: pytest.fail("vision is off in this test"))
    monkeypatch.setattr(security, "get_mode", lambda: "safe")
    monkeypatch.setattr(security, "armed_status_label", lambda: "safe")
    monkeypatch.setattr(security, "get_tray_max_mode", lambda: None)

    st = _REAL_BUILD_STATUS()
    assert st["ollama_ok"] is ok
    assert st["ollama_state"] == state
    assert [c["message"] for c in st["checks"]] == ["Ollama", "Memory", "Security", "Voice"]


# ---------------------------------------------------------------------------
# Friendly 503 when an endpoint can't reach Ollama
# ---------------------------------------------------------------------------


def test_connection_error_while_ollama_is_down_is_a_friendly_503(client, hdr, monkeypatch):
    def boom():
        raise ConnectionError("Failed to connect to Ollama.")

    monkeypatch.setattr(shell_server, "_memory_list_payload", boom)
    monkeypatch.setattr(ollama_service, "status", lambda **kw: _status("down"))
    r = client.get("/memory", headers=hdr)
    assert r.status_code == 503
    assert r.json()["code"] == "ollama_down"
    assert "Ollama isn't running" in r.json()["error"]


def test_connection_error_while_ollama_is_up_is_not_blamed_on_ollama(client, hdr, monkeypatch):
    def boom():
        raise ConnectionError("some other socket died")

    monkeypatch.setattr(shell_server, "_memory_list_payload", boom)
    monkeypatch.setattr(ollama_service, "status", lambda **kw: _status("running"))
    r = client.get("/memory", headers=hdr)
    assert r.status_code == 502
    assert "code" not in r.json()
    assert "some other socket died" in r.json()["error"]
