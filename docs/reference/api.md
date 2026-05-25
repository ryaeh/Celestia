# Shell Server API

The Python backend exposes a local-only HTTP API on `127.0.0.1:8765` (port configurable via `ui.shell_port`). The Tauri shell and any local tool talk to this API. **Requests from non-localhost addresses are rejected with 403.**

Start the server:

```powershell
# Production (starts server + shell window)
.\venv\Scripts\python.exe run_celestia.py --shell

# Dev (server only, hot-reload the frontend separately)
.\venv\Scripts\python.exe run_celestia.py --shell-server
```

Source: `celestia_core/shell_server.py`

---

## Status

### `GET /status`

Returns the current application state. Called by the shell on load and every 5 seconds.

**Response `200`**

```json
{
  "display_name": "Celestia",
  "mode": "safe",
  "mode_label": "Safe",
  "tray_max_mode": null,
  "personality": "default",
  "ollama_ok": true,
  "checks": [
    { "ok": true,  "message": "Ollama OK" },
    { "ok": true,  "message": "Memory OK" },
    { "ok": true,  "message": "Security OK" },
    { "ok": false, "message": "Voice: model not found" }
  ]
}
```

`mode` is one of `"safe"` · `"scoped"` · `"armed"`.  
`tray_max_mode` is `null` if `security.tray_max_mode` is not set in config.

---

### `POST /mode`

Change the security mode.

**Body**

```json
{ "mode": "scoped" }
```

`mode` must be `"safe"`, `"scoped"`, or `"armed"`.

**Response `200`**

```json
{ "ok": true, "mode": "scoped", "label": "Scoped" }
```

**Response `400`** — invalid mode string.

---

## Workspaces

### `GET /workspaces`

Returns the list of active workspace root paths (set by `scope add`).

**Response `200`**

```json
{ "workspaces": ["C:\\Users\\you\\Projects", "C:\\celestia"] }
```

---

## Audit Log

### `GET /audit/tail?n=20`

Returns the last `n` entries from `logs/tool_audit.jsonl`.

**Query params**

| Name | Default | Description |
|------|---------|-------------|
| `n` | `20` | Number of entries to return |

**Response `200`**

```json
{
  "entries": [
    {
      "ts": 1716000000.0,
      "tool": "open_path",
      "mode": "scoped",
      "source": "shell",
      "summary": "open notepad",
      "ok": true
    }
  ]
}
```

---

## Chat

### `GET /chat/sessions`

Lists all stored sessions.

**Response `200`**

```json
{
  "sessions": [
    { "id": "abc123", "title": "Hey Celestia", "when": "Today", "active": true },
    { "id": "def456", "title": "Open notepad", "when": "Yesterday", "active": false }
  ],
  "active_id": "abc123"
}
```

`title` is derived from the first user message. `when` is a human-readable relative date.

---

### `GET /chat/history?session=<id>`

Returns message history for a session.

**Query params**

| Name | Default | Description |
|------|---------|-------------|
| `session` | active session | Session ID |

**Response `200`**

```json
{
  "messages": [
    { "role": "user",      "content": "Hi" },
    { "role": "assistant", "content": "Hey! What's up?" }
  ],
  "session_id": "abc123"
}
```

Only `user` and `assistant` messages are returned. Internal `system` and `tool` messages are stripped.

---

### `POST /chat`

Send a message and get a reply. This is a **blocking** call — it returns after the LLM finishes the full response (including any tool rounds). Expect 3–10 seconds depending on the model and query.

**Body**

```json
{ "message": "What time is it?", "session_id": "abc123" }
```

`session_id` is optional; omit to use the active session.

**Response `200`**

```json
{
  "reply": "It's 9:30 PM.",
  "session_id": "abc123",
  "messages": [
    { "role": "user",      "content": "What time is it?" },
    { "role": "assistant", "content": "It's 9:30 PM." }
  ]
}
```

`messages` is the full filtered history after the turn.

**Response `400`** — empty message or session error.  
**Response `500`** — LLM or tool error.

> **Known limitation:** This endpoint is synchronous. While a `/chat` request is processing, `/status` polls may be delayed. See [architecture.md](architecture.md) for the planned FastAPI migration.

---

### `POST /chat/new`

Create a new chat session. The new session becomes the active session.

**Body** — empty `{}` accepted.

**Response `200`**

```json
{ "ok": true, "session_id": "newid123", "messages": [] }
```

---

### `POST /chat/select`

Switch the active session to an existing one.

**Body**

```json
{ "session_id": "def456" }
```

**Response `200`**

```json
{
  "ok": true,
  "session_id": "def456",
  "messages": [
    { "role": "user", "content": "Open notepad" },
    { "role": "assistant", "content": "Done — Notepad is open." }
  ]
}
```

**Response `400`** — session ID not found.

---

## Push-to-Talk (PTT)

PTT lets the shell frontend trigger voice input. The lifecycle is: `start` → user speaks → `stop` (transcribe + reply) or `cancel` (discard).

### `GET /chat/ptt/status`

Poll the current PTT state. The shell frontend polls this at 250ms intervals.

**Response `200`**

```json
{
  "phase": "idle",
  "listening": false,
  "busy": false,
  "error": null
}
```

`phase` values: `"idle"` · `"recording"` · `"transcribing"` · `"replying"` · `"error"`

---

### `POST /chat/ptt/start`

Begin recording. The STT engine starts capturing audio.

**Body** — empty `{}` accepted.

**Response `200`**

```json
{ "ok": true }
```

**Response `400`** — STT not enabled or already recording.

---

### `POST /chat/ptt/stop`

Stop recording, transcribe, and generate a reply. Equivalent to releasing the mic button.

**Body**

```json
{ "session_id": "abc123" }
```

`session_id` is optional.

**Response `200`** — same shape as `POST /chat`.

**Response `400` / `500`** — transcription or LLM error.

---

### `POST /chat/ptt/cancel`

Discard the current recording without transcribing.

**Body** — empty `{}` accepted.

**Response `200`**

```json
{ "ok": true }
```

---

## Memory

Memory entries have four kinds: `fact` · `instruction` · `summary` · `task`.  
All write operations also return the updated full entry list.

### `GET /memory`

List all stored memory entries (up to 200).

**Response `200`**

```json
{
  "entries": [
    {
      "id": "mem_abc123",
      "text": "Prefers dark mode",
      "kind": "fact",
      "updated_at": 1716000000.0
    }
  ]
}
```

---

### `GET /memory/{id}`

Fetch a single entry by ID.

**Response `200`** — single entry object.  
**Response `404`** — ID not found.

---

### `POST /memory`

Add a new memory entry manually.

**Body**

```json
{ "text": "Prefers dark mode", "kind": "fact" }
```

`kind` defaults to `"fact"` if omitted. Valid values: `fact` · `instruction` · `summary` · `task`.

**Response `200`**

```json
{ "ok": true, "entries": [ ... ] }
```

---

### `PATCH /memory/{id}`

Update an existing entry's text or kind.

**Body** — include only the fields you want to change.

```json
{ "text": "Prefers dark mode in the editor", "kind": "instruction" }
```

**Response `200`**

```json
{ "ok": true, "message": "Updated.", "entries": [ ... ] }
```

**Response `404`** — ID not found.

---

### `DELETE /memory/{id}`

Delete a memory entry permanently.

**Response `200`**

```json
{ "ok": true, "message": "Deleted.", "entries": [ ... ] }
```

**Response `400`** — delete failed.

---

### `GET /memory/last-session`

Returns the last-session note — a short plain-text summary of the previous conversation.

**Response `200`**

```json
{
  "bullets": ["Worked on the Tauri shell", "Discussed memory v2"],
  "text": "Last time: worked on the Tauri shell and discussed memory v2.",
  "updated_at": 1716000000.0
}
```

`bullets` and `text` may both be empty strings if no session has been consolidated yet.

---

### `POST /memory/last-session/refresh`

Re-generate the last-session note from the current active session's history.

**Body** — empty `{}` accepted.

**Response `200`** — same shape as `GET /memory/last-session`, plus `"ok": true`.

---

### `GET /memory/activity?n=30`

Returns the last `n` memory consolidation events from `data/memory/activity_feed.jsonl`.

**Query params**

| Name | Default | Description |
|------|---------|-------------|
| `n` | `30` | Number of recent events |

**Response `200`**

```json
{
  "events": [
    {
      "ts": 1716000000.0,
      "action": "saved",
      "kind": "fact",
      "text": "Prefers dark mode",
      "source": "consolidate"
    }
  ]
}
```

`source` is `"consolidate"` (auto-save) or `"manual"` (shell Memory page add).

---

## Error format

All error responses follow the same shape:

```json
{ "error": "descriptive message here" }
```

HTTP codes used: `200` success · `400` bad request · `403` non-localhost · `404` not found · `500` internal error.
