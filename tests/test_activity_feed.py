"""Tests for skills/memory/activity_feed.py — the JSONL ring buffer + SSE fan-out.

Disk writes are redirected to tmp_path via _feed_path; the subscriber list is
reset between tests so broadcasts don't leak across cases.
"""

from __future__ import annotations

import json
import queue

import pytest

import skills.memory.activity_feed as af


@pytest.fixture()
def feed_tmp(tmp_path, monkeypatch):
    path = tmp_path / "activity_feed.jsonl"
    monkeypatch.setattr(af, "_feed_path", lambda: path)
    with af._subs_lock:
        af._subs.clear()
    yield path
    with af._subs_lock:
        af._subs.clear()


# ---------------------------------------------------------------------------
# append_event — disk
# ---------------------------------------------------------------------------


def test_append_event_writes_one_jsonl_row(feed_tmp) -> None:
    af.append_event(action="read_screen", text="hello", kind="fact", source="read_hotkey")
    lines = feed_tmp.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["action"] == "read_screen"
    assert row["text"] == "hello"
    assert row["kind"] == "fact"
    assert row["source"] == "read_hotkey"
    assert isinstance(row["ts"], (int, float))


def test_append_event_truncates_long_text(feed_tmp) -> None:
    af.append_event(action="add", text="y" * 600)
    row = json.loads(feed_tmp.read_text(encoding="utf-8").strip())
    assert len(row["text"]) == 500


def test_append_event_defaults(feed_tmp) -> None:
    af.append_event(action="consolidate", text="note")
    row = json.loads(feed_tmp.read_text(encoding="utf-8").strip())
    assert row["kind"] == "fact"
    assert row["source"] == "consolidate"


# ---------------------------------------------------------------------------
# subscribe / unsubscribe — SSE fan-out
# ---------------------------------------------------------------------------


def test_subscribe_receives_broadcast(feed_tmp) -> None:
    q = af.subscribe()
    af.append_event(action="add", text="note")
    row = q.get_nowait()
    assert row["action"] == "add"
    assert row["text"] == "note"


def test_multiple_subscribers_all_receive(feed_tmp) -> None:
    q1 = af.subscribe()
    q2 = af.subscribe()
    af.append_event(action="update", text="x")
    assert q1.get_nowait()["action"] == "update"
    assert q2.get_nowait()["action"] == "update"


def test_unsubscribe_stops_delivery(feed_tmp) -> None:
    q = af.subscribe()
    af.unsubscribe(q)
    af.append_event(action="add", text="note")
    with pytest.raises(queue.Empty):
        q.get_nowait()


def test_unsubscribe_unknown_queue_is_safe(feed_tmp) -> None:
    # Removing a queue that was never subscribed must not raise.
    af.unsubscribe(queue.SimpleQueue())


def test_subscribe_does_not_receive_past_events(feed_tmp) -> None:
    af.append_event(action="add", text="before")
    q = af.subscribe()
    with pytest.raises(queue.Empty):
        q.get_nowait()
