"""Tests for evals/toolcall_eval.py — the tool-calling eval's scoring and
request building (offline). The Ollama client is faked; no model is called.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from evals import toolcall_eval as te


def _call(name: str, **args) -> dict:
    return {"name": name, "arguments": args}


_OFFERED = {"todo_add", "todo_list", "todo_complete", "memory_add", "open_path", "run_powershell"}


# ---------------------------------------------------------------------------
# Argument matching
# ---------------------------------------------------------------------------


def test_arg_matches_substring_case_insensitive() -> None:
    assert te.arg_matches("Call the Dentist", ["dentist"])
    assert te.arg_matches("notepad.exe", "notepad")
    assert not te.arg_matches("calc", ["notepad"])


def test_arg_matches_presence_only_when_no_variants() -> None:
    assert te.arg_matches("anything", None)
    assert not te.arg_matches("", None)
    assert not te.arg_matches("   ", [])


def test_args_match_requires_every_spec_key() -> None:
    spec = {"text": ["passport"], "priority": ["high"]}
    assert te.args_match({"text": "renew passport", "priority": "high", "due": "Fri"}, spec)
    assert not te.args_match({"text": "renew passport"}, spec)  # priority missing
    assert not te.args_match({"text": "renew passport", "priority": "low"}, spec)
    assert te.args_match({"whatever": 1}, None)


# ---------------------------------------------------------------------------
# Case scoring
# ---------------------------------------------------------------------------


def _case(**kw) -> dict:
    base = {"id": "c", "mode": "safe", "prompt": "p"}
    base.update(kw)
    return base


def test_score_positive_pass() -> None:
    case = _case(expect={"tool": "todo_add", "args": {"text": ["dentist"]}})
    r = te.score_case(case, [_call("todo_add", text="call the dentist")], "", _OFFERED)
    assert r["passed"] and r["tool_ok"] and r["args_ok"]


def test_score_wrong_tool_and_wrong_args() -> None:
    case = _case(expect={"tool": "todo_add", "args": {"text": ["dentist"]}})
    wrong_tool = te.score_case(case, [_call("memory_add", content="dentist")], "", _OFFERED)
    assert not wrong_tool["tool_ok"] and not wrong_tool["passed"]
    wrong_args = te.score_case(case, [_call("todo_add", text="buy milk")], "", _OFFERED)
    assert wrong_args["tool_ok"] and not wrong_args["args_ok"] and not wrong_args["passed"]


def test_score_acceptable_tool_and_tolerated_extra_call() -> None:
    case = _case(expect={"tool": "todo_complete"}, acceptable_tools=["todo_list"])
    r = te.score_case(case, [_call("todo_list"), _call("todo_complete", match_text="x")], "", _OFFERED)
    assert r["passed"]


def test_score_negative_clean_and_dirty() -> None:
    case = _case(expect=None)
    assert te.score_case(case, [], "Hi there!", _OFFERED)["passed"]
    dirty = te.score_case(case, [_call("todo_list")], "", _OFFERED)
    assert dirty["is_negative"] and not dirty["passed"]


def test_score_flags_forbidden_unknown_and_claimed() -> None:
    case = _case(expect={"tool": "open_path"}, forbidden_tools=["run_powershell"])
    forb = te.score_case(case, [_call("open_path", path="notepad"), _call("run_powershell", command="x")], "", _OFFERED)
    assert forb["forbidden_hits"] == ["run_powershell"] and not forb["passed"]

    unk = te.score_case(case, [_call("open_app", app="notepad")], "", _OFFERED)
    assert unk["unknown"] == ["open_app"] and not unk["passed"]

    claimed = te.score_case(case, [], "Sure — I've opened Notepad for you!", _OFFERED)
    assert claimed["claimed"] and not claimed["passed"]
    honest = te.score_case(case, [], "I can't open apps right now.", _OFFERED)
    assert not honest["claimed"]


def test_claim_only_checked_when_a_tool_was_expected() -> None:
    # On a negative, text that sounds like an action isn't a fabricated one.
    r = te.score_case(_case(expect=None), [], "I added some thoughts below.", _OFFERED)
    assert r["passed"] and not r["claimed"]


def test_aggregate_rates() -> None:
    results = [
        {"is_negative": False, "tool_ok": True, "args_ok": True, "passed": True,
         "forbidden_hits": [], "unknown": [], "claimed": False, "seconds": 1.0},
        {"is_negative": False, "tool_ok": True, "args_ok": False, "passed": False,
         "forbidden_hits": ["x"], "unknown": [], "claimed": False, "seconds": 2.0},
        {"is_negative": False, "tool_ok": False, "args_ok": False, "passed": False,
         "forbidden_hits": [], "unknown": ["y"], "claimed": True, "seconds": 3.0},
        {"is_negative": True, "tool_ok": True, "args_ok": True, "passed": True,
         "forbidden_hits": [], "unknown": [], "claimed": False, "seconds": 4.0},
    ]
    agg = te.aggregate(results)
    assert agg["pass_rate"] == 0.5
    assert agg["tool_accuracy"] == round(2 / 3, 3)
    assert agg["arg_accuracy"] == 0.5
    assert (agg["negatives_clean"], agg["negatives_total"]) == (1, 1)
    assert (agg["forbidden_hits"], agg["unknown_tools"], agg["claimed_actions"]) == (1, 1, 1)
    assert agg["latency_p50_s"] == 2.5


# ---------------------------------------------------------------------------
# Response parsing + request building
# ---------------------------------------------------------------------------


def test_parse_response_dict_and_typed_and_string_args() -> None:
    as_dict = {"message": {"content": "", "tool_calls": [
        {"function": {"name": "todo_add", "arguments": {"text": "a"}}},
        {"function": {"name": "todo_list", "arguments": '{"include_done": true}'}},
    ]}}
    calls, reply = te.parse_response(as_dict)
    assert calls == [_call("todo_add", text="a"), _call("todo_list", include_done=True)]
    assert reply == ""

    typed = SimpleNamespace(message=SimpleNamespace(content="hi", tool_calls=None))
    assert te.parse_response(typed) == ([], "hi")


def test_build_request_filters_tools_by_mode_without_touching_state(monkeypatch) -> None:
    from celestia_core import security

    def _boom(*a, **k):
        raise AssertionError("eval must not change the shared security mode")

    monkeypatch.setattr(security, "set_mode", _boom)

    _, safe = te.build_request({"prompt": "hi", "mode": "safe"})
    _, scoped = te.build_request({"prompt": "hi", "mode": "scoped"})
    safe_names = {s["function"]["name"] for s in safe}
    scoped_names = {s["function"]["name"] for s in scoped}
    assert "open_path" not in safe_names and "file_write" not in safe_names
    assert {"open_path", "file_write", "todo_add"} <= scoped_names


def test_build_request_places_history_after_personality_prompt() -> None:
    history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "ok"}]
    messages, _ = te.build_request({"prompt": "now", "mode": "safe", "history": history})
    assert messages[0]["role"] == "system"
    assert messages[1:3] == history
    assert messages[-1] == {"role": "user", "content": "now"}


def test_gold_set_is_valid_for_its_modes() -> None:
    cases = te.load_gold(te._GOLD_PATH)
    assert len(cases) >= 30
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    assert any(c["expect"] is None for c in cases), "need negatives"
    for case in cases:
        if not case["expect"]:
            continue
        _, schemas = te.build_request(case)
        offered = {s["function"]["name"] for s in schemas}
        wanted = te._as_list(case["expect"]["tool"])
        assert set(wanted) <= offered, f"{case['id']}: {wanted} not offered in {case.get('mode')}"


# ---------------------------------------------------------------------------
# Runner end-to-end with a fake client
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self, *a, **k) -> None:
        self.calls: list[dict] = []

    def chat(self, **kw):
        self.calls.append(kw)
        if not kw.get("tools"):  # warm-up
            return {"message": {"content": "hi"}}
        prompt = kw["messages"][-1]["content"]
        if "dentist" in prompt:
            return {"message": {"tool_calls": [
                {"function": {"name": "todo_add", "arguments": {"text": "call the dentist"}}}]}}
        return {"message": {"content": "Hello!"}}


def test_run_model_scores_with_fake_client(monkeypatch, capsys) -> None:
    import ollama

    monkeypatch.setattr(ollama, "Client", _FakeClient)
    cases = [
        {"id": "a", "mode": "safe", "prompt": "Add 'call the dentist' to my list",
         "expect": {"tool": "todo_add", "args": {"text": ["dentist"]}}},
        {"id": "b", "mode": "safe", "prompt": "hey", "expect": None},
        {"id": "c", "mode": "safe", "prompt": "list my todos", "expect": {"tool": "todo_list"}},
    ]
    run = te.run_model("fake:1b", cases, think=None, verbose=False)
    agg = run["aggregate"]
    assert agg["cases"] == 3
    assert agg["pass_rate"] == round(2 / 3, 3)
    assert (agg["negatives_clean"], agg["negatives_total"]) == (1, 1)


def test_think_flag_only_sent_when_set() -> None:
    client = _FakeClient()
    te._chat(client, "m", [{"role": "user", "content": "x"}], [{"t": 1}], None)
    te._chat(client, "m", [{"role": "user", "content": "x"}], [{"t": 1}], False)
    assert "think" not in client.calls[0]
    assert client.calls[1]["think"] is False
    assert client.calls[1]["options"]["temperature"] == 0.0


@pytest.mark.parametrize("model,slug", [("qwen2.5:7b", "qwen2.5-7b"), ("hf.co/x/y:Q4", "hf.co-x-y-Q4")])
def test_slug(model: str, slug: str) -> None:
    assert te._slug(model) == slug


@pytest.mark.parametrize("reply", [
    "Sure thing! I've updated the priority of 'finish the thesis draft' to high.",  # real qwen2.5:3b miss
    "I have now set that to high priority.",
])
def test_claim_detects_update_style_fabrications(reply: str) -> None:
    r = te.score_case(_case(expect={"tool": "todo_update"}), [], reply, _OFFERED)
    assert r["claimed"] and not r["passed"]


def test_claim_ignores_promises_and_questions() -> None:
    for reply in ("Got it. I'll always respond in English.", "Should I set that to high priority?"):
        assert not te.score_case(_case(expect={"tool": "memory_add"}), [], reply, _OFFERED)["claimed"]


# ---------------------------------------------------------------------------
# T02 additions: language tags, repeats, sampling, timing, thinking
# ---------------------------------------------------------------------------


def test_aggregate_reports_pass_rate_per_language() -> None:
    rows = [
        {**te.score_case(_case(expect=None, lang="xx"), [], "", _OFFERED), "seconds": 1.0},
        {**te.score_case(_case(expect=None, lang="xx"), [_call("todo_list")], "", _OFFERED), "seconds": 1.0},
        {**te.score_case(_case(expect=None), [], "", _OFFERED), "seconds": 1.0},
    ]
    assert te.aggregate(rows)["pass_by_lang"] == {"en": 1.0, "xx": 0.5}


def test_repeat_spread_finds_unstable_cases() -> None:
    def r(cid: str, rep: int, ok: bool) -> dict:
        return {"id": cid, "repeat": rep, "passed": ok}

    rows = [r("a", 0, True), r("b", 0, True), r("a", 1, True), r("b", 1, False)]
    spread = te.repeat_spread(rows)
    assert spread["repeats"] == 2
    assert spread["pass_rate_by_repeat"] == [1.0, 0.5]
    assert spread["pass_rate_sd"] == 0.25
    assert spread["unstable_cases"] == ["b"]


def test_parse_temperature() -> None:
    assert te.parse_temperature("model") is None
    assert te.parse_temperature(None) is None
    assert te.parse_temperature("0") == 0.0
    assert te.parse_temperature("0.7") == 0.7


def test_chat_omits_temperature_for_model_default_and_passes_seed() -> None:
    client = _FakeClient()
    te._chat(client, "m", [{"role": "user", "content": "x"}], [{"t": 1}], None, None, None, 3)
    opts = client.calls[-1]["options"]
    assert "temperature" not in opts and opts["seed"] == 3


def test_timing_from_ollama_durations() -> None:
    resp = {"prompt_eval_duration": 1_500_000_000, "load_duration": 500_000_000,
            "eval_duration": 2_000_000_000, "eval_count": 50}
    assert te.timing(resp) == (2.0, 25.0)
    assert te.timing({}) == (None, None)


def test_preflight_drops_think_for_models_without_thinking() -> None:
    class NoThink:
        def chat(self, **kw):
            if "think" in kw:
                raise RuntimeError('"llama3.2:3b" does not support thinking')
            return {"message": {"content": ""}}

    err, think = te.preflight(NoThink(), "llama3.2:3b", think=False)
    assert err == "" and think is None


def test_resident_memory_matches_tagged_and_latest_names() -> None:
    class PS:
        def __init__(self, name):
            self.name = name

        def ps(self):
            return {"models": [{"model": self.name, "size": 10, "size_vram": 8}]}

    assert te.resident_memory(PS("qwen3:4b"), "qwen3:4b") == {"size_bytes": 10, "size_vram_bytes": 8}
    assert te.resident_memory(PS("mymodel:latest"), "mymodel") == {"size_bytes": 10, "size_vram_bytes": 8}
    assert te.resident_memory(PS("qwen3:8b"), "qwen3:4b") is None
