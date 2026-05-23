# Phase 2 — Screen vision

## Models

```powershell
ollama pull qwen2.5vl:7b
ollama pull llama3.2-vision:11b
ollama pull moondream
```

`config.yaml`:

```yaml
vision:
  enabled: true
  text_model: qwen2.5vl:7b
  max_edge_px: 2048
  confirm_mode: text
```

## Usage

```powershell
.\venv\Scripts\python.exe run_atlas.py --screen "Read every line of text in this image"
```

1. Drag rectangle (Esc = cancel) — **crop tight** for text files
2. Confirm audio + preview window
3. Type **yes** or **no** → preview **closes**
4. Text mode: transcribe → answer

## Modes

```powershell
--screen-mode region
--screen-mode active_window
--screen-mode fullscreen
```

## Tray

**Ctrl+Shift+S** = screen ask  
**Ctrl+Alt+V** = voice

## Tips for reading files (requirements.txt, code)

- Crop only the text area
- Ask: "Read every line exactly" or "List all packages"
- `force_text_mode: true` in config if needed

## Privacy

- Image deleted after analysis
- `logs/vision_audit.jsonl` — no image data
