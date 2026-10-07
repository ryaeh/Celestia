// ---------------------------------------------------------------------------
// Message time helpers. `ts` is epoch seconds as stored by shell_chat.py.
// Formatting follows the OS locale (12/24h, day/month order).
// ---------------------------------------------------------------------------

const DAY_MS = 86_400_000;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** "14:05" / "2:05 PM" */
export function clockTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/** Full date + time for a tooltip. */
export function fullStamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { dateStyle: "full", timeStyle: "short" });
}

/** Local calendar day, comparable across messages. */
export function dayKey(ts: number): number {
  return startOfDay(new Date(ts * 1000));
}

/** "Today" · "Yesterday" · "Mon 5 Oct" · "Mon 5 Oct 2025" (older years). */
export function dayLabel(ts: number, now: Date = new Date()): string {
  const d = new Date(ts * 1000);
  const diff = Math.round((startOfDay(now) - startOfDay(d)) / DAY_MS);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
    ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}),
  });
}

/** Unix seconds for "now", in the same unit the server stores. */
export function nowTs(): number {
  return Date.now() / 1000;
}
