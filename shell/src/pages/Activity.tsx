import { useEffect, useRef, useState } from "react";
import {
  fetchActivityFeed,
  subscribeActivityStream,
  type ActivityEvent,
} from "../api";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";

const ACTION_COLOR: Record<string, string> = {
  read_screen:  "text-[var(--accent-bright)] bg-[var(--accent-glow)]",
  add:          "text-[var(--safe)] bg-[var(--safe)]/10",
  update:       "text-[var(--scoped)] bg-[var(--scoped)]/10",
  consolidate:  "text-[var(--text-muted)] bg-[var(--bg-panel)]",
};

function actionColor(action: string): string {
  return ACTION_COLOR[action] ?? "text-[var(--text-dim)] bg-[var(--bg-panel)]";
}

function relativeTime(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export default function Activity() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchActivityFeed(50);
      setEvents(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();

    const unsub = subscribeActivityStream((ev) => {
      setEvents((prev) => [ev, ...prev].slice(0, 200));
    });
    unsubRef.current = unsub;

    return () => {
      unsub();
      unsubRef.current = null;
    };
  }, []);

  return (
    <div className="memory-page">
      <header className="memory-head">
        <h1>Activity</h1>
        <p className="muted">Live feed of memory updates, screen reads, and system events.</p>
      </header>

      <div className="flex items-center gap-3 mb-4">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={loading}
          onClick={load}
        >
          Refresh
        </Button>
        {loading && <span className="muted text-sm">Loading…</span>}
        {error && <span className="text-[var(--armed)] text-sm">{error}</span>}
      </div>

      <ScrollArea className="flex-1">
        {events.length === 0 && !loading ? (
          <p className="muted text-sm">No activity yet.</p>
        ) : (
          <ul className="space-y-1">
            {events.map((ev, i) => (
              <li
                key={`${ev.ts}-${i}`}
                className="flex items-start gap-3 px-3 py-2 rounded-md bg-[var(--bg-panel)] border border-[var(--border-light)] text-sm"
              >
                <span
                  className={`shrink-0 mt-0.5 rounded px-1.5 py-0.5 text-[0.65rem] font-mono ${actionColor(ev.action)}`}
                >
                  {ev.action}
                </span>
                <span className="flex-1 text-[var(--text)] leading-relaxed break-words min-w-0">
                  {ev.text}
                </span>
                <span className="shrink-0 text-[var(--text-dim)] text-[0.7rem] whitespace-nowrap mt-0.5">
                  {relativeTime(ev.ts)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>
    </div>
  );
}
