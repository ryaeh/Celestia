"""Memory writer (T15): one reasoning pass → text-memory ops + graph triples.

Replaces the turn-count consolidation + separate graph extraction with a single
call that sees the chat since the last checkpoint, the rolling session summary,
and the relevant existing memories, and returns *operations* on text memory.
Each operation carries its own graph triples, so text memory and the graph are
written from the same decision and stay in sync.

This module is the pure half — prompt building and parsing — so the
consolidation eval (``evals/consolidation_eval.py``) scores exactly what
production will run. Applying ops to the stores is a separate step.

Ops:
  add        new memory (nothing existing covers it)
  update     refine an existing memory that is still true (extra detail)
  supersede  an existing memory is no longer true; replaced by ``text``
  forget     the user retracted it or asked to forget it
Omitting a memory means "no change" — restatements of known facts emit nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

OPS = ("add", "update", "supersede", "forget")
# Ops that point at an existing memory and must name a valid target.
TARGETED_OPS = ("update", "supersede", "forget")
# Kinds the writer may produce. Summaries are a separate output field; tasks are
# routed to the To-do list when the ops are applied.
WRITER_KINDS = ("fact", "instruction", "task")

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_MAX_OPS = 12
_MAX_TEXT = 300
_MAX_TERM = 80

PROMPT = (
    "You maintain the long-term memory of a personal assistant. Read the EXISTING "
    "MEMORIES, the SESSION SUMMARY and the NEW CHAT, then decide what must change "
    "in memory. Return JSON only.\n"
    "Operations:\n"
    '- "add": a new durable fact, standing instruction, or open task the USER stated '
    "that no existing memory covers.\n"
    '- "update": an existing memory is still true but the user added detail.\n'
    '- "supersede": an existing memory is no longer true (the user moved, changed '
    "jobs, changed a preference or rule).\n"
    '- "forget": ONLY when the user explicitly says an existing memory is wrong or '
    "asks you to forget it.\n"
    "Rules:\n"
    "- Most memories do not change. A memory that is repeated, mentioned, or not "
    "mentioned at all stays as it is: output NOTHING for it. Never use forget or "
    "update just to confirm a memory.\n"
    "- update/supersede/forget must copy an id from EXISTING MEMORIES into \"target\". "
    "If EXISTING MEMORIES is (none), the only possible op is add. add has no target.\n"
    "- text is the memory AFTER the change: the new fact, not the old one. One short "
    "third-person sentence, e.g. \"User lives in Izmir.\"\n"
    "- Only what the USER stated as true. Skip jokes, hypotheticals (\"if I moved...\"), "
    "questions, greetings, and anything the assistant guessed or suggested.\n"
    "- Never store passwords, PINs, keys or other secrets.\n"
    "- kind: fact, instruction (a rule for how the assistant should behave), or task "
    "(something the user plans to do).\n"
    "- triples: the same information as [subject, predicate, object] with short terms; "
    'use "user" for the user. forget needs no text or triples.\n'
    "- summary: 1-2 sentences on what this chat was about (may be empty).\n"
    "Format (the ids here are placeholders; use real ones):\n"
    '{"ops":[{"op":"add","kind":"fact","text":"User has a cat named Mochi.",'
    '"triples":[["user","has cat","Mochi"]]},'
    '{"op":"supersede","target":"<id>","kind":"fact","text":"User lives in Izmir.",'
    '"triples":[["user","lives in","Izmir"]]}],"summary":"..."}\n'
    'Nothing changed: {"ops":[],"summary":"Small talk about the weekend."}\n'
)


@dataclass
class MemoryOp:
    op: str
    kind: str = "fact"
    text: str = ""
    target: str | None = None
    triples: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "kind": self.kind,
            "text": self.text,
            "target": self.target,
            "triples": self.triples,
        }


@dataclass
class WriterResult:
    ops: list[MemoryOp]
    summary: str = ""
    dropped: list[str] = field(default_factory=list)  # why malformed ops were skipped


def format_existing(existing: list[dict[str, Any]]) -> str:
    """Existing memories as prompt lines. Each entry needs ``id`` (a short prompt
    id like ``m1`` — the caller maps it back to the store id), ``kind``, ``text``."""
    if not existing:
        return "(none)"
    return "\n".join(
        f"[{e['id']}] ({e.get('kind', 'fact')}) {str(e.get('text', '')).strip()}" for e in existing
    )


def build_prompt(transcript: str, existing: list[dict[str, Any]], summary: str = "") -> str:
    return (
        PROMPT
        + "\nEXISTING MEMORIES:\n"
        + format_existing(existing)
        + "\n\nSESSION SUMMARY (earlier in this chat):\n"
        + (summary.strip() or "(none)")
        + "\n\n--- NEW CHAT ---\n"
        + transcript.strip()
    )


def _clean(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _parse_triples(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for t in raw:
        if isinstance(t, (list, tuple)) and len(t) == 3:
            s, p, o = (_clean(x, _MAX_TERM) for x in t)
        elif isinstance(t, dict):
            s, p, o = (_clean(t.get(k), _MAX_TERM) for k in ("subject", "predicate", "object"))
        else:
            continue
        if s and p and o and s.lower() != o.lower():
            out.append({"subject": s, "predicate": p, "object": o})
    return out


def _first_object(raw: str) -> tuple[Any, str | None]:
    """The first JSON object in ``raw``. Tries the outermost {...} span, then
    decodes from each '{' so trailing prose or a second object can't break it."""
    match = _JSON_BLOCK.search(raw)
    if not match:
        return None, "no JSON object"
    try:
        return json.loads(match.group()), None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(raw, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "ops" in obj:
                return obj, None
    return None, "invalid JSON"


def _same_text(a: str, b: str) -> bool:
    return re.sub(r"[^a-z0-9]+", " ", a.lower()).strip() == re.sub(r"[^a-z0-9]+", " ", b.lower()).strip()


def parse_ops(raw: str, existing: set[str] | dict[str, str] | None = None) -> WriterResult:
    """Parse the model's JSON into validated ops. Tolerant of junk: malformed ops
    are dropped with a reason rather than failing the whole pass. A targeted op
    naming an unknown id is dropped (it would edit nothing, or the wrong thing).

    ``existing`` is the set of valid prompt ids, or a mapping id → current text;
    with texts, an update/supersede that restates its target unchanged is a no-op
    and is dropped."""
    if not (raw or "").strip():
        return WriterResult(ops=[])
    data, err = _first_object(raw)
    if err:
        return WriterResult(ops=[], dropped=[err])
    if not isinstance(data, dict):
        return WriterResult(ops=[], dropped=["JSON is not an object"])
    existing_ids = set(existing) if existing is not None else None
    texts = existing if isinstance(existing, dict) else {}

    ops: list[MemoryOp] = []
    dropped: list[str] = []
    raw_ops = data.get("ops") or []
    if not isinstance(raw_ops, list):
        raw_ops = []
    for item in raw_ops:
        if not isinstance(item, dict):
            dropped.append("op is not an object")
            continue
        op = str(item.get("op") or "").strip().lower()
        if op in ("noop", "none", "keep"):
            continue
        if op not in OPS:
            dropped.append(f"unknown op {op!r}")
            continue
        target = item.get("target")
        target = str(target).strip() if target not in (None, "") else None
        if op in TARGETED_OPS:
            if not target:
                dropped.append(f"{op} without target")
                continue
            if existing_ids is not None and target not in existing_ids:
                dropped.append(f"{op} on unknown target {target!r}")
                continue
        elif target:
            target = None  # add never points at an existing memory
        kind = str(item.get("kind") or "fact").strip().lower()
        if kind not in WRITER_KINDS:
            kind = "fact"
        text = _clean(item.get("text"), _MAX_TEXT)
        if op != "forget" and not text:
            dropped.append(f"{op} without text")
            continue
        if op in ("update", "supersede") and target in texts and _same_text(text, texts[target]):
            dropped.append(f"{op} {target} repeats the current text (no change)")
            continue
        triples = [] if op == "forget" else _parse_triples(item.get("triples"))
        ops.append(MemoryOp(op=op, kind=kind, text=text, target=target, triples=triples))
        if len(ops) >= _MAX_OPS:
            break

    return WriterResult(ops=ops, summary=_clean(data.get("summary"), 400), dropped=dropped)
