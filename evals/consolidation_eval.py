"""Consolidation eval (T15): score a memory pass against a hand-labeled gold set.

Each case gives the memories that already exist, an optional rolling session
summary, and a chat transcript. The pass under test returns *operations* on
text memory (add / update / supersede / forget), each with graph triples. The
scorer checks that the right memories change, that restated facts are left
alone, and that the text and the graph say the same thing.

Two pipelines can be scored on the same cases:

  writer   the T15 memory writer (``skills/memory/writer.py``) — one call,
           sees existing memories, emits targeted ops with triples.
  legacy   today's production path — the typed-consolidation prompt + word-
           overlap dedupe (``session_consolidate``) and the separate graph
           extraction (``graph_extract``). It can only add, so every correction
           is a miss by construction; that gap is what T15 must close.

Usage (Ollama must be running)::

    .\\venv\\Scripts\\python.exe -m evals.consolidation_eval --model qwen3.5:4b
    .\\venv\\Scripts\\python.exe -m evals.consolidation_eval --model qwen3.5:4b --think on,off
    .\\venv\\Scripts\\python.exe -m evals.consolidation_eval --model qwen2.5:3b --pipeline legacy
    .\\venv\\Scripts\\python.exe -m evals.consolidation_eval --only move-01,dup-01 -v --json out/c.json

Case schema: see evals/README.md ("Consolidation eval").
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from evals.extraction_eval import _as_list, load_gold, norm, triple_matches

_GOLD_PATH = Path(__file__).parent / "consolidation_gold.jsonl"
_CONTENT_OPS = ("add", "update", "supersede")


# ---------------------------------------------------------------------------
# Matching (pure — unit-tested in tests/test_consolidation_eval.py)
# ---------------------------------------------------------------------------


def mentions_match(text: str, groups: Any) -> bool:
    """Every group must be satisfied; a group is a list of alternatives, any of
    which may appear (normalized substring) in ``text``."""
    t = norm(text)
    for group in groups or []:
        if not any(norm(alt) and norm(alt) in t for alt in _as_list(group)):
            return False
    return True


def op_matches(op: dict[str, Any], spec: dict[str, Any]) -> bool:
    if op.get("op") not in _as_list(spec.get("op_any")):
        return False
    if spec.get("target") is not None and op.get("target") != spec["target"]:
        return False
    if spec.get("kind") and op.get("op") != "forget" and op.get("kind") != spec["kind"]:
        return False
    if op.get("op") != "forget" and not mentions_match(op.get("text", ""), spec.get("mentions")):
        return False
    return True


def _op_terms(op: dict[str, Any]) -> list[str]:
    terms = [norm(op.get("text", ""))]
    for t in op.get("triples") or []:
        terms += [norm(t.get("subject", "")), norm(t.get("object", ""))]
    return [x for x in terms if x]


def is_duplicate_add(op: dict[str, Any], existing: list[dict[str, Any]]) -> str | None:
    """An ``add`` that restates an existing memory → that memory's id. Uses the
    gold ``key`` mention groups when present, else production's word-overlap test."""
    if op.get("op") != "add":
        return None
    from skills.memory.session_consolidate import _is_duplicate

    for e in existing:
        if e.get("key"):
            if mentions_match(op.get("text", ""), e["key"]):
                return e["id"]
        elif _is_duplicate(op.get("text", ""), [e.get("text", "")]):
            return e["id"]
    return None


def score_case(
    case: dict[str, Any],
    ops: list[dict[str, Any]],
    *,
    summary: str = "",
    graph_triples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score one case. ``graph_triples`` is the legacy pipeline's separately
    extracted graph; the writer's triples live on its ops."""
    expected: list[dict[str, Any]] = case.get("expected", [])
    optional: list[dict[str, Any]] = case.get("optional", [])
    existing: list[dict[str, Any]] = case.get("existing", [])

    matched: dict[int, int] = {}  # spec index → op index
    accounted: set[int] = set()
    for j, spec in enumerate(expected):
        for i, op in enumerate(ops):
            if i not in accounted and op_matches(op, spec):
                matched[j] = i
                accounted.add(i)
                break
    for i, op in enumerate(ops):
        if i not in accounted and any(op_matches(op, spec) for spec in optional):
            accounted.add(i)

    duplicates = []
    for i, op in enumerate(ops):
        if i in accounted:
            continue
        dup = is_duplicate_add(op, existing)
        if dup:
            duplicates.append(f"add restates {dup}: {op.get('text')}")

    wrong_touch = []
    untouched = set(_as_list(case.get("untouched")))
    banned_ops: dict[str, list[str]] = case.get("untouched_ops") or {}
    for op in ops:
        tgt = op.get("target")
        if tgt and (tgt in untouched or op.get("op") in banned_ops.get(tgt, [])):
            wrong_touch.append(f"{op.get('op')} {tgt}: {op.get('text') or ''}".strip())

    forbidden_hits = []
    everything = [t for op in ops for t in _op_terms(op)] + [norm(summary)]
    everything += [norm(t.get(k, "")) for t in graph_triples or [] for k in ("subject", "object")]
    for banned in _as_list(case.get("forbidden")):
        if any(norm(banned) in t for t in everything if t):
            forbidden_hits.append(banned)
    add_terms = [t for op in ops if op.get("op") == "add" for t in _op_terms(op)]
    for banned in _as_list(case.get("forbidden_add")):
        if any(norm(banned) in t for t in add_terms):
            forbidden_hits.append(f"add:{banned}")

    # Graph sync: a matched op whose spec names a triple must carry a matching
    # triple (writer), or the separate graph must contain one (legacy).
    sync_total = sync_ok = 0
    for j, i in matched.items():
        spec_triple = expected[j].get("triple")
        if not spec_triple:
            continue
        sync_total += 1
        pool = graph_triples if graph_triples is not None else ops[i].get("triples") or []
        if any(triple_matches(t, spec_triple) for t in pool):
            sync_ok += 1

    corrections = [j for j, s in enumerate(expected) if "add" not in _as_list(s.get("op_any"))]
    spurious = [
        f"{op.get('op')} {op.get('target') or ''} {op.get('text') or ''}".replace("  ", " ").strip()
        for i, op in enumerate(ops)
        if i not in accounted
    ]
    missed = [
        f"{'|'.join(_as_list(s.get('op_any')))} {s.get('target') or ''} {s.get('mentions') or ''}".strip()
        for j, s in enumerate(expected)
        if j not in matched
    ]
    passed = (
        len(matched) == len(expected)
        and not spurious
        and not wrong_touch
        and not forbidden_hits
    )
    return {
        "id": case.get("id", "?"),
        "n_ops": len(ops),
        "n_expected": len(expected),
        "tp_precision": len(accounted),
        "tp_recall": len(matched),
        "corrections_total": len(corrections),
        "corrections_found": sum(1 for j in corrections if j in matched),
        "duplicates": duplicates,
        "wrong_touch": wrong_touch,
        "forbidden_hits": forbidden_hits,
        "sync_total": sync_total,
        "sync_ok": sync_ok,
        "spurious": spurious,
        "missed": missed,
        "is_negative": not expected,
        "clean_negative": not expected and not ops,
        "passed": passed,
        "ops": ops,
        "summary": summary,
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    def total(key: str) -> int:
        return sum(r[key] if isinstance(r[key], int) else len(r[key]) for r in results)

    n_ops, n_exp = total("n_ops"), total("n_expected")
    precision = total("tp_precision") / n_ops if n_ops else 1.0
    recall = total("tp_recall") / n_exp if n_exp else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negatives = [r for r in results if r["is_negative"]]
    sync_total = total("sync_total")
    return {
        "cases": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "corrections": f"{total('corrections_found')}/{total('corrections_total')}",
        "duplicates": total("duplicates"),
        "wrong_touch": total("wrong_touch"),
        "forbidden_hits": total("forbidden_hits"),
        "graph_sync": round(total("sync_ok") / sync_total, 3) if sync_total else None,
        "negatives_clean": sum(1 for r in negatives if r["clean_negative"]),
        "negatives_total": len(negatives),
        "errors": sum(1 for r in results if r.get("error")),
    }


# ---------------------------------------------------------------------------
# Runner (needs Ollama)
# ---------------------------------------------------------------------------


class ThinkUnsupported(RuntimeError):
    pass


def _chat(model: str, prompt: str, *, think: bool | None, num_predict: int, json_mode: bool = False) -> str:
    import ollama

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"num_predict": num_predict, "temperature": 0.0},
    }
    if json_mode:
        # Constrained decoding against the writer's schema: always valid JSON,
        # only known ops/kinds.
        from skills.memory.writer import OUTPUT_SCHEMA

        kwargs["format"] = OUTPUT_SCHEMA
    if think is not None:
        kwargs["think"] = think
    try:
        resp = ollama.chat(**kwargs)
    except Exception as e:
        if think is not None and "think" in str(e).lower():
            if think:
                raise ThinkUnsupported(str(e)) from e
            kwargs.pop("think")  # "off" on a non-thinking model = the default
            resp = ollama.chat(**kwargs)
        else:
            raise
    msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
    raw = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
    return str(raw)


def _scrub(text: str) -> str:
    # Production scrubs secrets before any memory LLM sees the excerpt.
    from skills.memory.scrub import scrub_for_storage

    return scrub_for_storage(text)


def run_writer(case: dict[str, Any], model: str, think: bool | None) -> dict[str, Any]:
    from skills.memory.writer import build_prompt, parse_ops

    existing = case.get("existing", [])
    prompt = build_prompt(_scrub(case["transcript"]), existing, case.get("summary", ""))
    # The writer runs with JSON-constrained output; the legacy prompts run as
    # production runs them today (free text).
    raw = _chat(model, prompt, think=think, num_predict=4096 if think else 1024, json_mode=True)
    result = parse_ops(raw, {e["id"]: e.get("text", "") for e in existing})
    return {
        "ops": [o.as_dict() for o in result.ops],
        "summary": result.summary,
        "graph_triples": None,
        "dropped": result.dropped,
    }


def run_legacy(case: dict[str, Any], model: str) -> dict[str, Any]:
    """Today's path: typed consolidation + dedupe, then separate graph extraction.
    Mirrors ``consolidate_session_messages`` minus the store writes."""
    from skills.memory.graph_extract import _PROMPT, _parse_relations
    from skills.memory.session_consolidate import _is_duplicate, _parse_typed, _reject_entry, build_prompt
    from skills.memory.types import KINDS

    existing = case.get("existing", [])
    excerpt = _scrub(case["transcript"])
    if case.get("summary"):
        # Today's pass has no summary input; the closest it gets is earlier
        # messages in the excerpt, so hand it the summary as a preamble.
        excerpt = f"(Earlier: {case['summary']})\n{excerpt}"
    by_kind = {k: [e["text"] for e in existing if e.get("kind", "fact") == k] for k in KINDS}
    blocks = [f"{k.upper()}:\n" + "\n".join(f"- {t}" for t in v) for k, v in by_kind.items() if v]
    raw = _chat(model, build_prompt("\n\n".join(blocks) or "(none yet)", excerpt), think=False, num_predict=512)
    typed = _parse_typed(raw)

    ops: list[dict[str, Any]] = []
    summaries: list[str] = []
    for kind in KINDS:
        known = list(by_kind[kind])
        for text in typed[kind][:3]:
            text = text.strip()
            if kind == "summary":
                summaries.append(text)
                continue
            if _reject_entry(text, kind) or _is_duplicate(text, known):
                continue
            known.append(text)
            ops.append({"op": "add", "kind": kind, "text": text, "target": None, "triples": []})

    graph = _parse_relations(_chat(model, _PROMPT + excerpt, think=False, num_predict=512))
    return {"ops": ops, "summary": " ".join(summaries), "graph_triples": graph, "dropped": []}


def _variants(pipelines: list[str], thinks: list[str]) -> list[tuple[str, bool | None]]:
    """Cheapest first (legacy, writer think off/default, writer think on), so a
    timeout costs the slow thinking variant rather than the baselines."""
    out: list[tuple[str, bool | None]] = []
    if "legacy" in pipelines:
        out.append(("legacy", False))
    if "writer" in pipelines:
        order = {"off": 0, "default": 1, "on": 2}
        for t in sorted(thinks, key=lambda t: order[t]):
            out.append(("writer", {"on": True, "off": False}.get(t)))
    return out


def _label(pipeline: str, think: bool | None) -> str:
    if pipeline == "legacy":
        return "legacy"
    return f"writer (think {'on' if think else 'off' if think is False else 'default'})"


def run_variant(model: str, cases: list[dict[str, Any]], pipeline: str, think: bool | None, verbose: bool) -> dict[str, Any] | None:
    label = _label(pipeline, think)
    print(f"\n{model} · {label} · {len(cases)} cases")
    results = []
    for case in cases:
        started = time.monotonic()
        try:
            out = run_legacy(case, model) if pipeline == "legacy" else run_writer(case, model, think)
            r = score_case(case, out["ops"], summary=out["summary"], graph_triples=out["graph_triples"])
            r["dropped"] = out["dropped"]
        except ThinkUnsupported as e:
            print(f"  skipped: {model} does not support thinking ({e})")
            return None
        except Exception as e:  # an errored request always fails the case
            r = score_case(case, [])
            r.update(error=str(e)[:300], passed=False, clean_negative=False, dropped=[])
        r["seconds"] = round(time.monotonic() - started, 1)
        results.append(r)

        tag = "ok  " if r["passed"] else ("ERR " if r.get("error") else "FAIL")
        detail = f"ops {r['n_ops']} · found {r['tp_recall']}/{r['n_expected']}"
        flags = []
        if r["duplicates"]:
            flags.append(f"{len(r['duplicates'])} dup")
        if r["wrong_touch"]:
            flags.append("wrong target")
        if r["forbidden_hits"]:
            flags.append("!! FORBIDDEN")
        if r.get("error"):
            flags.append(r["error"][:80])
        print(f"  [{tag}] {r['id']:<16} {detail} ({r['seconds']}s) {' · '.join(flags)}".rstrip())
        if verbose:
            for key in ("spurious", "missed", "duplicates", "wrong_touch", "dropped"):
                for item in r.get(key) or []:
                    print(f"          {key}: {item}")

    agg = aggregate(results)
    print(
        f"  passed {agg['passed']}/{agg['cases']} · f1 {agg['f1']} (p {agg['precision']} r {agg['recall']})"
        f" · corrections {agg['corrections']} · duplicates {agg['duplicates']}"
        f" · wrong target {agg['wrong_touch']} · forbidden {agg['forbidden_hits']}"
        f" · graph sync {agg['graph_sync']} · negatives {agg['negatives_clean']}/{agg['negatives_total']}"
        f" · errors {agg['errors']}"
    )
    return {"model": model, "pipeline": pipeline, "think": think, "label": label, "aggregate": agg, "cases": results}


def markdown_table(runs: list[dict[str, Any]]) -> str:
    lines = [
        "## Consolidation eval (T15)\n",
        "| model | pipeline | passed | f1 | corrections | duplicates | wrong target | forbidden | graph sync | negatives clean | errors |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in runs:
        a = r["aggregate"]
        lines.append(
            f"| `{r['model']}` | {r['label']} | {a['passed']}/{a['cases']} | {a['f1']} | {a['corrections']} | "
            f"{a['duplicates']} | {a['wrong_touch']} | {a['forbidden_hits']} | {a['graph_sync']} | "
            f"{a['negatives_clean']}/{a['negatives_total']} | {a['errors']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Consolidation eval (T15)")
    parser.add_argument("--model", required=True, help="Ollama model(s), comma-separated")
    parser.add_argument("--pipeline", default="writer,legacy", help="writer, legacy, or both (comma-separated)")
    parser.add_argument("--think", default="on,off", help="writer thinking: on, off, default (comma-separated)")
    parser.add_argument("--cases", type=Path, default=_GOLD_PATH, help="gold JSONL path")
    parser.add_argument("--only", help="comma-separated case ids to run")
    parser.add_argument("--json", type=Path, help="write full results JSON here")
    parser.add_argument("--markdown", type=Path, help="write a summary table here")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    cases = load_gold(args.cases)
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        cases = [c for c in cases if c.get("id") in wanted]
        if not cases:
            raise SystemExit(f"no cases match --only {args.only}")
    pipelines = [p.strip() for p in args.pipeline.split(",") if p.strip()]
    if bad := [p for p in pipelines if p not in ("writer", "legacy")]:
        raise SystemExit(f"unknown pipeline(s): {bad}")
    thinks = [t.strip() for t in args.think.split(",") if t.strip()]
    if bad := [t for t in thinks if t not in ("on", "off", "default")]:
        raise SystemExit(f"--think takes on/off/default, got {bad}")

    def write_outputs(runs: list[dict[str, Any]]) -> str:
        # Written after every variant so a job killed mid-run (CPU thinking
        # runs are slow) still leaves the finished variants on disk.
        table = markdown_table(runs)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(table, encoding="utf-8")
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(
                json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "runs": runs}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return table

    runs = []
    for model in [m.strip() for m in args.model.split(",") if m.strip()]:
        for pipeline, think in _variants(pipelines, thinks):
            run = run_variant(model, cases, pipeline, think, args.verbose)
            if run:
                runs.append(run)
                write_outputs(runs)

    print("\n" + write_outputs(runs))
    if args.json:
        print(f"results → {args.json}")
    return 1 if any(r["aggregate"]["errors"] for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
