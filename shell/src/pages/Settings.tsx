import { useCallback, useEffect, useRef, useState } from "react";
import {
  addWorkspace,
  fetchAuditTail,
  fetchPrefs,
  fetchStatus,
  fetchWorkspaces,
  removeWorkspace,
  setMode,
  setPref,
  type AuditEntry,
  type Status,
} from "../api";
import type { Route } from "../App";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  FolderPlus,
  Trash2,
  RefreshCw,
  ExternalLink,
  Mic,
  Volume2,
  Brain,
  Shield,
  FolderOpen,
  ClipboardList,
  AlertTriangle,
  Camera,
} from "lucide-react";
import { cn } from "@/lib/utils";

const MODES = [
  { label: "Safe",   value: "safe",   color: "var(--safe)",   desc: "Read-only tools only" },
  { label: "Scoped", value: "scoped", color: "var(--scoped)", desc: "Files in workspaces" },
  { label: "Armed",  value: "armed",  color: "var(--armed)",  desc: "Full PC access" },
] as const;

const STT_MODELS = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3", "large-v3-turbo"];
const STT_DEVICES = ["cpu", "cuda"];
const STT_COMPUTE_TYPES = ["int8", "float16", "float32"];
const TTS_PROVIDERS = ["edge", "orpheus"];

// ── Audit row ────────────────────────────────────────────────────────────────

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

// ── Pref controls ─────────────────────────────────────────────────────────────

type PrefSelectProps = {
  label: string;
  prefKey: string;
  options: readonly string[];
  value: string;
  hint?: string;
  onSaved: (key: string, val: unknown) => void;
};

function PrefSelect({ label, prefKey, options, value, hint, onSaved }: PrefSelectProps) {
  const [saving, setSaving] = useState(false);
  async function onChange(v: string) {
    setSaving(true);
    try {
      await setPref(prefKey, v);
      onSaved(prefKey, v);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="pref-row">
      <span className="pref-label">{label}</span>
      <div className="flex flex-col gap-1">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={saving}
          className="pref-select"
        >
          {options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        {hint && <span className="pref-hint">{hint}</span>}
      </div>
    </div>
  );
}

type PrefNumberProps = {
  label: string;
  prefKey: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
  onSaved: (key: string, val: unknown) => void;
};

function PrefNumber({ label, prefKey, value, min, max, step = 0.1, hint, onSaved }: PrefNumberProps) {
  const [draft, setDraft] = useState(String(value));
  const [saving, setSaving] = useState(false);

  useEffect(() => { setDraft(String(value)); }, [value]);

  async function onBlur() {
    const n = parseFloat(draft);
    if (isNaN(n)) { setDraft(String(value)); return; }
    if (n === value) return;
    setSaving(true);
    try {
      await setPref(prefKey, n);
      onSaved(prefKey, n);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="pref-row">
      <span className="pref-label">{label}</span>
      <div className="flex flex-col gap-1">
        <input
          type="number"
          value={draft}
          min={min}
          max={max}
          step={step}
          disabled={saving}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={onBlur}
          className="pref-number"
        />
        {hint && <span className="pref-hint">{hint}</span>}
      </div>
    </div>
  );
}

type PrefToggleProps = {
  label: string;
  prefKey: string;
  value: boolean;
  hint?: string;
  onSaved: (key: string, val: unknown) => void;
};

function PrefToggle({ label, prefKey, value, hint, onSaved }: PrefToggleProps) {
  const [saving, setSaving] = useState(false);
  async function onChange(v: boolean) {
    setSaving(true);
    try {
      await setPref(prefKey, v);
      onSaved(prefKey, v);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="pref-row">
      <span className="pref-label">{label}</span>
      <div className="flex flex-col gap-1">
        <button
          type="button"
          role="switch"
          aria-checked={value}
          disabled={saving}
          onClick={() => onChange(!value)}
          className={cn("pref-toggle", value && "pref-toggle-on")}
        >
          <span className="pref-toggle-knob" />
        </button>
        {hint && <span className="pref-hint">{hint}</span>}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type SettingsProps = { onNavigate?: (route: Route) => void };

export default function Settings({ onNavigate }: SettingsProps) {
  const [status, setStatus] = useState<Status | null>(null);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [prefs, setPrefs] = useState<Record<string, unknown>>({});
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
      const [s, ws, log, p] = await Promise.all([
        fetchStatus(),
        fetchWorkspaces(),
        fetchAuditTail(50),
        fetchPrefs().catch(() => ({ prefs: {}, saved: {} })),
      ]);
      setStatus(s);
      setWorkspaces(ws);
      setAudit(log);
      setPrefs(p.prefs);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  function onPrefSaved(key: string, val: unknown) {
    setPrefs((prev) => ({ ...prev, [key]: val }));
  }

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

  // Typed pref helpers
  function ps(key: string, fallback: string): string {
    const v = prefs[key];
    return typeof v === "string" ? v : fallback;
  }
  function pn(key: string, fallback: number): number {
    const v = prefs[key];
    return typeof v === "number" ? v : fallback;
  }
  function pb(key: string, fallback: boolean): boolean {
    const v = prefs[key];
    return typeof v === "boolean" ? v : fallback;
  }

  return (
    <div className="settings-page">
      <div className="settings-head">
        <h1>Settings</h1>
        <p className="muted text-sm">Live controls — changes take effect immediately without restart.</p>
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
          <div className="flex gap-2 mt-3">
            <Input
              ref={wsInputRef}
              value={wsInput}
              onChange={(e) => setWsInput(e.target.value)}
              placeholder="C:\path\to\folder"
              className="h-8 text-xs font-mono bg-[var(--bg-input)] border-[var(--border-light)] flex-1"
              onKeyDown={(e) => { if (e.key === "Enter") onAddWorkspace(); }}
            />
            <Button type="button" size="sm" variant="outline" className="h-8 gap-1 text-xs" disabled={busy || !wsInput.trim()} onClick={onAddWorkspace}>
              <FolderPlus size={13} /> Add
            </Button>
          </div>
          {workspaces.length === 0 ? (
            <p className="muted text-xs pt-3">No workspaces configured. Add a folder above.</p>
          ) : (
            <div className="mt-3 flex flex-col gap-1.5">
              {workspaces.map((ws) => (
                <div key={ws} className="workspace-row flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 bg-[var(--bg-panel)] border border-[var(--border-light)]">
                  <span className="font-mono text-[0.75rem] text-[var(--text-muted)] truncate flex-1">{ws}</span>
                  <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-[var(--text-muted)] hover:text-red-400 shrink-0" disabled={busy} onClick={() => onRemoveWorkspace(ws)}>
                    <Trash2 size={12} />
                  </Button>
                </div>
              ))}
            </div>
          )}
          <p className="text-[0.72rem] text-[var(--text-muted)] mt-3 opacity-70">
            Permanent workspaces go in <code>security.policy.yaml</code>. Runtime paths are stored in <code>data/scope_workspaces.json</code>.
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
              <ExternalLink size={10} /> Open
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
          subtitle="Whisper model, noise processing and push-to-talk behaviour"
          expanded={openSection === "voice"}
          onToggle={() => toggle("voice")}
        >
          <div className="pref-grid mt-3">
            <PrefSelect
              label="Whisper model"
              prefKey="voice.stt.model"
              options={STT_MODELS}
              value={ps("voice.stt.model", "base.en")}
              hint="base.en → fast/CPU · large-v3 → best/GPU. Reloads automatically."
              onSaved={onPrefSaved}
            />
            <PrefSelect
              label="Device"
              prefKey="voice.stt.device"
              options={STT_DEVICES}
              value={ps("voice.stt.device", "cpu")}
              hint="cpu (always works) or cuda (needs NVIDIA GPU + CUDA)."
              onSaved={onPrefSaved}
            />
            <PrefSelect
              label="Compute type"
              prefKey="voice.stt.compute_type"
              options={STT_COMPUTE_TYPES}
              value={ps("voice.stt.compute_type", "int8")}
              hint="int8 fastest on CPU · float16 for GPU · float32 most accurate."
              onSaved={onPrefSaved}
            />
            <PrefNumber
              label="Noise gate"
              prefKey="voice.stt.noise_gate_threshold"
              value={pn("voice.stt.noise_gate_threshold", 0.005)}
              min={0} max={0.1} step={0.001}
              hint="0.005 default. Raise to 0.01–0.02 if background noise causes hallucinations."
              onSaved={onPrefSaved}
            />
            <PrefToggle
              label="VAD filter"
              prefKey="voice.stt.vad_filter"
              value={pb("voice.stt.vad_filter", false)}
              hint="Silero VAD strips silence before transcription. Faster on GPU, adds overhead on CPU."
              onSaved={onPrefSaved}
            />
            <PrefNumber
              label="Auto-stop silence"
              prefKey="voice.stt.silence_stop_seconds"
              value={pn("voice.stt.silence_stop_seconds", 1.5)}
              min={0.3} max={5.0} step={0.1}
              hint="Seconds of silence before recording auto-stops. Lower = snappier."
              onSaved={onPrefSaved}
            />
            <PrefToggle
              label="Cap voice replies"
              prefKey="voice.reply_cap_voice"
              value={pb("voice.reply_cap_voice", true)}
              hint="Injects a system hint to keep replies concise during voice mode."
              onSaved={onPrefSaved}
            />
          </div>
          <p className="text-[0.72rem] text-[var(--text-muted)] mt-3 opacity-70">
            Saved to <code>data/ui_prefs.json</code> — overrides config.yaml without touching it.
          </p>
        </Section>

        {/* ── TTS ───────────────────────────────────────────────────────── */}
        <Section
          icon={<Volume2 size={16} />}
          title="Text-to-Speech"
          subtitle="Voice output provider"
          expanded={openSection === "tts"}
          onToggle={() => toggle("tts")}
        >
          <div className="pref-grid mt-3">
            <PrefSelect
              label="Provider"
              prefKey="voice.tts.provider"
              options={TTS_PROVIDERS}
              value={ps("voice.tts.provider", "edge")}
              hint="edge = fast, no GPU needed. orpheus = high quality, requires local GPU model."
              onSaved={onPrefSaved}
            />
          </div>
          <p className="text-[0.72rem] text-[var(--text-muted)] mt-3 opacity-70">
            TTS streams first sentence while LLM is still generating (CC-115). Provider change takes effect on next reply.
          </p>
        </Section>

        {/* ── Vision / Screenshot (CC-68) ──────────────────────────────── */}
        <Section
          icon={<Camera size={16} />}
          title="Vision & Screenshots"
          subtitle="Screenshot history ring buffer — CC-68"
          expanded={openSection === "vision"}
          onToggle={() => toggle("vision")}
          badge={
            <Badge variant="secondary" className="text-[0.68rem] bg-[var(--bg-panel)] border-[var(--border-light)]">
              Soon
            </Badge>
          }
        >
          <p className="text-sm text-[var(--text-muted)] mt-2">
            CC-68 implements a local ring buffer of recent screenshots so you can re-ask about a capture
            without taking a new one. Hotkey triggers (e.g. <code>Ctrl+Alt+Shift+S</code>) and viewing
            recent crops will appear here once implemented.
          </p>
          <p className="text-[0.72rem] text-[var(--text-muted)] mt-2 opacity-70">
            Current vision hotkey: configured in <code>config.yaml</code> › <code>vision.hotkey</code>.
          </p>
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
              <RefreshCw size={12} /> Refresh
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
