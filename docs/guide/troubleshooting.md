# Troubleshooting

Common failures and how to recover from them. Run `--check` first — it catches most things.

```powershell
.\venv\Scripts\python.exe run_celestia.py --check
```

---

## Ollama not running or unreachable

**Symptom:** `--check` says Ollama is down. Chat returns an error immediately. Shell status shows `ollama_ok: false`.

**Fix:**

```powershell
ollama serve
```

Leave it running in a background terminal. Celestia does not start Ollama for you.

**If Ollama is running but still failing:**

```powershell
ollama list          # verify models are pulled
ollama ps            # check if a model is loaded
curl http://127.0.0.1:11434/api/tags   # test the API directly
```

If the host/port is non-default, update `llm.host` in `config.yaml`.

---

## Chat hangs indefinitely

**Symptom:** You send a message. The shell shows "Thinking…" forever or the `-i` REPL never returns.

**Cause:** The LLM call in `agent.py` has no timeout. If Ollama stops responding mid-generation (OOM, crash, context overflow), the request hangs.

**Fix:**
- Kill the Celestia process and restart.
- Check Ollama: `ollama ps` — if a model is listed but Ollama is unresponsive, restart it.
- Try a shorter message to rule out context overflow.

**Workaround until CC-92 ships:** Add `timeout` to the `ollama.chat()` call in `agent.py` manually if this happens repeatedly.

---

## CUDA out of memory (OOM)

**Symptom:** Python crashes with `CUDA out of memory`, or Ollama logs show OOM. Usually happens when STT, LLM, and vision are all loaded at once.

**Quick fix:** Unload what you do not need:

- STT unloads itself after `voice.stt.idle_unload_minutes` (default 10). Force it by restarting.
- TTS unloads after `voice.tts.orpheus.idle_shutdown_minutes` (default 5).
- Vision releases VRAM after the confirm step.

**Config tweaks for low VRAM:**

```yaml
llm:
  chat_model: llama3.2:3b        # smaller than qwen2.5:7b
voice:
  stt:
    model: small                 # or base
    idle_unload_minutes: 5
  tts:
    orpheus:
      idle_shutdown_minutes: 2
vision:
  text_model: moondream
  two_pass_text: false
```

See [performance.md](../reference/performance.md) for full profiles.

---

## Whisper (STT) fails to load

**Symptom:** Voice PTT is silent. `-i` `listen` command returns immediately with no transcription. Logs show a model load error.

**Check:**

```powershell
.\venv\Scripts\python.exe run_celestia.py --check
```

Look for a voice check failure. Common causes:

| Cause | Fix |
|-------|-----|
| `large-v3` not downloaded yet | First run downloads it; check `~/.cache/huggingface/hub/` |
| `HF_TOKEN` missing | Copy `.env.example` → `.env` and add `HF_TOKEN=...` |
| CUDA unavailable | Set `voice.stt.device: cpu` and `compute_type: int8` in config |
| llama-cpp-python CUDA build missing | Reinstall: `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124` |

---

## Orpheus TTS produces no audio

**Symptom:** Celestia replies in text but there is no voice output. No error message.

**Check:**

1. Is `voice.tts.provider: orpheus` in config?
2. Does `models/Orpheus-3b-FT-Q8_0.gguf` exist? (`dir models\`)
3. Is the audio device available? Another app may have exclusive control.
4. Try switching to Edge TTS to isolate the issue:

```yaml
voice:
  tts:
    provider: edge
    edge:
      voice: en-US-GuyNeural
```

If Edge TTS works, the issue is Orpheus-specific (GGUF path, GPU layers, SNAC decode).

---

## Chroma / memory corruption

**Symptom:** `--check` says memory is down. The `memory` command crashes. Errors mention `sqlite3` or `hnswlib`.

**Fix:**

```powershell
# Back up first
xcopy data\chroma data\chroma_backup /E /I

# Then delete the corrupted store
rmdir /S /Q data\chroma
```

Restart Celestia. Chroma recreates itself from scratch on the next run. You lose stored memories.

**Prevention:** Do not kill the process mid-write. Use `newchat` or `Ctrl+C` once to let it consolidate cleanly.

---

## Shell server port conflict

**Symptom:** `--shell` or `--shell-server` prints an address-in-use error. The Tauri shell shows a connection error.

**Cause:** Port 8765 is taken by another process (or a previous Celestia instance that did not shut down cleanly).

**Fix:**

```powershell
# Find what's on the port
netstat -ano | findstr :8765

# Kill by PID
taskkill /PID <pid> /F
```

Or change the port in `config.yaml`:

```yaml
ui:
  shell_port: 8766
```

Then run `--trust-config` and restart.

---

## Config trust warning on startup

**Symptom:** Celestia prints `[warn] config changed since last trust` or similar on start.

**Cause:** `config.yaml` or `security.policy.yaml` was edited after the last `--trust-config` run.

**If you made the change on purpose:**

```powershell
.\venv\Scripts\python.exe run_celestia.py --trust-config
```

**If you did not make the change:** Inspect the diff before trusting:

```powershell
git diff config.yaml
git diff security.policy.yaml
```

See [security.md](security.md) for details on the integrity check.

---

## Tauri shell window does not open

**Symptom:** `--shell` starts the Python server (you see the API URL printed) but no window appears. Or the window opens blank.

**Checks:**

1. **WebView2** — must be installed (usually present on Windows 10/11). Install from [microsoft.com/webview2](https://developer.microsoft.com/microsoft-edge/webview2/).
2. **Node modules** — run `npm install` inside `shell/` if you have not done so.
3. **Tauri CLI** — `cd shell && npm run tauri -- info` to verify the Rust toolchain.
4. **Port** — the shell frontend connects to `127.0.0.1:8765`. If the server is on a different port, update `ui.shell_port` in config.

For dev mode only: if the Vite dev server is on a different port, set `VITE_SHELL_API` in `shell/.env` to `http://127.0.0.1:8765`.

---

## Shell PTT mic button does nothing

**Symptom:** Holding the mic button in the shell shows "Listening…" but releases immediately or never transcribes.

**Check `/chat/ptt/status`:**

```powershell
curl http://127.0.0.1:8765/chat/ptt/status
```

| `phase` / `error` | Cause | Fix |
|---|---|---|
| `error: stt not enabled` | `voice.stt.enabled: false` in config | Set to `true` |
| `error: no audio device` | No mic available or exclusive mode | Check Windows sound settings |
| Stuck in `recording` | STT load failed silently | Check logs; restart |

---

## `--check` passes but replies are wrong or tool calls fail

**Likely causes:**

- **Stale memory** — run `memory` in `-i` and delete bad entries. Run `newchat` to start fresh.
- **Wrong personality** — check `personality.active` in `config.yaml`.
- **Mode mismatch** — run `status` in `-i` to confirm mode. `scope safe` disables all PC tools.
- **Model misbehaving** — try `ollama run qwen2.5:7b` directly and ask it the same question to isolate the issue.

---

## Resetting to a clean state

```powershell
# Wipe memory only
.\venv\Scripts\python.exe run_celestia.py -i
> forget

# Wipe memory + session store
rmdir /S /Q data\chroma
del data\shell_chat\sessions.json
del data\memory\last_session.json
del data\memory\activity_feed.jsonl

# Re-trust config after manual edits
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```
