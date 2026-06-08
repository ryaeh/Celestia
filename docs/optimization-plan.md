# Efficiency / cleanup pass

Status of the code-review optimization work on `claude/code-review-optimization-HRBjp`.
Each item maps to one reviewable commit. Tests (`pytest tests/ -v`) run after each.

## ✅ Commit 1 — DONE: `shell_chat` store isolation
**File:** `celestia_core/shell_chat.py`

`_read_store` / `_write_store` read+parsed *every* session file and rewrote *all*
of them on each mutation — one chat message re-serialized every session, twice.
Replaced with granular helpers (`_read_session`, `_write_session`, `_read_active`,
`_write_active`, `_list_session_ids`, `_resolve_active`). Every operation now
touches only the session it changes. On-disk format unchanged (backward-compatible).

## Commit 2 — `agent.py` hot path
**File:** `celestia_core/agent.py`
- `_memory_context()` runs twice on a fresh session (result at ~L331 discarded,
  recomputed in `_build_fresh_messages` ~L291) → double vector search. Compute once.
- `tool_schemas(user_message)` rebuilt every iteration of the up-to-8 tool loop
  (`run_turn` ~L354, `run_turn_stream` ~L520). Hoist above the loop — deterministic
  per turn.
- `_needs_memory()` (L45–81) is dead code. Remove.

## Commit 3 — memory store
**Files:** `skills/memory/store.py`, `skills/memory/session_consolidate.py`
- `update_entry()`: scans all users to find an ID, scans again, then delete-then-add
  (non-atomic — crash between loses the memory). Use in-place update; single scan
  only when `user_id` not supplied.
- Consolidation issues 4 separate vector queries (one per kind). Fetch once, filter.

## Commit 4 — Tier 2 caching
**Files:** `celestia_core/security.py`, `celestia_core/scope.py`,
`celestia_core/shell_server.py`
- `get_mode()` / scope workspaces re-read state files on every call. Cache keyed on
  file mtime (re-read only when the file changes — safe across tray/CLI/shell).
- `/status` re-runs all preflight checks per request → short TTL.
- `/audit/tail` reads the whole JSONL to return last N lines → seek from end.
- Memory CRUD endpoints refetch the full 200-entry list after one edit → return only
  the changed entry.

## Commit 5 — cleanup
**Files:** `run_celestia.py`, `celestia_core/shell_ptt.py`, `skills/stt/engine.py`,
`skills/tts/orpheus_local.py`
- Dedup near-identical record→transcribe→reply in `_run_listen` / `_run_voice_loop`.
- `shell_ptt`: move phase mutation inside the lock (TOCTOU).
- STT/TTS idle-unload calls `time.time()` twice — read once.

## Explicitly NOT changing (audit over-flagged)
- `config.yaml` parsing — already cached via `load_config`.
- Top-level `ollama` import in `vision/analyze.py` — thin HTTP client, not a heavy
  lazy-dep.
