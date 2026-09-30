"""Offline tests for the T15 memory writer parser and the consolidation eval scorer."""

from __future__ import annotations

import json

import pytest

import evals.consolidation_eval as ce
from evals.extraction_eval import _as_list, load_gold
from skills.memory.writer import build_prompt, parse_ops

GOLD = load_gold(ce._GOLD_PATH)


# ---------------------------------------------------------------------------
# writer.parse_ops
# ---------------------------------------------------------------------------


def test_parse_ops_valid_ops_and_summary() -> None:
    raw = json.dumps({
        "ops": [
            {"op": "supersede", "target": "m1", "kind": "fact", "text": "User lives in Izmir.",
             "triples": [["user", "lives in", "Izmir"]]},
            {"op": "add", "kind": "instruction", "text": "Keep answers short.", "triples": []},
            {"op": "forget", "target": "m2", "text": "ignored", "triples": [["a", "b", "c"]]},
        ],
        "summary": "Talked about the move.",
    })
    res = parse_ops("Sure!\n" + raw, {"m1", "m2"})
    assert [o.op for o in res.ops] == ["supersede", "add", "forget"]
    assert res.ops[0].triples == [{"subject": "user", "predicate": "lives in", "object": "Izmir"}]
    assert res.ops[1].kind == "instruction"
    assert res.ops[2].triples == []  # forget carries no graph content
    assert res.summary == "Talked about the move."
    assert res.dropped == []


def test_parse_ops_drops_bad_targets_and_unknown_ops() -> None:
    raw = json.dumps({"ops": [
        {"op": "update", "target": "m9", "text": "x is y"},     # unknown id
        {"op": "supersede", "text": "no target"},                # missing target
        {"op": "rewrite", "target": "m1", "text": "?"},          # unknown op
        {"op": "add", "text": ""},                               # empty text
        {"op": "noop", "target": "m1"},                          # explicit no-op → silently skipped
        {"op": "add", "target": "m1", "kind": "weird", "text": "User likes tea."},
    ]})
    res = parse_ops(raw, {"m1"})
    assert len(res.ops) == 1
    assert res.ops[0].target is None and res.ops[0].kind == "fact"
    assert len(res.dropped) == 4


def test_parse_ops_tolerates_junk() -> None:
    assert parse_ops("", {"m1"}).ops == []
    assert parse_ops("no json here", set()).dropped == ["no JSON object"]
    assert parse_ops("{not json}", set()).dropped == ["invalid JSON"]


def test_build_prompt_lists_existing_ids_and_summary() -> None:
    p = build_prompt("User: hi", [{"id": "m1", "kind": "fact", "text": "User lives in Izmir."}], "diet talk")
    assert "[m1] (fact) User lives in Izmir." in p
    assert "diet talk" in p and p.rstrip().endswith("User: hi")
    assert "(none)" in build_prompt("User: hi", [])


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def _perfect_ops(case: dict) -> list[dict]:
    """A correct answer synthesized from the case's expected specs."""
    ops = []
    for spec in case.get("expected", []):
        op = _as_list(spec["op_any"])[0]
        text = " ".join(_as_list(g)[0] for g in spec.get("mentions") or []) or "x"
        triples = []
        if spec.get("triple"):
            t = spec["triple"]
            triples = [{
                "subject": _as_list(t.get("subject") or "user")[0],
                "predicate": _as_list(t.get("predicate_any") or "rel")[0],
                "object": _as_list(t.get("object"))[0],
            }]
        ops.append({"op": op, "target": spec.get("target"), "kind": spec.get("kind", "fact"),
                    "text": "" if op == "forget" else f"User {text}.", "triples": triples})
    return ops


@pytest.mark.parametrize("case", GOLD, ids=[c["id"] for c in GOLD])
def test_gold_case_is_satisfiable(case: dict) -> None:
    ids = {e["id"] for e in case.get("existing", [])}
    for spec in case.get("expected", []) + case.get("optional", []):
        assert set(_as_list(spec["op_any"])) <= set(ce._CONTENT_OPS) | {"forget"}
        if spec.get("target"):
            assert spec["target"] in ids
    for tid in _as_list(case.get("untouched")) + list((case.get("untouched_ops") or {})):
        assert tid in ids
    r = ce.score_case(case, _perfect_ops(case))
    assert r["passed"], r
    if r["sync_total"]:
        assert r["sync_ok"] == r["sync_total"]


def test_gold_ids_unique_and_cover_every_behavior() -> None:
    ids = [c["id"] for c in GOLD]
    assert len(ids) == len(set(ids))
    ops = {o for c in GOLD for s in c.get("expected", []) for o in _as_list(s["op_any"])}
    assert {"add", "update", "supersede", "forget"} <= ops
    assert sum(1 for c in GOLD if not c.get("expected")) >= 4
    assert any(c.get("summary") for c in GOLD)


def _case(cid: str) -> dict:
    return next(c for c in GOLD if c["id"] == cid)


def test_restating_existing_memory_is_a_duplicate() -> None:
    r = ce.score_case(_case("dup-01"), [{"op": "add", "kind": "fact", "text": "User lives in Ankara.", "triples": []}])
    assert r["duplicates"] and not r["passed"] and not r["clean_negative"]


def test_legacy_style_add_misses_correction() -> None:
    # Today's pipeline can only add: the new city arrives, the old one is never closed.
    case = _case("move-01")
    r = ce.score_case(case, [{"op": "add", "kind": "fact", "text": "User moved to Izmir.", "triples": []}],
                      graph_triples=[{"subject": "user", "predicate": "lives in", "object": "Izmir"}])
    assert r["corrections_found"] == 0 and r["corrections_total"] == 1
    assert not r["passed"]


def test_wrong_target_and_banned_op_flagged() -> None:
    r = ce.score_case(_case("neg-hypo"), [{"op": "supersede", "target": "m1", "text": "User lives in Berlin.", "triples": []}])
    assert r["wrong_touch"] and not r["passed"]
    r = ce.score_case(_case("multi-01"), [
        {"op": "supersede", "target": "m1", "kind": "fact", "text": "User likes green tea.",
         "triples": [{"subject": "user", "predicate": "likes", "object": "green tea"}]},
    ])
    assert r["wrong_touch"]


def test_secret_in_summary_or_graph_is_forbidden() -> None:
    case = _case("secret-01")
    assert ce.score_case(case, [], summary="Wifi password is sunflower2024")["forbidden_hits"]
    assert ce.score_case(case, [], graph_triples=[{"subject": "wifi", "predicate": "password", "object": "sunflower2024"}])["forbidden_hits"]
    assert ce.score_case(case, [])["passed"]


def test_missing_triple_counts_against_graph_sync() -> None:
    case = _case("add-01")
    r = ce.score_case(case, [{"op": "add", "kind": "fact", "text": "User adopted a cat named Mochi.", "triples": []}])
    assert r["passed"] and r["sync_total"] == 1 and r["sync_ok"] == 0


def test_aggregate_counts() -> None:
    results = [ce.score_case(c, _perfect_ops(c)) for c in GOLD]
    agg = ce.aggregate(results)
    assert agg["passed"] == len(GOLD) and agg["f1"] == 1.0 and agg["duplicates"] == 0
    found, total = agg["corrections"].split("/")
    assert found == total and int(total) >= 8
    assert agg["graph_sync"] == 1.0


# ---------------------------------------------------------------------------
# End to end with a stubbed model
# ---------------------------------------------------------------------------


def test_main_end_to_end_with_stub(monkeypatch, tmp_path) -> None:
    """Writer answers perfectly; legacy re-adds the old city. The writer must win."""
    by_transcript = {c["transcript"]: c for c in GOLD}

    def fake_chat(model, prompt, *, think, num_predict, json_mode=False):
        case = next(c for t, c in by_transcript.items() if t in prompt)
        if "--- NEW CHAT ---" in prompt:  # writer prompt
            return json.dumps({"ops": _perfect_ops(case), "summary": ""})
        if "Extract the factual relationships" in prompt:  # legacy graph pass
            return '{"relations": []}'
        texts = [e["text"] for e in case.get("existing", [])] or ["User said hello there."]
        return json.dumps({"facts": [{"text": t} for t in texts]})

    monkeypatch.setattr(ce, "_chat", fake_chat)
    monkeypatch.setattr(ce, "_scrub", lambda t: t)
    out = tmp_path / "r.json"
    md = tmp_path / "r.md"
    rc = ce.main(["--model", "stub", "--think", "off", "--json", str(out), "--markdown", str(md)])
    assert rc == 0
    runs = {r["pipeline"]: r["aggregate"] for r in json.loads(out.read_text(encoding="utf-8"))["runs"]}
    assert runs["writer"]["passed"] == len(GOLD)
    assert runs["legacy"]["passed"] < len(GOLD)
    assert runs["legacy"]["corrections"].startswith("0/")
    assert "| `stub` | writer (think off) |" in md.read_text(encoding="utf-8")


def test_think_unsupported_skips_variant(monkeypatch) -> None:
    def fake_chat(model, prompt, *, think, num_predict, json_mode=False):
        raise ce.ThinkUnsupported("model does not support thinking")

    monkeypatch.setattr(ce, "_chat", fake_chat)
    assert ce.run_variant("stub", GOLD[:2], "writer", True, False) is None


def test_request_error_fails_case_and_exit_code(monkeypatch) -> None:
    def boom(*a, **k):
        raise ConnectionError("ollama down")

    monkeypatch.setattr(ce, "_chat", boom)
    monkeypatch.setattr(ce, "_scrub", lambda t: t)
    run = ce.run_variant("stub", [_case("neg-smalltalk")], "writer", False, False)
    assert run["aggregate"]["errors"] == 1 and run["aggregate"]["negatives_clean"] == 0
    assert ce.main(["--model", "stub", "--pipeline", "writer", "--think", "off", "--only", "neg-smalltalk"]) == 1


def test_op_on_wrong_target_does_not_match() -> None:
    case = {"id": "t", "existing": [{"id": "m1", "text": "User lives in Ankara."}, {"id": "m2", "text": "User has a dog."}],
            "expected": [{"op_any": ["supersede"], "target": "m1", "mentions": [["izmir"]]}]}
    r = ce.score_case(case, [{"op": "supersede", "target": "m2", "kind": "fact", "text": "User lives in Izmir.", "triples": []}])
    assert r["tp_recall"] == 0 and not r["passed"]


def test_parse_ops_drops_unchanged_restatement() -> None:
    # Seen on qwen2.5:3b: "update m1" with the memory's own text, or a supersede
    # that copies the old value. Neither changes anything.
    raw = json.dumps({"ops": [
        {"op": "update", "target": "m1", "text": "User's main project is Celestia, a local AI companion"},
        {"op": "supersede", "target": "m2", "text": "User lives in Izmir."},
    ]})
    res = parse_ops(raw, {"m1": "User's main project is Celestia, a local AI companion.", "m2": "User lives in Ankara."})
    assert [o.target for o in res.ops] == ["m2"]
    assert "no change" in res.dropped[0]


def test_parse_ops_recovers_object_after_junk() -> None:
    raw = 'Here you go {not json} and then {"ops": [{"op": "add", "text": "User likes tea."}], "summary": ""} done'
    res = parse_ops(raw, set())
    assert [o.text for o in res.ops] == ["User likes tea."]


def test_prompt_placeholder_target_is_not_a_real_id() -> None:
    # The format example must not name an id a model can copy into an empty memory.
    from skills.memory.writer import PROMPT

    assert '"target":"m1"' not in PROMPT and "(none), the only possible op is add" in PROMPT
    # No example values a model could copy into memory (qwen2.5:3b stored the
    # example's "cat named Mochi" in an unrelated chat).
    gold_terms = {"mochi", "izmir", "ankara", "acme", "elif", "sencha"}
    assert not any(term in PROMPT.lower() for term in gold_terms)


def test_output_schema_matches_parser_vocabulary() -> None:
    from skills.memory.writer import OPS, OUTPUT_SCHEMA, WRITER_KINDS

    item = OUTPUT_SCHEMA["properties"]["ops"]["items"]["properties"]
    assert item["op"]["enum"] == list(OPS) and item["kind"]["enum"] == list(WRITER_KINDS)
