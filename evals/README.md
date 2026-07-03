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

## Planned companions (same pattern, not yet built)

- **Recall gold-set** — seeded memory entries + query → expected top-k ids;
  measures `build_context` blended ranking and A/Bs hybrid (graph+vector)
  recall against plain vector. Needs an isolated Chroma path.
- **Voice-consistency baseline** — fixed prompts → reply set scored against
  the personality contract; guards regressions when swapping chat models.
