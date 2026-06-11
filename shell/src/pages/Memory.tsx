import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createMemoryEntry,
  deleteMemoryEntry,
  fetchLastSession,
  fetchMemoryEntries,
  memoryDecay,
  refreshLastSession,
  setMemoryKeep,
  updateMemoryEntry,
  type DecayResult,
  type LastSessionNote,
  type MemoryEntry,
  type MemoryKind,
} from "../api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { Star, Sparkles } from "lucide-react";

const KINDS: MemoryKind[] = ["instruction", "fact", "summary", "task"];
const KIND_LABELS: Record<MemoryKind, string> = {
  instruction: "Instructions",
  fact: "Facts",
  summary: "Summaries",
  task: "Tasks",
};

const KIND_COLOR: Record<MemoryKind, string> = {
  instruction: "text-[var(--accent-bright)] bg-[var(--accent-glow)] border-[var(--accent-bright)]/30",
  fact:        "text-[var(--safe)] bg-[var(--safe)]/10 border-[var(--safe)]/30",
  summary:     "text-[var(--scoped)] bg-[var(--scoped)]/10 border-[var(--scoped)]/30",
  task:        "text-[var(--text-muted)] bg-[var(--bg-panel)] border-[var(--border-light)]",
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
  const [decay, setDecay] = useState<DecayResult | null>(null);

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

  useEffect(() => { refresh(); }, [refresh]);

  const grouped = useMemo(() => {
    const map: Record<MemoryKind, MemoryEntry[]> = {
      fact: [], instruction: [], summary: [], task: [],
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
      setEntries(await createMemoryEntry(text, newKind));
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
      setEntries(await deleteMemoryEntry(id));
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
      setEntries(await updateMemoryEntry(editingId, editText, editKind));
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function togglePin(entry: MemoryEntry) {
    setBusy(true);
    try {
      setEntries(await setMemoryKeep(entry.id, !entry.keep));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function previewDecay() {
    setBusy(true);
    setError(null);
    try {
      setDecay(await memoryDecay(true));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runDecay() {
    setBusy(true);
    try {
      const res = await memoryDecay(false);
      setDecay(null);
      if (res.entries) setEntries(res.entries);
      else await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="memory-page">
      <header className="memory-head">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1>Memory</h1>
            <p className="muted">
              Long-term facts, instructions, summaries, and tasks. Auto-saved in the
              background from chat.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={previewDecay}
            className="shrink-0 gap-1.5"
            title="Preview which never-recalled, low-importance memories would be cleaned up"
          >
            <Sparkles size={14} /> Clean up
          </Button>
        </div>
      </header>

      {/* Decay preview / confirm */}
      {decay && (
        <div className="memory-card flex items-center justify-between gap-3 border-[var(--border-light)]">
          <p className="text-sm m-0">
            {!decay.enabled ? (
              <>Decay is off — set <code>memory.decay.enabled: true</code> in config to clean up automatically.</>
            ) : decay.ids.length === 0 ? (
              <>Nothing to clean up — every memory is pinned, important, or still in use.</>
            ) : (
              <>
                <strong>{decay.ids.length}</strong> {decay.ids.length === 1 ? "memory was" : "memories were"} never
                recalled and have low importance. Remove {decay.ids.length === 1 ? "it" : "them"}?
              </>
            )}
          </p>
          <span className="flex gap-1 shrink-0">
            {decay.enabled && decay.ids.length > 0 && (
              <Button type="button" variant="destructive" size="sm" disabled={busy} onClick={runDecay}>
                Remove {decay.ids.length}
              </Button>
            )}
            <Button type="button" variant="ghost" size="sm" onClick={() => setDecay(null)}>
              {decay.enabled && decay.ids.length > 0 ? "Cancel" : "Dismiss"}
            </Button>
          </span>
        </div>
      )}

      {error && <p className="memory-error">{error}</p>}
      {loading && <p className="muted">Loading…</p>}

      {/* Last session card */}
      <section className="memory-card last-session-card">
        <div className="memory-card-head">
          <h2>Last session</h2>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setLastSession(await refreshLastSession());
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Refresh
          </Button>
        </div>
        <p className="last-session-body">
          {lastSession?.text?.trim() || "No last-session note yet."}
        </p>
      </section>

      {/* Add entry */}
      <section className="memory-add">
        <h2>Add</h2>
        <div className="memory-add-row flex gap-2 items-center">
          <select
            value={newKind}
            onChange={(e) => setNewKind(e.target.value as MemoryKind)}
            aria-label="Kind"
            className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--bg-panel)] text-[var(--text)] text-sm px-2 py-1 outline-none focus:ring-1 focus:ring-[var(--ring)]"
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>{KIND_LABELS[k]}</option>
            ))}
          </select>
          <Input
            type="text"
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            placeholder="What should Celestia remember?"
            onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); }}
            className="flex-1 bg-[var(--bg-panel)] border-[var(--border)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus-visible:ring-[var(--ring)]"
          />
          <Button
            type="button"
            variant="default"
            size="sm"
            disabled={busy || !newText.trim()}
            onClick={handleAdd}
            className="shrink-0"
          >
            Add
          </Button>
        </div>
      </section>

      {/* Memory groups */}
      <ScrollArea className="flex-1">
        {KINDS.map((kind) => (
          <section key={kind} className="memory-group">
            <div className="flex items-center gap-2 mb-2">
              <h2 className="m-0">{KIND_LABELS[kind]}</h2>
              {grouped[kind].length > 0 && (
                <Badge className={cn("text-[0.68rem]", KIND_COLOR[kind])}>
                  {grouped[kind].length}
                </Badge>
              )}
            </div>
            <Separator className="bg-[var(--border-light)] mb-3" />
            {grouped[kind].length === 0 ? (
              <p className="muted text-sm">None yet.</p>
            ) : (
              <ul className="memory-list">
                {grouped[kind].map((entry) => (
                  <li key={entry.id} className="memory-item">
                    {editingId === entry.id ? (
                      <div className="memory-edit-row flex gap-2 items-center w-full">
                        <select
                          value={editKind}
                          onChange={(e) => setEditKind(e.target.value as MemoryKind)}
                          className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--bg-panel)] text-[var(--text)] text-sm px-2 py-1 outline-none"
                        >
                          {KINDS.map((k) => (
                            <option key={k} value={k}>{KIND_LABELS[k]}</option>
                          ))}
                        </select>
                        <Input
                          type="text"
                          value={editText}
                          onChange={(e) => setEditText(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") setEditingId(null); }}
                          className="flex-1 bg-[var(--bg-panel)] border-[var(--border)] text-[var(--text)] focus-visible:ring-[var(--ring)]"
                          autoFocus
                        />
                        <Button type="button" variant="default" size="sm" disabled={busy} onClick={saveEdit}>
                          Save
                        </Button>
                        <Button type="button" variant="ghost" size="sm" onClick={() => setEditingId(null)}>
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 w-full">
                        <div className="flex-1 min-w-0">
                          <span className="memory-text">{entry.text}</span>
                          <span className="memory-meta block text-[0.66rem] text-[var(--text-dim)] mt-0.5">
                            importance {(entry.importance ?? 0).toFixed(2)}
                            {entry.recall_count ? ` · recalled ${entry.recall_count}×` : ""}
                            {entry.keep ? " · kept" : ""}
                          </span>
                        </div>
                        <span className="memory-actions flex gap-1 shrink-0 items-center">
                          <Button
                            type="button"
                            variant="ghost"
                            size="xs"
                            disabled={busy}
                            onClick={() => togglePin(entry)}
                            aria-pressed={!!entry.keep}
                            title={entry.keep ? "Pinned — never auto-deleted (click to unpin)" : "Keep — never auto-delete"}
                          >
                            <Star
                              size={13}
                              className={cn(entry.keep && "text-[var(--accent-bright)]")}
                              fill={entry.keep ? "currentColor" : "none"}
                            />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="xs"
                            onClick={() => startEdit(entry)}
                          >
                            Edit
                          </Button>
                          <Button
                            type="button"
                            variant="destructive"
                            size="xs"
                            disabled={busy}
                            onClick={() => handleDelete(entry.id)}
                          >
                            Delete
                          </Button>
                        </span>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </ScrollArea>
    </div>
  );
}
