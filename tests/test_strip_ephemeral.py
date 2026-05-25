"""Tests for _strip_ephemeral() in celestia_core/agent.py.

This is a pure-function test — no mocks needed. It validates that:
- The first system message (personality prompt) is preserved.
- Per-turn system injections added after the first user message are removed.
- User/assistant/tool messages are never touched.
"""

from celestia_core.agent import _strip_ephemeral


def test_empty_list():
    assert _strip_ephemeral([]) == []


def test_single_system_kept():
    msgs = [{"role": "system", "content": "You are Celestia."}]
    result = _strip_ephemeral(msgs)
    assert result == msgs


def test_personality_prompt_preserved():
    """The first system message (before any user turn) must survive."""
    msgs = [
        {"role": "system", "content": "You are Celestia."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    result = _strip_ephemeral(msgs)
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are Celestia."


def test_ephemeral_hints_after_user_stripped():
    """System messages injected AFTER the first user turn must be stripped.

    In practice these are the per-turn mode-hint and memory-context messages
    that run_turn() injects between the previous assistant reply and the next
    user message.  They appear *after* the first user turn in the history, so
    _strip_ephemeral() removes them.

    System messages that appear BEFORE the first user turn (the initial prompt
    bundle for turn 1) are all kept — they are part of that first-turn context.
    """
    msgs = [
        {"role": "system", "content": "You are Celestia."},   # keep — personality
        {"role": "system", "content": "PC control is SAFE."},  # keep — turn-1 pre-user hint
        {"role": "user", "content": "Open YouTube"},           # first user turn
        {"role": "assistant", "content": "I cannot do that in safe mode."},
        # Turn-2 hints appear AFTER the first user turn → must be stripped
        {"role": "system", "content": "PC control is SAFE."},
        {"role": "system", "content": "User wants to open something."},
        {"role": "user", "content": "Ok, arm me"},
        {"role": "assistant", "content": "Armed."},
    ]
    result = _strip_ephemeral(msgs)
    roles = [m["role"] for m in result]
    # 2 pre-first-user system messages kept; 2 post-first-user stripped
    assert roles.count("system") == 2
    assert result[0]["content"] == "You are Celestia."
    assert len(result) == 6  # 2 system + 2 user + 2 assistant


def test_no_system_messages_unchanged():
    """History with no system messages at all should pass through unmodified."""
    msgs = [
        {"role": "user", "content": "Hey"},
        {"role": "assistant", "content": "Hello!"},
    ]
    assert _strip_ephemeral(msgs) == msgs


def test_multiple_pre_user_system_messages():
    """ALL system messages before the first user turn are preserved.

    run_turn() packs the personality prompt, mode hints, and memory context
    into the message list before appending the user message.  _strip_ephemeral()
    keeps this entire pre-user bundle because it is part of the first-turn context.
    """
    msgs = [
        {"role": "system", "content": "First system — personality."},
        {"role": "system", "content": "Second system — mode hint."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hey"},
    ]
    result = _strip_ephemeral(msgs)
    system_msgs = [m for m in result if m["role"] == "system"]
    # Both pre-user system messages must be preserved
    assert len(system_msgs) == 2
    assert system_msgs[0]["content"] == "First system — personality."
    assert system_msgs[1]["content"] == "Second system — mode hint."


def test_tool_messages_preserved():
    """Tool result messages must never be stripped."""
    msgs = [
        {"role": "system", "content": "You are Celestia."},
        {"role": "user", "content": "Open Notepad"},
        {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "open_path"}}]},
        {"role": "tool", "content": "Opened notepad", "name": "open_path"},
        {"role": "assistant", "content": "Opened Notepad for you."},
    ]
    result = _strip_ephemeral(msgs)
    tool_msgs = [m for m in result if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["content"] == "Opened notepad"
