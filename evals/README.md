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

## Consolidation eval (T15)

Scores the **memory writer** — the single pass that decides how long-term
memory changes after a chat ([#134](https://github.com/ryaeh/Celestia/issues/134)).
Each case gives the memories that already exist, an optional rolling session
summary, and a transcript. The pass returns operations on text memory, each with
its own graph triples:

| op | meaning |
|---|---|
| `add` | new durable fact / instruction / task nothing existing covers |
| `update` | existing memory still true, user added detail |
| `supersede` | existing memory no longer true (moved, changed jobs, reversed a rule) |
| `forget` | user retracted it or asked to forget it |

Emitting nothing for a restated fact is the correct answer, so duplicates are
measured directly.

```powershell
.\venv\Scripts\python.exe -m evals.consolidation_eval --model qwen3.5:4b                  # writer (think on + off) and legacy
.\venv\Scripts\python.exe -m evals.consolidation_eval --model qwen3.5:4b --pipeline writer --think on
.\venv\Scripts\python.exe -m evals.consolidation_eval --model qwen2.5:3b,qwen3.5:4b --markdown out/c.md --json out/c.json
.\venv\Scripts\python.exe -m evals.consolidation_eval --model qwen3.5:4b --only move-01,dup-01 -v
```

Pipelines on the same cases:

- **writer** — `skills/memory/writer.py` (prompt + parser, no store writes).
  `--think on,off` runs it with and without thinking; `on` is skipped for models
  that can't think.
- **legacy** — today's production path: the typed-consolidation prompt with
  word-overlap dedupe, plus the separate graph extraction. It can only add, so
  it scores 0 on corrections by construction. That's the gap T15 must close.

Reported per run:

| metric | meaning |
|---|---|
| passed | cases with every expected op found and nothing wrong |
| f1 (p, r) | ops that were justified / expected ops that were found |
| corrections | expected `update` / `supersede` / `forget` ops found |
| duplicates | `add` ops that restate an existing memory |
| wrong target | ops that edit a memory the case says must stay as is |
| forbidden | secrets or stale / hypothetical values in any op, triple or summary |
| graph sync | matched ops whose triples agree with the text (legacy: whether its separate graph pass found it) |
| negatives clean | cases where the right answer is no change |
| errors | failed requests (always fail the case; exit code 1) |

### Results (GitHub CPU runners, Sep 30 2026)

Latest: [run 36768684847](https://github.com/ryaeh/Celestia/actions/runs/36768684847), writer at
`62f0fd8` (no example values in the prompt, JSON-schema output). Thinking-on row from
[run 36746524491](https://github.com/ryaeh/Celestia/actions/runs/36746524491) (writer at `cf79190`).

| model | pipeline | passed | f1 | corrections | duplicates | wrong target | forbidden | negatives clean | time / case |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen3.5:4b` | **writer, think off** | **16/20** | **0.828** | **9/9** | 0 | 3 | 0 | **6/6** | ~35 s |
| `qwen3.5:4b` | writer, think on (`cf79190`) | 14/20 | 0.727 | 4/9 | 0 | 0 | 0 | 6/6 | 130–510 s |
| `qwen3.5:4b` | legacy (today) | 5/20 | 0.329 | 0/9 | 4 | 0 | 2 | 3/6 | ~40 s |
| `qwen2.5:3b` | writer, think off | 9/20 | 0.465 | 3/9 | 0 | 0 | 1 | 4/6 | ~7 s |
| `qwen2.5:3b` | legacy (today) | 2/20 | 0.242 | 0/9 | 5 | 0 | 2 | 2/6 | ~13 s |

Re-run on the finished T15 branch (all of step 4 merged with `main`'s message times,
`9afa16f`, [run 37845668342](https://github.com/ryaeh/Celestia/actions/runs/37845668342), Oct 8 2026):

| model | pipeline | passed | f1 | corrections | duplicates | wrong target | forbidden | graph sync | negatives clean |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen3.5:4b` | writer, think off | 17/20 | 0.857 | 9/9 | 0 | 2 | 0 | 1.0 | 6/6 |
| `qwen3.5:4b` | legacy (today) | 7/20 | 0.333 | 0/9 | 3 | 0 | 1 | 0.333 | 3/6 |

Same picture as Sep 30, within noise. The three writer misses are the known ones:
Rust folded into the Celestia memory, the dog memory touched on a move, and the tea
preference in `multi-01` not saved.

- The writer beats today's pipeline on every column; `qwen3.5:4b` with thinking **off**
  is the pick for the memory pass. `qwen2.5:3b` is too weak for it.
- Thinking on is ~10× slower and not better on CPU: its misses were the slowest cases,
  which ran out of output budget. Worth re-testing on a GPU. The workflow defaults to
  `consolidation_think: off`.
- Remaining writer weakness: it sometimes rewrites a memory that was only *mentioned*
  (the dog on a move, jazz when quitting guitar) or folds a new fact into an existing
  one (Rust into the Celestia project) instead of adding it.
- Today's pipeline stores the prompt's own rules ("Never duplicate items under KNOWN
  MEMOS") and the natural-language wifi password in `secret-01`; the writer does neither.

### Gold case schema (`consolidation_gold.jsonl`)

```jsonc
{
  "id": "move-01",
  "notes": "relocation supersedes the old city",
  "existing": [                                  // prompt ids m1..mN, as the writer sees them
    {"id": "m1", "kind": "fact", "text": "User lives in Ankara.", "key": [["ankara"]]}
  ],                                             // key: mention groups that identify a restatement (duplicate)
  "summary": "",                                 // optional rolling session summary
  "transcript": "User: ...\nAssistant: ...",
  "expected": [{
    "op_any": ["supersede", "update"],           // accepted ops
    "target": "m1",                              // required for update/supersede/forget
    "kind": "instruction",                       // optional
    "mentions": [["izmir"]],                     // all groups must appear in the text; any alternative per group
    "triple": {"subject": "user", "predicate_any": ["live"], "object": "izmir"}   // optional; drives graph sync
  }],
  "optional": [ /* same shape — rescue precision only */ ],
  "untouched": ["m2"],                           // ids no op may target
  "untouched_ops": {"m1": ["supersede", "forget"]},  // ops banned on an id
  "forbidden": ["sunflower2024"],                // never in any op, triple, graph or summary
  "forbidden_add": ["berlin"]                    // never in an add op
}
```

`tests/test_consolidation_eval.py` builds a perfect answer from every case's
specs and checks it passes, so a mislabeled case fails CI offline.

## Summary eval (T15 working memory)

Scores the running summary that keeps long chats from forgetting their start.
Each case in `summary_gold.jsonl` is a chat cut into 2–4 checkpoints; the
summarizer runs once per checkpoint (previous summary + that window), exactly
as in production, and the **final** summary is scored:

| metric | meaning |
|---|---|
| retention | expected facts still present at the end (`early retention`: the ones from the first checkpoint) |
| exact | exact values (`exact` list: numbers, dates, paths, commands) kept verbatim |
| now | the summary knows what the chat is on at the end |
| forbidden | secrets, hypotheticals-as-decisions, invented content |
| avg chars | size of what's sent with each turn |

```powershell
.\venv\Scripts\python.exe -m evals.summary_eval --model qwen3.5:4b              # structured vs prose
.\venv\Scripts\python.exe -m evals.summary_eval --model qwen3.5:4b --pipeline structured -v
```

`structured` is `skills/memory/session_summary.py` (fields + carry-over);
`prose` is the earlier plain-paragraph summary, kept as the baseline.

### Summary results (GitHub CPU runners, Oct 1 2026)

[Run 36828362108](https://github.com/ryaeh/Celestia/actions/runs/36828362108), `qwen3.5:4b`, thinking off:

| pipeline | passed | retention | early retention | exact | now | forbidden | avg chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| structured (`624e4ae`) | 4/6 | 0.879 | 0.778 | 0.875 | 6/6 | 2 | 1001 |
| prose (step-3 baseline) | 1/6 | 0.515 | 0.333 | 0.25 | 6/6 | 0 | 517 |
| structured + fixes (`bc8b0fe`, [run 36835544674](https://github.com/ryaeh/Celestia/actions/runs/36835544674)) | 4/6 | **0.97** | **0.944** | 0.75 | 6/6 | **0** | 1119 |
| + labelled-details prompt (`e664dfb`, [run 36841179651](https://github.com/ryaeh/Celestia/actions/runs/36841179651)) — reverted | 4/6 | 0.909 | 0.833 | 0.75 | 6/6 | 0 | 1157 |
| finished T15 branch (`9afa16f`, [run 37845668342](https://github.com/ryaeh/Celestia/actions/runs/37845668342), Oct 8) | **5/6** | 0.97 | 0.944 | **0.875** | 6/6 | 0 | 1109 |
| prose, same run | 1/6 | 0.545 | 0.389 | 0.25 | 6/6 | 0 | 468 |

The structured notes keep more than twice as many early facts and exact details.
The two failures in the first structured run led to these fixes (`bc8b0fe`):

- **Topic switch:** the model `drop`ped the whole Berlin trip when the chat moved to
  the server bug. Fix: the old goal moves to an "Earlier in this chat" list (kept in
  code), facts and details lose at most 3 items per update, and the prompt says a
  topic change is not a reason to drop.
- **Password:** "my portal password is Tulip#2291" was kept as an exact detail. Fix:
  the shared scrubber now redacts plain-sentence disclosures ("my wifi password is …",
  "the PIN was …") before any memory prompt, and items that mention credentials are
  filtered out of the notes.

After the fixes, early retention is 0.94 and nothing leaks. The two remaining misses were
about detail wording: "clap 4.5" got split into "clap" and "4.5", and the flight was kept
without its date. Asking for labelled details ("flight out May 12") didn't help (exact
unchanged, retention down), so that prompt change was reverted. With 6 cases, swings of
about ±0.1 between runs are noise (the prose baseline moved 0.25 → 0.375 on exact with no
change); more real-chat cases would make these numbers firmer.

On the finished T15 branch (Oct 8) the only miss left is the same flight date: "May 12"
in `trip-then-code`, while the rest of the Berlin trip survives the topic switch.

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
| **err** | the request failed (timeout, Ollama error) — counted apart, never as a clean "no tool" |
| **p50 s** | median latency per case, after a warm-up call (load time excluded) |
| **max tok** | largest prompt Ollama reported (`prompt_eval_count`) — compare with the context window |

Before scoring, each model gets a one-tool probe: a model Ollama says "does not
support tools" is **skipped with a reason**, not scored (it would otherwise
"pass" every negative case). The exit code is non-zero when any model couldn't
be evaluated. Useful flags: `--markdown report.md` (comparison + misses),
`--timeout 900` (CPU-only runs), `--num-ctx 8192` (try a larger context window),
`--repeat N --temperature model` (see below),
`--report DIR` (merge saved `toolcall-*.json` runs without re-running).

Red flags matter more than the headline pass rate. `--think` / `--no-think` pass
Ollama's `think` flag for reasoning models (omitted = model default); compare
both, since thinking usually helps accuracy but costs latency on the hot path.

### Repeats and sampling

Celestia's chat loop doesn't set a temperature, so the model samples at its own
default. A single run at temperature 0 is reproducible but **not** what users get,
and repeating it on the same machine mostly repeats the same answers. For model
comparisons use `--repeat 3 --temperature model`: every case is attempted three
times with seeds 1–3, the table shows the pooled pass rate plus its **± sd** across
repeats, and cases that pass only sometimes are listed as *unstable*. Two models
closer than about two standard deviations aren't meaningfully different.

Each run also records the Ollama version,
time-to-first-token (load + prompt evaluation), output tokens/s and — after the
run — how much of the model sits in VRAM (`ollama ps`). On a GPU those last three
are what the residency plan needs.

`--no-think` turns thinking off for Qwen3-style reasoning models; models without a
thinking switch get the flag dropped automatically (noted in the output). The
extraction eval takes `--repeat`, `--lang` and `--no-think` too; it stays at
temperature 0 like the production extractor.

### Run it on GitHub (no local GPU needed)

`.github/workflows/evals.yml` installs Ollama on a GitHub CPU runner, pulls each
model, and runs both evals — one parallel job per model, then a merged table on
the run's **Summary** page (full JSON in the `eval-results-*` artifacts). It runs
on PRs that touch prompts/tools/evals, or on demand: **Actions → Evals (real
models) → Run workflow**, with a comma-separated model list. CPU runners suit
≤4B models (~15–30 min each); benchmark 7–14B models on your GPU.

The harness itself is covered end-to-end by `tests/test_toolcall_eval_e2e.py`: a
fake Ollama HTTP server with a deliberately imperfect rule-based "model", so the
real client, wire format, scoring, CLI and reports are checked against exact
expected scores on every CI run.

### First real-model results (GitHub CPU runners, Sep 2026)

From [the first `evals.yml` run](https://github.com/ryaeh/Celestia/actions/runs/36475137010) (40 cases, temperature 0):

| model | pass | tool | args | negatives clean | red flags | p50 | max prompt |
|---|---:|---:|---:|---:|---:|---:|---:|
| `qwen2.5:3b` | 0.90 | 0.86 | 1.00 | 12/12 | 0 | 3.8 s | 2657 tok |
| `llama3.2:3b` | 0.70 | 0.93 | 0.96 | **3/12** | 0 | 2.2 s | 2699 tok |

`llama3.2:3b` (the `config.example.yaml` default) reaches for tools on plain chat —
`memory_add` on "how's it going", `morning_briefing` on "I'm nervous about my exam",
`web_search` for a joke — and once wrote a tool call as raw JSON text instead of
calling it. `qwen2.5:3b` never called a tool it shouldn't; its misses were answering
memory requests without `memory_add`/`memory_search`, and one fabricated
"I've updated the priority…" with no tool call (the claim detector was widened to
catch that wording after this run). Extraction on the same runners: `llama3.2:3b`
F1 0.273 (your local baseline: 0.284 — consistent), `qwen2.5:3b` F1 0.20.

### T02 results (GitHub CPU runners, Ollama 0.35.0, Sep 30 2026)

[Run on PR #132](https://github.com/ryaeh/Celestia/actions/runs/36716549317) — tool-calling
3 repeats at the model's own temperature; extraction at temperature 0 with thinking off.
Numbers below are the English cases (a Turkish subset was in that run and has since been
dropped from scope).

| model | tool-call pass (English) | extraction F1 (English) | median latency / case |
|---|---:|---:|---:|
| `qwen2.5:3b` | **0.90** | 0.11 | **3.7 s** |
| `qwen3.5:4b` | 0.77 | **0.83** | 11.6 s |
| `llama3.2:3b` (old default) | 0.69 | 0.18 | 5.2 s |

No single small model wins both jobs, so the defaults split them: **chat `qwen2.5:3b`**,
**background memory `qwen3.5:4b`** (`memory.session_consolidate_model`,
`memory.background_think: false`). `qwen2.5:3b` still sometimes *claims* an action it
didn't take ("I've updated the priority…") — watch the `claim` column.

**`qwen3:4b` is out.** With thinking turned off (`think: false`) it still writes its
reasoning into the reply ("Okay, the user wants… Let me think…"), so replies run to the
1024-token cap: 60–400 s per case on CPU, and several tool calls never happen because
the budget is spent thinking out loud. As a chat model it would show that monologue to
the user. [Run 36729215905](https://github.com/ryaeh/Celestia/actions/runs/36729215905)
hit the 5-hour job limit in its second repeat; it's no longer in the default matrix.
`qwen3.5:4b` doesn't have this problem.

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
