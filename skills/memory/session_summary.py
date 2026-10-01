"""Structured running summary of one chat (T15 working memory).

The plain-paragraph summary blurred details a little more at every rewrite.
This one is a small structured state:

  goal       what the chat is about overall
  now        what is being worked on right now
  facts      things the user stated in this chat
  decisions  what was agreed or chosen
  open       unanswered questions and things still to do
  details    exact values — numbers, names, dates, paths, links, commands

Each checkpoint, the model gets the previous state plus the new messages and
returns the updated state. Items carry over in code, not just by asking: an
item the model leaves out survives unless it is listed in ``drop`` (wrong now /
resolved). So exact details can't quietly fade, and a stale one goes only when
the model says why.

Pure module — prompt, schema, parse, merge, render — so the summary eval
(``evals/summary_eval.py``) scores exactly what production runs.
"""

from __future__ import annotations

import json
import re
from typing import Any

LIST_FIELDS: dict[str, int] = {"facts": 10, "decisions": 8, "open": 8, "details": 12}
# Kept by code, not written by the model: earlier goals, so a topic switch
# doesn't erase what the chat was about before.
TOPICS_CAP = 5
# Most items a single update may drop from these fields. A model that "cleans
# up" after a topic switch can't wipe them; real corrections are rarely more.
DROP_CAP = {"facts": 3, "details": 3}
# Items that talk about credentials never belong in the notes, whatever the
# model writes (values are already scrubbed before the prompt; this catches the rest).
_SECRETISH = re.compile(
    r"(?i)\[REDACTED|\b(password|passcode|passphrase|pin code|api key|secret key|access token)\b"
)
TEXT_FIELDS = ("goal", "now")
_MAX_ITEM = 180
_MAX_TEXT = 240
_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")

PROMPT = (
    "You keep the working notes for one ongoing conversation between a user and their "
    "assistant. Update the PREVIOUS NOTES with the NEW MESSAGES and return JSON only.\n"
    "Fields:\n"
    "- goal: what this conversation is about overall (one short sentence).\n"
    "- now: what is being worked on at the end of the NEW MESSAGES (one short sentence).\n"
    "- facts: things the USER stated in this conversation (short, third person: \"The user ...\").\n"
    "- decisions: what the USER chose or agreed to. An assistant suggestion is not a "
    "decision unless the user accepted it.\n"
    "- open: questions still unanswered and things still to do. When one is answered or "
    "done, put it in drop and add the outcome to decisions.\n"
    "- details: exact values worth keeping word for word: numbers, names, dates, times, "
    "prices, file paths, URLs, commands, error messages, versions. Copy them exactly, and "
    "keep each with a short label so it makes sense alone (\"flight out May 12\", "
    "\"clap 4.5\", \"budget 900 euros\"), never a bare number. General words (a tool or "
    "topic name with no value) are not details.\n"
    "- drop: items from the PREVIOUS NOTES that are now wrong, replaced or resolved "
    "(copy the item text exactly). Anything not dropped is kept automatically. A change "
    "of topic is NOT a reason to drop: a conversation can cover several topics, and the "
    "earlier ones still matter.\n"
    "Rules:\n"
    "- Only what was actually said. Do not guess or add advice.\n"
    "- Never include passwords, PINs, API keys or other secrets.\n"
    "- Hypotheticals and jokes are not facts or decisions.\n"
    "- Keep items short. Do not repeat an item that is already in the PREVIOUS NOTES.\n"
)

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "now": {"type": "string"},
        **{f: {"type": "array", "items": {"type": "string"}} for f in LIST_FIELDS},
        "drop": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["goal", "now", *LIST_FIELDS, "drop"],
}


def empty() -> dict[str, Any]:
    return {"goal": "", "now": "", **{f: [] for f in LIST_FIELDS}, "topics": []}


def coerce(summary: Any) -> dict[str, Any]:
    """Any stored summary → the structured shape (a pre-structure string becomes the goal)."""
    out = empty()
    if isinstance(summary, str):
        out["goal"] = _clean(summary, _MAX_TEXT * 3)
        return out
    if not isinstance(summary, dict):
        return out
    for f in TEXT_FIELDS:
        out[f] = _clean(summary.get(f), _MAX_TEXT)
    for f, cap in LIST_FIELDS.items():
        out[f] = _clean_list(summary.get(f))[-cap:]
    out["topics"] = _clean_list(summary.get("topics"))[-TOPICS_CAP:]
    return out


def is_empty(summary: Any) -> bool:
    s = coerce(summary)
    return not any(s[f] for f in (*TEXT_FIELDS, *LIST_FIELDS, "topics"))


def _clean(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip().strip("-•* ").strip()[:limit]


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [c for c in (_clean(v, _MAX_ITEM) for v in value) if c and not _SECRETISH.search(c)]


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9.:/\\_-]{2,}", text.lower()))


def _same_item(a: str, b: str) -> bool:
    """Exact (normalized) match, or a near-restatement: one item's distinctive
    words are almost all in the other's. Exact values must match exactly —
    "port 8765" and "port 9000" are different details."""
    if _key(a) == _key(b):
        return True
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    nums_a, nums_b = set(re.findall(r"\d+", a)), set(re.findall(r"\d+", b))
    if nums_a != nums_b:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.8


def build_prompt(transcript: str, previous: Any = None) -> str:
    prev = coerce(previous)
    prev_text = render(prev) if not is_empty(prev) else "(none)"
    return PROMPT + "\nPREVIOUS NOTES:\n" + prev_text + "\n\n--- NEW MESSAGES ---\n" + transcript.strip()


def parse(raw: str) -> dict[str, Any] | None:
    """Model JSON → {fields..., drop: [...]}; None when no usable object."""
    match = _JSON_BLOCK.search(raw or "")
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    out = coerce(data)
    out.pop("topics", None)  # code-maintained; the model doesn't write it
    for f in TEXT_FIELDS:
        if _SECRETISH.search(out[f]):
            out[f] = ""
    out["drop"] = _clean_list(data.get("drop"))
    return out


def merge(previous: Any, update: dict[str, Any]) -> dict[str, Any]:
    """Apply a parsed update to the previous state.

    Lists: every previous item the model neither restated nor dropped (carry-over),
    then the model's items, deduplicated; the oldest go first when over the cap.
    A resolved ``open`` item leaves only via ``drop`` — omission isn't enough —
    and ``facts`` / ``details`` lose at most ``DROP_CAP`` items per update.
    Text fields: the update's value, or the previous one when it came back empty.
    When the goal changes, the old goal moves to ``topics``.
    """
    prev = coerce(previous)
    drops = update.get("drop") or []
    out = empty()
    for f in TEXT_FIELDS:
        out[f] = update.get(f) or prev[f]
    topics = list(prev["topics"])
    if prev["goal"] and out["goal"] and not _same_item(prev["goal"], out["goal"]):
        if not any(_same_item(prev["goal"], t) for t in topics):
            topics.append(prev["goal"])
    out["topics"] = topics[-TOPICS_CAP:]
    for f, cap in LIST_FIELDS.items():
        new_items: list[str] = []
        for item in update.get(f) or []:
            if not any(_same_item(item, x) for x in new_items):
                new_items.append(item)
        budget = DROP_CAP.get(f, len(prev[f]))
        kept: list[str] = []
        for p in prev[f]:
            if any(_same_item(p, n) for n in new_items):
                continue  # restated: the new wording replaces it
            if budget > 0 and any(_same_item(p, d) for d in drops):
                budget -= 1
                continue
            kept.append(p)
        out[f] = (kept + new_items)[-cap:]  # oldest first, so the cap trims the oldest
    return out


_LABELS = {
    "goal": "Goal",
    "now": "Right now",
    "facts": "Facts from the user",
    "decisions": "Decided",
    "open": "Still open",
    "details": "Exact details",
    "topics": "Earlier in this chat",
}


def render(summary: Any) -> str:
    """Compact text for the per-turn note (and for the next prompt)."""
    s = coerce(summary)
    lines: list[str] = []
    for f in TEXT_FIELDS:
        if s[f]:
            lines.append(f"{_LABELS[f]}: {s[f]}")
    for f in (*LIST_FIELDS, "topics"):
        if s[f]:
            lines.append(f"{_LABELS[f]}:")
            lines.extend(f"- {item}" for item in s[f])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Baseline kept for the eval: the step-3 plain-paragraph summary
# ---------------------------------------------------------------------------

PROSE_PROMPT = (
    "Update the running summary of a conversation between a user and their assistant. "
    "You get the PREVIOUS SUMMARY (may be empty) and the NEW MESSAGES that came after it. "
    "Write 2-4 sentences covering the whole conversation so far: topics, names, decisions, "
    "open questions, and anything the user asked to be done later. Third person "
    '("The user ..."). Plain text only: no lists, no headings. Never include passwords, '
    "PINs or keys.\n"
)


def build_prose_prompt(transcript: str, previous: str = "") -> str:
    return (
        PROSE_PROMPT
        + "\nPREVIOUS SUMMARY:\n"
        + (previous.strip() or "(none)")
        + "\n\n--- NEW MESSAGES ---\n"
        + transcript.strip()
    )


def clean_prose(raw: str) -> str:
    text = re.sub(r"^\s*(#+|[-*•]|\d+[.)])\s*", "", raw or "", flags=re.M)
    return re.sub(r"\s+", " ", text).strip()[:800]
