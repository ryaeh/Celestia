"""Tests for skills/pc_control/tools.py — _run_ps() timeout, denylist, truncation."""

import subprocess
from subprocess import CompletedProcess
from unittest.mock import MagicMock

import pytest

import celestia_core.config as _cfg
from skills.pc_control.tools import _run_ps, execute_pc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fast_config(monkeypatch):
    """Inject fast config defaults so tests don't touch config.yaml on disk."""
    monkeypatch.setattr(
        _cfg,
        "get",
        lambda key, default=None: {
            "pc_control.powershell_timeout_seconds": 5,
            "pc_control.powershell_output_max_chars": 200,
        }.get(key, default),
    )


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    p = MagicMock(spec=CompletedProcess)
    p.stdout = stdout
    p.stderr = stderr
    p.returncode = returncode
    return p


# ---------------------------------------------------------------------------
# Denylist — no subprocess needed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "Remove-Item -Recurse C:\\temp",
        "iex (Invoke-WebRequest x)",
        "Format-Volume D:",
        "shutdown /s /t 0",
        "Invoke-Expression 'rm -r C:\\'",
        "powershell -EncodedCommand abc123",
    ],
)
def test_blocked_commands_return_blocked(cmd: str) -> None:
    result = _run_ps(cmd)
    assert result == "Blocked: command matches safety denylist."


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_timeout_returns_blocked_message(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=5)

    monkeypatch.setattr(subprocess, "run", _raise)
    result = _run_ps("Get-ChildItem C:\\")
    assert "timed out" in result
    assert "Blocked" in result


def test_timeout_message_includes_timeout_seconds(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=5)

    monkeypatch.setattr(subprocess, "run", _raise)
    result = _run_ps("Get-Process")
    assert "5s" in result


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_success_returns_stripped_stdout(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _proc(stdout="  C:\\Users  "))
    assert _run_ps("pwd") == "C:\\Users"


def test_empty_stdout_returns_placeholder(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _proc(stdout=""))
    assert _run_ps("echo nothing") == "(no output)"


def test_nonzero_exit_includes_code_and_stderr(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _proc(stderr="Access denied.", returncode=1),
    )
    result = _run_ps("Get-Item C:\\protected")
    assert "Exit 1" in result
    assert "Access denied" in result


def test_nonzero_exit_uses_stdout_when_no_stderr(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: _proc(stdout="something failed", returncode=2),
    )
    result = _run_ps("some-cmd")
    assert "Exit 2" in result
    assert "something failed" in result


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------


def test_long_output_is_truncated(monkeypatch) -> None:
    big = "X" * 300  # exceeds max_chars=200
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _proc(stdout=big))
    result = _run_ps("Get-Content huge.txt")
    assert "truncated" in result
    assert len(result) < 400  # must be substantially shorter than the raw output


def test_truncation_appends_total_char_count(monkeypatch) -> None:
    big = "Y" * 500
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _proc(stdout=big))
    result = _run_ps("Get-Content big.txt")
    assert "500" in result  # total char count reported in truncation note


def test_output_within_limit_is_not_truncated(monkeypatch) -> None:
    short = "ok result"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _proc(stdout=short))
    result = _run_ps("Get-Date")
    assert result == "ok result"
    assert "truncated" not in result


# ---------------------------------------------------------------------------
# execute_pc dispatch
# ---------------------------------------------------------------------------


def test_execute_pc_unknown_tool_returns_error() -> None:
    result = execute_pc("totally_unknown_tool_xyz", {})
    assert "Unknown" in result
