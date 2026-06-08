# 09 — Adaptive test-time compute

**Pitch:** Spend more inference compute *only on hard questions*. Easy chats stay
single-pass and fast; hard ones automatically get a "think longer" or "answer it a few
times and reconcile" path. Same model, same parameter count — more reasoning where it
matters, no latency tax on small talk.

This is the horizontal enhancer behind the "more reasoning without more params" idea: at a
fixed model size, accuracy on hard problems scales with test-time compute (longer chains,
self-consistency, verify-and-revise). The trick is *routing* — don't pay that cost on the
90% of turns that don't need it.

## Why this is a Celestia feature

Local compute is the budget; you can't afford to run every turn 3×. But you control the
whole turn loop (`celestia_core/agent.py`), so you can cheaply classify difficulty and
escalate compute selectively — something a fixed cloud endpoint doesn't expose.

## The three tiers

| Tier | When | What it does | Streams? |
|------|------|--------------|----------|
| `fast` | greetings, simple Q&A, tool actions | current single pass, `num_predict≈1024` | yes |
| `think` | reasoning/math/code/"why"/multi-constraint | switch to reasoning model and/or raise `num_predict`, temp≈0.6, allow long CoT | yes |
| `consensus` | hard reasoning with a checkable or high-stakes answer | sample N completions (temp≈0.7), then **fuse/vote** into one answer (universal self-consistency) | no (status event, then final) |

Tools and `consensus` don't mix cleanly, so the rule is: run the first pass; if the model
emits tool calls, drop to the normal tool loop (tools already *are* reasoning-via-action).
`consensus` only applies to tool-free answers. `think` is tool-compatible (just a better
model + more tokens).

## The router (cheap, runs first)

- **`heuristic` (default, zero extra cost):** keyword/structure signals — math operators,
  numbers, "prove / why / step by step / compare / debug", code fences, long multi-clause
  questions → escalate; greetings/short → `fast`.
- **`model` (optional, one tiny call):** ask a small fast model to rate difficulty 1–5.
- **`hybrid`:** heuristic first, escalate only the ambiguous middle to the model rater.

`voice_mode` always forces `fast` (latency matters more than depth when speaking).

## How it plugs into `agent.py`

A new module `celestia_core/reasoning.py` owns the router + tier strategies. `run_turn` /
`run_turn_stream` consult it once, after the `preflight_chat_pc` early-return and before the
chat loop.

```python
# celestia_core/reasoning.py  (new)
from dataclasses import dataclass
from celestia_core.config import get

@dataclass
class Plan:
    tier: str                # "fast" | "think" | "consensus"
    model: str               # may differ from the default chat model
    options: dict            # ollama options (num_predict, temperature, ...)
    samples: int = 1         # >1 only for consensus

def route(user_message: str, *, voice_mode: bool, default_model: str) -> Plan:
    if voice_mode or not get("reasoning.enabled", False):
        return Plan("fast", default_model, {"num_predict": 1024})

    score = _difficulty(user_message)          # heuristic / model / hybrid
    if score <= get("reasoning.fast_max", 2):
        return Plan("fast", default_model, {"num_predict": 1024})

    reason_model = get("reasoning.reason_model", default_model)
    if score <= get("reasoning.think_max", 4):
        return Plan("think", reason_model, {
            "num_predict": int(get("reasoning.think_num_predict", 4096)),
            "temperature": float(get("reasoning.think_temperature", 0.6)),
        })

    return Plan("consensus", reason_model, {
        "num_predict": int(get("reasoning.think_num_predict", 4096)),
        "temperature": float(get("reasoning.consensus_temperature", 0.7)),
    }, samples=int(get("reasoning.consensus_samples", 3)))
```

In `run_turn`, the only change to the existing loop is parameterizing the call:

```python
plan = reasoning.route(user_message, voice_mode=voice_mode, default_model=model)
...
response = client.chat(
    model=plan.model,
    messages=messages,
    tools=tools,                 # tools already hoisted out of the loop (commit 2)
    options=plan.options,
)
```

`consensus` runs as a wrapper around the *first* response only:

```python
def consensus_answer(client, *, model, messages, tools, plan, parse_args, execute):
    first = client.chat(model=model, messages=messages, tools=tools, options=plan.options)
    msg = _message_to_dict(first["message"])
    if msg.get("tool_calls"):
        return ("tools", msg)                 # bail to normal tool loop
    candidates = [msg.get("content", "")]
    for _ in range(plan.samples - 1):
        r = client.chat(model=model, messages=messages, options=plan.options)
        candidates.append(_message_to_dict(r["message"]).get("content", ""))
    fused = _fuse(client, model, user_question(messages), candidates)  # 1 aggregator call
    return ("text", {"role": "assistant", "content": fused})
```

`_fuse` is "universal self-consistency": one LLM call that sees the N candidates and
returns the single best/most-consistent answer — generalizes to free-form chat, not just
numeric answers.

## Streaming behaviour

- `fast` / `think`: stream exactly as today (think just changes model + options).
- `consensus`: emit `{"status": "thinking"}` so the shell shows a spinner, compute the N
  samples + fusion, then emit the final answer in the normal `done` event. (A later
  refinement can stream the winning candidate's tokens.)

## Data & config

```yaml
reasoning:
  enabled: false             # opt-in; off = today's behaviour exactly
  router: heuristic          # heuristic | model | hybrid
  reason_model: ""           # optional bigger/thinking model for think/consensus tiers
  fast_max: 2                # difficulty <= this -> fast
  think_max: 4               # <= this -> think; above -> consensus
  think_num_predict: 4096
  think_temperature: 0.6
  consensus_samples: 3
  consensus_temperature: 0.7
```

## Security & privacy

No new surface — all inference stays local. Only cost is latency/compute, capped by
`consensus_samples` and the `fast` default. Voice and tool turns never pay the tax.

## Integrates with

- **04 Autonomy (●●●):** plan generation is exactly where `think`/`consensus` pays off —
  better multi-step plans without a bigger model.
- **01 Ambient (●●):** ambient can afford `consensus` on its rare nudges since they're not
  latency-sensitive; the router's difficulty score can also gate whether a nudge is worth
  raising at all.
- **03 RAG (●●):** reasoning over retrieved context benefits most from the `think` tier.
- **06 Affect (●):** mostly `fast`; not compute-bound.

## Effort / risk

Medium. The router + `think` tier are small and low-risk (default off = no behaviour
change). `consensus` is the involved part (sampling loop + fusion + the tools bail-out) and
the main latency cost. Build `think` first behind the flag, add `consensus` once the router
proves accurate.

## Open questions

- Heuristic vs model router: is one cheap LLM difficulty-rating call worth it, or do
  keywords get 90% of the value?
- Fusion strategy: universal-self-consistency (LLM judge) vs answer-extraction + majority
  vote for verifiable answers — support both?
- Should `think` use a *separate reasoning model* (extra VRAM / model swap) or just more
  tokens on the same model?
