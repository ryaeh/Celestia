import { usePersistedState } from "../hooks/usePersistedState";
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

export default function StatusHeader({ status }: StatusHeaderProps) {
  const [open, setOpen] = usePersistedState("celestia.shell.statusBarOpen", true);
  const name = status?.display_name ?? "Celestia";
  const security = status
    ? modeBadge(status.mode)
    : { label: "…", tone: "safe" as const };
  const personality = status ? status.personality.toUpperCase() : "…";

  const preflightItems =
    status?.checks.slice(0, 4).map((c, i) => ({
      label: ["Context", "Memory", "Tools", "Models"][i] ?? `Check ${i + 1}`,
      ok: c.ok,
    })) ?? [];

  while (preflightItems.length < 4) {
    preflightItems.push({
      label: ["Context", "Memory", "Tools", "Models"][preflightItems.length],
      ok: true,
    });
  }

  return (
    <header className={`status-header ${open ? "is-open" : "is-collapsed"}`}>
      <div className="status-header-grid">
        <div className="status-side status-side-left" aria-hidden={!open}>
          <div className="status-card">
            <span className="status-card-label">Security</span>
            <span className={`status-pill status-pill-${security.tone}`}>
              {security.label}
            </span>
          </div>
          <div className="status-card">
            <span className="status-card-label">Personality</span>
            <span className="status-pill status-pill-accent">
              {personality}
            </span>
          </div>
        </div>

        <div className="status-center">
          <button
            type="button"
            className="status-bar-toggle"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Hide status panels" : "Show status panels"}
            title={open ? "Hide status" : "Show status"}
          >
            <span className="status-bar-toggle-icon" />
          </button>
          <div className="status-avatar-slot">
            <Avatar name={name} size="md" />
          </div>
          <div className="status-avatar-meta">
            <strong>{name}</strong>
            <span>Always available</span>
          </div>
        </div>

        <div className="status-side status-side-right" aria-hidden={!open}>
          <div className="status-card status-card-wide">
            <span className="status-card-label">Preflight</span>
            <ul className="preflight-list">
              {preflightItems.map((item) => (
                <li key={item.label}>
                  <span className={`preflight-dot ${item.ok ? "ok" : "warn"}`} />
                  <span>{item.label}</span>
                  <span className="preflight-state">{item.ok ? "active" : "check"}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="status-card">
            <span className="status-card-label">Active mode</span>
            <span className="status-pill status-pill-accent">FOCUS</span>
            <span className="placeholder-tag">placeholder</span>
          </div>
        </div>
      </div>
    </header>
  );
}
