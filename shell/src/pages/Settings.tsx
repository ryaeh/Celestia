import { useCallback, useEffect, useState } from "react";
import {
  fetchAuditTail,
  fetchStatus,
  fetchWorkspaces,
  setMode,
  type AuditEntry,
  type Status,
} from "../api";

const MODES = [
  { label: "Safe", value: "safe" },
  { label: "Scoped", value: "scoped" },
  { label: "Armed", value: "armed" },
] as const;

function formatAuditEntry(entry: AuditEntry): string {
  if ("raw" in entry && typeof entry.raw === "string") {
    return entry.raw;
  }
  const ts = entry.ts ?? "?";
  const tool = entry.tool ?? entry.event ?? "?";
  const result = entry.result ?? entry.mode ?? "";
  const summary =
    typeof entry.summary === "string" ? entry.summary.slice(0, 80) : "";
  return `${ts} [${tool}] ${result} ${summary}`.trim();
}

export default function Settings() {
  const [status, setStatus] = useState<Status | null>(null);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    refresh();
  }, [refresh]);

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

  return (
    <div className="panel">
      <h1>Settings</h1>
      <p className="lead">
        Shell settings are not capped by <code>tray_max_mode</code> (same as the
        old tk window).
      </p>

      {error && <p className="error">{error}</p>}
      {message && <p className="ok-text">{message}</p>}

      <section className="settings-section">
        <h2>Security mode</h2>
        {status && (
          <p className="muted">
            Current: <strong>{status.mode_label}</strong>
            {status.tray_max_mode && (
              <>
                {" "}
                · Tray cap: <strong>{status.tray_max_mode}</strong>
              </>
            )}
          </p>
        )}
        <div className="mode-row">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              className={status?.mode === m.value ? "active" : ""}
              disabled={busy}
              onClick={() => onMode(m.value)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </section>

      <section className="settings-section">
        <h2>Workspaces</h2>
        <p className="muted">Read-only list from scope config.</p>
        {workspaces.length === 0 ? (
          <p className="muted">No workspaces configured.</p>
        ) : (
          <ul className="workspace-list">
            {workspaces.map((ws) => (
              <li key={ws}>{ws}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="settings-section">
        <div className="section-head">
          <h2>Recent tool audit</h2>
          <button type="button" onClick={refresh} disabled={busy}>
            Refresh
          </button>
        </div>
        <pre className="audit-log">
          {audit.length === 0
            ? "(empty log)"
            : audit.map((e) => formatAuditEntry(e)).join("\n")}
        </pre>
      </section>
    </div>
  );
}
