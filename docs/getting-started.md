# Getting started

Celestia is one Python app: `run_celestia.py`. You need **Ollama** on your machine. Memory sits in **Chroma** on disk (no Docker). Voice uses **Orpheus** inside the same process — you don't run LM Studio for normal use.

Folder: `C:\celestia`

## Install once

```powershell
cd C:\celestia
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

Or: `.\scripts\setup.ps1`

Pull some models:

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text
```

Orpheus GGUF goes here: `models/Orpheus-3b-FT-Q8_0.gguf`

Optional — copy `.env.example` to `.env` and put your `HF_TOKEN` there (speeds up SNAC download). Don't put tokens in `config.yaml`.

## Config

```powershell
copy config.example.yaml config.yaml
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```

When you change `config.yaml` on purpose, run `--trust-config` again so you don't get spurious "config changed" warnings. More on that in [guide/security.md](guide/security.md).

## Day to day

```powershell
.\venv\Scripts\python.exe run_celestia.py -i          # chat loop
.\venv\Scripts\python.exe run_celestia.py --tray       # tray + hotkeys
.\venv\Scripts\python.exe run_celestia.py --arm "open notepad"
.\venv\Scripts\python.exe run_celestia.py --screen "Read all text"
.\venv\Scripts\python.exe run_celestia.py --screen "..." --screen-mode active_window
```

In `-i`, type `help` for commands, or read [guide/commands.md](guide/commands.md).

**Security quick reference:**

- `scope safe` / `disarm` — chat, voice, screen only; no opening apps or files via tools
- `scope scoped` — allowlisted apps (notepad, calc, …) and `read` in folders you've added
- `arm` / `scope armed` — full PC control (still has a denylist)

## Notepad on Windows 11

You might have two Notepads. Celestia opens the classic one (`System32\notepad.exe`, "Not Defteri" on Turkish Windows). It does **not** run `start notepad` — that can hit the broken Store app.

To point at Notepad++ or something else:

```yaml
pc_control:
  app_aliases:
    notepad: "C:\\Path\\To\\Notepad++.exe"
```

## More

- Personality: [guide/personality.md](guide/personality.md)
- Memory: [guide/memory.md](guide/memory.md)
- What's next to build: [project/backlog.md](project/backlog.md)
- Pick up tomorrow: [project/resume.md](project/resume.md)
