import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createMemoryEntry,
  deleteMemoryEntry,
  fetchLastSession,
  fetchMemoryEntries,
  refreshLastSession,
  updateMemoryEntry,
  type LastSessionNote,
  type MemoryEntry,
  type MemoryKind,
} from "../api";

const KINDS: MemoryKind[] = ["instruction", "fact", "summary", "task"];
const KIND_LABELS: Record<MemoryKind, string> = {
  instruction: "Instructions",
  fact: "Facts",
  summary: "Summaries",
  task: "Tasks",
};

export default function Memory() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [lastSession, setLastSession] = useState<LastSessionNote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newText, setNewText] = useState("");
  const [newKind, setNewKind] = useState<MemoryKind>("fact");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [editKind, setEditKind] = useState<MemoryKind>("fact");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mem, note] = await Promise.all([
        fetchMemoryEntries(),
        fetchLastSession(),
      ]);
      setEntries(mem);
      setLastSession(note);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const grouped = useMemo(() => {
    const map: Record<MemoryKind, MemoryEntry[]> = {
      fact: [],
      instruction: [],
      summary: [],
      task: [],
    };
    for (const e of entries) {
      const k = KINDS.includes(e.kind as MemoryKind) ? (e.kind as MemoryKind) : "fact";
      map[k].push(e);
    }
    return map;
  }, [entries]);

  async function handleAdd() {
    const text = newText.trim();
    if (!text) return;
    setBusy(true);
    try {
      const updated = await createMemoryEntry(text, newKind);
      setEntries(updated);
      setNewText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id: string) {
    setBusy(true);
    try {
      const updated = await deleteMemoryEntry(id);
      setEntries(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(entry: MemoryEntry) {
    setEditingId(entry.id);
    setEditText(entry.text);
    setEditKind(entry.kind as MemoryKind);
  }

  async function saveEdit() {
    if (!editingId) return;
    setBusy(true);
    try {
      const updated = await updateMemoryEntry(editingId, editText, editKind);
      setEntries(updated);
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="memory-page">
      <header className="memory-head">
        <h1>Memory</h1>
        <p className="muted">
          Long-term facts, instructions, summaries, and tasks. Auto-saved in the
          background from chat.
        </p>
      </header>

      {error ? <p className="memory-error">{error}</p> : null}
      {loading ? <p className="muted">Loading…</p> : null}

      <section className="memory-card last-session-card">
        <div className="memory-card-head">
          <h2>Last session</h2>
          <button
            type="button"
            className="btn-ghost"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const note = await refreshLastSession();
                setLastSession(note);
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Refresh
          </button>
        </div>
        <p className="last-session-body">
          {lastSession?.text?.trim() || "No last-session note yet."}
        </p>
      </section>

      <section className="memory-add">
        <h2>Add</h2>
        <div className="memory-add-row">
          <select
            value={newKind}
            onChange={(e) => setNewKind(e.target.value as MemoryKind)}
            aria-label="Kind"
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            placeholder="What should Celestia remember?"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAdd();
            }}
          />
          <button type="button" className="btn-primary" disabled={busy} onClick={handleAdd}>
            Add
          </button>
        </div>
      </section>

      {KINDS.map((kind) => (
        <section key={kind} className="memory-group">
          <h2>{KIND_LABELS[kind]}</h2>
          {grouped[kind].length === 0 ? (
            <p className="muted">None yet.</p>
          ) : (
            <ul className="memory-list">
              {grouped[kind].map((entry) => (
                <li key={entry.id} className="memory-item">
                  {editingId === entry.id ? (
                    <div className="memory-edit-row">
                      <select
                        value={editKind}
                        onChange={(e) => setEditKind(e.target.value as MemoryKind)}
                      >
                        {KINDS.map((k) => (
                          <option key={k} value={k}>
                            {KIND_LABELS[k]}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                      />
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={busy}
                        onClick={saveEdit}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => setEditingId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <span className="memory-text">{entry.text}</span>
                      <span className="memory-actions">
                        <button type="button" className="btn-ghost" onClick={() => startEdit(entry)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn-ghost danger"
                          disabled={busy}
                          onClick={() => handleDelete(entry.id)}
                        >
                          Delete
                        </button>
                      </span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
