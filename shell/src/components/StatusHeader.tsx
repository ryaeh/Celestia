import { useEffect, useState } from "react";
import {
  fetchChatNotes,
  fetchGpuInfo,
  type ChatNotes,
  type GpuInfo,
  type LiveState,
  type Status,
} from "../api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronUp, PictureInPicture2 } from "lucide-react";
import { inTauri, toggleOverlay } from "@/lib/overlayWindow";

/** How often the HUD refreshes the resident-model list. Deliberately slow — the
 *  backend call hits Ollama (ollama ps) + nvidia-smi, so it stays off the 1s
 *  /ws/state tick and polls on its own relaxed cadence. */
const GPU_INFO_INTERVAL_MS = 30_000;

function gb(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

/** "qwen2.5:7b" from "registry/qwen2.5:7b" — keep the tag, drop any path. */
function shortModelName(name: string): string {
  const parts = name.split("/");
  return parts[parts.length - 1] || name;
}

type StatusHeaderProps = {
  status: Status | null;
  /** Live state from /ws/state — overrides the polled status for mode and feeds
   *  the GPU activity readout. Optional so the header still renders from polling
   *  alone if the socket is down. */
  live?: LiveState;
};

// Status is always a dot plus a word (never colour alone); the full backend
// label ("scoped (allowlist), tray max …") stays available as the tooltip.
const MODE_STYLE: Record<string, string> = {
  armed:  "status-pill-armed",
  scoped: "status-pill-scoped",
  safe:   "status-pill-safe",
};
const MODE_WORD: Record<string, string> = { armed: "Armed", scoped: "Scoped", safe: "Safe" };

const CHECK_LABELS = ["Context", "Memory", "Tools", "Models"];

const NOTE_LISTS: [keyof ChatNotes["notes"], string][] = [
  ["facts", "From you"],
  ["decisions", "Decided"],
  ["open", "Still open"],
  ["details", "Exact details"],
  ["topics", "Earlier in this chat"],
];

export default function StatusHeader({ status, live }: StatusHeaderProps) {
  const [expanded, setExpanded] = useState(false);
  const [gpuInfo, setGpuInfo] = useState<GpuInfo | null>(null);
  const [notes, setNotes] = useState<ChatNotes | null>(null);
  const memorySaving = live?.memory_saving ?? null;

  const gpuBusyLive = live?.gpu_busy ?? false;

  // Resident models + VRAM on a slow poll, refreshed early when the GPU goes
  // busy (a model just loaded) so the HUD doesn't lag a whole interval behind.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const info = await fetchGpuInfo();
        if (!cancelled) setGpuInfo(info);
      } catch {
        /* API down — keep the last snapshot */
      }
    };
    load();
    const t = setInterval(load, GPU_INFO_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, [gpuBusyLive]);

  // Working-memory notes (T15): load when the panel opens and again once a
  // memory pass finishes, since that's when the notes change.
  useEffect(() => {
    if (!expanded || memorySaving) return;
    let cancelled = false;
    fetchChatNotes()
      .then((n) => { if (!cancelled) setNotes(n); })
      .catch(() => { /* API down — keep the last snapshot */ });
    return () => { cancelled = true; };
  }, [expanded, memorySaving]);

  const name = status?.display_name ?? "Celestia";
  // Live mode (pushed) wins over the polled value so a tray/CLI mode change shows
  // immediately; fall back to the polled status, then a safe default.
  const mode = (live?.mode ?? status?.mode ?? "safe").toLowerCase();
  const modeLabel =
    live?.mode_label ??
    status?.mode_label ??
    (mode === "armed" ? "ARMED" : mode === "scoped" ? "SCOPED" : "SAFE");
  const personality = status?.personality ?? "";
  const gpuBusy = live?.gpu_busy ?? false;
  const gpuTask = live?.gpu_task ?? null;

  const preflightItems =
    status?.checks.slice(0, 4).map((c, i) => ({
      label: CHECK_LABELS[i] ?? `Check ${i + 1}`,
      ok: c.ok,
    })) ?? CHECK_LABELS.map((label) => ({ label, ok: true }));

  return (
    <>
      <div className="top-bar">
        <span className="top-bar-name">{name}</span>

        {/* Mode badge */}
        <span
          className={cn("status-pill", MODE_STYLE[mode] ?? MODE_STYLE.safe)}
          title={modeLabel}
        >
          {MODE_WORD[mode] ?? MODE_WORD.safe}
        </span>

        {/* Personality badge */}
        {personality && (
          <span className="badge">{personality}</span>
        )}

        <span className="top-bar-spacer" />

        {/* GPU activity — shown only while a model is working (UI V2 / F3). */}
        {gpuBusy && (
          <span
            className="gpu-pill"
            title={[
              gpuTask ? `GPU busy — ${gpuTask}` : "GPU busy",
              ...(gpuInfo?.models.length
                ? [`Resident: ${gpuInfo.models.map((m) => shortModelName(m.name)).join(", ")}`]
                : []),
            ].join("\n")}
          >
            <span className="gpu-pill-dot" aria-hidden />
            {gpuTask ?? "GPU"}
          </span>
        )}

        {/* Memory pass running (T15) — chat keeps working meanwhile. */}
        {memorySaving && (
          <span
            className="status-pill status-pill-accent memory-saving-pill"
            title={
              memorySaving === "end"
                ? "Saving what I learned from the last chat"
                : "Saving memories from this long chat — you can keep talking"
            }
          >
            Saving memories…
          </span>
        )}

        {/* Companion bubble — pop Celestia out onto the desktop (Tauri only). */}
        {inTauri() && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-[var(--text-muted)] hover:text-[var(--text)]"
            title="Show / hide the companion bubble"
            aria-label="Toggle companion bubble"
            onClick={() => void toggleOverlay()}
          >
            <PictureInPicture2 size={15} />
          </Button>
        )}

        {/* Preflight dots */}
        <div className="top-bar-preflight flex items-center gap-1" title="Preflight checks">
          {preflightItems.map((item) => (
            <span
              key={item.label}
              className={cn("preflight-dot", item.ok ? "ok" : "warn")}
              title={item.label}
            />
          ))}
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="top-bar-expand h-7 w-7 text-[var(--text-muted)] hover:text-[var(--text)]"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          title={expanded ? "Hide status" : "Show status"}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </Button>
      </div>

      {expanded && (
        <div className="top-bar-panel">
          <div className="top-bar-card">
            <span className="top-bar-card-label">Preflight</span>
            <ul className="top-bar-check-list">
              {preflightItems.map((item) => (
                <li key={item.label} className="flex items-center gap-2">
                  <span className={cn("preflight-dot", item.ok ? "ok" : "warn")} />
                  {item.label}
                </li>
              ))}
            </ul>
          </div>
          {status?.tray_max_mode && (
            <div className="top-bar-card">
              <span className="top-bar-card-label">Tray cap</span>
              <span className="badge">{status.tray_max_mode}</span>
            </div>
          )}

          {/* Working memory of this chat (T15) */}
          <div className="top-bar-card notes-card">
            <span className="top-bar-card-label">What I'm keeping in mind</span>
            {!notes || notes.empty ? (
              <p className="gpu-model-empty">
                Nothing yet — notes start once this chat gets long.
              </p>
            ) : (
              <div className="notes-body">
                {notes.notes.goal && (
                  <p><span className="notes-label">About</span>{notes.notes.goal}</p>
                )}
                {notes.notes.now && (
                  <p><span className="notes-label">Right now</span>{notes.notes.now}</p>
                )}
                {NOTE_LISTS.map(([key, label]) => {
                  const items = notes.notes[key] as string[];
                  return items.length ? (
                    <div key={key}>
                      <span className="notes-label">{label}</span>
                      <ul className="notes-list">
                        {items.map((it, i) => <li key={i}>{it}</li>)}
                      </ul>
                    </div>
                  ) : null;
                })}
                {(notes.archived > 0 || notes.untrusted) && (
                  <p className="notes-foot">
                    {notes.archived > 0 && `${notes.archived} older messages archived. `}
                    {notes.untrusted && "Built partly from untrusted content."}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Resident models + VRAM (UI V2 / F3 follow-up) */}
          <div className="top-bar-card">
            <span className="top-bar-card-label">GPU</span>
            {gpuInfo?.models.length ? (
              <ul className="gpu-model-list">
                {gpuInfo.models.map((m) => (
                  <li key={m.name} className="gpu-model-row">
                    <span className="gpu-model-name">{shortModelName(m.name)}</span>
                    {m.size_vram > 0 && (
                      <span className="gpu-model-size">{gb(m.size_vram)}</span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="gpu-model-empty">No models resident</p>
            )}
            {gpuInfo?.vram && gpuInfo.vram.total_mb > 0 && (
              <div
                className="vram-bar-wrap"
                title={`VRAM ${(gpuInfo.vram.used_mb / 1024).toFixed(1)} / ${(gpuInfo.vram.total_mb / 1024).toFixed(1)} GB`}
              >
                <div className="vram-bar">
                  <div
                    className="vram-bar-fill"
                    style={{
                      width: `${Math.min(100, (gpuInfo.vram.used_mb / gpuInfo.vram.total_mb) * 100)}%`,
                    }}
                  />
                </div>
                <span className="vram-bar-label">
                  {(gpuInfo.vram.used_mb / 1024).toFixed(1)} / {(gpuInfo.vram.total_mb / 1024).toFixed(1)} GB
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
