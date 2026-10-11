import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  cancelOllamaPull,
  fetchOllamaStatus,
  pullOllamaModels,
  setPref,
  startOllama,
  type OllamaOnLaunch,
  type OllamaStatus,
} from "../api";

// Poll cadence by situation. Probing localhost is cheap, but there's no reason to
// hammer it while everything is fine.
const IDLE_MS = 15_000; //    up, nothing in flight — still notices it dying
const WAITING_MS = 3_000; //  down / models missing — notice it coming back
const BUSY_MS = 1_000; //     starting or pulling — keep the progress live

export const ON_LAUNCH_PREF = "llm.ollama_on_launch";

export type OllamaApi = {
  /** null until the first answer (or while the API itself is down). */
  status: OllamaStatus | null;
  /** A chat turn can run: Ollama up and the chat model installed. Optimistic
   *  until the first answer, so the composer isn't flashed disabled at startup. */
  chatReady: boolean;
  /** Last start/pull failure from the user's own click (cleared on the next one). */
  error: string | null;
  refresh: () => Promise<void>;
  start: () => Promise<void>;
  pull: () => Promise<void>;
  cancelPull: () => Promise<void>;
  /** Persist the "when Ollama is off at launch" choice (ask · start · skip). */
  setOnLaunch: (choice: OllamaOnLaunch) => Promise<void>;
};

const noop = async () => {};
const OllamaContext = createContext<OllamaApi>({
  status: null,
  chatReady: true,
  error: null,
  refresh: noop,
  start: noop,
  pull: noop,
  cancelPull: noop,
  setOnLaunch: noop,
});

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** One poller per window (the main window and the bubble each mount their own). */
export function OllamaProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef<OllamaStatus | null>(null);

  const apply = useCallback((s: OllamaStatus) => {
    latest.current = s;
    setStatus(s);
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply(await fetchOllamaStatus());
    } catch {
      /* API not up yet — keep the last answer */
    }
  }, [apply]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      await refresh();
      if (stopped) return;
      const s = latest.current;
      const delay = !s
        ? WAITING_MS
        : s.state === "starting" || s.pull.active
          ? BUSY_MS
          : s.state === "running"
            ? IDLE_MS
            : WAITING_MS;
      timer = setTimeout(tick, delay);
    };
    void tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [refresh]);

  const act = useCallback(
    async (call: () => Promise<OllamaStatus>) => {
      setError(null);
      try {
        apply(await call());
      } catch (e) {
        setError(errMsg(e));
        await refresh();
      }
    },
    [apply, refresh],
  );

  const start = useCallback(() => act(startOllama), [act]);
  const pull = useCallback(() => act(() => pullOllamaModels()), [act]);
  const cancelPull = useCallback(() => act(cancelOllamaPull), [act]);

  const setOnLaunch = useCallback(async (choice: OllamaOnLaunch) => {
    try {
      await setPref(ON_LAUNCH_PREF, choice);
      setStatus((s) => (s ? { ...s, on_launch: choice } : s));
      if (latest.current) latest.current = { ...latest.current, on_launch: choice };
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);

  const value = useMemo<OllamaApi>(
    () => ({
      status,
      chatReady: status ? status.chat_ready : true,
      error,
      refresh,
      start,
      pull,
      cancelPull,
      setOnLaunch,
    }),
    [status, error, refresh, start, pull, cancelPull, setOnLaunch],
  );

  return <OllamaContext.Provider value={value}>{children}</OllamaContext.Provider>;
}

export function useOllama(): OllamaApi {
  return useContext(OllamaContext);
}

/** Why the composer is locked, or undefined when chat can run. */
export function chatLockReason(status: OllamaStatus | null): string | undefined {
  if (!status || status.chat_ready) return undefined;
  switch (status.state) {
    case "starting":
      return "Starting Ollama…";
    case "not_installed":
      return "Ollama isn't installed — chat is paused";
    case "missing_models":
      return "The chat model isn't installed yet — pull it to chat";
    default:
      return status.local ? "Ollama is off — start it to chat" : "Can't reach Ollama — chat is paused";
  }
}
