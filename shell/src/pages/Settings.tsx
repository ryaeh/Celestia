import { useCallback, useEffect, useRef, useState } from "react";
import {
  addWorkspace,
  fetchAuditTail,
  fetchStatus,
  fetchWorkspaces,
  removeWorkspace,
  setMode,
  type AuditEntry,
  type Status,
} from "../api";
import type { Route } from "../App";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FolderPlus, Trash2, RefreshCw, ExternalLink, Mic, Volume2, Brain, Shield, FolderOpen, ClipboardList, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

const MODES = [
  { label: "Safe",   value: "safe",   color: "var(--safe)",   desc: "Read-only tools only" },
  { label: "Scoped", value: "scoped", color: "var(--scoped)", desc: "Files in workspaces" },
  { label: "Armed",  value: "armed",  color: "var(--armed)",  desc: "Full PC access" },
] as const;

function formatAuditEntry(entry: AuditEntry): { ts: string; tool: string; result: string; summary: string } {
  if ("raw" in entry && typeof entry.raw === "string") {
    return { ts: "", tool: "raw", result: entry.raw, summary: "" };
  }
  const ts = typeof entry.ts === "string" ? entry.ts.slice(11, 19) : "?";
  const tool = typeof entry.tool === "string" ? entry.tool : (typeof entry.event === "string" ? entry.event : "?");
  const result = typeof entry.result === "string" ? entry.result : (typeof entry.mode === "string" ? entry.mode : "");
  const summary = typeof entry.summary === "string" ? entry.summary.slice(0, 120) : "";
  return { ts, tool, result, summary };
}

function AuditRow({ entry, idx }: { entry: AuditEntry; idx: number }) {
  const { ts, tool, result, summary } = formatAuditEntry(entry);
  const isOk = !result.toLowerCase().startsWith("block") && !result.toLowerCase().startsWith("error");
  return (
    <div className={cn("audit-row", idx % 2 === 0 ? "audit-row-even" : "")}>
      <span className="audit-ts">{ts}</span>
      <span className={cn("audit-tool", isOk ? "audit-ok" : "audit-blocked")}>{tool}</span>
      <span className="audit-result">{result || summary}</span>
    </div>
  );
}

// ── Section card ──────────────────────────────────────────────────────────────

type SectionProps = {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  expanded?: boolean;
  onToggle?: () => void;
  badge?: React.ReactNode;
  children?: React.ReactNode;
};

function Section({ icon, title, subtitle, expanded = false, onToggle, badge, children }: SectionProps) {
  return (
    <div className="setting-card">
      <div
        className={cn("setting-row", expanded && "setting-row-open")}
        onClick={onToggle}
        role={onToggle ? "button" : undefined}
        tabIndex={onToggle ? 0 : undefined}
        onKeyDown={(e) => { if (onToggle && (e.key === "Enter" || e.key === " ")) onToggle(); }}
      >
        <div className="setting-icon">{icon}</div>
        <div className="setting-text">
          <span className="setting-title">{title}</span>
          <span className="setting-sub">{subtitle}</span>
        </div>
        {badge}
        {onToggle && (
          <span className={cn("setting-chevron transition-transform duration-200", expanded && "rotate-90")}>›</span>
        )}
      </div>
      {expanded && children && <div className="setting-body">{children}</div>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type SettingsProps = { onNavigate?: (route: Route) => void };

export default function Settings({ onNavigate }: SettingsProps) {
  const [status, setStatus] = useState<Status | null>(null);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openSection, setOpenSection] = useState<string | null>("security");
  const [wsInput, setWsInput] = useState("");
  const [wsMsg, setWsMsg] = useState<string | null>(null);
  const wsInputRef = useRef<HTMLInputElement>(null);

  const toggle = (s: string) => setOpenSection((p) => (p === s ? null : s));

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [s, ws, log] = await Promise.all([
        fetchStatus(),
        fetchWorkspaces(),
        fetchAuditTail(50),
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

  async function onAddWorkspace() {
    const path = wsInput.trim();
    if (!path) return;
    setBusy(true);
    setWsMsg(null);
    try {
      const res = await addWorkspace(path);
      setWsMsg(res.message);
      setWorkspaces(res.workspaces);
      setWsInput("");
    } catch (e) {
      setWsMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onRemoveWorkspace(path: string) {
    setBusy(true);
    setWsMsg(null);
    try {
      const res = await removeWorkspace(path);
      setWsMsg(res.message);
      setWorkspaces(res.workspaces);
    } catch (e) {
      setWsMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  const modeValue = status?.mode ?? "";

  return (
    <div className="settings-page">
      <div className="settings-head">
        <h1>Settings</h1>
        <p>Configure Celestia — changes to voice/model settings require editing <code>config.yaml</code>.</p>
      </div>

      {error && <p className="error" style={{ marginBottom: "0.75rem" }}>{error}</p>}

      <div className="settings-list">

        {/* ── Security ─────────────────────────────────────────────────── */}
        <Section
          icon={<Shield size={16} />}
          title="Security"
          subtitle="Threat level and access policies"
          expanded={openSection === "security"}
          onToggle={() => toggle("security")}
          badge={
            <span className={`status-pill status-pill-${modeValue || "safe"}`}>
              {status?.mode_label ?? "…"}
            </span>
          }
        >
          {message && <p className="setting-msg ok-text">{message}</p>}
          <div className="mode-row">
            {MODES.map((m) => (
              <Button
                key={m.value}
                type="button"
                variant={modeValue === m.value ? "default" : "outline"}
                size="sm"
                className={cn("mode-btn flex-1 flex-col h-auto py-2 gap-0.5", modeValue === m.value && `mode-active-${m.value}`)}
                disabled={busy}
                onClick={() => onMode(m.value)}
                style={modeValue === m.value ? { background: m.color, borderColor: m.color } : undefined}
              >
                <span>{m.label}</span>
                <span className="text-[0.65rem] opacity-70 font-normal">{m.desc}</span>
              </Button>
            ))}
          </div>
        </Section>

        {/* ── Workspaces ────────────────────────────────────────────────── */}
        <Section
          icon={<FolderOpen size={16} />}
          title="Workspaces"
          subtitle="Allowed directories for file access in Scoped mode"
          expanded={openSection === "workspaces"}
          onToggle={() => toggle("workspaces")}
          badge={
            workspaces.length > 0
              ? <Badge variant="secondary" className="text-[0.68rem] bg-[var(--bg-panel)] border-[var(--border-light)]">{workspaces.length}</Badge>
              : undefined
          }
        >
          {wsMsg && (
            <p className={cn("setting-msg text-xs mt-2", wsMsg.toLowerCase().startsWith("added") ? "ok-text" : "text-[var(--text-muted)]")}>
              {wsMsg}
            </p>
          )}

          {/* Add workspace */}
          <div className="flex gap-2 mt-3">
            <Input
              ref={wsInputRef}
              value={wsInput}
              onChange={(e) => setWsInput(e.target.value)}
              placeholder="C:\path\to\folder"
              className="h-8 text-xs font-mono bg-[var(--bg-input)] border-[var(--border-light)] flex-1"
              onKeyDown={(e) => { if (e.key === "Enter") onAddWorkspace(); }}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 gap-1 text-xs"
              disabled={busy || !wsInput.trim()}
              onClick={onAddWorkspace}
            >
              <FolderPlus size={13} />
              Add
            </Button>
          </div>

          {/* Workspace list */}
          {workspaces.length === 0 ? (
            <p className="muted text-xs pt-3">No workspaces configured. Add a folder above.</p>
          ) : (
            <div className="mt-3 flex flex-col gap-1.5">
              {workspaces.map((ws) => (
                <div key={ws} className="workspace-row flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 bg-[var(--bg-panel)] border border-[var(--border-light)]">
                  <span className="font-mono text-[0.75rem] text-[var(--text-muted)] truncate flex-1">{ws}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-[var(--text-muted)] hover:text-red-400 shrink-0"
                    disabled={busy}
                    onClick={() => onRemoveWorkspace(ws)}
                  >
                    <Trash2 size={12} />
                  </Button>
                </div>
              ))}
            </div>
          )}
          <p className="text-[0.72rem] text-[var(--text-muted)] mt-3 opacity-70">
            Permanent workspaces go in <code>security.policy.yaml</code>. Paths added here are stored in <code>data/scope_workspaces.json</code>.
          </p>
        </Section>

        {/* ── Memory ────────────────────────────────────────────────────── */}
        <Section
          icon={<Brain size={16} />}
          title="Memory"
          subtitle="Facts, instructions and summaries Celestia recalls"
          onToggle={onNavigate ? () => onNavigate("memory") : undefined}
          badge={
            <Badge variant="secondary" className="text-[0.68rem] bg-[var(--bg-panel)] border-[var(--border-light)] gap-1">
              <ExternalLink size={10} />
              Open
            </Badge>
          }
        />

        {/* ── Personality ───────────────────────────────────────────────── */}
        <Section
          icon={<span className="text-sm">✦</span>}
          title="Personality"
          subtitle="Tone, style and behaviour preset — edit personalities/ YAML to change"
          badge={
            status?.personality ? (
              <Badge variant="secondary" className="text-[var(--accent-bright)] border-[var(--accent-bright)]/30 bg-[var(--accent-glow)] text-[0.68rem]">
                {status.personality.toUpperCase()}
              </Badge>
            ) : undefined
          }
        />

        {/* ── Voice & STT ───────────────────────────────────────────────── */}
        <Section
          icon={<Mic size={16} />}
          title="Voice & STT"
          subtitle="Whisper model, noise processing and push-to-talk options"
          expanded={openSection === "voice"}
          onToggle={() => toggle("voice")}
        >
          <div className="voice-info-grid mt-3">
            <InfoRow label="STT Model" value={<><code>config.yaml</code> › <code>voice.stt.model</code><br /><span className="opacity-60 text-[0.7rem]">Recommended: <code>base.en</code> (CPU), <code>large-v3</code> (GPU)</span></>} />
            <InfoRow label="STT Device" value={<><code>config.yaml</code> › <code>voice.stt.device</code><br /><span className="opacity-60 text-[0.7rem]">CPU or cuda</span></>} />
            <InfoRow label="Noise gate" value={<><code>voice.stt.noise_gate_threshold</code> (default 0.005)<br /><span className="opacity-60 text-[0.7rem]">Raise to 0.01 if Whisper hallucinates on background noise</span></>} />
            <InfoRow label="VAD filter" value={<><code>voice.stt.vad_filter</code>: true/false<br /><span className="opacity-60 text-[0.7rem]">Filters silence during transcription — reduces hallucination tokens</span></>} />
            <InfoRow label="Auto-stop" value={<><code>voice.stt.silence_stop_seconds</code> (default 1.5 s)<br /><span className="opacity-60 text-[0.7rem]">Seconds of silence before recording auto-stops</span></>} />
            <InfoRow label="PTT hotkey" value={<code>{status ? "ctrl+alt+shift+v" : "…"}</code>} />
          </div>
        </Section>

        {/* ── TTS ───────────────────────────────────────────────────────── */}
        <Section
          icon={<Volume2 size={16} />}
          title="Text-to-Speech"
          subtitle="Voice output provider and quality settings"
          expanded={openSection === "tts"}
          onToggle={() => toggle("tts")}
        >
          <div className="voice-info-grid mt-3">
            <InfoRow label="Provider" value={<><code>voice.tts.provider</code>: orpheus or edge<br /><span className="opacity-60 text-[0.7rem]">Orpheus (GPU, local) · Edge (CPU, streaming via Microsoft)</span></>} />
            <InfoRow label="Orpheus model" value={<code>models/Orpheus-3b-FT-Q8_0.gguf</code>} />
            <InfoRow label="Orpheus context warning" value={<><span className="text-yellow-400">n_ctx_seq 8192 &lt; n_ctx_train 131072</span> is informational — Orpheus at 8 K is fine for TTS sentences. Increase <code>n_ctx</code> only if you send very long prompts.</>} />
            <InfoRow label="Streaming TTS" value={<><code>voice.tts.streaming</code>: true<br /><span className="opacity-60 text-[0.7rem]">Speaks first sentence as LLM streams — ~2 s time-to-first-audio</span></>} />
          </div>
        </Section>

        {/* ── Tool audit ────────────────────────────────────────────────── */}
        <Section
          icon={<ClipboardList size={16} />}
          title="Tool Audit"
          subtitle="Last 50 tool calls and security events"
          expanded={openSection === "audit"}
          onToggle={() => toggle("audit")}
          badge={audit.length > 0
            ? <Badge variant="secondary" className="text-[0.68rem] bg-[var(--bg-panel)] border-[var(--border-light)]">{audit.length}</Badge>
            : undefined
          }
        >
          <div className="flex items-center justify-between pt-2 pb-1">
            <span className="text-xs text-[var(--text-muted)]">{audit.length} entries</span>
            <Button type="button" variant="outline" size="sm" onClick={refresh} disabled={busy} className="h-7 gap-1 text-xs">
              <RefreshCw size={12} />
              Refresh
            </Button>
          </div>
          <ScrollArea className="h-64 rounded-md border border-[var(--border-light)] bg-[var(--bg-input)]">
            <div className="audit-table p-1">
              {audit.length === 0
                ? <p className="text-xs text-[var(--text-muted)] p-2">(empty log)</p>
                : [...audit].reverse().map((e, i) => <AuditRow key={i} entry={e} idx={i} />)
              }
            </div>
          </ScrollArea>
        </Section>

        <Separator className="bg-[var(--border-light)]" />

        {/* ── Error log ─────────────────────────────────────────────────── */}
        <Section
          icon={<AlertTriangle size={16} />}
          title="Error Log"
          subtitle="data/logs/errors.log — check here when something breaks"
        />

      </div>
    </div>
  );
}

// ── Helper ────────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="info-row">
      <span className="info-label">{label}</span>
      <span className="info-value">{value}</span>
    </div>
  );
}
