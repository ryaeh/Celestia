# Screen / vision

Take a screenshot, confirm you’re happy to send it, then ask the vision model. For dense text (CMD, code, requirements.txt) we often do two passes: read the lines first, then answer your question.

## Models

```powershell
ollama pull qwen2.5vl:7b
```

Handy config bits:

```yaml
vision:
  enabled: true
  default_mode: region
  text_model: qwen2.5vl:7b
  two_pass_text: true
  confirm_before_send: true
```

## How to capture

- **region** — drag a rectangle (`screen region …` or `--screen-mode region`)
- **fullscreen** — whole desktop
- **window** — active window only (`active_window` in CLI)

If you don’t say, it uses `vision.default_mode` (usually region).

## What happens

1. Grab pixels (mss)
2. Beep + preview — say yes or no
3. Drop voice models if we need VRAM
4. Analyze (text mode: OCR-style pass, then answer)
5. Maybe speak the answer

## Examples

```powershell
.\venv\Scripts\python.exe run_celestia.py --screen "Read every line of text in this image exactly"
.\venv\Scripts\python.exe run_celestia.py --screen "What's this window?" --screen-mode active_window
```

In `-i`:

```
screen window Read every line of text exactly
```

Tray: **Ctrl+Shift+S** (uses config default mode).

## Tips for text

- Crop only the text in region mode
- Ask plainly: “read every line exactly”
- If she keeps chatting instead of OCR, try `force_text_mode: true` in config

## Privacy

Images land in `temp/vision/` and get cleaned up. The audit log doesn’t store the picture.
