"""Tool-calling eval (Gate A): score how reliably a chat model picks the right
tool — or correctly picks none — for Celestia's real tool set.

Each case in ``toolcall_gold.jsonl`` is sent through the *production* message
builder (``agent._build_fresh_messages``: personality system prompt + the
per-mode PC-control hints) with the *production* tool schemas
(``registry.tool_schemas()``) filtered for the case's security mode. Only the
model's **first response** is scored: which tool(s) it called and with what
arguments. **No tool is ever executed** — the preflight (which can open URLs)
is skipped, memory context is left out (no Chroma needed), and the security
mode is patched in-process, so the shared state file is never touched.

Usage (Ollama must be running)::

    .\\venv\\Scripts\\python.exe -m evals.toolcall_eval                        # config chat model
    .\\venv\\Scripts\\python.exe -m evals.toolcall_eval --model qwen2.5:7b
    .\\venv\\Scripts\\python.exe -m evals.toolcall_eval --model llama3.2:3b,qwen2.5:7b,qwen3:8b
    .\\venv\\Scripts\\python.exe -m evals.toolcall_eval --only todo-add-01,neg-greeting -v
    .\\venv\\Scripts\\python.exe -m evals.toolcall_eval --model qwen3:8b --no-think --out-dir evals/results

Metrics (per model): **pass rate** (tool + args right, no red flags);
**tool accuracy** on cases that need a tool; **arg accuracy** given the right
tool; **negatives clean** (chit-chat / blocked requests where calling nothing is
correct); and three red flags — **forbidden** (a dangerous or clearly wrong tool
was called), **unknown** (a tool name that was not offered, i.e. hallucinated),
and **claimed** (no tool call, but the reply claims the action happened — the
"I've opened it!" failure). Latency is measured after a warm-up call so model
load time is excluded. Case schema is documented in evals/README.md.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from unittest import mock

_GOLD_PATH = Path(__file__).parent / "toolcall_gold.jsonl"
_MODES = ("safe", "scoped", "armed")

# Reply text that asserts an action was performed. Only checked when the model
# made no tool call on a case that needed one — then it is a fabricated action.
_CLAIM_RE = re.compile(
    r"\b(i(?:'ve| have)? (?:just )?(?:opened|launched|started|added|saved|created|"
    r"deleted|removed|written|wrote|copied|ran|executed|marked|remembered|noted|stored)|"
    r"(?:opened|launched|added|saved|deleted|removed)[.!]|"
    r"açtım|ekledim|kaydettim|sildim)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Scoring (pure — unit-tested in tests/test_toolcall_eval.py)
# ---------------------------------------------------------------------------


def _as_list(field: Any) -> list[str]:
    if field is None:
        return []
    if isinstance(field, str):
        return [field]
    return [str(x) for x in field]


def arg_matches(value: Any, accepted: Any) -> bool:
    """True when an argument value contains any accepted variant
    (case-insensitive). ``accepted`` of ``None`` / ``[]`` just requires the
    argument to be present and non-empty."""
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = re.sub(r"\s+", " ", text).strip().lower()
    variants = _as_list(accepted)
    if not variants:
        return bool(text) and text not in ('""', "null", "{}", "[]")
    return any(v.strip().lower() in text for v in variants if v.strip())


def args_match(args: dict[str, Any], spec: dict[str, Any] | None) -> bool:
    """Every argument named in ``spec`` must be present and match. Arguments
    not named in the spec are free (models may add optional params)."""
    if not spec:
        return True
    for key, accepted in spec.items():
        if key not in args or args[key] is None:
            return False
        if not arg_matches(args[key], accepted):
            return False
    return True


def score_case(
    case: dict[str, Any],
    calls: list[dict[str, Any]],
    reply: str,
    offered: set[str],
) -> dict[str, Any]:
    """Score one case from the model's first response.

    ``calls`` is ``[{"name": str, "arguments": dict}, ...]`` in order;
    ``offered`` is the set of tool names the model was given.
    """
    expect = case.get("expect")
    expected_tools = set(_as_list(expect.get("tool"))) if expect else set()
    expected_tools |= set(_as_list(case.get("acceptable_tools"))) if expect else set()
    forbidden = set(_as_list(case.get("forbidden_tools")))

    names = [c["name"] for c in calls]
    unknown = [n for n in names if n not in offered]
    forbidden_hits = [n for n in names if n in forbidden]

    if expect:
        # Some call must be an expected tool. Extra, non-forbidden calls in the
        # same response are tolerated (e.g. todo_list alongside todo_complete).
        hit = next((c for c in calls if c["name"] in expected_tools), None)
        tool_ok = hit is not None
        args_ok = tool_ok and args_match(hit["arguments"], expect.get("args"))
        claimed = not calls and bool(_CLAIM_RE.search(reply or ""))
    else:
        tool_ok = not calls
        args_ok = tool_ok
        claimed = False

    passed = tool_ok and args_ok and not unknown and not forbidden_hits and not claimed
    return {
        "id": case.get("id", "?"),
        "mode": case.get("mode", "safe"),
        "category": case.get("category", ""),
        "is_negative": not expect,
        "expected": sorted(expected_tools),
        "called": [f"{c['name']}({json.dumps(c['arguments'], ensure_ascii=False)})" for c in calls],
        "tool_ok": tool_ok,
        "args_ok": args_ok,
        "unknown": unknown,
        "forbidden_hits": forbidden_hits,
        "claimed": claimed,
        "passed": passed,
        "reply": (reply or "")[:300],
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    pos = [r for r in results if not r["is_negative"]]
    neg = [r for r in results if r["is_negative"]]
    tool_right = [r for r in pos if r["tool_ok"]]
    secs = [r["seconds"] for r in results if "seconds" in r]

    def _rate(n: int, d: int) -> float:
        return round(n / d, 3) if d else 1.0

    return {
        "cases": len(results),
        "pass_rate": _rate(sum(r["passed"] for r in results), len(results)),
        "tool_accuracy": _rate(len(tool_right), len(pos)),
        "arg_accuracy": _rate(sum(r["args_ok"] for r in tool_right), len(tool_right)),
        "negatives_clean": sum(r["tool_ok"] for r in neg),
        "negatives_total": len(neg),
        "forbidden_hits": sum(len(r["forbidden_hits"]) for r in results),
        "unknown_tools": sum(len(r["unknown"]) for r in results),
        "claimed_actions": sum(r["claimed"] for r in results),
        "latency_mean_s": round(statistics.mean(secs), 2) if secs else None,
        "latency_p50_s": round(statistics.median(secs), 2) if secs else None,
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
            case = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path.name}:{line_no}: bad JSON — {e}")
        if case.get("mode", "safe") not in _MODES:
            raise SystemExit(f"{path.name}:{line_no}: unknown mode {case.get('mode')!r}")
        cases.append(case)
    return cases


def build_request(case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Production messages + tool schemas for the case's mode, with no side
    effects: the mode is patched in-process and memory context is empty."""
    from celestia_core import agent

    mode = case.get("mode", "safe")
    with mock.patch("celestia_core.security.get_mode", return_value=mode):
        from skills.registry import tool_schemas

        schemas = tool_schemas()
        messages = agent._build_fresh_messages(case["prompt"], mem_ctx="")
    if case.get("history"):
        # Mirror agent._prepare_messages: prior turns follow the personality
        # prompt, then this turn's hints, then the new user message.
        messages = messages[:1] + list(case["history"]) + messages[1:]
    return messages, schemas


def _field(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def parse_response(resp: Any) -> tuple[list[dict[str, Any]], str]:
    """(calls, reply_text) from an ollama chat response (dict or typed)."""
    msg = _field(resp, "message") or {}
    calls: list[dict[str, Any]] = []
    for tc in _field(msg, "tool_calls") or []:
        fn = _field(tc, "function") or {}
        raw = _field(fn, "arguments")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                raw = {"_raw": raw}
        calls.append({"name": str(_field(fn, "name") or ""), "arguments": dict(raw or {})})
    return calls, str(_field(msg, "content") or "")


def _chat(client: Any, model: str, messages: list, tools: list, think: bool | None) -> Any:
    from celestia_core.config import get

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "options": {"num_predict": int(get("llm.max_tokens", 1024)), "temperature": 0.0},
    }
    if think is not None:
        kwargs["think"] = think
    return client.chat(**kwargs)


def run_model(
    model: str,
    cases: list[dict[str, Any]],
    *,
    think: bool | None,
    verbose: bool,
) -> dict[str, Any]:
    import ollama

    from celestia_core.config import get

    client = ollama.Client(
        host=get("llm.host", "http://127.0.0.1:11434"),
        timeout=float(get("llm.request_timeout_seconds", 60)) * 3,
    )

    print(f"\ntool-call eval — model: {model}, cases: {len(cases)}")
    # Warm-up so the first case's latency doesn't include the model load.
    try:
        client.chat(model=model, messages=[{"role": "user", "content": "hi"}],
                    options={"num_predict": 1})
    except Exception as e:  # noqa: BLE001 — report and skip this model
        print(f"  !! could not load {model}: {e}")
        return {"model": model, "error": str(e)}

    results = []
    for case in cases:
        messages, schemas = build_request(case)
        offered = {s["function"]["name"] for s in schemas}
        started = time.monotonic()
        try:
            calls, reply = parse_response(_chat(client, model, messages, schemas, think))
        except Exception as e:  # noqa: BLE001 — a failed call scores as a miss
            calls, reply = [], f"<error: {e}>"
        r = score_case(case, calls, reply, offered)
        r["seconds"] = round(time.monotonic() - started, 2)
        results.append(r)

        flags = []
        if r["forbidden_hits"]:
            flags.append("FORBIDDEN " + ",".join(r["forbidden_hits"]))
        if r["unknown"]:
            flags.append("UNKNOWN " + ",".join(r["unknown"]))
        if r["claimed"]:
            flags.append("CLAIMED")
        status = "ok  " if r["passed"] else ("ARGS" if r["tool_ok"] else "FAIL")
        called = ", ".join(c.split("(")[0] for c in r["called"]) or "—"
        want = "|".join(r["expected"]) or "none"
        tail = f"  !! {' · '.join(flags)}" if flags else ""
        print(f"  [{status}] {r['id']:<24} {r['mode']:<6} want {want:<22} got {called} ({r['seconds']}s){tail}")
        if verbose and not r["passed"]:
            for c in r["called"]:
                print(f"          call:  {c}")
            if r["reply"]:
                print(f"          reply: {r['reply'][:160]!r}")

    agg = aggregate(results)
    print(
        f"\n  pass {agg['pass_rate']}  tool {agg['tool_accuracy']}  args {agg['arg_accuracy']}"
        f"  |  negatives clean {agg['negatives_clean']}/{agg['negatives_total']}"
        f"  |  forbidden {agg['forbidden_hits']}  unknown {agg['unknown_tools']}"
        f"  claimed {agg['claimed_actions']}  |  p50 {agg['latency_p50_s']}s"
    )
    return {
        "model": model,
        "think": think,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "aggregate": agg,
        "cases": results,
    }


def _slug(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.]+", "-", model).strip("-")


def print_comparison(runs: list[dict[str, Any]]) -> None:
    ok = [r for r in runs if "aggregate" in r]
    if len(ok) < 2:
        return
    cols = ("pass", "tool", "args", "neg", "forb", "unk", "claim", "p50 s")
    width = max(len(r["model"]) for r in ok) + 2
    print("\n" + "model".ljust(width) + "".join(c.rjust(8) for c in cols))
    for r in sorted(ok, key=lambda r: -r["aggregate"]["pass_rate"]):
        a = r["aggregate"]
        vals = (
            a["pass_rate"], a["tool_accuracy"], a["arg_accuracy"],
            f"{a['negatives_clean']}/{a['negatives_total']}",
            a["forbidden_hits"], a["unknown_tools"], a["claimed_actions"], a["latency_p50_s"],
        )
        print(r["model"].ljust(width) + "".join(str(v).rjust(8) for v in vals))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Tool-calling eval (Gate A)")
    parser.add_argument("--model", help="Ollama model(s), comma-separated (default: llm.chat_model)")
    parser.add_argument("--cases", type=Path, default=_GOLD_PATH, help="gold JSONL path")
    parser.add_argument("--only", help="comma-separated case ids to run")
    parser.add_argument("--mode", choices=_MODES, help="run only cases for this security mode")
    parser.add_argument("--out-dir", type=Path, help="write toolcall-<model>.json per model here")
    think = parser.add_mutually_exclusive_group()
    think.add_argument("--think", dest="think", action="store_true", default=None,
                       help="force thinking on (reasoning models)")
    think.add_argument("--no-think", dest="think", action="store_false",
                       help="force thinking off (reasoning models; faster)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print calls/replies on misses")
    args = parser.parse_args(argv)

    from celestia_core.config import get

    models = [m.strip() for m in (args.model or get("llm.chat_model", "llama3.2:3b")).split(",") if m.strip()]
    cases = load_gold(args.cases)
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        cases = [c for c in cases if c.get("id") in wanted]
    if args.mode:
        cases = [c for c in cases if c.get("mode", "safe") == args.mode]
    if not cases:
        raise SystemExit("no cases selected")

    runs = [run_model(m, cases, think=args.think, verbose=args.verbose) for m in models]
    print_comparison(runs)

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for run in runs:
            out = args.out_dir / f"toolcall-{_slug(run['model'])}.json"
            out.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  results → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
