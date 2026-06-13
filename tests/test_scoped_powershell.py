"""Scoped mode allows read-only PowerShell/Cmd; mutating commands stay armed-only.

Plus the PC-specs tool is always-ok (works in every mode).
"""

from __future__ import annotations

import pytest

import celestia_core.security as sec
from celestia_core.security import gate_pc_tool, is_readonly_powershell, PC_TOOLS_ALWAYS_OK


@pytest.fixture()
def scoped_mode(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    # Flag on by default; force it deterministically regardless of config.yaml.
    monkeypatch.setattr(
        sec,
        "get",
        lambda key, default=None: True
        if key == "security.scoped_allow_readonly_powershell"
        else default,
    )


# ---------------------------------------------------------------------------
# is_readonly_powershell classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cmd",
    [
        "Get-Date",
        "Get-CimInstance Win32_Processor",
        "dir",
        "ipconfig /all",
        "systeminfo",
        "whoami",
        "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 5",
    ],
)
def test_readonly_commands_classified_readonly(cmd):
    assert is_readonly_powershell(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "Remove-Item C:\\x -Recurse",
        "Set-Content a.txt 'x'",
        "New-Item foo",
        "Stop-Process -Name notepad",
        "Get-Date; Remove-Item x",          # mutating verb anywhere → blocked
        "Get-Content a > b.txt",            # redirection → blocked
        "Invoke-WebRequest http://x",       # network/exec → blocked
        "del important.txt",                # cmd-style delete
    ],
)
def test_mutating_commands_classified_not_readonly(cmd):
    assert is_readonly_powershell(cmd) is False


def test_blank_command_not_readonly():
    assert is_readonly_powershell("") is False
    assert is_readonly_powershell("   ") is False


# ---------------------------------------------------------------------------
# Gate behavior in scoped mode
# ---------------------------------------------------------------------------

def test_scoped_allows_readonly_powershell(scoped_mode):
    assert gate_pc_tool("run_powershell", {"command": "Get-Date"}) is None


def test_scoped_blocks_mutating_powershell(scoped_mode):
    blocked = gate_pc_tool("run_powershell", {"command": "Remove-Item x"})
    assert blocked is not None and "Blocked" in blocked


def test_scoped_blocks_all_when_flag_off(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    monkeypatch.setattr(
        sec,
        "get",
        lambda key, default=None: False
        if key == "security.scoped_allow_readonly_powershell"
        else default,
    )
    blocked = gate_pc_tool("run_powershell", {"command": "Get-Date"})
    assert blocked is not None and "Blocked" in blocked


def test_pc_specs_is_always_ok():
    assert "get_pc_specs" in PC_TOOLS_ALWAYS_OK
    for mode in ("safe", "scoped", "armed"):
        # always-ok tools return None (allowed) before any mode logic runs.
        import celestia_core.security as s
        orig = s.get_mode
        s.get_mode = lambda: mode  # type: ignore
        try:
            assert gate_pc_tool("get_pc_specs", {}) is None
        finally:
            s.get_mode = orig
