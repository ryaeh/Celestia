"""Graph entity resolution (Feature 10 refinement — an idle "tidy" job).

Name-based node matching fragments entities: "VS Code", "vscode", and
"Visual Studio Code" become three nodes and the graph-walk misses their
connections. This pass repairs that offline:

1. **Embedding pre-filter** — embed every canonical name (nomic-embed-text),
   pair up names above a cosine threshold. Cheap, no LLM.
2. **LLM confirm** — a judge model answers "same entity?" per candidate pair,
   with each node's type and sample relations as context. Conservative: any
   parse failure means "no".
3. **Merge + alias cache** — ``graph_store.merge_nodes`` folds the duplicate
   into the keeper (higher degree wins, then age); every old spelling stays in
   the alias table, so repeat mentions never need the LLM again.

Runs only from the GPU-idle tidy pass (or its manual trigger) — never on the
chat hot path. Caps per run keep a single pass short and interruptible.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from celestia_core.config import get
from skills.memory import graph_store as gs

_JSON_BLOCK = re.compile(r"\{[\s\S]*?\}")

# Hard cap on LLM confirmations per run, independent of the merge cap — keeps a
# pathological candidate list (bad threshold, huge graph) from pinning the GPU.
_MAX_CONFIRMS = 40

_CONFIRM_PROMPT = """Do these two names refer to the SAME single real-world entity?

A: {a}
B: {b}

Consider spelling variants, abbreviations, casing, and nicknames.
Different versions, different people, or distinct products are NOT the same.
Answer JSON only: {{"same": true}} or {{"same": false}}"""


def _describe(node: dict[str, Any]) -> str:
    """One-line context card for the confirm prompt: name (type) — relations."""
    parts = [f'"{node["canonical_name"]}"']
    if node.get("type"):
        parts.append(f"(type: {node['type']})")
    rels = [gs.relation_text(e) for e in gs.neighbors(node["id"])[:3]]
    if rels:
        parts.append("— known relations: " + "; ".join(rels))
    return " ".join(parts)


def _embed_names(names: list[str], model: str) -> list[list[float]] | None:
    """Batch-embed names via Ollama; None on any failure (pass is skipped)."""
    try:
        import ollama

        resp = ollama.embed(model=model, input=names)
        embs = resp.get("embeddings") if isinstance(resp, dict) else getattr(resp, "embeddings", None)
        if not embs or len(embs) != len(names):
            return None
        return [list(map(float, e)) for e in embs]
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _squash(name: str) -> str:
    """Spacing/casing/punctuation-blind form: 'VS Code' → 'vscode'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def candidate_pairs(
    nodes: list[dict[str, Any]],
    embeddings: list[list[float]],
    threshold: float,
) -> list[tuple[int, int, float, bool]]:
    """(i, j, similarity, lexical) pairs that look like duplicates, strongest first.

    Two signals:

    - **Lexical** — squashed-name equality ('VS Code' == 'vscode',
      'qwen 2.5 7b' == 'qwen2.5:7b'). Decisive: these merge *without* the LLM
      judge, because a 7B judge demonstrably rejects such pairs as "distinct
      products", and nomic-embed-text scores them as low as ~0.65. Guarded to
      ≥3 chars and not-all-digits so '1.5'/'15' style collisions stay out.
    - **Embedding** — cosine above ``threshold``; these still need the judge.

    Pairs with two *different* explicit types are skipped (a person can't be a
    tool); an empty type matches anything.
    """
    squashed = [_squash(n["canonical_name"]) for n in nodes]
    out: list[tuple[int, int, float, bool]] = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            ti, tj = nodes[i].get("type"), nodes[j].get("type")
            if ti and tj and ti != tj:
                continue
            sq = squashed[i]
            if sq and sq == squashed[j] and len(sq) >= 3 and not sq.isdigit():
                out.append((i, j, 1.0, True))
                continue
            sim = _cosine(embeddings[i], embeddings[j])
            if sim >= threshold:
                out.append((i, j, sim, False))
    out.sort(key=lambda t: -t[2])
    return out


def _confirm_same_entity(a: dict[str, Any], b: dict[str, Any], model: str) -> bool:
    """LLM judge for one candidate pair. Any failure → False (never merge on doubt)."""
    try:
        import ollama

        resp = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": _CONFIRM_PROMPT.format(a=_describe(a), b=_describe(b)),
                }
            ],
            options={"num_predict": 64, "temperature": 0.0},
        )
        msg = resp.get("message") if isinstance(resp, dict) else getattr(resp, "message", None)
        raw = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")) or ""
        match = _JSON_BLOCK.search(str(raw))
        if not match:
            return False
        return json.loads(match.group()).get("same") is True
    except Exception:
        return False


def _pick_keeper(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(keep, dup): more-connected node wins, then the older one."""
    ka = (a.get("degree", 0), -a.get("created_at", 0.0))
    kb = (b.get("degree", 0), -b.get("created_at", 0.0))
    return (a, b) if ka >= kb else (b, a)


def resolve_entities(
    *,
    model: str | None = None,
    embed_model: str | None = None,
    threshold: float | None = None,
    max_merges: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """One entity-resolution pass over the whole graph. Returns a report dict.

    The caller (tidy pass) is responsible for scheduling and for holding the
    GPU task slot; this function just does the work.
    """
    judge = model or str(get("memory.tidy.model", "qwen2.5:7b"))
    embedder = embed_model or str(get("llm.embed_model", "nomic-embed-text"))
    # Default 0.60: on nomic-embed-text, real duplicate spellings score
    # 0.65–0.90 while unrelated names sit ≤0.50 — the LLM judge supplies the
    # precision, so the pre-filter errs toward recall.
    thresh = float(threshold if threshold is not None else get("memory.tidy.entity_similarity", 0.60))
    cap = int(max_merges if max_merges is not None else get("memory.tidy.max_merges_per_run", 10))

    nodes = gs.all_nodes()
    report: dict[str, Any] = {
        "nodes": len(nodes),
        "candidates": 0,
        "merges": [],
        "dry_run": dry_run,
    }
    if len(nodes) < 2:
        return report

    embeddings = _embed_names([n["canonical_name"] for n in nodes], embedder)
    if embeddings is None:
        report["skipped"] = f"embedding failed ({embedder})"
        return report

    pairs = candidate_pairs(nodes, embeddings, thresh)
    report["candidates"] = len(pairs)

    gone: set[str] = set()  # node ids merged away earlier in this run
    confirms = 0
    for i, j, sim, lexical in pairs:
        if len(report["merges"]) >= cap or confirms >= _MAX_CONFIRMS:
            break
        a, b = nodes[i], nodes[j]
        if a["id"] in gone or b["id"] in gone:
            continue
        if not lexical:  # lexical identity is decisive; only embeddings need the judge
            confirms += 1
            if not _confirm_same_entity(a, b, judge):
                continue
        keep, dup = _pick_keeper(a, b)
        if not dry_run:
            if not gs.merge_nodes(keep["id"], dup["id"]):
                continue
        gone.add(dup["id"])
        report["merges"].append(
            {
                "kept": keep["canonical_name"],
                "merged": dup["canonical_name"],
                "similarity": round(sim, 3),
            }
        )
    return report
