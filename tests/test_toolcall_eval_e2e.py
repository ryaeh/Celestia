"""End-to-end check of evals/toolcall_eval.py over the *real* Ollama wire protocol.

A tiny HTTP server stands in for Ollama (`POST /api/chat`), so the eval goes
through the actual `ollama` client, JSON (de)serialisation, tool-call parsing,
scoring, the CLI entry point, JSON + Markdown output and the exit code — the
whole path a real run takes, minus the model. The fake "model" is rule-based
and deliberately makes a few mistakes, so the scores must come out exactly as
predicted (proving the harness measures, not just runs).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import celestia_core.config as _cfg
from evals import toolcall_eval as te

# (prompt substring) -> tool call the fake "model" makes. Everything else: plain text.
_RULES = {
    "dentist": ("todo_add", {"text": "call the dentist"}),
    "what's on my to-do": ("todo_list", {}),
    "notepad up": ("open_path", {"path": "notepad"}),        # correct in scoped, not offered in safe
    "how's it going": ("todo_list", {}),                     # wrong: calls a tool on chit-chat
    "graphics card": ("open_app", {"name": "gpu"}),          # hallucinated tool name
}
_CLAIM = {"birthday": "Done! I've saved that for you."}      # claims an action, calls nothing


class _FakeOllama(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *a):  # keep pytest output clean
        pass

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802 — http.server API
        if self.path == "/api/version":
            return self._send(200, {"version": "0.99.0-fake"})
        if self.path == "/api/ps":
            return self._send(200, {"models": [{"name": "fake:3b", "model": "fake:3b", "size": 3 * 1024**3,
                                                "size_vram": 2 * 1024**3, "digest": "x",
                                                "expires_at": "2026-01-01T00:00:00Z"}]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802 — http.server API
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(body)
        if self.path != "/api/chat":
            return self._send(404, {"error": "not found"})
        if body["model"].startswith("notools"):
            return self._send(400, {"error": f"registry.ollama.ai/library/{body['model']} does not support tools"})
        if body["model"].startswith("missing"):
            return self._send(404, {"error": f"model '{body['model']}' not found"})

        prompt = body["messages"][-1]["content"].lower()
        offered = {t["function"]["name"] for t in body.get("tools") or []}
        msg: dict = {"role": "assistant", "content": ""}
        for key, (name, args) in _RULES.items():
            if key in prompt and (name in offered or name == "open_app"):
                msg["tool_calls"] = [{"function": {"name": name, "arguments": args}}]
                break
        else:
            msg["content"] = next((v for k, v in _CLAIM.items() if k in prompt), "Sure, happy to help!")
        self._send(200, {
            "model": body["model"], "created_at": "2026-01-01T00:00:00Z", "message": msg,
            "done": True, "done_reason": "stop",
            "prompt_eval_count": 100 + len(json.dumps(body)) // 4, "eval_count": 7,
            "prompt_eval_duration": 400_000_000, "load_duration": 100_000_000, "eval_duration": 350_000_000,
        })


@pytest.fixture
def fake_ollama(monkeypatch):
    _FakeOllama.requests = []
    server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg = json.loads(json.dumps(_cfg.load_config()))  # real config, deep copy
    cfg.setdefault("llm", {})["host"] = f"http://127.0.0.1:{server.server_port}"
    cfg.setdefault("mcp", {})["enabled"] = False
    monkeypatch.setattr(_cfg, "_config", cfg)
    yield _FakeOllama.requests
    server.shutdown()


_CASES = [
    {"id": "todo", "mode": "safe", "prompt": "Add 'call the dentist' to my to-do list.",
     "expect": {"tool": "todo_add", "args": {"text": ["dentist"]}}},                           # pass
    {"id": "list", "mode": "safe", "prompt": "What's on my to-do list?", "expect": {"tool": "todo_list"}},  # pass
    {"id": "open-scoped", "mode": "scoped", "prompt": "Could you get notepad up for me?",
     "expect": {"tool": "open_path", "args": {"path": ["notepad"]}}},                           # pass
    {"id": "open-safe", "mode": "safe", "prompt": "Could you get notepad up for me?", "expect": None},  # pass (not offered)
    {"id": "greet", "mode": "safe", "prompt": "Hey! How's it going?", "expect": None},         # FAIL: tool on chit-chat
    {"id": "specs", "mode": "safe", "prompt": "What graphics card do I have?",
     "expect": {"tool": "get_pc_specs"}},                                                       # FAIL: unknown tool
    {"id": "birthday", "mode": "safe", "prompt": "Remember my sister's birthday is March 14.",
     "expect": {"tool": "memory_add"}},                                                         # FAIL: claimed
    {"id": "joke", "mode": "safe", "prompt": "Tell me a joke.", "expect": None},              # pass
]


def _write_cases(tmp_path):
    p = tmp_path / "cases.jsonl"
    p.write_text("\n".join(json.dumps(c) for c in _CASES), encoding="utf-8")
    return p


def test_full_run_over_http_scores_exactly(fake_ollama, tmp_path) -> None:
    out_dir, md = tmp_path / "out", tmp_path / "report.md"
    code = te.main(["--model", "fake:3b", "--cases", str(_write_cases(tmp_path)),
                    "--out-dir", str(out_dir), "--markdown", str(md), "--num-ctx", "8192"])
    assert code == 0

    run = json.loads((out_dir / "toolcall-fake-3b.json").read_text(encoding="utf-8"))
    agg = run["aggregate"]
    by_id = {c["id"]: c for c in run["cases"]}
    assert {i for i, c in by_id.items() if c["passed"]} == {"todo", "list", "open-scoped", "open-safe", "joke"}
    assert agg["pass_rate"] == round(5 / 8, 3)
    assert agg["tool_accuracy"] == 0.6  # positives: 3 of 5 picked the right tool
    assert (agg["negatives_clean"], agg["negatives_total"]) == (2, 3)  # greet called a tool
    assert (agg["unknown_tools"], agg["claimed_actions"], agg["errors"]) == (1, 1, 0)
    assert by_id["specs"]["unknown"] == ["open_app"]
    assert agg["prompt_tokens_max"] and agg["prompt_tokens_max"] > 100

    # What went over the wire is the production request: real tool schemas per
    # mode, temperature 0, the num_ctx override, and no tool execution.
    chat_calls = [r for r in fake_ollama if r["messages"][-1]["content"] != "hi"]
    assert len(chat_calls) == len(_CASES)
    first = chat_calls[0]
    assert first["options"]["temperature"] == 0.0 and first["options"]["num_ctx"] == 8192
    assert first["messages"][0]["role"] == "system"
    safe_tools = {t["function"]["name"] for t in first["tools"]}
    assert "todo_add" in safe_tools and "open_path" not in safe_tools

    report = md.read_text(encoding="utf-8")
    assert "| `fake:3b` | 0.625 |" in report and "birthday" in report


def test_tool_accuracy_counts_only_positive_cases(fake_ollama, tmp_path) -> None:
    # Positives: todo ✓, list ✓, open-scoped ✓, specs ✗, birthday ✗ → 3/5.
    run = te.run_model("fake:3b", _CASES, think=None, verbose=False)
    assert run["aggregate"]["tool_accuracy"] == 0.6


def test_model_without_tool_support_is_skipped_not_scored(fake_ollama, tmp_path) -> None:
    md = tmp_path / "r.md"
    code = te.main(["--model", "notools:1b,fake:3b", "--cases", str(_write_cases(tmp_path)),
                    "--markdown", str(md)])
    assert code == 1  # a model couldn't be evaluated → non-zero exit
    report = md.read_text(encoding="utf-8")
    assert "does not support tool calling" in report
    assert "| `fake:3b` |" in report and "| `notools:1b` |" not in report


def test_missing_model_and_unreachable_server_fail_loudly(monkeypatch, fake_ollama) -> None:
    run = te.run_model("missing:7b", _CASES, think=None, verbose=False)
    assert "not found" in run["error"] and "aggregate" not in run

    _cfg._config["llm"]["host"] = "http://127.0.0.1:9"  # nothing listens here
    run = te.run_model("fake:3b", _CASES, think=None, verbose=False)
    assert run.get("error") and "aggregate" not in run


def test_errors_mid_run_never_count_as_clean_negatives(monkeypatch, fake_ollama) -> None:
    real_chat = te._chat
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise TimeoutError("timed out")
        return real_chat(*a, **kw)

    monkeypatch.setattr(te, "_chat", flaky)
    neg_only = [c for c in _CASES if c["expect"] is None]
    run = te.run_model("fake:3b", neg_only, think=None, verbose=False)
    agg = run["aggregate"]
    assert agg["errors"] == 1  # every 2nd request fails; 3 cases → 1 error
    assert agg["negatives_clean"] <= len(neg_only) - agg["errors"]
    assert all(not c["passed"] for c in run["cases"] if c["error"])


def test_report_merges_saved_runs(fake_ollama, tmp_path) -> None:
    cases = _write_cases(tmp_path)
    for model in ("fake:3b", "fake:7b"):
        assert te.main(["--model", model, "--cases", str(cases), "--out-dir", str(tmp_path / model.replace(":", "-"))]) == 0
    md = tmp_path / "merged.md"
    assert te.main(["--report", str(tmp_path), "--markdown", str(md)]) == 0
    report = md.read_text(encoding="utf-8")
    assert "| `fake:3b` |" in report and "| `fake:7b` |" in report


def test_repeat_run_records_version_timing_vram_and_spread(fake_ollama, tmp_path) -> None:
    out_dir, md = tmp_path / "out", tmp_path / "r.md"
    code = te.main(["--model", "fake:3b", "--cases", str(_write_cases(tmp_path)), "--repeat", "2",
                    "--temperature", "model", "--out-dir", str(out_dir), "--markdown", str(md)])
    assert code == 0
    run = json.loads((out_dir / "toolcall-fake-3b.json").read_text(encoding="utf-8"))
    assert run["ollama_version"] == "0.99.0-fake"
    assert run["temperature"] == "model"
    assert run["resident"] == {"size_bytes": 3 * 1024**3, "size_vram_bytes": 2 * 1024**3}
    assert run["spread"]["repeats"] == 2 and len(run["cases"]) == 2 * len(_CASES)
    assert run["aggregate"]["ttft_p50_s"] == 0.5 and run["aggregate"]["tok_per_s_p50"] == 20.0
    chat_calls = [r for r in fake_ollama if r["messages"][-1]["content"] != "hi"]
    assert all("temperature" not in r["options"] for r in chat_calls)  # model default = production
    assert {r["options"]["seed"] for r in chat_calls} == {1, 2}
    report = md.read_text(encoding="utf-8")
    assert "ollama 0.99.0-fake" in report and "VRAM 2.0 GB" in report
    assert "failed" in report and "2/2" in report  # per-case failure counts across repeats


def test_lang_filter(fake_ollama, tmp_path) -> None:
    cases = tmp_path / "c.jsonl"
    rows = [dict(_CASES[0], id="en-1"), dict(_CASES[-1], id="tr-1", lang="tr")]
    cases.write_text("\n".join(json.dumps(c) for c in rows), encoding="utf-8")
    out = tmp_path / "o"
    assert te.main(["--model", "fake:3b", "--cases", str(cases), "--lang", "tr", "--out-dir", str(out)]) == 0
    run = json.loads((out / "toolcall-fake-3b.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in run["cases"]] == ["tr-1"] and run["aggregate"]["pass_by_lang"] == {"tr": 1.0}
