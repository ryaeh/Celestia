"""GPU-idle "tidying" pass — the smart half of the memory lifecycle.

The chat hot path stays on cheap heuristics; hygiene that needs a bigger model
runs only when the *machine* is free: user AFK, system GPU quiet
(`idle_probe`), and no Celestia foreground op (non-blocking `gpu_task`). The
judge model is loaded just for the pass and unloaded after, so it never
competes with chat for VRAM.

Jobs (v1): **graph entity resolution** (`entity_resolution.resolve_entities`),
plus an opportunistic decay sweep when `decay.should_sweep_now()` agrees.
Importance re-scoring and memory dedupe slot in here later.

OFF by default (``memory.tidy.enabled``). The daemon thread is started by
``shell_server.start_server``; ``POST /memory/tidy`` triggers a forced run for
testing (still yields to a busy GPU). At most one automatic run per
``min_interval_hours``; state lives in ``data/memory/tidy_state.json``.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get

_daemon_lock = threading.Lock()
_daemon_started = False


# ---------------------------------------------------------------------------
# Run-state (throttle) persistence
# ---------------------------------------------------------------------------


def _state_path() -> Path:
    return Path(ROOT) / "data" / "memory" / "tidy_state.json"


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _throttled() -> bool:
    last = float(_load_state().get("last_run", 0.0) or 0.0)
    interval_h = float(get("memory.tidy.min_interval_hours", 6))
    return (time.time() - last) < interval_h * 3600.0


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


def run_tidy(*, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Run one tidy pass now (jobs behind a non-blocking GPU slot).

    ``force`` skips the enabled/throttle gates (manual trigger) but still
    yields to a busy GPU — a tidy pass must never delay chat/vision/STT.
    """
    if not force and not get("memory.tidy.enabled", False):
        return {"ran": False, "enabled": False}
    if not force and _throttled():
        return {"ran": False, "throttled": True}

    from celestia_core.gpu import gpu_task, unload_model

    with gpu_task("memory-tidy", blocking=False) as got:
        if not got:
            return {"ran": False, "busy": True}

        report: dict[str, Any] = {"ran": True, "dry_run": dry_run}

        try:
            from skills.memory.entity_resolution import resolve_entities

            report["entity_resolution"] = resolve_entities(dry_run=dry_run)
        except Exception as e:
            report["entity_resolution"] = {"error": str(e)}

        # Opportunistic decay sweep — fully governed by decay's own
        # enabled/throttle config; tidy just provides the quiet moment.
        try:
            from skills.memory.decay import should_sweep_now, sweep_decay

            if should_sweep_now():
                report["decay"] = sweep_decay(dry_run=dry_run)
        except Exception as e:
            report["decay"] = {"error": str(e)}

    # Free the judge model's VRAM immediately — don't wait for keep_alive.
    try:
        unload_model(str(get("memory.tidy.model", "qwen2.5:7b")))
    except Exception:
        pass

    if not dry_run:
        merged = (report.get("entity_resolution") or {}).get("merges") or []
        _save_state({"last_run": time.time(), "last_report": report})
        if merged:
            try:
                from skills.memory.activity_feed import append_event

                names = ", ".join(f"{m['merged']}→{m['kept']}" for m in merged[:5])
                append_event(
                    action="tidy",
                    text=f"merged {len(merged)} duplicate entit{'y' if len(merged) == 1 else 'ies'}: {names}",
                    kind="fact",
                    source="tidy",
                )
            except Exception:
                pass

    return report


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------


def _should_run_now() -> bool:
    """The daemon's per-tick gate: enabled, not throttled, machine idle."""
    if not get("memory.tidy.enabled", False):
        return False
    if _throttled():
        return False
    from celestia_core.idle_probe import system_is_idle

    return system_is_idle(
        min_afk_seconds=float(get("memory.tidy.min_afk_minutes", 10)) * 60.0,
        max_gpu_utilization=int(get("memory.tidy.max_gpu_utilization", 20)),
    )


def start_tidy_daemon() -> None:
    """Start the background idle-watcher thread (idempotent, daemon thread)."""
    global _daemon_started
    with _daemon_lock:
        if _daemon_started:
            return
        _daemon_started = True

    def _loop() -> None:
        while True:
            time.sleep(max(60.0, float(get("memory.tidy.check_interval_minutes", 10)) * 60.0))
            try:
                if _should_run_now():
                    result = run_tidy()
                    if result.get("ran"):
                        print(f"[tidy] idle pass: {result.get('entity_resolution')}", flush=True)
            except Exception as e:
                print(f"[tidy] pass failed: {e}", flush=True)

    threading.Thread(target=_loop, name="memory-tidy", daemon=True).start()
