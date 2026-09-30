"""Tests for evals/extraction_eval.py — the Gate A scoring logic (offline).

Only the pure matching/scoring functions are exercised; the Ollama-calling
runner is not (that's the eval itself, not a unit test).
"""

from __future__ import annotations

from pathlib import Path

from evals.extraction_eval import (
    _GOLD_PATH,
    aggregate,
    field_match,
    load_gold,
    norm,
    predicate_match,
    score_case,
    triple_matches,
)


def _triple(s: str, p: str, o: str) -> dict:
    return {"subject": s, "predicate": p, "object": o}


# ---------------------------------------------------------------------------
# Normalization + field matching
# ---------------------------------------------------------------------------


def test_norm_strips_articles_case_and_quotes() -> None:
    assert norm("The User") == "user"
    assert norm("  my   cat ") == "cat"
    assert norm('"Neovim".') == "neovim"
    assert norm("the my cat") == "cat"  # articles stripped repeatedly


def test_field_match_exact_and_variants() -> None:
    assert field_match("Neovim", "neovim")
    assert field_match("VS Code", ["vscode", "vs code"])
    assert not field_match("emacs", ["vscode", "vs code"])


def test_field_match_containment_both_directions() -> None:
    assert field_match("neovim editor", "neovim")  # extracted is longer
    assert field_match("neovim", "neovim editor")  # spec is longer
    # Short-fragment guard: 1–2 char variants can't match by containment.
    assert not field_match("port 8765", "8")


def test_field_match_none_spec_matches_anything() -> None:
    assert field_match("whatever", None)


def test_field_match_folds_first_person_to_user() -> None:
    # Models often say "I" where gold says "user" — that's correct extraction.
    assert field_match("I", "user")
    assert field_match("me", ["user"])
    assert field_match("ben", "user")  # Turkish first person
    # But not the other way round for unrelated variants.
    assert not field_match("I", "celestia")


def test_predicate_match_substring_or_free() -> None:
    assert predicate_match("switched to using", ["use", "switch"])
    assert not predicate_match("dislikes", ["use", "switch"])
    assert predicate_match("anything at all", None)


def test_triple_matches_requires_all_fields() -> None:
    spec = {"subject": "user", "predicate_any": ["use"], "object": "neovim"}
    assert triple_matches(_triple("the user", "uses daily", "Neovim"), spec)
    assert not triple_matches(_triple("the user", "uses daily", "emacs"), spec)
    assert not triple_matches(_triple("assistant", "uses", "neovim"), spec)


# ---------------------------------------------------------------------------
# Case scoring
# ---------------------------------------------------------------------------


def test_score_perfect_case() -> None:
    case = {"id": "c1", "expected": [{"subject": "user", "object": "neovim"}]}
    r = score_case(case, [_triple("user", "uses", "neovim")])
    assert r["tp_recall"] == 1 and r["n_expected"] == 1
    assert r["tp_precision"] == 1 and r["n_extracted"] == 1
    assert r["spurious"] == [] and r["missed"] == []


def test_score_missed_expected_and_spurious() -> None:
    case = {
        "id": "c2",
        "expected": [
            {"subject": "user", "object": "ankara"},
            {"subject": "user", "object": "celestia"},
        ],
    }
    r = score_case(case, [_triple("user", "lives in", "ankara"), _triple("user", "hates", "mondays")])
    assert r["tp_recall"] == 1  # celestia missed
    assert len(r["missed"]) == 1
    assert r["tp_precision"] == 1  # mondays is spurious
    assert len(r["spurious"]) == 1


def test_optional_rescues_precision_not_recall() -> None:
    case = {
        "id": "c3",
        "expected": [{"subject": "user", "object": "neovim"}],
        "optional": [{"subject": "user", "object": "vs code"}],
    }
    r = score_case(
        case,
        [_triple("user", "uses", "neovim"), _triple("user", "switched from", "vs code")],
    )
    assert r["tp_recall"] == 1 and r["n_expected"] == 1  # optional not in recall
    assert r["tp_precision"] == 2 and r["spurious"] == []  # but justified


def test_expected_spec_matched_at_most_once() -> None:
    case = {"id": "c4", "expected": [{"subject": "user", "object": "neovim"}]}
    r = score_case(case, [_triple("user", "uses", "neovim"), _triple("user", "prefers", "neovim")])
    assert r["tp_recall"] == 1
    # The duplicate is unaccounted (greedy 1:1), so it shows as spurious.
    assert r["tp_precision"] == 1 and len(r["spurious"]) == 1


def test_negative_case_clean_and_dirty() -> None:
    case = {"id": "n1", "expected": []}
    assert score_case(case, [])["clean_negative"] is True
    dirty = score_case(case, [_triple("user", "says", "hello")])
    assert dirty["clean_negative"] is False
    assert dirty["tp_precision"] == 0 and dirty["n_extracted"] == 1


def test_forbidden_hit_detected() -> None:
    case = {
        "id": "f1",
        "expected": [{"subject": "api server", "object": "8765"}],
        "forbidden": ["8000"],
    }
    r = score_case(
        case,
        [_triple("api server", "runs on port", "8765"), _triple("api server", "moved from", "port 8000")],
    )
    assert r["forbidden_hits"] == ["8000"]


# ---------------------------------------------------------------------------
# Aggregate + gold file integrity
# ---------------------------------------------------------------------------


def test_aggregate_micro_averages() -> None:
    results = [
        score_case({"id": "a", "expected": [{"subject": "u", "object": "x"}]}, [_triple("u", "p", "x")]),
        score_case({"id": "b", "expected": []}, [_triple("u", "p", "junk")]),
    ]
    agg = aggregate(results)
    assert agg["recall"] == 1.0
    assert agg["precision"] == 0.5  # 1 justified of 2 extracted
    assert agg["negatives_clean"] == 0 and agg["negatives_total"] == 1


def test_gold_file_parses_and_ids_unique() -> None:
    cases = load_gold(Path(_GOLD_PATH))
    assert len(cases) >= 15
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    for c in cases:
        assert c["excerpt"].strip(), f"{c['id']}: empty excerpt"
        assert isinstance(c.get("expected"), list), f"{c['id']}: expected must be a list"


# ---------------------------------------------------------------------------
# T02 additions: Turkish subset, per-language F1, repeats, thinking switch
# ---------------------------------------------------------------------------


def test_gold_set_has_turkish_subset_with_negatives() -> None:
    cases = load_gold(_GOLD_PATH)
    tr = [c for c in cases if c.get("lang") == "tr"]
    assert len(tr) >= 10
    assert sum(1 for c in tr if not c["expected"]) >= 3


def test_aggregate_reports_f1_per_language() -> None:
    from evals.extraction_eval import aggregate as agg_fn

    en = score_case({"id": "e", "expected": [{"subject": "user", "object": "neovim"}]},
                    [_triple("user", "uses", "neovim")])
    tr = dict(score_case({"id": "t", "lang": "tr", "expected": [{"subject": "user", "object": "ankara"}]}, []))
    agg = agg_fn([en, tr])
    assert agg["f1_by_lang"]["en"] == 1.0 and agg["f1_by_lang"]["tr"] == 0.0


def test_repeat_spread_f1() -> None:
    from evals.extraction_eval import repeat_spread

    hit = score_case({"id": "e", "expected": [{"subject": "user", "object": "x"}]}, [_triple("user", "is", "x")])
    miss = score_case({"id": "e", "expected": [{"subject": "user", "object": "x"}]}, [])
    spread = repeat_spread([{**hit, "repeat": 0}, {**miss, "repeat": 1}])
    assert spread["repeats"] == 2 and spread["f1_by_repeat"] == [1.0, 0.0] and spread["f1_sd"] == 0.5


def test_run_extraction_retries_without_think_when_unsupported(monkeypatch) -> None:
    import ollama

    from evals.extraction_eval import run_extraction

    seen: list[dict] = []

    def fake_chat(**kw):
        seen.append(kw)
        if "think" in kw:
            raise RuntimeError("model does not support thinking")
        return {"message": {"content": '{"relations":[{"subject":"user","predicate":"uses","object":"neovim"}]}'}}

    monkeypatch.setattr(ollama, "chat", fake_chat)
    rels = run_extraction("User: I use neovim", "m", think=False)
    assert rels and rels[0]["object"] == "neovim"
    assert "think" in seen[0] and "think" not in seen[1]
