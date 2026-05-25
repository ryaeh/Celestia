import { useCallback, useEffect, useState } from "react";
import {
  fetchAuditTail,
  fetchStatus,
  fetchWorkspaces,
  setMode,
  type AuditEntry,
  type Status,
} from "../api";
import type { Route } from "../App";

const MODES = [
  { label: "Safe",   value: "safe"   },
  { label: "Scoped", value: "scoped" },
  { label: "Armed",  value: "armed"  },
] as const;

function formatAuditEntry(entry: AuditEntry): string {
  if ("raw" in entry && typeof entry.raw === "string") return entry.raw;
  const ts     = entry.ts ?? "?";
  const tool   = entry.tool ?? entry.event ?? "?";
  const result = entry.result ?? entry.mode ?? "";
  const summary = typeof entry.summary === "string" ? entry.summary.slice(0, 80) : "";
  return `${ts} [${tool}] ${result} ${summary}`.trim();
}

// ── card row ──────────────────────────────────────────────────────────────

type RowProps = {
  icon: string;
  iconClass?: string;
  title: string;
  subtitle: string;
  expanded?: boolean;
  onToggle?: () => void;
  pill?: React.ReactNode;
  children?: React.ReactNode;
};

function SettingRow({
  icon, iconClass = "", title, subtitle, expanded = false, onToggle, pill, children,
}: RowProps) {
  return (
    <div className="setting-card">
      <div
        className={`setting-row${expanded ? " setting-row-open" : ""}`}
        onClick={onToggle}
        role={onToggle ? "button" : undefined}
        tabIndex={onToggle ? 0 : undefined}
        onKeyDown={(e) => { if (onToggle && (e.key === "Enter" || e.key === " ")) onToggle(); }}
      >
        <div className={`setting-icon ${iconClass}`}>{icon}</div>
        <div className="setting-text">
          <span className="setting-title">{title}</span>
          <span className="setting-sub">{subtitle}</span>
        </div>
        {pill}
        {onToggle && <span className="setting-chevron">›</span>}
      </div>
      {expanded && children && <div className="setting-body">{children}</div>}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────

type SettingsProps = {
  onNavigate?: (route: Route) => void;
};

export default function Settings({ onNavigate }: SettingsProps) {
  const [status, setStatus] = useState<Status | null>(null);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openSection, setOpenSection] = useState<string | null>("security");

  const toggle = (s: string) => setOpenSection((p) => (p === s ? null : s));

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [s, ws, log] = await Promise.all([
        fetchStatus(),
        fetchWorkspaces(),
        fetchAuditTail(20),
      ]);
      setStatus(s);
      setWorkspaces(ws);
      setAudit(log);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function onMode(mode: string) {
    setBusy(true);
    setMessage(null);
    try {
      await setMode(mode);
      setMessage(`Mode set to ${mode}`);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const modeLabel = status?.mode_label ?? "…";
  const modeValue = status?.mode ?? "";

  return (
    <div className="settings-page">
      <div className="settings-head">
        <h1>Settings</h1>
        <p>Configure Celestia to your preference.</p>
      </div>

      {error && <p className="error" style={{ marginBottom: "0.75rem" }}>{error}</p>}

      <div className="settings-list">

        {/* Security */}
        <SettingRow
          icon="🔒"
          iconClass="setting-icon-security"
          title="Security"
          subtitle={`Threat level, access & session policies`}
          expanded={openSection === "security"}
          onToggle={() => toggle("security")}
          pill={
            <span className={`status-pill status-pill-${modeValue || "safe"}`}>
              {modeLabel}
            </span>
          }
        >
          {message && <p className={`setting-msg ok-text`}>{message}</p>}
          <div className="mode-row">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                className={`mode-btn${modeValue === m.value ? ` mode-active-${m.value}` : ""}`}
                disabled={busy}
                onClick={() => onMode(m.value)}
              >
                {m.label}
              </button>
            ))}
          </div>
        </SettingRow>

        {/* Memory */}
        <SettingRow
          icon="🧠"
          iconClass="setting-icon-memory"
          title="Memory"
          subtitle="What Celestia remembers across sessions"
          onToggle={onNavigate ? () => onNavigate("memory") : undefined}
        />

        {/* Personality */}
        <SettingRow
          icon="✦"
          iconClass="setting-icon-personality"
          title="Personality"
          subtitle="Tone, style and behaviour presets"
          pill={
            status?.personality ? (
              <span className="status-pill status-pill-accent">
                {status.personality.toUpperCase()}
              </span>
            ) : undefined
          }
        />

        {/* Workspaces */}
        <SettingRow
          icon="📁"
          iconClass="setting-icon-workspace"
          title="Workspaces"
          subtitle="Allowed directories and app paths"
          expanded={openSection === "workspaces"}
          onToggle={() => toggle("workspaces")}
        >
          {workspaces.length === 0 ? (
            <p className="muted" style={{ paddingTop: "0.65rem", margin: 0, fontSize: "0.85rem" }}>
              No workspaces configured.
            </p>
          ) : (
            <div className="workspace-pills">
              {workspaces.map((ws) => (
                <span key={ws} className="workspace-pill">{ws}</span>
              ))}
            </div>
          )}
        </SettingRow>

        {/* Tool audit */}
        <SettingRow
          icon="📋"
          iconClass="setting-icon-audit"
          title="Tool audit"
          subtitle="Recent tool executions and events"
          expanded={openSection === "audit"}
          onToggle={() => toggle("audit")}
        >
          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "0.6rem" }}>
            <button type="button" onClick={refresh} disabled={busy}>Refresh</button>
          </div>
          <pre className="audit-log">
            {audit.length === 0
              ? "(empty log)"
              : audit.map((e) => formatAuditEntry(e)).join("\n")}
          </pre>
        </SettingRow>

        {/* Error log */}
        <SettingRow
          icon="⚠"
          iconClass="setting-icon-logs"
          title="Error log"
          subtitle="data/logs/errors.log — check here when something breaks"
        />

      </div>
    </div>
  );
}
