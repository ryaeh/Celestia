"""Relation extraction → temporal knowledge graph (Feature 10, A2).

The deep-background half of graph ingestion. Runs during session consolidation
(off the chat hot-path): one LLM pass over the session excerpt emits
(subject, predicate, object) triples, which are written to ``graph_store`` —
single-valued relations supersede, multi-valued ones accumulate.

Entity resolution here is the cheap normalized-name + alias path provided by
``graph_store``; full embedding-pre-filtered LLM canonicalization is a later
refinement (the alias cache means repeat mentions never hit the LLM anyway).
"""

from __future__ import annotations

import json
import re
from typing import Any

import ollama

from celestia_core.config import get
from skills.memory import graph_store as gs
from skills.memory.activity_feed import append_event

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")

# Guardrails on what counts as a usable triple.
_MAX_RELATIONS = 12
_MAX_TERM_LEN = 80

_PROMPT = (
    "Extract the factual relationships stated in this chat excerpt as a knowledge "
    "graph. Return JSON only.\n"
    "Each relation: subject, predicate (a short verb phrase), object.\n"
    'Mark "single_valued": true when the subject can have only ONE such object at '
    "a time (e.g. runs, located_in, main_project), false for many (e.g. uses, knows, likes).\n"
    "Optionally add subject_type / object_type (person, project, tool, file, concept).\n"
    "Rules:\n"
    "- Only relationships the USER actually stated. No guesses, no assistant opinions.\n"
    "- Skip greetings and meta-talk. 0 relations is valid.\n"
    "- Keep subject/object short (a name or noun phrase), not whole sentences.\n"
    'Format: {"relations":[{"subject":"...","predicate":"...","object":"...",'
    '"single_valued":false,"subject_type":null,"object_type":null}]}\n\n'
    "--- Excerpt ---\n"
)


def _clean_term(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _parse_relations(raw: str) -> list[dict[str, Any]]:
    """Parse the LLM JSON into validated relation dicts. Tolerant of junk."""
    match = _JSON_BLOCK.search(raw or "")
    if not match:
        return []
    try:
        data = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return []

    items = data.get("relations") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        subject = _clean_term(item.get("subject"))
        predicate = _clean_term(item.get("predicate"))
        obj = _clean_term(item.get("object"))
        if not subject or not predicate or not obj:
            continue
        if subject.lower() == obj.lower():
            continue
        if max(len(subject), len(obj), len(predicate)) > _MAX_TERM_LEN:
            continue
        out.append(
            {
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "single_valued": bool(item.get("single_valued", False)),
                "subject_type": _clean_term(item.get("subject_type")) or None,
                "object_type": _clean_term(item.get("object_type")) or None,
            }
        )
        if len(out) >= _MAX_RELATIONS:
            break
    return out


def store_relations(
    relations: list[dict[str, Any]], *, source: str = "chat", confidence: float | None = 0.7
) -> int:
    """Write parsed relations to the graph. Returns the number stored."""
    stored = 0
    for r in relations:
        try:
            writer = gs.set_relation if r["single_valued"] else gs.add_relation
            writer(
                r["subject"],
                r["predicate"],
                r["object"],
                source=source,
                confidence=confidence,
                subject_type=r["subject_type"],
                object_type=r["object_type"],
            )
            stored += 1
        except Exception:
            continue
    return stored


def extract_and_store(
    excerpt: str,
    *,
    user_id: str = "default",
    source: str = "chat",
    model: str | None = None,
) -> list[str]:
    """Run one extraction pass over ``excerpt`` and write relations to the graph.

    Returns short summary lines for the verbose consolidation log. Never raises —
    extraction failures are reported as lines, not exceptions.
    """
    excerpt = (excerpt or "").strip()
    if len(excerpt) < 30:
        return []

    # Defensive scrub: keep secrets out of the extractor prompt and the graph even
    # when called outside the consolidation path (which already scrubs upstream).
    from skills.memory.scrub import scrub_for_storage

    excerpt = scrub_for_storage(excerpt)

    use_model = (
        model
        or get("memory.graph.extraction_model")
        or get("memory.session_consolidate_model")
        or get("llm.chat_model", "llama3.2:3b")
    )

    # Background pass: never contend with a foreground GPU op (vision / STT).
    from celestia_core.gpu import gpu_task

    with gpu_task("graph-extract", blocking=False) as got:
        if not got:
            return ["graph extract deferred: gpu busy"]
        return _extract_with_model(excerpt, use_model, source)


def _extract_with_model(excerpt: str, use_model: str, source: str) -> list[str]:
    try:
        resp = ollama.chat(
            model=use_model,
            messages=[{"role": "user", "content": _PROMPT + excerpt}],
            options={"num_predict": 512, "temperature": 0.0},
        )
        raw = (resp.get("message") or {}).get("content") or ""
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump().get("content", "") or str(raw)
    except Exception as e:
        return [f"graph extract skipped: {e}"]

    relations = _parse_relations(str(raw))
    if not relations:
        return []

    stored = store_relations(relations, source=source)
    if stored:
        append_event(action="graph", text=f"+{stored} relation(s) to knowledge graph", kind="fact", source="graph")
    return [f"[graph] {r['subject']} {r['predicate']} {r['object']}" for r in relations[:stored]]
