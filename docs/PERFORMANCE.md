# Performance & heavy apps

## HF token

Put in **`c:\celestia\.env`** only:

```env
HF_TOKEN=hf_...
```

See [SETUP.md](SETUP.md). Not required, but recommended for Orpheus SNAC download.

## One heavy model at a time

| Step | Loads | Freed before next |
|------|-------|-------------------|
| Confirm TTS | Edge (tiny) | — |
| Vision | Ollama vision / qwen2.5vl | Whisper + Orpheus unloaded |
| Answer TTS | Orpheus GGUF | After idle timeout |

## Gaming profile (`config.yaml`)

```yaml
llm:
  vision_model: moondream
  vision_text_model: qwen2.5vl:7b
voice:
  tts:
    provider: edge
  stt:
    model: medium
vision:
  confirm_mode: text
  max_edge_px: 2048
```

## `llama_context` warning

Informational only — smaller context window than model maximum.
