import { useEffect, useState } from "react";
import Aura from "./Aura";
import { fetchGpuInfo, type GpuInfo, type LiveState, type Status } from "../api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronUp } from "lucide-react";

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

const MODE_STYLE: Record<string, string> = {
  armed:  "bg-[var(--armed)]/15  text-[var(--armed)]  border-[var(--armed)]/40",
  scoped: "bg-[var(--scoped)]/15 text-[var(--scoped)] border-[var(--scoped)]/40",
  safe:   "bg-[var(--safe)]/15   text-[var(--safe)]   border-[var(--safe)]/40",
};

const CHECK_LABELS = ["Context", "Memory", "Tools", "Models"];

export default function StatusHeader({ status, live }: StatusHeaderProps) {
  const [expanded, setExpanded] = useState(false);
  const [gpuInfo, setGpuInfo] = useState<GpuInfo | null>(null);

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
