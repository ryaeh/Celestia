"""Tests for skills/memory/tidy.py — the GPU-idle tidy pass orchestration.

Jobs (entity resolution, decay) and side effects (activity feed, model unload)
are stubbed; state files go to tmp. The daemon thread itself is not started —
its gate logic (`_should_run_now`) is tested directly.
"""

from __future__ import annotations

import json
import time

import pytest

import skills.memory.tidy as tidy


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Tmp state file, config dict, and stubbed jobs/side-effects."""
    cfg: dict[str, object] = {
        "memory.tidy.enabled": True,
        "memory.tidy.min_interval_hours": 6,
        "memory.tidy.model": "judge-model",
        "memory.tidy.min_afk_minutes": 10,
        "memory.tidy.max_gpu_utilization": 20,
    }
    monkeypatch.setattr(tidy, "get", lambda key, default=None: cfg.get(key, default))
    monkeypatch.setattr(tidy, "_state_path", lambda: tmp_path / "tidy_state.json")

    calls: dict[str, list] = {"resolve": [], "unload": [], "events": [], "decay": []}

    import skills.memory.entity_resolution as er

    def _resolve(**kw):
        calls["resolve"].append(kw)
        return {"nodes": 4, "candidates": 1, "merges": [{"kept": "VS Code", "merged": "vscode", "similarity": 0.95}], "dry_run": kw.get("dry_run", False)}

    monkeypatch.setattr(er, "resolve_entities", _resolve)

    import skills.memory.decay as decay

    monkeypatch.setattr(decay, "should_sweep_now", lambda: False)
    monkeypatch.setattr(decay, "sweep_decay", lambda **kw: calls["decay"].append(kw) or {"deleted": 0})

    import celestia_core.gpu as gpu

    monkeypatch.setattr(gpu, "unload_model", lambda name: calls["unload"].append(name))

    import skills.memory.activity_feed as af

    def _append_event(*, action, text, kind="fact", source="consolidate"):
        calls["events"].append({"action": action, "text": text, "source": source})

    monkeypatch.setattr(af, "append_event", _append_event)

    return tidy, cfg, calls, tmp_path


# ---------------------------------------------------------------------------
# run_tidy — gates
# ---------------------------------------------------------------------------


def test_disabled_does_not_run(env) -> None:
    mod, cfg, calls, _ = env
    cfg["memory.tidy.enabled"] = False
    assert mod.run_tidy() == {"ran": False, "enabled": False}
    assert calls["resolve"] == []


def test_throttled_does_not_run(env) -> None:
    mod, _, calls, tmp = env
    (tmp / "tidy_state.json").write_text(json.dumps({"last_run": time.time()}), encoding="utf-8")
    assert mod.run_tidy() == {"ran": False, "throttled": True}
    assert calls["resolve"] == []


def test_force_bypasses_gates(env) -> None:
    mod, cfg, calls, tmp = env
    cfg["memory.tidy.enabled"] = False
    (tmp / "tidy_state.json").write_text(json.dumps({"last_run": time.time()}), encoding="utf-8")
    report = mod.run_tidy(force=True)
    assert report["ran"] is True
    assert len(calls["resolve"]) == 1


def test_busy_gpu_yields(env, monkeypatch) -> None:
    mod, _, calls, _ = env
    from contextlib import contextmanager

    import celestia_core.gpu as gpu

    @contextmanager
    def _busy(name, *, blocking=True, timeout=None):
        yield False

    monkeypatch.setattr(gpu, "gpu_task", _busy)
    assert mod.run_tidy(force=True) == {"ran": False, "busy": True}
    assert calls["resolve"] == []


# ---------------------------------------------------------------------------
# run_tidy — effects
# ---------------------------------------------------------------------------


def test_run_saves_state_unloads_and_logs(env) -> None:
    mod, _, calls, tmp = env
    report = mod.run_tidy()
    assert report["ran"] is True
    assert report["entity_resolution"]["merges"]

    state = json.loads((tmp / "tidy_state.json").read_text(encoding="utf-8"))
    assert state["last_run"] > 0
    assert calls["unload"] == ["judge-model"]
    assert len(calls["events"]) == 1
    assert "vscode" in calls["events"][0]["text"]


def test_dry_run_skips_state_and_event_but_unloads(env) -> None:
    mod, _, calls, tmp = env
    report = mod.run_tidy(force=True, dry_run=True)
    assert report["dry_run"] is True
    assert not (tmp / "tidy_state.json").exists()
    assert calls["events"] == []
    assert calls["unload"] == ["judge-model"]  # judge loaded either way — free it


def test_decay_runs_only_when_its_own_gate_agrees(env, monkeypatch) -> None:
    mod, _, calls, _ = env
    import skills.memory.decay as decay

    monkeypatch.setattr(decay, "should_sweep_now", lambda: True)
    report = mod.run_tidy(force=True)
    assert len(calls["decay"]) == 1
    assert report["decay"] == {"deleted": 0}


def test_job_error_is_contained(env, monkeypatch) -> None:
    mod, _, _, _ = env
    import skills.memory.entity_resolution as er

    def _boom(**kw):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(er, "resolve_entities", _boom)
    report = mod.run_tidy(force=True)
    assert report["ran"] is True
    assert "ollama down" in report["entity_resolution"]["error"]


# ---------------------------------------------------------------------------
# _should_run_now (daemon gate)
# ---------------------------------------------------------------------------


def test_should_run_requires_enabled(env, monkeypatch) -> None:
    mod, cfg, _, _ = env
    import celestia_core.idle_probe as ip

    monkeypatch.setattr(ip, "system_is_idle", lambda **kw: True)
    assert mod._should_run_now() is True
    cfg["memory.tidy.enabled"] = False
    assert mod._should_run_now() is False


def test_should_run_requires_idle_system(env, monkeypatch) -> None:
    mod, _, _, _ = env
    import celestia_core.idle_probe as ip

    monkeypatch.setattr(ip, "system_is_idle", lambda **kw: False)
    assert mod._should_run_now() is False


def test_should_run_respects_throttle(env, monkeypatch, tmp_path) -> None:
    mod, _, _, tmp = env
    import celestia_core.idle_probe as ip

    monkeypatch.setattr(ip, "system_is_idle", lambda **kw: True)
    (tmp / "tidy_state.json").write_text(json.dumps({"last_run": time.time()}), encoding="utf-8")
    assert mod._should_run_now() is False
