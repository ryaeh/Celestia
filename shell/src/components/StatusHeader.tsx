import { useState } from "react";
import Aura from "./Aura";
import type { LiveState, Status } from "../api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronUp } from "lucide-react";

type StatusHeaderProps = {
  status: Status | null;
  /** Live state from /ws/state — overrides the polled status for mode and feeds
   *  the GPU activity readout. Optional so the header still renders from polling
   *  alone if the socket is down. */
  live?: LiveState;
};

const MODE_STYLE: Record<string, string> = {
  armed:  "bg-[var(--armed)]/15  text-[var(--armed)]  border-[var(--armed)]/40",
  scoped: "bg-[var(--scoped)]/15 text-[var(--scoped)] border-[var(--scoped)]/40",
  safe:   "bg-[var(--safe)]/15   text-[var(--safe)]   border-[var(--safe)]/40",
};

const CHECK_LABELS = ["Context", "Memory", "Tools", "Models"];

export default function StatusHeader({ status, live }: StatusHeaderProps) {
  const [expanded, setExpanded] = useState(false);

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
        <Aura size="mark" state="idle" />
        <span className="top-bar-name">{name}</span>
        <span className="top-bar-divider" aria-hidden />

        {/* Mode badge */}
        <Badge
          className={cn(
            "text-[0.65rem] font-semibold tracking-wide px-1.5 py-0 h-5 border",
            MODE_STYLE[mode] ?? MODE_STYLE.safe,
          )}
        >
          {modeLabel}
        </Badge>

        {/* Personality badge */}
        {personality && (
          <Badge
            className="text-[0.65rem] font-semibold tracking-wide px-1.5 py-0 h-5 border bg-[var(--accent-glow)] text-[var(--accent-bright)] border-[var(--accent-bright)]/30"
          >
            {personality.toUpperCase()}
          </Badge>
        )}

        <span className="top-bar-spacer" />

        {/* GPU activity — shown only while a model is working (UI V2 / F3). */}
        {gpuBusy && (
          <span
            className="gpu-pill"
            title={gpuTask ? `GPU busy — ${gpuTask}` : "GPU busy"}
          >
            <span className="gpu-pill-dot" aria-hidden />
            {gpuTask ?? "GPU"}
          </span>
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
              <Badge className="text-[0.65rem] bg-[var(--accent-glow)] text-[var(--accent-bright)] border-[var(--accent-bright)]/30">
                {status.tray_max_mode.toUpperCase()}
              </Badge>
            </div>
          )}
        </div>
      )}
    </>
  );
}
