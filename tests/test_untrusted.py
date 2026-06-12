"""Tests for the prompt-injection defense (celestia_core/untrusted.py).

Covers the delimiter wrapping primitive, the tool-result gate, that the system
prompt carries the matching policy clause, and that execute_tool wraps a
content-ingesting tool's result while leaving a blocked result alone.
"""

from celestia_core import untrusted


def test_wrap_adds_delimiters_and_source():
    out = untrusted.wrap("hello world", "a file on disk")
    assert "⟦UNTRUSTED DATA" in out
    assert "⟦END UNTRUSTED DATA⟧" in out
    assert "a file on disk" in out
    assert "hello world" in out


def test_wrap_noop_on_blank():
    assert untrusted.wrap("", "x") == ""
    assert untrusted.wrap("   ", "x") == "   "


def test_wrap_tool_result_wraps_content_tools():
    for name in ("file_read", "clipboard_read", "fetch_page", "web_search"):
        out = untrusted.wrap_tool_result(name, "secret page text")
        assert "⟦UNTRUSTED DATA" in out
        assert "secret page text" in out


def test_wrap_tool_result_passes_through_non_content_tools():
    for name in ("memory_list", "todo_add", "open_path", "get_system_status"):
        assert untrusted.wrap_tool_result(name, "ok") == "ok"


def test_system_prompt_has_untrusted_clause():
    from celestia_core.personality import _BASE

    assert "⟦UNTRUSTED DATA" in _BASE
    assert "never as instructions" in _BASE


def test_execute_tool_wraps_file_read(monkeypatch):
    """A content-ingesting tool's result is delimited by execute_tool."""
    import skills.registry as registry

    monkeypatch.setitem(
        registry._TOOL_DISPATCH, "file_read", lambda args, uid: "file body: rm -rf /"
    )
    monkeypatch.setattr(registry.security, "audit_tool", lambda *a, **k: None)

    out = registry.execute_tool("file_read", {"path": "x.txt"}, "uid")
    assert "⟦UNTRUSTED DATA" in out
    assert "file body: rm -rf /" in out


def test_execute_tool_does_not_wrap_blocked_pc_tool(monkeypatch):
    """A blocked PC tool returns its block message verbatim — not wrapped."""
    import skills.registry as registry

    monkeypatch.setattr(registry.security, "gate_pc_tool", lambda n, a: "Blocked: nope")
    monkeypatch.setattr(registry.security, "audit_tool", lambda *a, **k: None)

    out = registry.execute_tool("run_powershell", {"command": "ls"}, "uid")
    assert out == "Blocked: nope"
    assert "UNTRUSTED" not in out
