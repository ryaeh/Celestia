"""Tests for celestia_core/ollama_service.py — probe, start, pull, CLI prompt.

Nothing here needs Ollama: the HTTP probe, subprocess.Popen and the ollama client
are all replaced, and the module's global state is reset around every test.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import requests

from celestia_core import ollama_service as svc

CHAT = "qwen2.5:3b"
EMBED = "nomic-embed-text"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Fixed config, fresh module state, and instant polling."""
    cfg: dict[str, Any] = {
        "llm.host": "http://127.0.0.1:11434",
        "llm.chat_model": CHAT,
        "llm.embed_model": EMBED,
    }
    monkeypatch.setattr(svc, "get", lambda key, default=None: cfg.get(key, default))
    monkeypatch.setattr(svc, "_START_POLL", 0)
    monkeypatch.setattr(svc, "_probe_cache", None)
    monkeypatch.setattr(svc, "_start", {"active": False, "error": None})
    monkeypatch.setattr(svc, "_pull", svc._idle_pull())
    monkeypatch.setattr(svc, "_start_thread", None)
    monkeypatch.setattr(svc, "_pull_thread", None)
    monkeypatch.setattr(svc, "find_exe", lambda: Path("C:/Ollama/ollama.exe"))
    return cfg


def _up(*names: str):
    """Probe stub: reachable, with exactly these (normalised) models installed."""
    got = {svc._norm(n) for n in names}
    return lambda: (set(got), None)


def _down():
    return lambda: (None, "connection refused")


# ---------------------------------------------------------------------------
# Model-name matching
# ---------------------------------------------------------------------------


def test_norm_adds_latest_to_bare_names_only():
    assert svc._norm("nomic-embed-text") == "nomic-embed-text:latest"
    assert svc._norm("Qwen2.5:3B") == "qwen2.5:3b"
    assert svc._norm("hf.co/user/model") == "hf.co/user/model:latest"
    assert svc._norm("hf.co/user/model:Q4") == "hf.co/user/model:q4"


def test_running_when_every_required_model_is_installed(monkeypatch):
    monkeypatch.setattr(svc, "_probe", _up(CHAT, "nomic-embed-text:latest"))
    st = svc.status(use_cache=False)
    assert st["state"] == "running"
    assert st["chat_ready"] is True
    assert st["missing"] == []
    assert st["can_start"] is False  # already up


def test_other_tag_of_the_same_model_does_not_count(monkeypatch):
    # The old check matched on the base name, so qwen2.5:7b "satisfied" qwen2.5:3b.
    monkeypatch.setattr(svc, "_probe", _up("qwen2.5:7b", EMBED))
    st = svc.status(use_cache=False)
    assert st["state"] == "missing_models"
    assert st["missing"] == [CHAT]
    assert st["chat_ready"] is False


def test_embed_missing_still_lets_chat_run(monkeypatch):
    monkeypatch.setattr(svc, "_probe", _up(CHAT))
    st = svc.status(use_cache=False)
    assert st["state"] == "missing_models"
    assert st["missing"] == [EMBED]
    assert st["chat_ready"] is True


# ---------------------------------------------------------------------------
# Down / not installed / remote
# ---------------------------------------------------------------------------


def test_down_with_exe_can_be_started(monkeypatch):
    monkeypatch.setattr(svc, "_probe", _down())
    st = svc.status(use_cache=False)
    assert st["state"] == "down"
    assert st["reachable"] is False
    assert st["can_start"] is True
    assert st["error"] == "connection refused"


def test_not_installed_when_no_exe_is_found(monkeypatch):
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(svc, "find_exe", lambda: None)
    st = svc.status(use_cache=False)
    assert st["state"] == "not_installed"
    assert st["can_start"] is False


def test_remote_host_is_down_but_never_startable(monkeypatch, _isolate):
    _isolate["llm.host"] = "http://gpu-box.lan:11434"
    monkeypatch.setattr(svc, "_probe", _down())
    st = svc.status(use_cache=False)
    assert st["state"] == "down"
    assert st["local"] is False
    assert st["can_start"] is False
    assert "gpu-box.lan" in st["message"]


def test_status_probe_is_cached_briefly(monkeypatch):
    calls = []

    def probe():
        calls.append(1)
        return set(), None

    monkeypatch.setattr(svc, "_probe", probe)
    svc.status()
    svc.status()
    assert len(calls) == 1
    svc.status(use_cache=False)
    assert len(calls) == 2


def test_probe_reads_installed_names_from_api_tags(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "qwen2.5:3b"}, {"model": "nomic-embed-text:latest"}]}

    monkeypatch.setattr(requests, "get", lambda url, timeout: Resp())
    names, err = svc._probe()
    assert err is None
    assert names == {"qwen2.5:3b", "nomic-embed-text:latest"}


def test_local_probe_fails_fast_but_gives_a_busy_server_time_to_answer(monkeypatch, _isolate):
    """Refused localhost connects hang for the whole connect timeout on Windows, so
    "Ollama is off" would cost 2 s a probe — keep connect short, read generous."""
    seen = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": []}

    monkeypatch.setattr(requests, "get", lambda url, timeout: seen.append(timeout) or Resp())
    svc._probe()
    _isolate["llm.host"] = "http://gpu-box.lan:11434"
    svc._probe()
    (local_connect, local_read), (remote_connect, remote_read) = seen
    assert local_connect <= 1.0 and local_read >= 3.0
    assert remote_connect > local_connect and remote_read >= 3.0


def test_probe_returns_the_error_when_unreachable(monkeypatch):
    def boom(url, timeout):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", boom)
    names, err = svc._probe()
    assert names is None
    assert "refused" in err


# ---------------------------------------------------------------------------
# find_exe
# ---------------------------------------------------------------------------


def test_find_exe_prefers_override_then_path_then_default_dir(monkeypatch, tmp_path, _isolate):
    monkeypatch.undo()  # drop the autouse find_exe stub for this test
    monkeypatch.setattr(svc, "get", lambda key, default=None: _isolate.get(key, default))
    override = tmp_path / "custom" / "ollama.exe"
    on_path = tmp_path / "path" / "ollama.exe"
    default = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    for p in (override, on_path, default):
        p.parent.mkdir(parents=True)
        p.write_text("")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(svc.shutil, "which", lambda name: str(on_path))

    _isolate["llm.ollama_path"] = str(override)
    assert svc.find_exe() == override
    del _isolate["llm.ollama_path"]
    assert svc.find_exe() == on_path
    monkeypatch.setattr(svc.shutil, "which", lambda name: None)
    assert svc.find_exe() == default
    default.unlink()
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    assert svc.find_exe() is None


# ---------------------------------------------------------------------------
# is_connection_error
# ---------------------------------------------------------------------------


def test_connection_errors_are_recognised_through_the_cause_chain():
    assert svc.is_connection_error(ConnectionError("x"))
    assert svc.is_connection_error(requests.ConnectionError("x"))
    assert svc.is_connection_error(httpx.ConnectError("x"))
    try:
        try:
            raise httpx.ConnectError("refused")
        except httpx.ConnectError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert svc.is_connection_error(outer)


def test_a_slow_model_or_plain_error_is_not_a_connection_error():
    assert not svc.is_connection_error(None)
    assert not svc.is_connection_error(ValueError("bad"))
    assert not svc.is_connection_error(httpx.ReadTimeout("model is just slow"))


# ---------------------------------------------------------------------------
# on_launch preference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [("ask", "ask"), ("START", "start"), (" skip ", "skip"), ("bogus", "ask"), (None, "ask"), ("", "ask")],
)
def test_on_launch_normalises_to_a_known_choice(_isolate, raw, expected):
    _isolate[svc.PREF_ON_LAUNCH] = raw
    assert svc.on_launch() == expected


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class _Popen:
    calls: list[tuple[list[str], dict]] = []

    def __init__(self, cmd, **kwargs):
        _Popen.calls.append((cmd, kwargs))


@pytest.fixture()
def popen(monkeypatch):
    _Popen.calls = []
    monkeypatch.setattr(svc.subprocess, "Popen", _Popen)
    return _Popen


def test_start_is_a_noop_when_ollama_already_answers(monkeypatch, popen):
    monkeypatch.setattr(svc, "_probe", _up(CHAT, EMBED))
    assert svc.start(block=True)["state"] == "running"
    assert popen.calls == []


def test_start_launches_serve_detached_and_waits_for_it(monkeypatch, popen):
    answers = iter([(None, "refused"), (None, "refused"), (None, "refused")])

    def probe():  # down for the status check + two polls, then up
        return next(answers, ({svc._norm(CHAT), svc._norm(EMBED)}, None))

    monkeypatch.setattr(svc, "_probe", probe)
    st = svc.start(block=True)

    assert st["state"] == "running"
    assert st["start_error"] is None
    (cmd, kwargs), = popen.calls
    assert cmd == [str(Path("C:/Ollama/ollama.exe")), "serve"]
    assert kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert kwargs["stdout"] is svc.subprocess.DEVNULL
    if sys.platform == "win32":
        assert kwargs["creationflags"] & 0x08000000  # CREATE_NO_WINDOW


def test_start_binds_to_the_configured_port(monkeypatch, popen, _isolate):
    _isolate["llm.host"] = "http://localhost:11555"
    answers = iter([(None, "refused")])
    monkeypatch.setattr(svc, "_probe", lambda: next(answers, (set(), None)))
    svc.start(block=True)
    assert popen.calls[0][1]["env"]["OLLAMA_HOST"] == "localhost:11555"


def test_start_twice_launches_only_one_process(monkeypatch, popen):
    monkeypatch.setattr(svc, "_probe", _down())
    svc._start["active"] = True  # a launch is already in flight
    st = svc.start()
    assert popen.calls == []
    assert st["state"] == "starting"


def test_start_reports_a_timeout(monkeypatch, popen):
    monkeypatch.setattr(svc, "_probe", _down())
    st = svc.start(block=True, timeout=0.05)
    assert st["state"] == "down"
    assert "didn't answer" in st["start_error"]
    assert len(popen.calls) == 1
    assert svc._start["active"] is False  # a retry is allowed


def test_start_reports_a_launch_failure(monkeypatch):
    def broken(cmd, **kwargs):
        raise PermissionError("blocked by policy")

    monkeypatch.setattr(svc.subprocess, "Popen", broken)
    monkeypatch.setattr(svc, "_probe", _down())
    st = svc.start(block=True)
    assert "blocked by policy" in st["start_error"]
    assert svc._start["active"] is False


def test_status_leaves_probing_to_the_worker_while_a_start_is_in_flight(monkeypatch):
    """A booting server accepts connections but stalls /api/tags for seconds; request
    threads must not pile onto that — they read the worker's latest probe instead."""
    import time

    monkeypatch.setattr(svc, "_probe_cache", (time.monotonic() - 100, (None, "refused")))  # long stale
    svc._start["active"] = True
    monkeypatch.setattr(svc, "_probe", lambda: pytest.fail("the start worker owns probing"))
    st = svc.status()
    assert st["state"] == "starting"
    assert st["can_start"] is False


def test_start_refuses_a_remote_host(monkeypatch, popen, _isolate):
    _isolate["llm.host"] = "http://gpu-box.lan:11434"
    monkeypatch.setattr(svc, "_probe", _down())
    with pytest.raises(svc.OllamaError, match="not this PC"):
        svc.start()
    assert popen.calls == []


def test_start_refuses_when_not_installed(monkeypatch, popen):
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(svc, "find_exe", lambda: None)
    with pytest.raises(svc.OllamaError, match="isn't installed"):
        svc.start()
    assert popen.calls == []


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


class _FakeClient:
    """Stands in for ollama.Client; ``script`` maps model -> chunk list or an exception."""

    script: dict[str, Any] = {}
    pulled: list[str] = []

    def __init__(self, host=None, timeout=None):
        pass

    def pull(self, model, stream=False):
        _FakeClient.pulled.append(model)
        plan = _FakeClient.script[model]
        if isinstance(plan, Exception):
            raise plan
        return iter(plan)


@pytest.fixture()
def fake_pull(monkeypatch):
    import ollama

    _FakeClient.script = {}
    _FakeClient.pulled = []
    monkeypatch.setattr(ollama, "Client", _FakeClient)
    return _FakeClient


def _wait_pull():
    thread = svc._pull_thread
    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_pull_needs_ollama_running(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _down())
    with pytest.raises(svc.OllamaError, match="start it first"):
        svc.start_pull()


def test_pull_rejects_models_celestia_does_not_use(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up())
    with pytest.raises(svc.OllamaError, match="Not a model Celestia is configured to use"):
        svc.start_pull(["llama3.1:405b"])
    assert fake_pull.pulled == []


def test_pull_with_nothing_missing_is_refused(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up(CHAT, EMBED))
    with pytest.raises(svc.OllamaError, match="Nothing to pull"):
        svc.start_pull()


def test_pull_downloads_each_missing_model_and_tracks_progress(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up())
    fake_pull.script = {
        CHAT: [
            {"status": "pulling manifest"},
            {"status": "pulling aaa", "digest": "aaa", "completed": 50, "total": 100},
            {"status": "pulling bbb", "digest": "bbb", "completed": 50, "total": 100},
            {"status": "success"},
        ],
        EMBED: [{"status": "success"}],
    }
    st = svc.start_pull()
    assert st["pull"]["models"] == [CHAT, EMBED]
    _wait_pull()

    assert fake_pull.pulled == [CHAT, EMBED]
    pull = svc.status(use_cache=False)["pull"]
    assert pull["active"] is False and pull["finished"] is True
    assert pull["error"] is None


def test_pull_percent_aggregates_layers(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up(EMBED))
    fake_pull.script = {
        CHAT: [
            {"status": "pulling aaa", "digest": "aaa", "completed": 50, "total": 100},
            {"status": "pulling bbb", "digest": "bbb", "completed": 150, "total": 300},
        ],
    }
    svc.start_pull([CHAT])
    _wait_pull()
    pull = svc.status(use_cache=False)["pull"]
    assert (pull["completed"], pull["total"], pull["percent"]) == (200, 400, 50)


def test_pull_only_requested_models(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up())
    fake_pull.script = {EMBED: [{"status": "success"}]}
    svc.start_pull([EMBED])
    _wait_pull()
    assert fake_pull.pulled == [EMBED]


def test_pull_failure_is_reported_not_raised(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up(EMBED))
    fake_pull.script = {CHAT: RuntimeError("pull model manifest: file does not exist")}
    svc.start_pull()
    _wait_pull()
    pull = svc.status(use_cache=False)["pull"]
    assert pull["finished"] is True
    assert "file does not exist" in pull["error"]


def test_pull_when_ollama_dies_mid_download_says_so(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up(EMBED))
    fake_pull.script = {CHAT: ConnectionError("gone")}
    svc.start_pull()
    _wait_pull()
    assert svc.status(use_cache=False)["pull"]["error"] == svc.DOWN_MESSAGE


def test_cancel_stops_before_the_next_model(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up())

    def stream():
        yield {"status": "pulling aaa", "digest": "aaa", "completed": 1, "total": 10}
        svc.cancel_pull()  # user hits Cancel while the first model is downloading
        yield {"status": "pulling aaa", "digest": "aaa", "completed": 2, "total": 10}

    fake_pull.script = {CHAT: stream(), EMBED: [{"status": "success"}]}
    svc.start_pull()
    _wait_pull()

    assert fake_pull.pulled == [CHAT]  # EMBED never started
    pull = svc.status(use_cache=False)["pull"]
    assert pull["cancelled"] is True and pull["finished"] is True and pull["active"] is False


def test_second_pull_while_one_runs_is_ignored(monkeypatch, fake_pull):
    monkeypatch.setattr(svc, "_probe", _up())
    svc._pull.update(active=True, models=[CHAT], current=CHAT)
    st = svc.start_pull()
    assert st["pull"]["active"] is True
    assert fake_pull.pulled == []


# ---------------------------------------------------------------------------
# cli_gate
# ---------------------------------------------------------------------------


class _Tty:
    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture()
def started(monkeypatch):
    calls = []

    def fake_start(*, block=False, timeout=None):
        calls.append(block)
        return {"state": "running", "message": "up", "start_error": None}

    monkeypatch.setattr(svc, "start", fake_start)
    return calls


def test_cli_gate_passes_straight_through_when_up(monkeypatch, started):
    monkeypatch.setattr(svc, "_probe", _up(CHAT, EMBED))
    assert svc.cli_gate() is True
    assert started == []


def test_cli_gate_never_blocks_a_non_terminal(monkeypatch, started):
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(sys, "stdin", _Tty(False))
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("must not prompt"))
    assert svc.cli_gate() is True
    assert started == []


@pytest.mark.parametrize(
    "answer, carry_on, start_calls",
    [("s", True, 1), ("start", True, 1), ("c", True, 0), ("", True, 0), ("q", False, 0)],
)
def test_cli_gate_prompt_choices(monkeypatch, started, answer, carry_on, start_calls):
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(sys, "stdin", _Tty(True))
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)
    assert svc.cli_gate() is carry_on
    assert len(started) == start_calls


def test_cli_gate_closed_stdin_carries_on_but_ctrl_c_quits(monkeypatch, started):
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(sys, "stdin", _Tty(True))

    def eof(prompt=""):
        raise EOFError

    def ctrl_c(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", eof)
    assert svc.cli_gate() is True  # nobody can answer — behave as before the prompt existed
    monkeypatch.setattr("builtins.input", ctrl_c)
    assert svc.cli_gate() is False
    assert started == []


def test_check_ollama_says_why_in_plain_words(monkeypatch):
    from celestia_core import preflight

    monkeypatch.setattr(svc, "_probe", lambda: (None, "HTTPConnectionPool(host='127.0.0.1') Max retries..."))
    ok, msg = preflight.check_ollama()
    assert ok is False
    assert "Ollama isn't running." in msg
    assert "HTTPConnectionPool" not in msg


def test_check_ollama_lists_the_pull_commands_for_missing_models(monkeypatch):
    from celestia_core import preflight

    monkeypatch.setattr(svc, "_probe", _up())
    ok, msg = preflight.check_ollama()
    assert ok is False
    assert f"ollama pull {CHAT}" in msg and f"ollama pull {EMBED}" in msg


def test_cli_gate_remembered_start_does_not_ask(monkeypatch, started, _isolate):
    _isolate[svc.PREF_ON_LAUNCH] = "start"
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(sys, "stdin", _Tty(True))
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("must not prompt"))
    assert svc.cli_gate() is True
    assert started == [True]  # blocks until Ollama answers


def test_cli_gate_remembered_skip_carries_on_without_starting(monkeypatch, started, _isolate):
    _isolate[svc.PREF_ON_LAUNCH] = "skip"
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(sys, "stdin", _Tty(True))
    assert svc.cli_gate() is True
    assert started == []


def test_cli_gate_cannot_start_a_missing_install(monkeypatch, started, _isolate):
    _isolate[svc.PREF_ON_LAUNCH] = "start"
    monkeypatch.setattr(svc, "_probe", _down())
    monkeypatch.setattr(svc, "find_exe", lambda: None)
    assert svc.cli_gate() is True
    assert started == []
