"""Link memories that predate T15 to the knowledge graph (T15 step 4).

The memory writer links every memory it writes to the graph edges derived from
it. Memories saved before that have no links, so the graph doesn't know them
and deleting one can't clean the graph. This pass gives each such memory one
small extraction (``graph_extract``'s prompt over the memory's own sentence),
writes the edges with ``source="memory:<id>"`` and records the link.

Runs in small batches from the shell's idle loop (``shell_chat.start_idle_daemon``)
and on demand (``POST /memory/graph/backfill``). Never blocks a foreground GPU
task, skips quarantined memories and incognito, and marks each memory done
even when it yields no relations, so nothing is extracted twice.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get
from celestia_core.file_utils import atomic_write_text, file_lock

_KINDS = ("fact", "instruction")


def _state_path() -> Path:
    d = ROOT / "data" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d / "graph_backfill.json"


def _load_done() -> set[str]:
    path = _state_path()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return {str(x) for x in data.get("done", [])} if isinstance(data, dict) else set()


def _mark_done(ids: list[str]) -> None:
    with file_lock(_state_path().with_suffix(".lock")):
        done = _load_done() | set(ids)
        atomic_write_text(_state_path(), json.dumps({"done": sorted(done)}, indent=1))


def pending(user_id: str) -> list[dict[str, Any]]:
    """Live fact/instruction memories with no graph links and not yet tried."""
    from skills.memory.links import load_links
    from skills.memory.store import get_all_entries

    linked = load_links()
    done = _load_done()
    return [
        e for e in get_all_entries(user_id, limit=500)
        if e.get("kind") in _KINDS and not e.get("quarantined")
        and e["id"] not in linked and e["id"] not in done
    ]


def _extract(text: str) -> list[dict[str, Any]]:
    from skills.memory.graph_extract import _PROMPT, _parse_relations
    from skills.memory.llm import background_chat

    model = (
        get("memory.graph.extraction_model")
        or get("memory.session_consolidate_model")
        or get("llm.chat_model", "qwen2.5:3b")
    )
    resp = background_chat(
        model=model,
        messages=[{"role": "user", "content": _PROMPT + f"User: {text}"}],
        options={"num_predict": 256, "temperature": 0.0},
    )
    msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
    raw = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
    return _parse_relations(str(raw))


def backfill_step(user_id: str, batch: int | None = None) -> list[str]:
    """Link up to ``batch`` (``memory.graph.backfill_batch``, default 10)
    memories. Returns one log line per memory; [] when off, busy or done."""
    if not get("memory.graph.enabled", True) or not get("memory.graph.backfill", True):
        return []
    from celestia_core import incognito

    if incognito.is_on():
        return []
    todo = pending(user_id)[: int(batch or get("memory.graph.backfill_batch", 10))]
    if not todo:
        return []

    from celestia_core.gpu import gpu_task
    from skills.memory import graph_store as gs
    from skills.memory.links import set_links

    lines: list[str] = []
    with gpu_task("graph-backfill", blocking=False) as got:
        if not got:
            return []
        for entry in todo:
            try:
                relations = _extract(entry["text"])
            except Exception as e:
                lines.append(f"(backfill stopped: {e})")
                break  # model down — retry the rest next time, don't mark them done
            ids = []
            for r in relations:
                try:
                    ids.append(gs.add_relation(
                        r["subject"], r["predicate"], r["object"],
                        source=f"memory:{entry['id']}", confidence=0.7,
                        subject_type=r.get("subject_type"), object_type=r.get("object_type"),
                    ))
                except Exception:
                    continue
            if ids:
                set_links(entry["id"], ids)
            _mark_done([entry["id"]])
            lines.append(f"[graph] {entry['text'][:60]} → {len(ids)} relation(s)")
    return lines
