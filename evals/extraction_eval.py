"""Graph-extraction eval (Gate A): score the production extractor against a
hand-labeled gold set.

Runs the *real* extraction prompt + parser (``graph_extract._PROMPT`` /
``_parse_relations``) over each excerpt in ``extraction_gold.jsonl`` and scores
the returned triples — so a prompt tweak, a model swap, or the Phase-2 idle
re-scoring pass can be measured instead of eyeballed. Nothing is written to the
graph.

Usage (Ollama must be running)::

    .\\venv\\Scripts\\python.exe -m evals.extraction_eval            # config default model
    .\\venv\\Scripts\\python.exe -m evals.extraction_eval --model qwen2.5:7b
    .\\venv\\Scripts\\python.exe -m evals.extraction_eval --only pets-01,neg-greeting -v
    .\\venv\\Scripts\\python.exe -m evals.extraction_eval --json evals/results/7b.json

Scoring: an extracted triple matches an expected spec when its subject and
object match any listed variant (normalized, containment-tolerant) and its
predicate contains any ``predicate_any`` substring (predicate is free-form when
the spec omits it). ``optional`` specs rescue precision but never count toward
recall; ``forbidden`` strings flag content that must never be extracted (stale
superseded values, secrets). Case schema is documented in evals/README.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_GOLD_PATH = Path(__file__).parent / "extraction_gold.jsonl"

# Leading noise words dropped before comparison, so "the user" == "user" and
# "my cat" == "cat". Applied repeatedly (handles "the my cat" style output).
_ARTICLES = ("the ", "a ", "an ", "my ", "his ", "her ", "its ", "their ", "user's ")


# ---------------------------------------------------------------------------
# Matching (pure — unit-tested in tests/test_extraction_eval.py)
# ---------------------------------------------------------------------------


def norm(value: str) -> str:
    """Normalize a term for comparison: lowercase, trim quotes/periods,
    collapse whitespace, strip leading articles/possessives."""
    v = re.sub(r"\s+", " ", str(value or "")).strip().strip("\"'.").lower()
    changed = True
    while changed:
        changed = False
        for art in _ARTICLES:
            if v.startswith(art):
                v = v[len(art):]
                changed = True
    return v.strip()


def _as_list(field: Any) -> list[str]:
    if field is None:
        return []
    if isinstance(field, str):
        return [field]
    return [str(x) for x in field]


# First-person forms the extractor legitimately emits where gold says "user".
# Folded on the extracted side only, so spec authors always write "user".
_FIRST_PERSON = {"i", "me", "ben"}


def field_match(value: str, spec_field: Any) -> bool:
    """True when ``value`` matches any accepted variant. Containment counts in
    either direction ("neovim" ~ "neovim editor") with a short-string guard so
    two-letter fragments can't match everything."""
    if spec_field is None:
        return True
    v = norm(value)
    candidates = {v, "user"} if v in _FIRST_PERSON else {v}
    for variant in _as_list(spec_field):
        nv = norm(variant)
        if not nv:
            continue
        for cand in candidates:
            if not cand:
                continue
            if cand == nv:
                return True
            if len(nv) >= 3 and nv in cand:
                return True
            if len(cand) >= 3 and cand in nv:
                return True
    return False


def predicate_match(predicate: str, predicate_any: Any) -> bool:
    """Predicates vary wildly in wording, so a spec either leaves the predicate
    free (omit ``predicate_any``) or lists acceptable substrings."""
    if not predicate_any:
        return True
    p = norm(predicate)
    return any(norm(sub) in p for sub in _as_list(predicate_any))


def triple_matches(extracted: dict[str, Any], spec: dict[str, Any]) -> bool:
    return (
        field_match(extracted.get("subject", ""), spec.get("subject"))
        and field_match(extracted.get("object", ""), spec.get("object"))
        and predicate_match(extracted.get("predicate", ""), spec.get("predicate_any"))
    )


def score_case(case: dict[str, Any], extracted: list[dict[str, Any]]) -> dict[str, Any]:
    """Score one gold case. Greedy 1:1 matching of extracted triples against
    ``expected`` specs; leftovers may still match ``optional`` specs (rescuing
    precision without inflating recall)."""
    expected: list[dict[str, Any]] = case.get("expected", [])
    optional: list[dict[str, Any]] = case.get("optional", [])

    matched_expected: set[int] = set()
    accounted: set[int] = set()

    for i, ext in enumerate(extracted):
        for j, spec in enumerate(expected):
            if j not in matched_expected and triple_matches(ext, spec):
                matched_expected.add(j)
                accounted.add(i)
                break

    for i, ext in enumerate(extracted):
        if i in accounted:
            continue
        if any(triple_matches(ext, spec) for spec in optional):
            accounted.add(i)

    forbidden_hits: list[str] = []
    for banned in _as_list(case.get("forbidden")):
        nb = norm(banned)
        for ext in extracted:
            terms = (norm(ext.get("subject", "")), norm(ext.get("object", "")))
            if any(nb and nb in t for t in terms):
                forbidden_hits.append(banned)
                break

    spurious = [
        f"{e.get('subject')} — {e.get('predicate')} — {e.get('object')}"
        for i, e in enumerate(extracted)
        if i not in accounted
    ]
    missed = [
        f"{spec.get('subject')} — {'|'.join(_as_list(spec.get('predicate_any'))) or '*'} — {spec.get('object')}"
        for j, spec in enumerate(expected)
        if j not in matched_expected
    ]

    return {
        "id": case.get("id", "?"),
        "n_extracted": len(extracted),
        "n_expected": len(expected),
        "tp_precision": len(accounted),   # extracted triples that were justified
        "tp_recall": len(matched_expected),  # expected specs that were found
        "spurious": spurious,
        "missed": missed,
        "forbidden_hits": forbidden_hits,
        # A negative case (expected == []) passes only when nothing is extracted.
        "clean_negative": not expected and not extracted,
        "is_negative": not expected,
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    tp_p = sum(r["tp_precision"] for r in results)
    n_ext = sum(r["n_extracted"] for r in results)
    tp_r = sum(r["tp_recall"] for r in results)
    n_exp = sum(r["n_expected"] for r in results)
    negatives = [r for r in results if r["is_negative"]]

    precision = tp_p / n_ext if n_ext else 1.0
    recall = tp_r / n_exp if n_exp else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "cases": len(results),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "negatives_clean": sum(1 for r in negatives if r["clean_negative"]),
        "negatives_total": len(negatives),
        "forbidden_hits": sum(len(r["forbidden_hits"]) for r in results),
    }


# ---------------------------------------------------------------------------
# Runner (needs Ollama)
# ---------------------------------------------------------------------------


def load_gold(path: Path) -> list[dict[str, Any]]:
    cases = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path.name}:{line_no}: bad JSON — {e}")
    return cases


def _default_model() -> str:
    # Mirror extract_and_store's resolution chain, so the eval measures what
    # production would actually run.
    from celestia_core.config import get

    return (
        get("memory.graph.extraction_model")
        or get("memory.session_consolidate_model")
        or get("llm.chat_model", "llama3.2:3b")
    )


def run_extraction(excerpt: str, model: str) -> list[dict[str, Any]]:
    """One extraction pass with the production prompt + parser; no graph writes."""
    import ollama

    from skills.memory.graph_extract import _PROMPT, _parse_relations

    resp = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": _PROMPT + excerpt}],
        options={"num_predict": 512, "temperature": 0.0},
    )
    msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
    raw = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
    return _parse_relations(str(raw))


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often default to a legacy codepage (cp1254 etc.) that
    # can't print the report's punctuation or Turkish excerpts.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Graph-extraction eval (Gate A)")
    parser.add_argument("--model", help="Ollama model to eval (default: config chain)")
    parser.add_argument("--cases", type=Path, default=_GOLD_PATH, help="gold JSONL path")
    parser.add_argument("--only", help="comma-separated case ids to run")
    parser.add_argument("--json", type=Path, help="write full results JSON here")
    parser.add_argument("-v", "--verbose", action="store_true", help="print triples per case")
    args = parser.parse_args(argv)

    model = args.model or _default_model()
    cases = load_gold(args.cases)
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        cases = [c for c in cases if c.get("id") in wanted]
        if not cases:
            raise SystemExit(f"no cases match --only {args.only}")

    print(f"extraction eval — model: {model}, cases: {len(cases)}\n")

    results = []
    for case in cases:
        started = time.monotonic()
        extracted = run_extraction(case["excerpt"], model)
        elapsed = time.monotonic() - started
        r = score_case(case, extracted)
        r["seconds"] = round(elapsed, 1)
        results.append(r)

        if r["is_negative"]:
            ok = "ok  " if r["clean_negative"] else "FAIL"
            detail = "clean" if r["clean_negative"] else f"{r['n_extracted']} spurious"
        else:
            full = r["tp_recall"] == r["n_expected"] and not r["spurious"]
            ok = "ok  " if full else "MISS"
            detail = (
                f"recall {r['tp_recall']}/{r['n_expected']}"
                f" · extracted {r['n_extracted']} ({len(r['spurious'])} spurious)"
            )
        flag = "  !! FORBIDDEN" if r["forbidden_hits"] else ""
        print(f"  [{ok}] {r['id']:<22} {detail} ({r['seconds']}s){flag}")
        if args.verbose:
            for s in r["spurious"]:
                print(f"          spurious: {s}")
            for m in r["missed"]:
                print(f"          missed:   {m}")

    agg = aggregate(results)
    print(
        f"\n  precision {agg['precision']}  recall {agg['recall']}  f1 {agg['f1']}"
        f"  |  negatives clean {agg['negatives_clean']}/{agg['negatives_total']}"
        f"  |  forbidden hits {agg['forbidden_hits']}"
    )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {"model": model, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "aggregate": agg, "cases": results},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"  results → {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
