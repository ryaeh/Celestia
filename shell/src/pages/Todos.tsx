import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createTodo,
  deleteTodo,
  fetchTodos,
  updateTodo,
  type Todo,
  type TodoPriority,
} from "../api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { Check, Trash2, Plus } from "lucide-react";

const PRIORITIES: TodoPriority[] = ["low", "normal", "high"];

const PRIORITY_COLOR: Record<TodoPriority, string> = {
  high: "text-[var(--armed)] bg-[var(--armed)]/10 border-[var(--armed)]/30",
  normal: "text-[var(--text-muted)] bg-[var(--bg-panel)] border-[var(--border-light)]",
  low: "text-[var(--scoped)] bg-[var(--scoped)]/10 border-[var(--scoped)]/30",
};

export default function Todos() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [newText, setNewText] = useState("");
  const [newPriority, setNewPriority] = useState<TodoPriority>("normal");
  const [newDue, setNewDue] = useState("");
  const [showDone, setShowDone] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTodos(await fetchTodos());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const { open, done } = useMemo(() => {
    const o: Todo[] = [];
    const d: Todo[] = [];
    for (const t of todos) (t.done ? d : o).push(t);
    return { open: o, done: d };
  }, [todos]);

  async function run(action: () => Promise<Todo[]>) {
    setBusy(true);
    setError(null);
    try {
      setTodos(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleAdd() {
    const text = newText.trim();
    if (!text) return;
    await run(() => createTodo(text, newPriority, newDue.trim() || null));
    setNewText("");
    setNewDue("");
    setNewPriority("normal");
  }

  function renderItem(t: Todo) {
    return (
      <li key={t.id} className="todo-row group flex items-center gap-3 py-2">
        <button
          type="button"
          title={t.done ? "Mark not done" : "Mark done"}
          aria-label={t.done ? "Mark not done" : "Mark done"}
          disabled={busy}
          className={cn(
            "grid h-5 w-5 shrink-0 place-items-center rounded border transition-colors",
            t.done
              ? "border-[var(--safe)] bg-[var(--safe)]/20 text-[var(--safe)]"
              : "border-[var(--border-light)] text-transparent hover:border-[var(--accent-bright)]",
          )}
          onClick={() => run(() => updateTodo(t.id, { done: !t.done }))}
        >
          <Check size={13} />
        </button>

        <div className="min-w-0 flex-1">
          <span
            className={cn(
              "block truncate",
              t.done && "text-[var(--text-muted)] line-through",
            )}
          >
            {t.text}
          </span>
          {(t.due || t.notes) && (
            <span className="text-xs text-[var(--text-muted)]">
              {t.due ? `due ${t.due}` : ""}
              {t.due && t.notes ? " · " : ""}
              {t.notes}
            </span>
          )}
        </div>

        {t.priority !== "normal" && (
          <Badge variant="outline" className={cn("shrink-0", PRIORITY_COLOR[t.priority])}>
            {t.priority}
          </Badge>
        )}

        <button
          type="button"
          title="Delete"
          aria-label={`Delete: ${t.text}`}
          disabled={busy}
          className="grid h-7 w-7 shrink-0 place-items-center rounded text-[var(--text-muted)] opacity-0 transition-opacity hover:bg-[var(--bg-input)] hover:text-[var(--armed)] focus:opacity-100 group-hover:opacity-100"
          onClick={() => run(() => deleteTodo(t.id))}
        >
          <Trash2 size={14} />
        </button>
      </li>
    );
  }

  return (
    <div className="page todos-page flex h-full flex-col">
      <header className="mb-3">
        <h1 className="text-lg font-semibold">To-do</h1>
        <p className="text-sm text-[var(--text-muted)]">
          Your list — Celestia can see and help organize it from chat.
        </p>
      </header>

      {/* Add */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={newText}
          placeholder="Add a to-do…"
          className="min-w-[12rem] flex-1"
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleAdd();
          }}
        />
        <select
          value={newPriority}
          onChange={(e) => setNewPriority(e.target.value as TodoPriority)}
          className="rounded-md border border-[var(--border-light)] bg-[var(--bg-input)] px-2 py-2 text-sm"
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <Input
          type="date"
          value={newDue}
          className="w-[9.5rem]"
          onChange={(e) => setNewDue(e.target.value)}
        />
        <Button onClick={handleAdd} disabled={busy || !newText.trim()}>
          <Plus size={15} /> Add
        </Button>
      </div>

      {error && <p className="mt-2 text-sm text-[var(--armed)]">{error}</p>}

      <Separator className="my-3 bg-[var(--border-light)]" />

      <ScrollArea className="min-h-0 flex-1">
        {loading ? (
          <p className="muted">Loading…</p>
        ) : open.length === 0 && done.length === 0 ? (
          <p className="muted">Nothing here yet. Add your first to-do above.</p>
        ) : (
          <>
            <ul className="todo-list">
              {open.length === 0 ? (
                <li className="muted py-2">All done. 🎉</li>
              ) : (
                open.map(renderItem)
              )}
            </ul>

            {done.length > 0 && (
              <div className="mt-4">
                <button
                  type="button"
                  className="text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
                  onClick={() => setShowDone((v) => !v)}
                >
                  {showDone ? "Hide" : "Show"} completed ({done.length})
                </button>
                {showDone && <ul className="todo-list mt-1">{done.map(renderItem)}</ul>}
              </div>
            )}
          </>
        )}
      </ScrollArea>
    </div>
  );
}
