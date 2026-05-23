# Performance profiles

Celestia runs locally on your GPU. Pick a profile in `config.yaml` (`llm.*`, `voice.*`, `vision.*`).

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

## Low VRAM / shared GPU

- `llm.chat_model: llama3.2:3b`
- `voice.stt.model: small` or `base`
- `vision.text_model: moondream` with `vision.two_pass_text: false`
- Shorter `voice.tts.orpheus.idle_shutdown_minutes` and `voice.stt.idle_unload_minutes`

Unload voice before vision (automatic in screen flow) to avoid OOM.
