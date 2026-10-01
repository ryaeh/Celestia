"""Offline tests for the structured session summary and the summary eval scorer."""

from __future__ import annotations

import json

import pytest

import evals.summary_eval as se
from evals.extraction_eval import load_gold
from skills.memory import session_summary as ss

GOLD = load_gold(se._GOLD_PATH)


# ---------------------------------------------------------------------------
# session_summary: parse / merge / render
# ---------------------------------------------------------------------------


def _upd(**kw) -> dict:
    base = {"goal": "", "now": "", "facts": [], "decisions": [], "open": [], "details": [], "drop": []}
    base.update(kw)
    return ss.parse(json.dumps(base))


def test_parse_tolerates_junk_and_cleans_items() -> None:
    raw = 'sure: {"goal": " Plan a trip ", "now": "x", "facts": ["- The user flies May 12", ""], ' \
          '"decisions": 3, "open": [], "details": ["port 9000"], "drop": []} thanks'
    u = ss.parse(raw)
    assert u["goal"] == "Plan a trip" and u["facts"] == ["The user flies May 12"]
    assert u["decisions"] == [] and u["details"] == ["port 9000"]
    assert ss.parse("no json") is None


def test_items_the_model_omits_carry_over() -> None:
    prev = ss.merge(ss.empty(), _upd(goal="Trip", details=["Flight May 12", "Budget 900 EUR"], open=["Renew passport"]))
    nxt = ss.merge(prev, _upd(now="Debugging the server", details=["Port 9000"]))
    assert nxt["details"] == ["Flight May 12", "Budget 900 EUR", "Port 9000"]
    assert nxt["open"] == ["Renew passport"] and nxt["goal"] == "Trip"


def test_drop_removes_stale_items() -> None:
    prev = ss.merge(ss.empty(), _upd(details=["Port 8765"], open=["Pick a dessert"]))
    nxt = ss.merge(prev, _upd(details=["Port 9000"], decisions=["Dessert: tiramisu"], drop=["Port 8765", "Pick a dessert"]))
    assert nxt["details"] == ["Port 9000"] and nxt["open"] == [] and nxt["decisions"] == ["Dessert: tiramisu"]


def test_restated_items_are_not_duplicated_but_changed_numbers_are_kept() -> None:
    prev = ss.merge(ss.empty(), _upd(facts=["The user is hosting dinner for 6 people"], details=["Port 8765"]))
    nxt = ss.merge(prev, _upd(facts=["The user is hosting a dinner for 6 people"], details=["Port 9000"]))
    assert len(nxt["facts"]) == 1
    assert nxt["details"] == ["Port 8765", "Port 9000"]    # different number → not the same detail


def test_caps_drop_the_oldest() -> None:
    state = ss.empty()
    for i in range(20):
        state = ss.merge(state, _upd(details=[f"detail number {i}"]))
    assert len(state["details"]) == ss.LIST_FIELDS["details"]
    assert state["details"][-1] == "detail number 19" and "detail number 0" not in state["details"]


def test_legacy_string_summary_is_coerced() -> None:
    s = ss.coerce("The user talked about Berlin.")
    assert s["goal"] == "The user talked about Berlin." and s["facts"] == []
    assert ss.is_empty(ss.empty()) and not ss.is_empty(s)


def test_render_and_prompt() -> None:
    state = ss.merge(ss.empty(), _upd(goal="Trip", now="Tests", details=["Port 9000"]))
    text = ss.render(state)
    assert "Goal: Trip" in text and "Right now: Tests" in text and "- Port 9000" in text
    p = ss.build_prompt("User: hi", state)
    assert "PREVIOUS NOTES:\nGoal: Trip" in p and p.rstrip().endswith("User: hi")
    assert "(none)" in ss.build_prompt("User: hi", None)


def test_schema_lists_every_field() -> None:
    assert set(ss.OUTPUT_SCHEMA["required"]) == {"goal", "now", *ss.LIST_FIELDS, "drop"}


# ---------------------------------------------------------------------------
# Eval scorer + gold sanity
# ---------------------------------------------------------------------------


def _perfect_text(case: dict) -> tuple[str, str]:
    parts = [" ".join(e_alt[0] if isinstance(e_alt, list) else e_alt for e_alt in e["mentions"]) for e in case["expect"]]
    parts += case.get("exact", [])
    now = case["now"][0][0] if case.get("now") else ""
    return "\n".join(parts + [now]), now


@pytest.mark.parametrize("case", GOLD, ids=[c["id"] for c in GOLD])
def test_gold_case_is_satisfiable(case: dict) -> None:
    assert len(case["segments"]) >= 2
    text, now = _perfect_text(case)
    r = se.score_case(case, text, now)
    assert r["passed"], r


def test_forgetting_early_facts_fails() -> None:
    case = next(c for c in GOLD if c["id"] == "trip-then-code")
    text = "Right now: writing a test for port 9000. Details: 9000, May 12"
    r = se.score_case(case, text, "writing a test")
    assert not r["passed"] and r["early_retained"] < r["early_expected"]


def test_leaked_password_fails() -> None:
    case = next(c for c in GOLD if c["id"] == "job-application")
    text, now = _perfect_text(case)
    r = se.score_case(case, text + "\nportal password Tulip#2291", now)
    assert r["forbidden_hits"] and not r["passed"]


def test_main_end_to_end_with_stub(monkeypatch, tmp_path) -> None:
    """Structured stub keeps everything (via carry-over); prose stub keeps only
    the last segment. The scorer must tell them apart."""

    def fake_chat(model, prompt, *, schema, num_predict):
        new = prompt.split("--- NEW MESSAGES ---")[1]
        if schema is None:
            return new[-300:]                       # prose: only the latest window survives
        return json.dumps({"goal": "", "now": new[-200:], "facts": [new[:900]], "decisions": [],
                           "open": [], "details": [new[900:1800]], "drop": []})

    monkeypatch.setattr(se, "_chat", fake_chat)
    monkeypatch.setattr(se, "_transcript", lambda msgs: "\n".join(m["content"] for m in msgs))
    out = tmp_path / "s.json"
    assert se.main(["--model", "stub", "--only", "trip-then-code", "--json", str(out)]) == 0
    runs = {r["pipeline"]: r["aggregate"] for r in json.loads(out.read_text(encoding="utf-8"))["runs"]}
    assert runs["structured"]["early_retention"] > runs["prose"]["early_retention"]


# ---------------------------------------------------------------------------
# Fixes from the first real run (qwen3.5:4b): topic switch, drop-all, secrets
# ---------------------------------------------------------------------------


def test_topic_switch_moves_the_old_goal_to_topics() -> None:
    s = ss.merge(ss.empty(), _upd(goal="Planning a Berlin trip in May"))
    s = ss.merge(s, _upd(goal="Fixing the Celestia shell server port"))
    assert s["goal"] == "Fixing the Celestia shell server port"
    assert s["topics"] == ["Planning a Berlin trip in May"]
    assert "Earlier in this chat:\n- Planning a Berlin trip in May" in ss.render(s)


def test_a_cleanup_cannot_wipe_facts_and_details() -> None:
    facts = [f"The user said thing {i}" for i in range(6)]
    s = ss.merge(ss.empty(), _upd(facts=facts, details=["Flight May 12", "Budget 900 EUR", "Hotel Alexanderplatz", "Port 8765"]))
    s = ss.merge(s, _upd(drop=facts + ["Flight May 12", "Budget 900 EUR", "Hotel Alexanderplatz", "Port 8765"]))
    assert len(s["facts"]) == 3 and len(s["details"]) == 1      # DROP_CAP = 3 per field
    s2 = ss.merge(ss.empty(), _upd(open=["a", "b", "c", "d", "e"]))
    assert ss.merge(s2, _upd(drop=["a", "b", "c", "d", "e"]))["open"] == []   # open items resolve freely


def test_credential_items_never_survive_parse() -> None:
    u = _upd(details=["Tulip#2291", "Portal password Tulip#2291", "[REDACTED:credential]", "October 15"],
             decisions=["Store the portal password in a password manager"], goal="password is Tulip#2291")
    assert u["details"] == ["Tulip#2291", "October 15"]   # bare value can't be recognized here…
    assert u["decisions"] == [] and u["goal"] == ""


def test_spoken_passwords_are_scrubbed_before_the_prompt() -> None:
    """…which is why the value is scrubbed out of the transcript first."""
    from skills.memory.scrub import scrub_secrets

    for text, keep in [
        ("my application portal password is Tulip#2291 in case I forget", "Tulip#2291"),
        ("my wifi password is sunflower2024 btw", "sunflower2024"),
        ("the PIN was 4821.", "4821"),
    ]:
        out, found = scrub_secrets(text)
        assert keep not in out and found == ["credential"], out
    for text in ("my pin is in the drawer", "use a password manager for that", "I forgot my password again"):
        assert scrub_secrets(text) == (text, [])
