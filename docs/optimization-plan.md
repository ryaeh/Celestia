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
- ✅ `get_mode()` / scope workspaces re-read state files on every call. Now cached
  keyed on file mtime (re-read only when the file changes — safe across
  tray/CLI/shell, since any write bumps the mtime).
- ✅ `/status` re-ran all preflight checks (incl. an Ollama probe) per request →
  now a 2s TTL cache.
- ✅ `/audit/tail` read the whole JSONL to return last N lines → now seeks from the
  end and reads only the trailing blocks.
- ⏸ Memory CRUD endpoints refetch the full 200-entry list after one edit. **Deferred:**
  returning only the changed entry is a response-shape contract change that also
  requires coordinated edits to `shell/src/api.ts` + `Memory.tsx`, which can't be
  type-checked/built in this environment (no `node_modules`, network-gated). It is a
  manual-UI path, not a per-turn hot path, so the win is marginal and the breakage
  risk is real. Revisit alongside frontend work.

## ✅ Commit 5 — DONE: cleanup
**Files:** `run_celestia.py`, `celestia_core/shell_ptt.py`, `skills/stt/engine.py`,
`skills/tts/orpheus_local.py`
- ✅ Deduped the record→transcribe→reply block in `_run_listen` / `_run_voice_loop`
  into a shared `_voice_reply()` helper (each caller keeps its own source/speak).
- ✅ `shell_ptt`: the two `_set_phase()` calls in `ptt_finish` ran outside `_lock`
  (racing `ptt_status()`); both now mutate under the lock. `_set_phase` documents
  the lock precondition.
- ✅ STT/TTS idle-unload read `time.time()` and the idle limit twice; both now read
  once before the double-checked unload.

## Explicitly NOT changing (audit over-flagged)
- `config.yaml` parsing — already cached via `load_config`.
- Top-level `ollama` import in `vision/analyze.py` — thin HTTP client, not a heavy
  lazy-dep.
