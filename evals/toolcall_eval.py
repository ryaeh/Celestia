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
    r"\b(i(?:'ve| have)? (?:just |now |already )?(?:opened|launched|started|added|saved|created|"
    r"deleted|removed|written|wrote|copied|ran|executed|marked|remembered|noted|stored|"
    r"updated|changed|completed|renamed|moved|scheduled|closed|sent|cleared)|"
    # "set" is also present tense ("Should I set…?"), so only the perfect form counts.
    r"i(?:'ve| have) (?:just |now |already )?set\b|"
    r"(?:opened|launched|added|saved|deleted|removed|updated)[.!]|"
    r"açtım|ekledim|kaydettim|sildim|güncelledim|değiştirdim|tamamladım|işaretledim|not ettim|not aldım)",
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
    error: str = "",
) -> dict[str, Any]:
    """Score one case from the model's first response.

    ``calls`` is ``[{"name": str, "arguments": dict}, ...]`` in order;
    ``offered`` is the set of tool names the model was given. A request that
    *errored* (Ollama down, model without tool support, timeout) fails outright —
    it must never count as a clean "no tool" answer on a negative case.
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

    if error:
        tool_ok = args_ok = claimed = False
    passed = tool_ok and args_ok and not unknown and not forbidden_hits and not claimed
    return {
        "id": case.get("id", "?"),
        "mode": case.get("mode", "safe"),
        "lang": case.get("lang", "en"),
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
        "error": error[:300],
        "reply": (reply or "")[:300],
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    pos = [r for r in results if not r["is_negative"]]
    neg = [r for r in results if r["is_negative"]]
    prompt_toks = [r["prompt_tokens"] for r in results if r.get("prompt_tokens")]
    tool_right = [r for r in pos if r["tool_ok"]]
    secs = [r["seconds"] for r in results if "seconds" in r]
    ttft = [r["ttft_s"] for r in results if r.get("ttft_s") is not None]
    tok_s = [r["tok_per_s"] for r in results if r.get("tok_per_s")]

    def _rate(n: int, d: int) -> float:
        return round(n / d, 3) if d else 1.0

    by_lang: dict[str, float] = {}
    for lang in sorted({r.get("lang", "en") for r in results}):
        subset = [r for r in results if r.get("lang", "en") == lang]
        by_lang[lang] = _rate(sum(r["passed"] for r in subset), len(subset))

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
        "errors": sum(1 for r in results if r.get("error")),
        "latency_mean_s": round(statistics.mean(secs), 2) if secs else None,
        "latency_p50_s": round(statistics.median(secs), 2) if secs else None,
        "prompt_tokens_max": max(prompt_toks) if prompt_toks else None,
        "ttft_p50_s": round(statistics.median(ttft), 2) if ttft else None,
        "tok_per_s_p50": round(statistics.median(tok_s), 1) if tok_s else None,
        "pass_by_lang": by_lang,
    }


def repeat_spread(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Run-to-run spread when cases were attempted several times (``--repeat``).

    Returns the pass rate of each repeat, their standard deviation, and the
    cases that passed on some attempts but not others ("unstable") — the ones a
    single run would score by luck.
    """
    repeats = sorted({r.get("repeat", 0) for r in results})
    per_repeat = []
    for k in repeats:
        subset = [r for r in results if r.get("repeat", 0) == k]
        per_repeat.append(round(sum(r["passed"] for r in subset) / len(subset), 3) if subset else 0.0)
    by_case: dict[str, list[bool]] = {}
    for r in results:
        by_case.setdefault(r["id"], []).append(bool(r["passed"]))
    unstable = sorted(cid for cid, oks in by_case.items() if any(oks) and not all(oks))
    return {
        "repeats": len(repeats),
        "pass_rate_by_repeat": per_repeat,
        "pass_rate_sd": round(statistics.pstdev(per_repeat), 3) if len(per_repeat) > 1 else 0.0,
        "unstable_cases": unstable,
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


def usage(resp: Any) -> tuple[int | None, int | None]:
    """(prompt_tokens, output_tokens) as Ollama reports them, when present."""
    return _field(resp, "prompt_eval_count"), _field(resp, "eval_count")


def timing(resp: Any) -> tuple[float | None, float | None]:
    """(time_to_first_token_s, output_tokens_per_s) from Ollama's durations (ns).

    TTFT ≈ load + prompt evaluation — what the user waits before the first
    token of a streamed reply. Both are None when the fields are missing.
    """
    prompt_ns = _field(resp, "prompt_eval_duration")
    load_ns = _field(resp, "load_duration") or 0
    eval_ns, eval_n = _field(resp, "eval_duration"), _field(resp, "eval_count")
    ttft = round((prompt_ns + load_ns) / 1e9, 3) if prompt_ns is not None else None
    tps = round(eval_n / (eval_ns / 1e9), 1) if eval_ns and eval_n else None
    return ttft, tps


def parse_temperature(value: str | None) -> float | None:
    """``"model"`` (or None) → don't set it: the model's default, which is what
    Celestia's chat loop uses. Anything else must be a number."""
    if value is None or str(value).strip().lower() in ("", "model", "default"):
        return None
    return float(value)


def ollama_version(host: str) -> str | None:
    """The server's version (``GET /api/version``), recorded with every run so
    results from different Ollama builds aren't compared blindly."""
    try:
        import httpx

        return str(httpx.get(host.rstrip("/") + "/api/version", timeout=5).json().get("version"))
    except Exception:  # noqa: BLE001 — informational only
        return None


def resident_memory(client: Any, model: str) -> dict[str, Any] | None:
    """Size and VRAM share of *model* as loaded (``ollama ps``) — the number the
    GPU residency plan needs. None when unavailable."""
    try:
        listing = client.ps()
    except Exception:  # noqa: BLE001 — informational only
        return None
    wanted = {model, model if ":" in model else f"{model}:latest"}
    for m in _field(listing, "models") or []:
        name = str(_field(m, "model") or _field(m, "name") or "")
        if name in wanted:
            return {"size_bytes": _field(m, "size"), "size_vram_bytes": _field(m, "size_vram")}
    return None


def _chat(
    client: Any,
    model: str,
    messages: list,
    tools: list,
    think: bool | None,
    num_ctx: int | None = None,
    temperature: float | None = 0.0,
    seed: int | None = None,
) -> Any:
    from celestia_core.config import get

    options: dict[str, Any] = {"num_predict": int(get("llm.max_tokens", 1024))}
    if temperature is not None:
        options["temperature"] = temperature
    if seed is not None:
        options["seed"] = seed
    if num_ctx:
        options["num_ctx"] = num_ctx
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "options": options,
    }
    if think is not None:
        kwargs["think"] = think
    return client.chat(**kwargs)


def preflight(client: Any, model: str, think: bool | None = None) -> tuple[str, bool | None]:
    """Load *model* (so case latency excludes load time), confirm it accepts
    tools, and settle the ``think`` flag.

    Returns ``(error, think)``: error is "" when the model is usable. A model
    that rejects the think flag ("does not support thinking") gets ``think``
    dropped to None instead of failing, so one ``--no-think`` works across a
    mixed list of thinking and non-thinking models.
    """
    probe = [{
        "type": "function",
        "function": {"name": "ping", "description": "Ping.", "parameters": {"type": "object", "properties": {}}},
    }]

    def _try(t: bool | None) -> str:
        kwargs: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": "hi"}],
                                  "tools": probe, "options": {"num_predict": 1}}
        if t is not None:
            kwargs["think"] = t
        try:
            client.chat(**kwargs)
        except Exception as e:  # noqa: BLE001 — surfaced to the caller as a skip reason
            return str(e)
        return ""

    msg = _try(think)
    if msg and think is not None and "think" in msg.lower():
        think, msg = None, _try(None)
    if msg:
        if "does not support tools" in msg:
            return f"{model} does not support tool calling in Ollama (pick a model tagged 'tools')", think
        return msg, think
    return "", think


def run_model(
    model: str,
    cases: list[dict[str, Any]],
    *,
    think: bool | None,
    verbose: bool,
    num_ctx: int | None = None,
    timeout: float | None = None,
    repeat: int = 1,
    temperature: float | None = 0.0,
) -> dict[str, Any]:
    import ollama

    from celestia_core.config import get

    host = get("llm.host", "http://127.0.0.1:11434")
    client = ollama.Client(
        host=host,
        timeout=timeout or float(get("llm.request_timeout_seconds", 60)) * 3,
    )
    repeat = max(1, int(repeat))
    version = ollama_version(host)

    temp_label = "model default" if temperature is None else str(temperature)
    print(f"\ntool-call eval — model: {model}, cases: {len(cases)} × {repeat}, "
          f"temperature: {temp_label}, ollama: {version or '?'}")
    requested_think = think
    problem, think = preflight(client, model, think)
    if problem:
        print(f"  !! skipped {model}: {problem}")
        return {"model": model, "error": problem, "ollama_version": version}
    if requested_think is not None and think is None:
        print(f"  (note: {model} has no thinking switch — think flag dropped)")

    results = []
    for rep in range(repeat):
        if repeat > 1:
            print(f"  — repeat {rep + 1}/{repeat}")
        for case in cases:
            r = _run_case(client, model, case, think=think, num_ctx=num_ctx,
                          temperature=temperature, seed=(rep + 1) if repeat > 1 else None)
            r["repeat"] = rep
            results.append(r)
            _print_case(r, verbose)
    resident = resident_memory(client, model)
    return _finish_run(model, results, think=think, requested_think=requested_think,
                       num_ctx=num_ctx, temperature=temperature, version=version, resident=resident)


def _run_case(client: Any, model: str, case: dict[str, Any], *, think: bool | None,
              num_ctx: int | None, temperature: float | None, seed: int | None) -> dict[str, Any]:
    messages, schemas = build_request(case)
    offered = {s["function"]["name"] for s in schemas}
    started = time.monotonic()
    error = ""
    prompt_tokens = output_tokens = ttft = tps = None
    try:
        resp = _chat(client, model, messages, schemas, think, num_ctx, temperature, seed)
        calls, reply = parse_response(resp)
        prompt_tokens, output_tokens = usage(resp)
        ttft, tps = timing(resp)
    except Exception as e:  # noqa: BLE001 — recorded as an error, never as a clean answer
        calls, reply, error = [], "", f"{type(e).__name__}: {e}"
    r = score_case(case, calls, reply, offered, error=error)
    r["seconds"] = round(time.monotonic() - started, 2)
    r["prompt_tokens"] = prompt_tokens
    r["output_tokens"] = output_tokens
    r["ttft_s"] = ttft
    r["tok_per_s"] = tps
    return r


def _print_case(r: dict[str, Any], verbose: bool) -> None:
    flags = []
    if r["forbidden_hits"]:
        flags.append("FORBIDDEN " + ",".join(r["forbidden_hits"]))
    if r["unknown"]:
        flags.append("UNKNOWN " + ",".join(r["unknown"]))
    if r["claimed"]:
        flags.append("CLAIMED")
    if r["error"]:
        flags.append("ERROR " + r["error"][:80])
    status = "ok  " if r["passed"] else ("ERR " if r["error"] else ("ARGS" if r["tool_ok"] else "FAIL"))
    called = ", ".join(c.split("(")[0] for c in r["called"]) or "—"
    want = "|".join(r["expected"]) or "none"
    tail = f"  !! {' · '.join(flags)}" if flags else ""
    print(f"  [{status}] {r['id']:<24} {r['mode']:<6} want {want:<22} got {called} ({r['seconds']}s){tail}")
    if verbose and not r["passed"]:
        for c in r["called"]:
            print(f"          call:  {c}")
        if r["reply"]:
            print(f"          reply: {r['reply'][:160]!r}")


def _finish_run(model: str, results: list[dict[str, Any]], *, think: bool | None,
                requested_think: bool | None, num_ctx: int | None, temperature: float | None,
                version: str | None, resident: dict[str, Any] | None) -> dict[str, Any]:
    agg = aggregate(results)
    spread = repeat_spread(results)
    print(
        f"\n  pass {agg['pass_rate']}  tool {agg['tool_accuracy']}  args {agg['arg_accuracy']}"
        f"  |  negatives clean {agg['negatives_clean']}/{agg['negatives_total']}"
        f"  |  forbidden {agg['forbidden_hits']}  unknown {agg['unknown_tools']}"
        f"  claimed {agg['claimed_actions']}  errors {agg['errors']}"
        f"  |  p50 {agg['latency_p50_s']}s  max prompt {agg['prompt_tokens_max']} tok"
        f"  |  by lang {agg['pass_by_lang']}"
        + (f"  |  repeats {spread['pass_rate_by_repeat']} sd {spread['pass_rate_sd']}"
           if spread["repeats"] > 1 else "")
    )
    run: dict[str, Any] = {
        "model": model,
        "think": think,
        "think_requested": requested_think,
        "num_ctx": num_ctx,
        "temperature": "model" if temperature is None else temperature,
        "ollama_version": version,
        "resident": resident,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "aggregate": agg,
        "spread": spread,
        "cases": results,
    }
    if agg["errors"] == len(results):
        run["error"] = f"every case errored (first: {results[0]['error']})"
    return run


def _slug(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.]+", "-", model).strip("-")


_COLS = ("pass", "± sd", "en", "tr", "tool", "args", "neg", "forb", "unk", "claim", "err",
         "p50 s", "ttft s", "tok/s", "max tok")


def _row(run: dict[str, Any]) -> tuple:
    a = run["aggregate"]
    spread = run.get("spread") or {}
    langs = a.get("pass_by_lang") or {}
    return (
        a["pass_rate"], spread.get("pass_rate_sd", "—") if spread.get("repeats", 1) > 1 else "—",
        langs.get("en", "—"), langs.get("tr", "—"),
        a["tool_accuracy"], a["arg_accuracy"],
        f"{a['negatives_clean']}/{a['negatives_total']}",
        a["forbidden_hits"], a["unknown_tools"], a["claimed_actions"], a.get("errors", 0),
        a["latency_p50_s"], a.get("ttft_p50_s", "—"), a.get("tok_per_s_p50", "—"), a.get("prompt_tokens_max"),
    )


def _ranked(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ok = [r for r in runs if "aggregate" in r]
    return sorted(ok, key=lambda r: -r["aggregate"]["pass_rate"])


def print_comparison(runs: list[dict[str, Any]]) -> None:
    ok = _ranked(runs)
    if len(ok) < 2:
        return
    width = max(len(r["model"]) for r in ok) + 2
    print("\n" + "model".ljust(width) + "".join(c.rjust(8) for c in _COLS))
    for r in ok:
        print(r["model"].ljust(width) + "".join(str(v).rjust(8) for v in _row(r)))


def markdown_report(runs: list[dict[str, Any]]) -> str:
    """Comparison table + per-model misses, as Markdown (CI job summary / PR)."""
    lines = ["## Tool-call eval", "", "| model | " + " | ".join(_COLS) + " |",
             "|---|" + "---:|" * len(_COLS)]
    for r in _ranked(runs):
        lines.append(f"| `{r['model']}` | " + " | ".join(str(v) for v in _row(r)) + " |")
    for r in runs:
        if r.get("error"):
            lines.append(f"\n> ⚠️ `{r['model']}`: {r['error']}")
    lines.append(
        "\npass = right tool + args, no red flags (en/tr = per language) · ± sd = spread across "
        "repeats · neg = correctly called nothing · forb/unk/claim = forbidden tool / hallucinated "
        "tool name / claimed an action it didn't take · err = request failed · ttft = time to first "
        "token (load + prompt) · max tok = largest prompt (tokens)"
    )
    meta = []
    for r in _ranked(runs):
        spread = r.get("spread") or {}
        res = r.get("resident") or {}
        vram = res.get("size_vram_bytes")
        meta.append(
            f"`{r['model']}`: ollama {r.get('ollama_version') or '?'}, temperature {r.get('temperature', 0.0)}, "
            f"think {r.get('think')}, repeats {spread.get('repeats', 1)}"
            + (f", VRAM {vram / 1024**3:.1f} GB" if vram else "")
        )
    if meta:
        lines += ["", "<sub>" + " · ".join(meta) + "</sub>"]
    for r in _ranked(runs):
        misses = [c for c in r["cases"] if not c["passed"]]
        if not misses:
            continue
        attempts: dict[str, int] = {}
        for c in r["cases"]:
            attempts[c["id"]] = attempts.get(c["id"], 0) + 1
        seen: dict[str, dict[str, Any]] = {}
        fails: dict[str, int] = {}
        for c in misses:
            fails[c["id"]] = fails.get(c["id"], 0) + 1
            seen.setdefault(c["id"], c)
        lines += ["", f"<details><summary><code>{r['model']}</code> — {len(seen)} cases missed</summary>", "",
                  "| case | lang | mode | failed | wanted | got (first miss) | note |", "|---|---|---|---|---|---|---|"]
        for cid, c in seen.items():
            got = ", ".join(x.replace("|", "\\|") for x in c["called"]) or "—"
            note = c["error"] or ("claimed action" if c["claimed"] else (c["reply"][:80].replace("\n", " ").replace("|", "\\|")))
            lines.append(f"| {cid} | {c.get('lang', 'en')} | {c['mode']} | {fails[cid]}/{attempts[cid]} | "
                         f"{'/'.join(c['expected']) or 'none'} | {got[:120]} | {note} |")
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Tool-calling eval (Gate A)")
    parser.add_argument("--model", help="Ollama model(s), comma-separated (default: llm.chat_model)")
    parser.add_argument("--cases", type=Path, default=_GOLD_PATH, help="gold JSONL path")
    parser.add_argument("--only", help="comma-separated case ids to run")
    parser.add_argument("--mode", choices=_MODES, help="run only cases for this security mode")
    parser.add_argument("--lang", help="run only cases in this language (en, tr)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="attempt every case N times and report the spread (use with sampling, "
                             "e.g. --temperature model; at temperature 0 repeats are near-identical)")
    parser.add_argument("--temperature", default="0",
                        help="sampling temperature, or 'model' for the model's default — what "
                             "Celestia's chat loop uses (default: 0, deterministic)")
    parser.add_argument("--out-dir", type=Path, help="write toolcall-<model>.json per model here")
    parser.add_argument("--markdown", type=Path, help="write a Markdown comparison report here")
    parser.add_argument("--report", type=Path, metavar="DIR",
                        help="don't run: merge toolcall-*.json files in DIR into one comparison "
                             "(use with --markdown; e.g. results from parallel CI jobs)")
    parser.add_argument("--timeout", type=float,
                        help="per-request timeout in seconds (default 3× llm.request_timeout_seconds; "
                             "raise it for CPU-only runs)")
    parser.add_argument("--num-ctx", type=int, help="Ollama context window override (default: model/Ollama default)")
    think = parser.add_mutually_exclusive_group()
    think.add_argument("--think", dest="think", action="store_true", default=None,
                       help="force thinking on (reasoning models)")
    think.add_argument("--no-think", dest="think", action="store_false",
                       help="force thinking off (reasoning models; faster)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print calls/replies on misses")
    args = parser.parse_args(argv)

    if args.report:
        runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(args.report.rglob("toolcall-*.json"))]
        if not runs:
            raise SystemExit(f"no toolcall-*.json under {args.report}")
        print_comparison(runs)
        report = markdown_report(runs)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(report, encoding="utf-8")
        else:
            print(report)
        return 1 if any(r.get("error") for r in runs) else 0

    from celestia_core.config import get

    models = [m.strip() for m in (args.model or get("llm.chat_model", "llama3.2:3b")).split(",") if m.strip()]
    cases = load_gold(args.cases)
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        cases = [c for c in cases if c.get("id") in wanted]
    if args.mode:
        cases = [c for c in cases if c.get("mode", "safe") == args.mode]
    if args.lang:
        cases = [c for c in cases if c.get("lang", "en") == args.lang]
    if not cases:
        raise SystemExit("no cases selected")

    runs = [
        run_model(m, cases, think=args.think, verbose=args.verbose,
                  num_ctx=args.num_ctx, timeout=args.timeout, repeat=args.repeat,
                  temperature=parse_temperature(args.temperature))
        for m in models
    ]
    print_comparison(runs)

    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(runs), encoding="utf-8")
        print(f"  report → {args.markdown}")

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for run in runs:
            out = args.out_dir / f"toolcall-{_slug(run['model'])}.json"
            out.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  results → {out}")
    # Non-zero when a model couldn't be evaluated at all, so CI/scripts notice
    # "Ollama was down" instead of reading an empty run as a result.
    return 1 if any(r.get("error") for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
