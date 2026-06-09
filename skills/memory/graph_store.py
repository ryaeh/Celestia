"""Temporal knowledge-graph store (Feature 10 — substrate).

A time-aware entity graph kept in a local SQLite database. Nodes are entities
(people, projects, tools, files, concepts); edges are typed relations that each
carry ``valid_from`` / ``valid_until``. Conflicts are resolved by **versioned
supersede**: a contradicting relation ends the old edge (sets ``valid_until``)
and starts a new current one — the old edge is *retained as history*, never
deleted. "Forgetting" is a ranking outcome elsewhere, never a destructive op
here.

Storage is plain stdlib ``sqlite3`` (no heavy deps, durable, on-device). Vector
similarity stays in the existing mem0/Chroma store; this module is the
structural half that answers connection/time questions similarity misses.

Design notes
------------
- ``set_relation``  — single-valued ("runs", "main_project"): a new object ends
  any other current object for that (subject, predicate).
- ``add_relation``  — multi-valued ("uses", "knows"): additive; only re-asserts
  an identical current edge instead of duplicating it.
- Nothing is ever deleted by the normal API. ``end_relation`` closes an edge by
  stamping ``valid_until``; the row stays for time-travel queries.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get

# A single cached connection (SQLite handles concurrency via WAL; we serialise
# writes with a lock). Reset when the active graph changes or in tests.
_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()
_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------


def _db_path() -> Path:
    name = str(get("memory.graph.active_graph", "default") or "default")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name) or "default"
    d = Path(ROOT) / "data" / "memory" / "graph"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe}.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id             TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    type           TEXT,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS aliases (
    node_id TEXT NOT NULL,
    alias   TEXT NOT NULL,
    PRIMARY KEY (node_id, alias),
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);
CREATE TABLE IF NOT EXISTS edges (
    id          TEXT PRIMARY KEY,
    subject_id  TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object_id   TEXT NOT NULL,
    valid_from  REAL NOT NULL,
    valid_until REAL,
    source      TEXT,
    confidence  REAL,
    created_at  REAL NOT NULL,
    FOREIGN KEY (subject_id) REFERENCES nodes(id),
    FOREIGN KEY (object_id)  REFERENCES nodes(id)
);
CREATE INDEX IF NOT EXISTS idx_edges_subject ON edges(subject_id, predicate);
CREATE INDEX IF NOT EXISTS idx_edges_object  ON edges(object_id, predicate);
CREATE INDEX IF NOT EXISTS idx_edges_current ON edges(valid_until);
"""


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.executescript(_SCHEMA)
                conn.commit()
                _conn = conn
    return _conn


def reset_connection() -> None:
    """Close the cached connection (call when switching graphs or in tests)."""
    global _conn
    with _conn_lock:
        if _conn is not None:
            try:
                _conn.close()
            except sqlite3.Error:
                pass
            _conn = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    """Normalise a name/predicate for matching: lowercased, collapsed spaces."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _norm_predicate(text: str) -> str:
    return re.sub(r"\s+", "_", _norm(text))


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def resolve_node(name: str) -> str | None:
    """Return the node id whose canonical name or any alias matches ``name``."""
    key = _norm(name)
    if not key:
        return None
    conn = _get_conn()
    row = conn.execute("SELECT node_id FROM aliases WHERE alias = ?", (key,)).fetchone()
    return row["node_id"] if row else None


def upsert_node(name: str, node_type: str | None = None) -> str:
    """Find the node for ``name`` (by alias) or create one. Returns its id.

    A later, more specific ``node_type`` fills an empty type; the original
    casing of ``name`` is kept as the canonical display name on creation.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("node name required")
    with _write_lock:
        conn = _get_conn()
        existing = resolve_node(name)
        now = _now()
        if existing:
            if node_type:
                cur = conn.execute("SELECT type FROM nodes WHERE id = ?", (existing,)).fetchone()
                if cur is not None and not cur["type"]:
                    conn.execute(
                        "UPDATE nodes SET type = ?, updated_at = ? WHERE id = ?",
                        (node_type, now, existing),
                    )
                    conn.commit()
            return existing
        node_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO nodes (id, canonical_name, type, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (node_id, name, node_type, now, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO aliases (node_id, alias) VALUES (?, ?)",
            (node_id, _norm(name)),
        )
        conn.commit()
        return node_id


def add_alias(node_id: str, alias: str) -> None:
    """Register an alternate name for an existing node (alias-cache for resolution)."""
    key = _norm(alias)
    if not key:
        return
    with _write_lock:
        conn = _get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO aliases (node_id, alias) VALUES (?, ?)", (node_id, key)
        )
        conn.commit()


def get_node(node_id: str) -> dict[str, Any] | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if not row:
        return None
    aliases = [
        r["alias"]
        for r in conn.execute("SELECT alias FROM aliases WHERE node_id = ?", (node_id,))
    ]
    d = dict(row)
    d["aliases"] = aliases
    return d


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def _current_edge(conn, subject_id: str, predicate: str, object_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM edges WHERE subject_id = ? AND predicate = ? AND object_id = ? "
        "AND valid_until IS NULL",
        (subject_id, predicate, object_id),
    ).fetchone()


def _insert_edge(
    conn,
    subject_id: str,
    predicate: str,
    object_id: str,
    *,
    valid_from: float,
    source: str | None,
    confidence: float | None,
) -> str:
    edge_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO edges (id, subject_id, predicate, object_id, valid_from, valid_until, "
        "source, confidence, created_at) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)",
        (edge_id, subject_id, predicate, object_id, valid_from, source, confidence, _now()),
    )
    return edge_id


def add_relation(
    subject: str,
    predicate: str,
    obj: str,
    *,
    source: str | None = None,
    confidence: float | None = None,
    valid_from: float | None = None,
    subject_type: str | None = None,
    object_type: str | None = None,
) -> str:
    """Add a multi-valued relation (additive). Re-asserting an identical current
    edge is idempotent (refreshes source/confidence) rather than duplicating.

    Returns the edge id.
    """
    pred = _norm_predicate(predicate)
    if not pred:
        raise ValueError("predicate required")
    sid = upsert_node(subject, subject_type)
    oid = upsert_node(obj, object_type)
    vf = valid_from if valid_from is not None else _now()
    with _write_lock:
        conn = _get_conn()
        existing = _current_edge(conn, sid, pred, oid)
        if existing is not None:
            conn.execute(
                "UPDATE edges SET source = ?, confidence = ? WHERE id = ?",
                (source, confidence, existing["id"]),
            )
            conn.commit()
            return existing["id"]
        edge_id = _insert_edge(
            conn, sid, pred, oid, valid_from=vf, source=source, confidence=confidence
        )
        conn.commit()
        return edge_id


def set_relation(
    subject: str,
    predicate: str,
    obj: str,
    *,
    source: str | None = None,
    confidence: float | None = None,
    valid_from: float | None = None,
    subject_type: str | None = None,
    object_type: str | None = None,
) -> str:
    """Set a single-valued relation with **versioned supersede**.

    Any *other* current object for this (subject, predicate) is ended (its
    ``valid_until`` stamped) and retained as history; the new object becomes the
    current edge. Re-asserting the same object is idempotent.

    Returns the (current) edge id.
    """
    pred = _norm_predicate(predicate)
    if not pred:
        raise ValueError("predicate required")
    sid = upsert_node(subject, subject_type)
    oid = upsert_node(obj, object_type)
    vf = valid_from if valid_from is not None else _now()
    with _write_lock:
        conn = _get_conn()
        same = _current_edge(conn, sid, pred, oid)
        if same is not None:
            conn.execute(
                "UPDATE edges SET source = ?, confidence = ? WHERE id = ?",
                (source, confidence, same["id"]),
            )
            conn.commit()
            return same["id"]
        # End every other current edge for this (subject, predicate).
        conn.execute(
            "UPDATE edges SET valid_until = ? WHERE subject_id = ? AND predicate = ? "
            "AND valid_until IS NULL",
            (vf, sid, pred),
        )
        edge_id = _insert_edge(
            conn, sid, pred, oid, valid_from=vf, source=source, confidence=confidence
        )
        conn.commit()
        return edge_id


def end_relation(subject: str, predicate: str, obj: str, *, at: float | None = None) -> bool:
    """Close a current relation by stamping ``valid_until``. Row is retained.

    Returns True if a current edge was found and ended.
    """
    sid = resolve_node(subject)
    oid = resolve_node(obj)
    if not sid or not oid:
        return False
    pred = _norm_predicate(predicate)
    ts = at if at is not None else _now()
    with _write_lock:
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE edges SET valid_until = ? WHERE subject_id = ? AND predicate = ? "
            "AND object_id = ? AND valid_until IS NULL",
            (ts, sid, pred, oid),
        )
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def _edge_dict(conn, row: sqlite3.Row) -> dict[str, Any]:
    subj = conn.execute("SELECT canonical_name FROM nodes WHERE id = ?", (row["subject_id"],)).fetchone()
    obj = conn.execute("SELECT canonical_name FROM nodes WHERE id = ?", (row["object_id"],)).fetchone()
    return {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "subject": subj["canonical_name"] if subj else None,
        "predicate": row["predicate"],
        "object_id": row["object_id"],
        "object": obj["canonical_name"] if obj else None,
        "valid_from": row["valid_from"],
        "valid_until": row["valid_until"],
        "source": row["source"],
        "confidence": row["confidence"],
    }


def _is_valid_at(row: sqlite3.Row, at: float | None) -> bool:
    if at is None:
        return row["valid_until"] is None
    return row["valid_from"] <= at and (row["valid_until"] is None or at < row["valid_until"])


def neighbors(node_id: str, *, at: float | None = None) -> list[dict[str, Any]]:
    """Edges touching ``node_id`` that are valid at ``at`` (None = current)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM edges WHERE subject_id = ? OR object_id = ?", (node_id, node_id)
    ).fetchall()
    return [_edge_dict(conn, r) for r in rows if _is_valid_at(r, at)]


def history(subject: str, predicate: str) -> list[dict[str, Any]]:
    """Every edge (current + ended) for a (subject, predicate), newest first."""
    sid = resolve_node(subject)
    if not sid:
        return []
    pred = _norm_predicate(predicate)
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM edges WHERE subject_id = ? AND predicate = ? ORDER BY valid_from DESC",
        (sid, pred),
    ).fetchall()
    return [_edge_dict(conn, r) for r in rows]


def walk(names: list[str] | str, hops: int = 2, *, at: float | None = None) -> list[dict[str, Any]]:
    """Breadth-first traverse up to ``hops`` from the named entities.

    Returns the edges reached (valid at ``at``; None = current), de-duplicated
    and in discovery order — the structural context a similarity search misses.
    """
    if isinstance(names, str):
        names = [names]
    frontier: list[str] = []
    for n in names:
        nid = resolve_node(n)
        if nid:
            frontier.append(nid)

    seen_nodes: set[str] = set(frontier)
    seen_edges: set[str] = set()
    out: list[dict[str, Any]] = []

    for _ in range(max(0, hops)):
        next_frontier: list[str] = []
        for nid in frontier:
            for edge in neighbors(nid, at=at):
                if edge["id"] not in seen_edges:
                    seen_edges.add(edge["id"])
                    out.append(edge)
                other = edge["object_id"] if edge["subject_id"] == nid else edge["subject_id"]
                if other not in seen_nodes:
                    seen_nodes.add(other)
                    next_frontier.append(other)
        if not next_frontier:
            break
        frontier = next_frontier
    return out


def relation_text(edge: dict[str, Any]) -> str:
    """Human-readable 'subject predicate object' line for a walked edge."""
    pred = edge["predicate"].replace("_", " ")
    line = f"{edge['subject']} {pred} {edge['object']}"
    if edge["valid_until"] is not None:
        line += " (past)"
    return line


def recall(names: list[str] | str, hops: int = 2, *, at: float | None = None) -> list[str]:
    """Graph-walk recall as plain text lines, for injection into the turn context."""
    return [relation_text(e) for e in walk(names, hops, at=at)]


def stats() -> dict[str, int]:
    """Counts for the inspect UI / diagnostics."""
    conn = _get_conn()
    nodes = conn.execute("SELECT COUNT(*) AS c FROM nodes").fetchone()["c"]
    edges = conn.execute("SELECT COUNT(*) AS c FROM edges").fetchone()["c"]
    current = conn.execute(
        "SELECT COUNT(*) AS c FROM edges WHERE valid_until IS NULL"
    ).fetchone()["c"]
    return {"nodes": nodes, "edges": edges, "current_edges": current}
