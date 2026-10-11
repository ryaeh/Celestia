import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useOllama } from "../hooks/useOllama";
import { closeMainWindow, inTauri } from "../lib/overlayWindow";
import { openDownload, PullProgress } from "./OllamaParts";

// ---------------------------------------------------------------------------
// Ollama launch gate. Celestia needs Ollama for chat and memory, so when it's
// off at launch we ask once what to do (start it / carry on without / quit)
// instead of dropping the user into a chat that can't answer. The answer can be
// remembered (Settings → Ollama changes it back). After that decision — or any
// time Ollama drops mid-session — a slim banner keeps the state visible and
// offers the fix in one click.
//
//   pending ─▶ done   Ollama is up, or the remembered choice is start / skip
//           └▶ gate ─▶ done   modal until the user picks (or Ollama comes up)
// ---------------------------------------------------------------------------

type Phase = "pending" | "gate" | "done";

export default function OllamaGate() {
  const { status, error, start, pull, cancelPull, refresh, setOnLaunch } = useOllama();
  const [phase, setPhase] = useState<Phase>("pending");
  const [remember, setRemember] = useState(false);
  const autoStarted = useRef(false);

  // Decide once, on the first real answer, whether this launch needs the dialog.
  useEffect(() => {
    if (phase !== "pending" || !status) return;
    if (status.state === "running") {
      setPhase("done");
    } else if (status.on_launch === "ask") {
      setPhase("gate");
    } else {
      setPhase("done");
      if (status.on_launch === "start" && status.can_start && !autoStarted.current) {
        autoStarted.current = true;
        void start(); // idempotent server-side, so a double fire is harmless
      }
    }
  }, [phase, status, start]);

  // Ollama came up while the dialog was open (we started it, or the user did).
  const state = status?.state;
  useEffect(() => {
    if (phase === "gate" && state === "running") setPhase("done");
  }, [phase, state]);

  if (!status || state === "running" || phase === "pending") return null;

  const failure = status.pull.error ?? status.start_error ?? error;
  const pulling = status.pull.active;

  async function onStart() {
    if (remember) await setOnLaunch("start");
    await start();
  }

  function onSkip() {
    if (remember) void setOnLaunch("skip");
    setPhase("done");
  }

  // ── Launch dialog ──────────────────────────────────────────────────────────
  if (phase === "gate") {
    let title: string;
    let body: ReactNode;
    let actions: ReactNode;
    const skipLabel = state === "missing_models" ? "Run Anyway" : "Run Without Ollama";

    const quit = inTauri() && (
      <Button type="button" variant="ghost" size="lg" className="w-full" onClick={() => void closeMainWindow()}>
        Quit
      </Button>
    );
    const skip = (
      <Button type="button" variant="outline" size="lg" className="w-full" onClick={onSkip}>
        {skipLabel}
      </Button>
    );

    switch (state) {
      case "starting":
        title = "Starting Ollama…";
        body = <p>This usually takes a few seconds. Celestia opens as soon as it's up.</p>;
        actions = (
          <>
            <Button type="button" size="lg" className="w-full ollama-primary" disabled>
              <RefreshCw size={14} className="ollama-spin" /> Starting…
            </Button>
            {skip}
            {quit}
          </>
        );
        break;
      case "not_installed":
        title = "Ollama isn't installed";
        body = (
          <p>
            Celestia runs on this PC and uses Ollama (free) for chat and memory. Install it, then come back — this
            window notices on its own.
          </p>
        );
        actions = (
          <>
            <Button type="button" size="lg" className="w-full ollama-primary" onClick={() => openDownload(status.download_url)}>
              Download Ollama
            </Button>
            {skip}
            {quit}
          </>
        );
        break;
      case "missing_models":
        title = "Models needed";
        body = pulling ? (
          <PullProgress pull={status.pull} onCancel={() => void cancelPull()} />
        ) : (
          <>
            <p>
              Ollama is running, but {status.missing.length === 1 ? "this model isn't" : "these models aren't"}{" "}
              installed yet: <strong>{status.missing.join(", ")}</strong>.
            </p>
            <p>They download once and stay on this PC — it can take a few minutes.</p>
          </>
        );
        actions = pulling ? (
          <>
            {skip}
            {quit}
          </>
        ) : (
          <>
            <Button type="button" size="lg" className="w-full ollama-primary" onClick={() => void pull()}>
              {status.pull.finished && status.pull.error ? "Try Again" : "Pull Missing Models Now"}
            </Button>
            {skip}
            {quit}
          </>
        );
        break;
      default: // down
        if (status.local) {
          title = "Ollama isn't running";
          body = (
            <p>
              Celestia keeps everything on this PC and uses Ollama for chat and memory. Start it now, or open the app
              without it — chat and memory stay paused until Ollama is up.
            </p>
          );
          actions = (
            <>
              <Button type="button" size="lg" className="w-full ollama-primary" disabled={!status.can_start} onClick={() => void onStart()}>
                {status.start_error ? "Try Again" : "Start Ollama and Run"}
              </Button>
              {skip}
              {quit}
            </>
          );
        } else {
          title = "Can't reach Ollama";
          body = (
            <p>
              Celestia is set to use Ollama at <code>{status.host}</code>, which isn't answering. Start it on that
              machine, or open the app without it.
            </p>
          );
          actions = (
            <>
              <Button type="button" size="lg" className="w-full ollama-primary" onClick={() => void refresh()}>
                Check Again
              </Button>
              {skip}
              {quit}
            </>
          );
        }
    }

    return (
      <div className="ollama-scrim">
        <div className="ollama-dialog" role="dialog" aria-modal="true" aria-labelledby="ollama-dialog-title">
          <h2 id="ollama-dialog-title">{title}</h2>
          {body}
          {failure && !pulling && <p className="ollama-error">{failure}</p>}
          {state === "down" && status.local && status.can_start && (
            <label className="ollama-remember">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              <span>
                Remember my choice and don't ask again
                <small>Change it any time in Settings → Ollama.</small>
              </span>
            </label>
          )}
          <div className="ollama-actions">{actions}</div>
        </div>
      </div>
    );
  }

  // ── Banner (after the dialog, or when Ollama drops mid-session) ────────────
  let message: ReactNode;
  let action: ReactNode = null;
  switch (state) {
    case "starting":
      message = "Starting Ollama…";
      break;
    case "not_installed":
      message = "Ollama isn't installed — chat and memory are paused.";
      action = (
        <Button type="button" size="sm" variant="outline" onClick={() => openDownload(status.download_url)}>
          Download Ollama
        </Button>
      );
      break;
    case "missing_models":
      message = pulling ? null : (
        <>
          {status.chat_ready ? "Memory needs" : "Chat needs"} {status.missing.join(", ")}.
        </>
      );
      action = pulling ? null : (
        <Button type="button" size="sm" variant="outline" onClick={() => void pull()}>
          {status.pull.finished && status.pull.error ? "Try Again" : "Pull Now"}
        </Button>
      );
      break;
    default:
      if (status.local) {
        message = "Ollama is off — chat and memory are paused.";
        action = (
          <Button type="button" size="sm" variant="outline" disabled={!status.can_start} onClick={() => void start()}>
            {status.start_error ? "Try Again" : "Start Ollama"}
          </Button>
        );
      } else {
        message = (
          <>
            Can't reach Ollama at <code>{status.host}</code> — chat and memory are paused.
          </>
        );
        action = (
          <Button type="button" size="sm" variant="outline" onClick={() => void refresh()}>
            Check Again
          </Button>
        );
      }
  }

  return (
    <div className="ollama-banner" role="status">
      <AlertTriangle size={14} className="ollama-banner-icon" aria-hidden />
      {message && <span className="ollama-banner-text">{message}</span>}
      {pulling && (
        <div className="ollama-banner-progress">
          <PullProgress pull={status.pull} onCancel={() => void cancelPull()} />
        </div>
      )}
      {failure && !pulling && <span className="ollama-error ollama-banner-text">{failure}</span>}
      {action}
    </div>
  );
}
