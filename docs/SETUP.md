# Celestia — setup & daily use

Single Windows app: `run_celestia.py`. **Ollama** required. **No Docker** for memory (Chroma). **No LM Studio** for normal TTS.

Project folder: **`C:\celestia`**

---

## 1. One-time install

```powershell
cd C:\celestia
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

Or: `.\scripts\setup.ps1`

### Ollama models

```powershell
ollama pull llama3.2:3b
ollama pull nomic-embed-text
ollama pull llama3.2-vision:11b
ollama pull qwen2.5vl:7b
ollama pull moondream
```

### Orpheus GGUF

`models/Orpheus-3b-FT-Q8_0.gguf`

### HuggingFace token (optional)

```powershell
copy .env.example .env
# HF_TOKEN=hf_... in .env
```

---

## 2. Config & trust

```powershell
copy config.example.yaml config.yaml
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```

---

## 3. Daily commands

| What | Command |
|------|---------|
| Chat | `.\venv\Scripts\python.exe run_celestia.py -i` |
| Arm + ask | `.\venv\Scripts\python.exe run_celestia.py --arm "open notepad"` |
| Screen | `.\venv\Scripts\python.exe run_celestia.py --screen "Read all text"` |
| Screen (window) | `... --screen "..." --screen-mode active_window` |
| Screen (full) | `... --screen-mode fullscreen` |
| Tray | `.\venv\Scripts\python.exe run_celestia.py --tray` |

REPL: `arm`, `disarm`, `status`, `listen`, `screen`, `screen fullscreen`, `screen window`

### Notepad on Windows 11 (including Turkish PCs)

You may see **two** apps:

| Name | What it is |
|------|------------|
| **Not Defteri** | Classic `System32\\notepad.exe` — Celestia opens this one |
| **Notepad** | Microsoft Store / WinUI app — often broken (`Microsoft.UI.Windowing.Core.dll`) |

Celestia launches **only** the classic path, not `start notepad` (that can hit the broken Store alias in PATH).

Optional alias in config:

```yaml
pc_control:
  app_aliases:
    notepad: "C:\\Path\\To\\Notepad++.exe"
```

---

## 4. Security (Phase 2.5)

- Default: **disarmed** (no PC control)
- `--arm` before commands that open apps or run PowerShell
- Audit: `logs/tool_audit.jsonl`
- Integrity: `data/config.trust` persists across restarts — see [PHASE2_5_SECURITY.md](PHASE2_5_SECURITY.md)

---

## 5. Personality

See [PERSONALITY.md](PERSONALITY.md) — files in `personalities/`, set `personality.active` in config.
