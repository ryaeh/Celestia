"""Running-summary eval (T15): does working memory keep what matters?

Each case is a long chat cut into checkpoints (``segments``). The summarizer
runs once per checkpoint — previous summary + that segment's messages, the
same as production — and the *final* summary is scored:

  retention   expected facts still present at the end (early ones are the point)
  exact       exact values (numbers, dates, paths, commands) kept verbatim
  now         the summary knows what the chat is on at the end
  forbidden   secrets, hypotheticals-as-decisions, invented content
  chars       length of what would be sent each turn

Two pipelines on the same cases:

  structured  ``skills/memory/session_summary.py`` — fields + carry-over merge
  prose       the step-3 plain paragraph, kept as the baseline

Usage (Ollama must be running)::

    .\\venv\\Scripts\\python.exe -m evals.summary_eval --model qwen3.5:4b
    .\\venv\\Scripts\\python.exe -m evals.summary_eval --model qwen3.5:4b --pipeline structured -v
    .\\venv\\Scripts\\python.exe -m evals.summary_eval --model qwen3.5:4b --json out/s.json --markdown out/s.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from evals.extraction_eval import _as_list, load_gold

_GOLD_PATH = Path(__file__).parent / "summary_gold.jsonl"


# ---------------------------------------------------------------------------
# Scoring (pure — unit-tested in tests/test_summary_eval.py)
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def mentions_match(text: str, groups: Any) -> bool:
    t = _norm(text)
    return all(any(_norm(alt) and _norm(alt) in t for alt in _as_list(g)) for g in groups or [])


def score_case(case: dict[str, Any], final_text: str, now_text: str) -> dict[str, Any]:
    expect = case.get("expect", [])
    hits = [mentions_match(final_text, e.get("mentions")) for e in expect]
    early = [h for h, e in zip(hits, expect) if int(e.get("seg", 0)) == 0]
    exact = case.get("exact", [])
    flat = re.sub(r"\s+", " ", final_text)
    exact_hits = [x for x in exact if re.sub(r"\s+", " ", x).lower() in flat.lower()]
    forbidden = [f for f in _as_list(case.get("forbidden")) if _norm(f) in _norm(final_text)]
    now_ok = mentions_match(now_text, [case["now"][0]] if case.get("now") else []) if case.get("now") else True
    max_chars = int(case.get("max_chars", 2000))
    missed = [e.get("mentions") for h, e in zip(hits, expect) if not h]
    return {
        "id": case.get("id", "?"),
        "retained": sum(hits),
        "expected": len(expect),
        "early_retained": sum(early),
        "early_expected": len(early),
        "exact_kept": len(exact_hits),
        "exact_total": len(exact),
        "forbidden_hits": forbidden,
        "now_ok": now_ok,
        "chars": len(final_text),
        "too_long": len(final_text) > max_chars,
        "missed": missed,
        "missed_exact": [x for x in exact if x not in exact_hits],
        "passed": all(hits) and len(exact_hits) == len(exact) and not forbidden and now_ok
        and len(final_text) <= max_chars,
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    def ratio(a: str, b: str) -> float:
        tot = sum(r[b] for r in results)
        return round(sum(r[a] for r in results) / tot, 3) if tot else 1.0

    return {
        "cases": len(results),
        "passed": sum(r["passed"] for r in results),
        "retention": ratio("retained", "expected"),
        "early_retention": ratio("early_retained", "early_expected"),
        "exact": ratio("exact_kept", "exact_total"),
        "now": sum(r["now_ok"] for r in results),
        "forbidden_hits": sum(len(r["forbidden_hits"]) for r in results),
        "avg_chars": round(sum(r["chars"] for r in results) / len(results)) if results else 0,
        "errors": sum(1 for r in results if r.get("error")),
    }


# ---------------------------------------------------------------------------
# Runner (needs Ollama)
# ---------------------------------------------------------------------------


def _chat(model: str, prompt: str, *, schema: dict | None, num_predict: int) -> str:
    import ollama

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"num_predict": num_predict, "temperature": 0.0},
    }
    if schema is not None:
        kwargs["format"] = schema
    try:
        resp = ollama.chat(**kwargs, think=False)
    except Exception as e:
        if "think" not in str(e).lower():
            raise
        resp = ollama.chat(**kwargs)
    msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
    return str((msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or "")


def _transcript(messages: list[dict[str, Any]]) -> str:
    # The production window text (assistant replies truncated, secrets scrubbed).
    from skills.memory.scrub import scrub_for_storage
    from skills.memory.writer_pass import transcript

    return scrub_for_storage(transcript(messages, 0))


def run_case(case: dict[str, Any], model: str, pipeline: str) -> tuple[str, str]:
    """Returns (final summary text as sent to the chat model, its 'now' part)."""
    from skills.memory import session_summary as ss

    if pipeline == "prose":
        summary = ""
        for seg in case["segments"]:
            raw = _chat(model, ss.build_prose_prompt(_transcript(seg), summary), schema=None, num_predict=300)
            summary = ss.clean_prose(raw) or summary
        return summary, summary
    state: Any = ss.empty()
    for seg in case["segments"]:
        raw = _chat(model, ss.build_prompt(_transcript(seg), state), schema=ss.OUTPUT_SCHEMA, num_predict=900)
        update = ss.parse(raw)
        if update is not None:
            state = ss.merge(state, update)
    return ss.render(state), state["now"]


def run_pipeline(model: str, cases: list[dict[str, Any]], pipeline: str, verbose: bool) -> dict[str, Any]:
    print(f"\n{model} · {pipeline} · {len(cases)} cases")
    results = []
    for case in cases:
        started = time.monotonic()
        try:
            text, now = run_case(case, model, pipeline)
            r = score_case(case, text, now)
            r["summary"] = text
        except Exception as e:
            r = score_case(case, "", "")
            r.update(error=str(e)[:300], passed=False, summary="")
        r["seconds"] = round(time.monotonic() - started, 1)
        results.append(r)
        tag = "ok  " if r["passed"] else ("ERR " if r.get("error") else "FAIL")
        flags = []
        if r["forbidden_hits"]:
            flags.append("!! FORBIDDEN " + ",".join(r["forbidden_hits"]))
        if not r["now_ok"]:
            flags.append("now?")
        print(
            f"  [{tag}] {r['id']:<18} kept {r['retained']}/{r['expected']} (early {r['early_retained']}/{r['early_expected']})"
            f" · exact {r['exact_kept']}/{r['exact_total']} · {r['chars']} chars ({r['seconds']}s) {' · '.join(flags)}".rstrip()
        )
        if verbose:
            for m in r["missed"]:
                print(f"          missed: {m}")
            for m in r["missed_exact"]:
                print(f"          missed exact: {m}")
            print("          " + r["summary"].replace("\n", "\n          "))
    agg = aggregate(results)
    print(
        f"  passed {agg['passed']}/{agg['cases']} · retention {agg['retention']} (early {agg['early_retention']})"
        f" · exact {agg['exact']} · now {agg['now']}/{agg['cases']} · forbidden {agg['forbidden_hits']}"
        f" · avg {agg['avg_chars']} chars · errors {agg['errors']}"
    )
    return {"model": model, "pipeline": pipeline, "aggregate": agg, "cases": results}


def markdown_table(runs: list[dict[str, Any]]) -> str:
    lines = [
        "## Summary eval (T15 working memory)\n",
        "| model | pipeline | passed | retention | early retention | exact | now | forbidden | avg chars | errors |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in runs:
        a = r["aggregate"]
        lines.append(
            f"| `{r['model']}` | {r['pipeline']} | {a['passed']}/{a['cases']} | {a['retention']} | {a['early_retention']} | "
            f"{a['exact']} | {a['now']}/{a['cases']} | {a['forbidden_hits']} | {a['avg_chars']} | {a['errors']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Running-summary eval (T15)")
    parser.add_argument("--model", required=True, help="Ollama model(s), comma-separated")
    parser.add_argument("--pipeline", default="structured,prose", help="structured, prose, or both")
    parser.add_argument("--cases", type=Path, default=_GOLD_PATH)
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    cases = load_gold(args.cases)
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        cases = [c for c in cases if c.get("id") in wanted]
        if not cases:
            raise SystemExit(f"no cases match --only {args.only}")
    pipelines = [p.strip() for p in args.pipeline.split(",") if p.strip()]
    if bad := [p for p in pipelines if p not in ("structured", "prose")]:
        raise SystemExit(f"unknown pipeline(s): {bad}")

    runs = []
    for model in [m.strip() for m in args.model.split(",") if m.strip()]:
        for p in pipelines:
            runs.append(run_pipeline(model, cases, p, args.verbose))
            table = markdown_table(runs)
            if args.markdown:
                args.markdown.parent.mkdir(parents=True, exist_ok=True)
                args.markdown.write_text(table, encoding="utf-8")
            if args.json:
                args.json.parent.mkdir(parents=True, exist_ok=True)
                args.json.write_text(json.dumps({"runs": runs}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + markdown_table(runs))
    return 1 if any(r["aggregate"]["errors"] for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
