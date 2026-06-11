const DEFAULT_API = "http://127.0.0.1:8765";
const DEV_PROXY_API = "/api";

const API_HINT =
  "Start the Python API: .\\venv\\Scripts\\python.exe run_celestia.py --shell-server (or run_celestia.py --shell).";

export function apiBase(): string {
  // Vite dev: same-origin proxy avoids browser blocks (localhost:1420 → :8765).
  if (import.meta.env.DEV) {
    return DEV_PROXY_API;
  }
  const fromEnv = import.meta.env.VITE_SHELL_API;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const injected = (window as unknown as { __CELESTIA_SHELL_API?: string })
      .__CELESTIA_SHELL_API;
    if (injected) return injected.replace(/\/$/, "");
  }
  return DEFAULT_API;
}

// ---------------------------------------------------------------------------
// CC-114: Session auth token
// Fetched once from GET /token (localhost-only endpoint) and cached in memory.
// Every apiFetch call includes it as X-Celestia-Token.
// ---------------------------------------------------------------------------

let _apiToken: string | null = null;
let _tokenFetch: Promise<string> | null = null;

async function acquireToken(): Promise<string> {
  if (_apiToken) return _apiToken;
  if (_tokenFetch) return _tokenFetch;
  _tokenFetch = (async () => {
    try {
      const r = await fetch(`${apiBase()}/token`);
      if (!r.ok) throw new Error(`/token ${r.status}`);
      const d = await r.json() as { token: string };
      _apiToken = d.token;
      return _apiToken;
    } catch {
      // If the server doesn't support tokens yet, continue unauthenticated.
      _apiToken = "";
      return "";
    } finally {
      _tokenFetch = null;
    }
  })();
  return _tokenFetch;
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await acquireToken();
  const url = `${apiBase()}${path}`;
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (token) headers["X-Celestia-Token"] = token;

  try {
    const res = await fetch(url, { ...init, headers });
    // If the server rotated its token (e.g. restart without frontend restart),
    // clear cache and retry once.
    if (res.status === 401 && _apiToken) {
      _apiToken = null;
      const retryToken = await acquireToken();
      const retryHeaders = { ...headers };
      if (retryToken) retryHeaders["X-Celestia-Token"] = retryToken;
      return fetch(url, { ...init, headers: retryHeaders });
    }
    return res;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/failed to fetch|network|load/i.test(msg)) {
      throw new Error(`${msg}. ${API_HINT}`);
    }
    throw e;
  }
}

export type Status = {
  display_name: string;
  mode: string;
  mode_label: string;
  tray_max_mode: string | null;
  personality: string;
  ollama_ok: boolean;
  vision_enabled?: boolean;
  checks: { ok: boolean; message: string }[];
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type ChatSession = {
  id: string;
  title: string;
  when: string;
  active: boolean;
};

export async function fetchStatus(): Promise<Status> {
  const r = await apiFetch("/status");
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json();
}

export async function setMode(mode: string): Promise<void> {
  const r = await apiFetch("/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!r.ok) throw new Error(`mode ${r.status}`);
}

export async function fetchWorkspaces(): Promise<string[]> {
  const r = await apiFetch("/workspaces");
  if (!r.ok) throw new Error(`workspaces ${r.status}`);
  const data = await r.json();
  return data.workspaces ?? [];
}

export async function addWorkspace(path: string): Promise<{ message: string; workspaces: string[] }> {
  const r = await apiFetch("/workspaces/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!r.ok) throw new Error(`workspaces/add ${r.status}`);
  return r.json();
}

export async function removeWorkspace(path: string): Promise<{ message: string; workspaces: string[] }> {
  const r = await apiFetch("/workspaces/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!r.ok) throw new Error(`workspaces/remove ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Vision (CC-49 / CC-68)
// ---------------------------------------------------------------------------

export type VisionCapture = {
  id: string;
  base64: string;
  width: number;
  height: number;
};

export type VisionHistoryEntry = {
  id: string;
  ts: string;
  base64: string;
};

export type VisionCaptureMode = "fullscreen" | "region" | "active_window";

export async function visionCapture(
  mode: VisionCaptureMode = "fullscreen",
): Promise<VisionCapture> {
  const r = await apiFetch(`/vision/capture?mode=${encodeURIComponent(mode)}`, {
    method: "POST",
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error((d as { error?: string }).error ?? `vision/capture ${r.status}`);
  }
  return r.json();
}

export async function visionAnalyze(
  captureId: string,
  question: string,
  sessionId: string,
): Promise<{ session_id: string; messages: ChatMessage[] }> {
  const r = await apiFetch("/vision/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ capture_id: captureId, question, session_id: sessionId }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error((d as { error?: string }).error ?? `vision/analyze ${r.status}`);
  }
  return r.json();
}

export async function fetchVisionHistory(n = 20): Promise<VisionHistoryEntry[]> {
  const r = await apiFetch(`/vision/history?n=${n}`);
  if (!r.ok) throw new Error(`vision/history ${r.status}`);
  const d = await r.json();
  return d.entries ?? [];
}

// ---------------------------------------------------------------------------
// UI runtime preferences — mirrors /prefs on the Python backend
// ---------------------------------------------------------------------------
export type PrefsResponse = {
  prefs: Record<string, unknown>;
  saved: Record<string, unknown>;
};

export async function fetchPrefs(): Promise<PrefsResponse> {
  const r = await apiFetch("/prefs");
  if (!r.ok) throw new Error(`prefs ${r.status}`);
  return r.json();
}

export async function setPref(key: string, value: unknown): Promise<void> {
  const r = await apiFetch("/prefs", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  if (!r.ok) throw new Error(`prefs PATCH ${r.status}`);
}

export type AuditEntry = Record<string, unknown>;

export async function fetchAuditTail(n = 50): Promise<AuditEntry[]> {
  const r = await apiFetch(`/audit/tail?n=${n}`);
  if (!r.ok) throw new Error(`audit ${r.status}`);
  const data = await r.json();
  return data.entries ?? [];
}

export async function fetchChatSessions(): Promise<{
  sessions: ChatSession[];
  active_id: string;
}> {
  const r = await apiFetch("/chat/sessions");
  if (!r.ok) throw new Error(`chat sessions ${r.status}`);
  return r.json();
}

export async function fetchChatHistory(sessionId?: string): Promise<{
  messages: ChatMessage[];
  session_id: string;
}> {
  const q = sessionId ? `?session=${encodeURIComponent(sessionId)}` : "";
  const r = await apiFetch(`/chat/history${q}`);
  if (!r.ok) throw new Error(`chat history ${r.status}`);
  return r.json();
}

export async function sendChatMessage(
  message: string,
  sessionId?: string,
): Promise<{
  reply: string;
  session_id: string;
  messages: ChatMessage[];
}> {
  const r = await apiFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!r.ok) {
    let detail = `chat ${r.status}`;
    try {
      const err = (await r.json()) as { error?: string };
      if (err.error) detail = err.error;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return r.json();
}

export async function createChatSession(): Promise<string> {
  const r = await apiFetch("/chat/new", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!r.ok) throw new Error(`chat/new ${r.status}`);
  const data = await r.json();
  return data.session_id as string;
}

export type PttStatus = {
  phase: string;
  listening: boolean;
  busy: boolean;
  error?: string | null;
};

export async function fetchPttStatus(): Promise<PttStatus> {
  const r = await apiFetch("/chat/ptt/status");
  if (!r.ok) throw new Error(`ptt status ${r.status}`);
  return r.json();
}

export async function pttStart(): Promise<{ ok?: boolean; error?: string }> {
  const r = await apiFetch("/chat/ptt/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `ptt start ${r.status}`);
  return data;
}

export async function pttStop(sessionId?: string): Promise<{
  reply?: string;
  session_id?: string;
  messages?: ChatMessage[];
  error?: string;
}> {
  const r = await apiFetch("/chat/ptt/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `ptt stop ${r.status}`);
  return data;
}

export async function pttCancel(): Promise<void> {
  const r = await apiFetch("/chat/ptt/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!r.ok) throw new Error(`ptt cancel ${r.status}`);
}

export async function selectChatSession(sessionId: string): Promise<{
  session_id: string;
  messages: ChatMessage[];
}> {
  const r = await apiFetch("/chat/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!r.ok) throw new Error(`chat/select ${r.status}`);
  return r.json();
}

/** @deprecated use createChatSession */
export async function clearChatSession(): Promise<string> {
  return createChatSession();
}

// ---------------------------------------------------------------------------
// Streaming chat (CC-90)
// ---------------------------------------------------------------------------

export type ChatStreamToken = { token: string };
export type ChatStreamDone = {
  done: true;
  reply: string;
  session_id: string;
  messages: ChatMessage[];
};
export type ChatStreamError = { error: string };
export type ChatStreamEvent = ChatStreamToken | ChatStreamDone | ChatStreamError;

/**
 * Async generator that yields token events as the model streams, then a
 * final done event once the response is complete and the session is saved.
 *
 * Falls back to the blocking POST /chat if the stream fails to open.
 */
export async function* streamChatMessage(
  message: string,
  sessionId?: string,
): AsyncGenerator<ChatStreamEvent> {
  const response = await apiFetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!response.ok) {
    let detail = `chat/stream ${response.status}`;
    try {
      const err = (await response.json()) as { error?: string };
      if (err.error) detail = err.error;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error("Streaming not supported by this environment.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          yield JSON.parse(data) as ChatStreamEvent;
        } catch {
          /* malformed chunk — skip */
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  // Flush any remaining data in the buffer
  if (buffer.startsWith("data: ")) {
    const data = buffer.slice(6).trim();
    if (data) {
      try {
        yield JSON.parse(data) as ChatStreamEvent;
      } catch {
        /* ignore */
      }
    }
  }
}

export function initialRoute(): string {
  const envRoute = import.meta.env.VITE_SHELL_ROUTE;
  if (envRoute) return envRoute;
  if (typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search);
    if (q.get("route")) return q.get("route")!;
  }
  return "home";
}

export type MemoryKind = "fact" | "instruction" | "summary" | "task";

export type MemoryEntry = {
  id: string;
  text: string;
  kind: MemoryKind | string;
  updated_at: number;
};

export type LastSessionNote = {
  bullets: string[];
  text: string;
  updated_at: number;
};

async function memoryPayload(r: Response): Promise<MemoryEntry[]> {
  if (!r.ok) throw new Error(`memory ${r.status}`);
  const data = await r.json();
  return data.entries ?? [];
}

export async function fetchMemoryEntries(): Promise<MemoryEntry[]> {
  const r = await apiFetch("/memory");
  return memoryPayload(r);
}

export async function fetchLastSession(): Promise<LastSessionNote> {
  const r = await apiFetch("/memory/last-session");
  if (!r.ok) throw new Error(`last-session ${r.status}`);
  return r.json();
}

export async function createMemoryEntry(
  text: string,
  kind: MemoryKind = "fact",
): Promise<MemoryEntry[]> {
  const r = await apiFetch("/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, kind }),
  });
  return memoryPayload(r);
}

export async function updateMemoryEntry(
  id: string,
  text: string,
  kind?: MemoryKind,
): Promise<MemoryEntry[]> {
  const r = await apiFetch(`/memory/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, kind }),
  });
  return memoryPayload(r);
}

export async function deleteMemoryEntry(id: string): Promise<MemoryEntry[]> {
  const r = await apiFetch(`/memory/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  return memoryPayload(r);
}

export async function refreshLastSession(): Promise<LastSessionNote> {
  const r = await apiFetch("/memory/last-session/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!r.ok) throw new Error(`refresh last-session ${r.status}`);
  const data = await r.json();
  return {
    bullets: data.bullets ?? [],
    text: data.text ?? "",
    updated_at: data.updated_at ?? 0,
  };
}

// ---------------------------------------------------------------------------
// Activity feed (CC-99 / Feature 07)
// ---------------------------------------------------------------------------

export type ActivityEvent = {
  ts: number;
  action: string;
  kind: string;
  text: string;
  source: string;
};

export async function fetchActivityFeed(n = 30): Promise<ActivityEvent[]> {
  const r = await apiFetch(`/memory/activity?n=${n}`);
  if (!r.ok) throw new Error(`activity ${r.status}`);
  const data = await r.json();
  return data.events ?? [];
}

/**
 * Opens an SSE connection to /activity/stream and calls onEvent for each
 * new event. Returns a cleanup function (call it to close the stream).
 */
export function subscribeActivityStream(
  onEvent: (e: ActivityEvent) => void,
): () => void {
  let closed = false;
  let es: EventSource | null = null;

  acquireToken().then((token) => {
    if (closed) return;
    const url = `${apiBase()}/activity/stream`;
    // EventSource doesn't support custom headers natively; pass token as query param
    // for the SSE connection only (the token is already localhost-scoped).
    const src = new EventSource(
      token ? `${url}?token=${encodeURIComponent(token)}` : url,
    );
    es = src;
    src.onmessage = (ev) => {
      if (!ev.data || ev.data.startsWith(":")) return;
      try {
        onEvent(JSON.parse(ev.data) as ActivityEvent);
      } catch {
        /* malformed — skip */
      }
    };
    src.onerror = () => {
      src.close();
    };
  });

  return () => {
    closed = true;
    es?.close();
  };
}

// Read screen (Feature 07): the in-chat "eye" button now goes through the
// regular vision capture + confirm flow (visionCapture("active_window")).
// The instant, no-confirm POST /read-screen/trigger path is reserved for the
// global hotkey, which calls the backend directly.
