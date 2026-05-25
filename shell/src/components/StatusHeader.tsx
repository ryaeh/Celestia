import { useState } from "react";
import Avatar from "./Avatar";
import type { Status } from "../api";

type StatusHeaderProps = {
  status: Status | null;
};

function modeBadge(mode: string): { label: string; tone: "safe" | "scoped" | "armed" } {
  const m = mode.toLowerCase();
  if (m === "armed") return { label: "ARMED", tone: "armed" };
  if (m === "scoped") return { label: "SCOPED", tone: "scoped" };
  return { label: "SAFE", tone: "safe" };
}

const CHECK_LABELS = ["Context", "Memory", "Tools", "Models"];

export default function StatusHeader({ status }: StatusHeaderProps) {
  const [expanded, setExpanded] = useState(false);

  const name = status?.display_name ?? "Celestia";
  const security = status ? modeBadge(status.mode) : { label: "…", tone: "safe" as const };
  const personality = status?.personality ?? "";

  const preflightItems =
    status?.checks.slice(0, 4).map((c, i) => ({
      label: CHECK_LABELS[i] ?? `Check ${i + 1}`,
      ok: c.ok,
    })) ?? CHECK_LABELS.map((label) => ({ label, ok: true }));

  return (
    <>
      <div className="top-bar">
        <Avatar name={name} size="xs" />
        <span className="top-bar-name">{name}</span>
        <span className="top-bar-divider" aria-hidden />
        <span className={`status-pill status-pill-${security.tone}`}>{security.label}</span>
        {personality && (
          <span className="status-pill status-pill-accent">{personality.toUpperCase()}</span>
        )}
        <span className="top-bar-spacer" />
        <div className="top-bar-preflight" title="Preflight checks">
          {preflightItems.map((item) => (
            <span
              key={item.label}
              className={`preflight-dot ${item.ok ? "ok" : "warn"}`}
              title={item.label}
            />
          ))}
        </div>
        <button
          type="button"
          className="top-bar-expand"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          title={expanded ? "Hide status" : "Show status"}
        >
          {expanded ? "▲" : "▼"}
        </button>
      </div>

      {expanded && (
        <div className="top-bar-panel">
          <div className="top-bar-card">
            <span className="top-bar-card-label">Preflight</span>
            <ul className="top-bar-check-list">
              {preflightItems.map((item) => (
                <li key={item.label}>
                  <span className={`preflight-dot ${item.ok ? "ok" : "warn"}`} />
                  {item.label}
                </li>
              ))}
            </ul>
          </div>
          {status?.tray_max_mode && (
            <div className="top-bar-card">
              <span className="top-bar-card-label">Tray cap</span>
              <span className="status-pill status-pill-accent">
                {status.tray_max_mode.toUpperCase()}
              </span>
            </div>
          )}
        </div>
      )}
    </>
  );
}
