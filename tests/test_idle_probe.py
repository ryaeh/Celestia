"""Tests for celestia_core/idle_probe.py — system AFK + GPU-utilization probes."""

from __future__ import annotations

import subprocess
import sys

import celestia_core.idle_probe as ip


# ---------------------------------------------------------------------------
# gpu_utilization
# ---------------------------------------------------------------------------


def test_gpu_utilization_parses_nvidia_smi(monkeypatch) -> None:
    class _Proc:
        returncode = 0
        stdout = "37\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    assert ip.gpu_utilization() == 37


def test_gpu_utilization_none_when_unavailable(monkeypatch) -> None:
    def _missing(*a, **k):
        raise FileNotFoundError("nvidia-smi not found")

    monkeypatch.setattr(subprocess, "run", _missing)
    assert ip.gpu_utilization() is None


def test_gpu_utilization_none_on_nonzero_exit(monkeypatch) -> None:
    class _Proc:
        returncode = 9
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    assert ip.gpu_utilization() is None


# ---------------------------------------------------------------------------
# user_idle_seconds
# ---------------------------------------------------------------------------


def test_user_idle_seconds_on_windows_is_nonnegative() -> None:
    if sys.platform != "win32":
        return  # covered by the non-windows test below
    val = ip.user_idle_seconds()
    assert val is None or (isinstance(val, float) and val >= 0.0)


def test_user_idle_seconds_none_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(ip.sys, "platform", "linux")
    assert ip.user_idle_seconds() is None


# ---------------------------------------------------------------------------
# system_is_idle
# ---------------------------------------------------------------------------


def test_idle_when_afk_and_gpu_quiet(monkeypatch) -> None:
    monkeypatch.setattr(ip, "user_idle_seconds", lambda: 900.0)
    monkeypatch.setattr(ip, "gpu_utilization", lambda: 5)
    assert ip.system_is_idle(min_afk_seconds=600, max_gpu_utilization=20) is True


def test_not_idle_when_user_active(monkeypatch) -> None:
    monkeypatch.setattr(ip, "user_idle_seconds", lambda: 30.0)
    monkeypatch.setattr(ip, "gpu_utilization", lambda: 0)
    assert ip.system_is_idle(min_afk_seconds=600, max_gpu_utilization=20) is False


def test_not_idle_when_gpu_busy(monkeypatch) -> None:
    monkeypatch.setattr(ip, "user_idle_seconds", lambda: 900.0)
    monkeypatch.setattr(ip, "gpu_utilization", lambda: 85)
    assert ip.system_is_idle(min_afk_seconds=600, max_gpu_utilization=20) is False


def test_unknown_afk_is_conservative(monkeypatch) -> None:
    monkeypatch.setattr(ip, "user_idle_seconds", lambda: None)
    monkeypatch.setattr(ip, "gpu_utilization", lambda: 0)
    assert ip.system_is_idle(min_afk_seconds=600, max_gpu_utilization=20) is False


def test_unknown_gpu_util_is_permissive(monkeypatch) -> None:
    # Non-NVIDIA machine: the utilization check is moot, AFK alone decides.
    monkeypatch.setattr(ip, "user_idle_seconds", lambda: 900.0)
    monkeypatch.setattr(ip, "gpu_utilization", lambda: None)
    assert ip.system_is_idle(min_afk_seconds=600, max_gpu_utilization=20) is True
