# Evals — Gate A

The roadmap's **Gate A**: an eval set must exist *before* more features stack on
the LLM-dependent layers (graph extraction, recall ranking, the Phase-2 idle
re-scoring pass). This directory is that instrument. It turns "does the 3B
extract well enough?" and "did the prompt tweak help?" into numbers you can
diff between runs instead of vibes.

These are **not unit tests** — they hit live Ollama and score model behavior.
The scoring logic itself *is* unit-tested (offline) in
`tests/test_extraction_eval.py`.

## Extraction eval

Scores the production extractor (`skills/memory/graph_extract.py` — its real
prompt and parser, no graph writes) against the hand-labeled cases in
`extraction_gold.jsonl`.

```powershell
# Ollama must be running
.\venv\Scripts\python.exe -m evals.extraction_eval                 # config-default model
.\venv\Scripts\python.exe -m evals.extraction_eval --model qwen2.5:7b
.\venv\Scripts\python.exe -m evals.extraction_eval --only supersede-01,neg-secret -v
.\venv\Scripts\python.exe -m evals.extraction_eval --json evals/results/7b-baseline.json
```

Reported per run: micro **precision** (are extracted triples justified?),
**recall** (are the expected facts found?), **F1**, **negatives clean** (cases
where extracting *nothing* is correct), and **forbidden hits** (stale
superseded values or secrets that must never be extracted — any hit is a red
flag regardless of the other numbers).

### Comparing models / prompts

Run once per variant with `--json`, then diff the aggregates:

```powershell
.\venv\Scripts\python.exe -m evals.extraction_eval --model llama3.2:3b   --json evals/results/3b.json
.\venv\Scripts\python.exe -m evals.extraction_eval --model qwen2.5:7b    --json evals/results/7b.json
.\venv\Scripts\python.exe -m evals.extraction_eval --model qwen2.5:14b   --json evals/results/14b.json
```

This is the go/no-go instrument for the Phase-2 idle "tidying" daemon: the
14B batch re-scoring pass ships only if its numbers beat the hot-path 3B here.

### Gold case schema (`extraction_gold.jsonl`, one JSON object per line)

```jsonc
{
  "id": "editor-01",              // unique, stable — used by --only and in reports
  "notes": "why this case exists",
  "excerpt": "User: ...\nAssistant: ...",   // consolidation-style excerpt
  "expected": [                   // required triples — drive RECALL
    {
      "subject": "user",                     // string or list of accepted variants
      "predicate_any": ["use", "switch"],    // optional — accepted predicate substrings; omit = any wording
      "object": ["neovim", "nvim"],          // string or list
      "single_valued": true                  // optional, documentation-only for now
    }
  ],
  "optional": [ /* same shape */ ],  // reasonable extras — rescue PRECISION, never count toward recall
  "forbidden": ["8000"]              // strings that must not appear as any subject/object
}
```

Matching is normalized (case, whitespace, leading articles/possessives) and
containment-tolerant in both directions ("neovim" matches "neovim editor").
A case with `"expected": []` is a **negative**: it passes only when the model
extracts nothing.

### Growing the set

The 18 seed cases are synthetic-but-realistic. The set becomes trustworthy at
**50+ cases labeled from your real chats**: when you see a bad graph entry (or
a missed fact) in daily use, copy the excerpt from the session JSON into a new
line here with the correct expectation. Negatives are as valuable as positives
— over-extraction is the known failure mode of the 3B.

## Tool-call eval

Scores how reliably a chat model picks the right tool — or correctly picks
none — using the **production** system prompt, per-mode PC-control hints
(`agent._build_fresh_messages`) and tool schemas (`registry.tool_schemas()`)
for the case's security mode. Only the model's **first response** is scored.
**No tool is executed**: the preflight (which can open URLs) is skipped, memory
context is left empty, and the security mode is patched in-process (the shared
state file is never written).

```powershell
# Ollama must be running; pull the candidates first (ollama pull <model>)
.\venv\Scripts\python.exe -m evals.toolcall_eval                                   # llm.chat_model
.\venv\Scripts\python.exe -m evals.toolcall_eval --model llama3.2:3b,qwen2.5:7b,qwen3:8b --out-dir evals/results
.\venv\Scripts\python.exe -m evals.toolcall_eval --model qwen3:8b --no-think       # reasoning models: thinking off
.\venv\Scripts\python.exe -m evals.toolcall_eval --mode scoped -v                   # one mode, show misses
```

Several comma-separated models print a side-by-side table at the end.
Per model:

| Metric | Meaning |
|--------|---------|
| **pass** | tool + args right, no red flags |
| **tool** | right tool chosen, on cases that need one |
| **args** | args right, given the right tool |
| **neg** | chit-chat / blocked requests where it correctly called nothing |
| **forb** 🚩 | a forbidden tool was called (e.g. `run_powershell` for an advice question) |
| **unk** 🚩 | called a tool that wasn't offered (hallucinated name / mode leak) |
| **claim** 🚩 | no tool call but the reply claims the action happened ("I've opened it!") |
| **p50 s** | median latency per case, after a warm-up call (load time excluded) |

Red flags matter more than the headline pass rate. `--think` / `--no-think` pass
Ollama's `think` flag for reasoning models (omitted = model default); compare
both, since thinking usually helps accuracy but costs latency on the hot path.

### What to benchmark

The goal is a model that beats the current default on **pass + red flags** at a
latency you can live with for chat. A sensible first sweep, sized for one
consumer GPU: the current `llama3.2:3b` / `qwen2.5:7b` baselines against newer
tool-capable families in the Ollama library (e.g. `qwen3:4b`, `qwen3:8b`,
`qwen3:14b`, `llama3.1:8b`) — check the library for newer releases before
running. Only models tagged with **tools** support in Ollama can be scored.
Switch `llm.chat_model` (then `--trust-config`) only when a candidate wins here
**and** doesn't regress the extraction eval above.

### Gold case schema (`toolcall_gold.jsonl`, one JSON object per line)

```jsonc
{
  "id": "todo-add-02",                  // unique, stable — used by --only and in reports
  "category": "todos",                  // free-form grouping
  "mode": "safe",                       // safe | scoped | armed — decides which tools are offered
  "prompt": "remind me to renew my passport, high priority",
  "history": [ {"role": "user", "content": "..."} ],   // optional prior turns
  "expect": {                           // null = negative: correct answer calls NO tool
    "tool": "todo_add",                 // string or list of accepted tools
    "args": {"text": ["passport"], "priority": ["high"]}  // each key required; value = accepted substrings ([] = any non-empty)
  },
  "acceptable_tools": ["todo_list"],    // also count as the right tool (positives only)
  "forbidden_tools": ["todo_remove"],   // any call is a red flag, even on a pass otherwise
  "notes": "why this case exists"
}
```

Extra non-forbidden calls alongside an expected one are tolerated. Grow the set
the same way as the extraction gold set: when Celestia picks the wrong tool (or
claims an action it didn't take) in real use, copy the message into a new line.

## Planned companions (same pattern, not yet built)

- **Recall gold-set** — seeded memory entries + query → expected top-k ids;
  measures `build_context` blended ranking and A/Bs hybrid (graph+vector)
  recall against plain vector. Needs an isolated Chroma path.
- **Voice-consistency baseline** — fixed prompts → reply set scored against
  the personality contract; guards regressions when swapping chat models.
