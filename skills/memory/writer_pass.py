"""Memory writer pass (T15): run the writer over a chat window and apply its ops.

One call to the background memory model (``memory.session_consolidate_model``,
thinking per ``memory.background_think``) reads the window since the last
checkpoint plus the relevant existing memories and returns
add / update / supersede / forget ops (``skills/memory/writer.py``). Each op is
applied to text memory *and* the graph together:

  add        new text memory; its triples become graph edges linked to it
  update     text edited in place; if the op carries triples, the old linked
             edges end and the new ones are linked instead
  supersede  new memory added, old one moved to ``history.jsonl`` and removed
             from live recall; its edges end (kept as graph history)
  forget     memory deleted; its edges deleted — the user asked for it gone

Tasks (``kind: task``) go to the To-do list instead of text memory.

T04 still applies: in a window that read untrusted content, an add the user's
own words don't back is stored quarantined (no graph edges until approved), and
update / supersede / forget the user didn't back are refused — injected text
must not rewrite or erase existing memories.

The caller owns the checkpoint cursor: ``PassResult.consumed`` says how far into
the given messages the pass got (0 when it was deferred and should be retried).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from celestia_core.config import get
from skills.memory.activity_feed import append_event

_MAX_EXCERPT_LINES = 80
_MAX_ASSISTANT_CHARS = 400
_EXISTING_LIMIT = 20
_NUM_PREDICT = 1024


@dataclass
class PassResult:
    consumed: int  # messages[:consumed] are done; 0 = deferred, retry later
    lines: list[str] = field(default_factory=list)
    summary: str = ""
    ops: list[dict[str, Any]] = field(default_factory=list)
    ran: bool = False


# ---------------------------------------------------------------------------
# Gate + window
# ---------------------------------------------------------------------------


def pass_allowed(messages: list[dict[str, Any]], start_index: int) -> bool:
    """Whether a pass over ``messages[start_index:]`` may record anything.

    Same switches as the legacy consolidation (``memory.enabled``,
    ``memory.session_consolidate``, ``memory.session_consolidate_mode``) and the
    incognito choke point. *When* to run is the caller's decision (end of chat
    or a checkpoint), so there is no turn-count rule here.
    """
    if not get("memory.enabled", True) or not get("memory.session_consolidate", True):
        return False
    from celestia_core import incognito
    from skills.memory.session_consolidate import _user_asked_to_remember, consolidate_mode

    if incognito.is_on():
        return False
    mode = consolidate_mode()
    if mode == "off":
        return False
    window = messages[start_index:]
    if not any(m.get("role") == "user" for m in window):
        return False
    if mode == "explicit":
        return _user_asked_to_remember(messages, start_index)
    return True


def transcript(messages: list[dict[str, Any]], start_index: int) -> str:
    lines: list[str] = []
    for m in messages[start_index:]:
        role = m.get("role")
        text = str(m.get("content") or "").strip()
        if not text:
            continue
        if role == "user":
            lines.append(f"User: {text}")
        elif role == "assistant":
            lines.append(f"Assistant: {text[:_MAX_ASSISTANT_CHARS]}")
    return "\n".join(lines[-_MAX_EXCERPT_LINES:])


def select_existing(user_id: str, query: str, limit: int = _EXISTING_LIMIT) -> list[dict[str, Any]]:
    """The memories the writer should see: what the chat is about (semantic
    hits), every standing instruction, then the most recent — live entries only."""
    from skills.memory.store import get_all_entries, search

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def take(entries: list[dict[str, Any]]) -> None:
        for e in entries:
            if len(out) >= limit:
                return
            if e.get("quarantined") or not e.get("id") or e["id"] in seen:
                continue
            seen.add(e["id"])
            out.append(e)

    take(search(query[-2000:], user_id, limit=10))
    recent = get_all_entries(user_id, limit=60)
    take([e for e in recent if e.get("kind") == "instruction"])
    take(recent)
    return out


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _result_id(result: Any) -> str | None:
    if isinstance(result, dict):
        rows = result.get("results", [result])
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0].get("id")
    return None


def _write_edges(memory_id: str, triples: list[dict[str, str]]) -> list[str]:
    if not triples or not get("memory.graph.enabled", True):
        return []
    from skills.memory import graph_store as gs

    ids: list[str] = []
    for t in triples:
        try:
            ids.append(
                gs.add_relation(
                    t["subject"], t["predicate"], t["object"], source=f"memory:{memory_id}", confidence=0.8
                )
            )
        except Exception:
            continue
    return ids


def _end_linked(memory_id: str) -> None:
    from skills.memory import graph_store as gs
    from skills.memory.links import pop_links

    ids = pop_links(memory_id)
    if ids:
        gs.end_edges(ids)


def _add_memory(text: str, kind: str, user_id: str, triples: list[dict[str, str]], *, untrusted: bool) -> str | None:
    from skills.memory import store
    from skills.memory.links import set_links

    mid = _result_id(store.add(text, user_id, kind=kind, origin="consolidation", untrusted=untrusted))
    if mid and not untrusted:
        set_links(mid, _write_edges(mid, triples))
    return mid


def apply_ops(
    ops: list[Any],
    idmap: dict[str, dict[str, Any]],
    user_id: str,
    *,
    tainted: bool = False,
    user_text: str = "",
) -> list[str]:
    """Apply parsed writer ops. ``idmap`` maps prompt ids (m1…) to the store
    entries they stood for. Returns one log line per op (applied or refused)."""
    from celestia_core.untrusted import supported_by
    from skills.memory import store
    from skills.memory.links import append_history, set_links
    from skills.memory.ranking import drop_stats

    lines: list[str] = []
    for op in ops:
        entry = idmap.get(op.target) if op.target else None
        backed = not tainted or (bool(op.text) and supported_by(op.text, user_text))
        try:
            if op.op == "add":
                if op.kind == "task":
                    from skills.todos.store import add_todo

                    add_todo(op.text, user_id, notes="From chat (memory writer)")
                    append_event(action="added to-do", text=op.text, kind="task")
                    lines.append(f"[todo] {op.text}")
                    continue
                _add_memory(op.text, op.kind, user_id, op.triples, untrusted=not backed)
                append_event(action="saved" if backed else "held for review", text=op.text, kind=op.kind)
                lines.append(f"[add{'' if backed else ', quarantined'}] {op.text}")
                continue

            if entry is None:
                continue  # parse_ops already drops unknown targets
            if not backed or (op.op == "forget" and tainted):
                lines.append(f"[refused {op.op}] {entry['text']} (window read untrusted content)")
                continue

            if op.op == "update":
                store.update_entry(entry["id"], text=op.text, user_id=user_id)
                if op.triples and get("memory.graph.enabled", True):
                    _end_linked(entry["id"])
                    set_links(entry["id"], _write_edges(entry["id"], op.triples))
                append_event(action="updated", text=op.text, kind=entry.get("kind", "fact"))
                lines.append(f"[update] {entry['text']} → {op.text}")
            elif op.op == "supersede":
                kind = op.kind if op.kind != "task" else entry.get("kind", "fact")
                new_id = _add_memory(op.text, kind, user_id, op.triples, untrusted=False)
                append_history(entry, superseded_by=new_id)
                _end_linked(entry["id"])  # graph keeps the old fact as history
                store.delete_by_id(entry["id"])
                drop_stats([entry["id"]])
                append_event(action="replaced", text=f"{entry['text']} → {op.text}", kind=kind)
                lines.append(f"[supersede] {entry['text']} → {op.text}")
            elif op.op == "forget":
                store.delete_by_id(entry["id"])  # cascades to linked edges
                drop_stats([entry["id"]])
                append_event(action="forgot", text=entry["text"], kind=entry.get("kind", "fact"))
                lines.append(f"[forget] {entry['text']}")
        except Exception as e:  # one bad op never sinks the rest
            lines.append(f"(failed {op.op} '{(op.text or '')[:40]}': {e})")
    return lines


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


def _model() -> str:
    return str(
        get("memory.writer.model")
        or get("memory.session_consolidate_model")
        or get("llm.chat_model", "qwen2.5:3b")
    )


def run_pass(
    messages: list[dict[str, Any]],
    user_id: str,
    *,
    start_index: int = 0,
    summary: str = "",
) -> PassResult:
    """Run the writer over ``messages[start_index:]`` and apply the result.

    Never raises. ``consumed == len(messages)`` when the window is done (written,
    or nothing allowed / worth recording); ``consumed == 0`` when the pass was
    deferred (GPU busy, model error) and the same window should be retried.
    """
    done = len(messages)
    if not pass_allowed(messages, start_index):
        return PassResult(consumed=done)

    text = transcript(messages, start_index)
    if len(text) < 30:
        return PassResult(consumed=done)

    from celestia_core.untrusted import is_wrapped
    from skills.memory.scrub import scrub_for_storage

    window = messages[start_index:]
    tainted = any(m.get("role") == "tool" and is_wrapped(m.get("content")) for m in window)
    user_text = "\n".join(str(m.get("content") or "") for m in window if m.get("role") == "user")
    text = scrub_for_storage(text)

    existing = select_existing(user_id, text)
    idmap = {f"m{i}": e for i, e in enumerate(existing, 1)}
    prompt_entries = [{"id": pid, "kind": e.get("kind", "fact"), "text": e["text"]} for pid, e in idmap.items()]

    from celestia_core.gpu import gpu_task
    from skills.memory.llm import background_chat
    from skills.memory.writer import OUTPUT_SCHEMA, build_prompt, parse_ops

    with gpu_task("memory-writer", blocking=False) as got:
        if not got:
            return PassResult(consumed=0, lines=["memory pass deferred: gpu busy"])
        try:
            resp = background_chat(
                model=_model(),
                messages=[{"role": "user", "content": build_prompt(text, prompt_entries, summary)}],
                format=OUTPUT_SCHEMA,
                options={"num_predict": _NUM_PREDICT, "temperature": 0.0},
            )
        except Exception as e:
            return PassResult(consumed=0, lines=[f"memory pass deferred: {e}"])

    msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
    raw = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
    result = parse_ops(str(raw), {pid: e["text"] for pid, e in idmap.items()})
    lines = apply_ops(result.ops, idmap, user_id, tainted=tainted, user_text=user_text)
    lines += [f"(dropped: {d})" for d in result.dropped]
    return PassResult(
        consumed=done,
        lines=lines,
        summary=result.summary,
        ops=[o.as_dict() for o in result.ops],
        ran=True,
    )


# ---------------------------------------------------------------------------
# Pipeline switch
# ---------------------------------------------------------------------------


def pipeline() -> str:
    """``writer`` (T15, default) or ``legacy`` (typed consolidation + separate
    graph extraction, kept for comparison and as a fallback)."""
    return "legacy" if str(get("memory.pipeline", "writer")).strip().lower() == "legacy" else "writer"


def consolidate(
    messages: list[dict[str, Any]],
    user_id: str,
    *,
    start_index: int = 0,
    end: bool = False,
    extract_graph: bool = True,
    summary: str = "",
) -> tuple[int, list[str]]:
    """Drop-in for ``consolidate_session_messages``: returns (new_start, lines).
    ``summary`` (rendered running summary) is context for the writer.

    With the writer pipeline a deferred pass returns ``start_index`` unchanged so
    the same window is retried at the next checkpoint or at the end of the chat.
    """
    if pipeline() == "legacy":
        from skills.memory.session_consolidate import consolidate_session_messages

        return consolidate_session_messages(
            messages, user_id, start_index=start_index, end=end, extract_graph=extract_graph
        )
    result = run_pass(messages, user_id, start_index=start_index, summary=summary)
    return (result.consumed or start_index), result.lines



# ---------------------------------------------------------------------------
# Session pass: memory + running summary (T15 step 3)
# ---------------------------------------------------------------------------


@dataclass
class SessionPassResult:
    new_start: int          # messages[:new_start] are done (== start_index when deferred)
    lines: list[str]
    summary: Any            # running summary after this pass (session_summary state; unchanged when deferred)
    tainted: bool = False   # this window read untrusted content


def _window_tainted(messages: list[dict[str, Any]], start_index: int) -> bool:
    from celestia_core.untrusted import is_wrapped

    return any(m.get("role") == "tool" and is_wrapped(m.get("content")) for m in messages[start_index:])


def summarize(messages: list[dict[str, Any]], start_index: int, previous: Any = None) -> Any | None:
    """Fold ``messages[start_index:]`` into the structured running summary
    (``session_summary``: goal / now / facts / decisions / open / details, with
    carry-over). Returns the new state dict, ``previous`` unchanged when there's
    nothing to add, or None when deferred (GPU busy / model error)."""
    from skills.memory import session_summary as ss
    from skills.memory.scrub import scrub_for_storage

    text = transcript(messages, start_index)
    if len(text) < 30:
        return previous
    from celestia_core.gpu import gpu_task
    from skills.memory.llm import background_chat

    with gpu_task("session-summary", blocking=False) as got:
        if not got:
            return None
        try:
            resp = background_chat(
                model=_model(),
                messages=[{"role": "user", "content": ss.build_prompt(scrub_for_storage(text), previous)}],
                format=ss.OUTPUT_SCHEMA,
                options={"num_predict": 900, "temperature": 0.0},
            )
        except Exception:
            return None
    msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
    raw = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
    update = ss.parse(str(raw))
    if update is None:
        return previous
    return ss.merge(previous, update)


def session_pass(
    messages: list[dict[str, Any]],
    user_id: str,
    *,
    start_index: int = 0,
    summary: Any = None,
    end: bool = False,
    extract_graph: bool = True,
) -> SessionPassResult:
    """One checkpoint over ``messages[start_index:]``: long-term memory (when
    allowed) and the session's structured running summary (``chat.session_summary``).

    The summary has its own call (``summarize``) whatever the memory pipeline:
    it keeps working memory going in incognito / with saving off, and keeps the
    memory writer's prompt as the eval measured it. At the end of a chat only
    memory runs — the summary has no one left to serve.
    """
    tainted = _window_tainted(messages, start_index)
    want_summary = bool(get("chat.session_summary", True)) and not end

    from skills.memory import session_summary as ss

    new_start, lines, memory_ran = len(messages), [], False
    if pass_allowed(messages, start_index) or pipeline() == "legacy":
        context = ss.render(summary) if summary else ""
        new_start, lines = consolidate(
            messages, user_id, start_index=start_index, end=end,
            extract_graph=extract_graph, summary=context,
        )
        if new_start == start_index and new_start < len(messages):
            return SessionPassResult(start_index, lines, summary)   # memory pass deferred: retry all
        memory_ran = True

    if want_summary:
        updated = summarize(messages, start_index, summary)
        if updated is None:
            if not memory_ran:
                return SessionPassResult(start_index, ["summary deferred"], summary)
            lines.append("summary deferred")  # memory already advanced; summary skips this window
        else:
            summary = updated
    return SessionPassResult(new_start, lines, summary, tainted)
