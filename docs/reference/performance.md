# Performance profiles

Celestia runs locally on your GPU. Pick a profile in `config.yaml` (`llm.*`, `voice.*`, `vision.*`).

## Reference machine (developer's main PC)

| Part | Spec | Budget that matters |
|------|------|---------------------|
| GPU | **RTX 4090** | **24 GB VRAM** — the hard ceiling for resident models |
| CPU | **Ryzen 9 7900X3D** | 12c/24t — fine for STT/embeds on CPU if needed |
| RAM | **32 GB** | caps how much can be offloaded to CPU / `keep_alive` in RAM |

This is the tuning target. 24 GB VRAM is the number every residency decision is sized
against (see [Feature 11 operating modes](../planned-features/11-operating-modes.md) and
`celestia_core/gpu.py`).

## RTX 4090 (default reference)

```yaml
llm:
  chat_model: qwen2.5:7b
  vision_text_model: qwen2.5vl:7b
voice:
  stt:
    model: large-v3
    compute_type: float16
  tts:
    orpheus:
      n_gpu_layers: -1
```

Orpheus GGUF: `models/Orpheus-3b-FT-Q8_0.gguf`

## Idle-time "bigger brain" tier (14B / 32B)

The resident **chat** model stays 7B (snappy, always-on). But the
["tidying while you're away"](../project/ideas-backlog.md) idle worker — smart memory
re-scoring, graph entity-resolution, deeper consolidation — can load a bigger model *only
while the machine is idle*, then unload it (`gpu.unload_model`). This does **not** violate
the "no always-resident 14B" stance: it's a transient batch worker, never in the chat path.

VRAM math on the 4090 (Q4_K_M, ~8k context): a 14B ≈ 10 GB, a 32B ≈ 19–20 GB. A 32B fits
**only when the chat model is unloaded first** (which idle mode does anyway), so it's the
natural idle tier on this hardware.

| Tier | Recommended | Why | VRAM |
|------|-------------|-----|------|
| **14B** (safe idle, or shorter idle windows) | **`qwen3:14b`** (thinking mode) — or `qwen2.5:14b-instruct` if you want to stay in-family with the chat model | Thinking mode gives real reasoning lift for re-scoring/extraction judgement; same tokenizer family as the 7B chat model = consistent behavior | ~10 GB |
| **32B** (deep idle, chat unloaded) | **`qwen3:32b`** (thinking mode) — general reasoning/extraction; **`deepseek-r1:32b`** if you want the strongest multi-step reasoning; **`qwen2.5-coder:32b`** only if the worker does code-heavy tasks | "Performance that used to need multi-GPU, now on one 4090." Best accuracy for the once-in-a-while deep memory pass | ~19–20 GB |
| **Embeddings** | `nomic-embed-text` | unchanged | ~0.3 GB |

**Recommendation for the idle worker:** start with **`qwen3:14b`** (fits alongside more,
unloads fast, low risk). Move the deep nightly/AFK pass to **`qwen3:32b`** once the idle/AFK
+ GPU-utilization probe exists (so a 20 GB load never lands while you're mid-task). Both pull
via `ollama pull qwen3:14b` / `ollama pull qwen3:32b`.

> Note (Jun 2026): the frontier has moved to Qwen3.5/3.6, but those don't ship **dense**
> 14B/32B variants — Qwen3 remains the best dense pick at exactly these two sizes. Re-check
> when a dense 3.5/3.6 at 14B/32B appears.

## Low VRAM / shared GPU

- `llm.chat_model: llama3.2:3b`
- `voice.stt.model: small` or `base`
- `vision.text_model: moondream` with `vision.two_pass_text: false`
- Shorter `voice.tts.orpheus.idle_shutdown_minutes` and `voice.stt.idle_unload_minutes`

Unload voice before vision (automatic in screen flow) to avoid OOM.
