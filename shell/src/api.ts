const DEFAULT_API = "http://127.0.0.1:8765";

export function apiBase(): string {
  const fromEnv = import.meta.env.VITE_SHELL_API;
  if (fromEnv) return fromEnv;
  if (typeof window !== "undefined") {
    const injected = (window as unknown as { __CELESTIA_SHELL_API?: string })
      .__CELESTIA_SHELL_API;
    if (injected) return injected;
  }
  return DEFAULT_API;
}

export type Status = {
  display_name: string;
  mode: string;
  mode_label: string;
  tray_max_mode: string | null;
  personality: string;
  ollama_ok: boolean;
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
  const r = await fetch(`${apiBase()}/status`);
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json();
}

export async function setMode(mode: string): Promise<void> {
  const r = await fetch(`${apiBase()}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!r.ok) throw new Error(`mode ${r.status}`);
}

export async function fetchWorkspaces(): Promise<string[]> {
  const r = await fetch(`${apiBase()}/workspaces`);
  if (!r.ok) throw new Error(`workspaces ${r.status}`);
  const data = await r.json();
  return data.workspaces ?? [];
}

export type AuditEntry = Record<string, unknown>;

export async function fetchAuditTail(n = 20): Promise<AuditEntry[]> {
  const r = await fetch(`${apiBase()}/audit/tail?n=${n}`);
  if (!r.ok) throw new Error(`audit ${r.status}`);
  const data = await r.json();
  return data.entries ?? [];
}

export async function fetchChatSessions(): Promise<{
  sessions: ChatSession[];
  active_id: string;
}> {
  const r = await fetch(`${apiBase()}/chat/sessions`);
  if (!r.ok) throw new Error(`chat sessions ${r.status}`);
  return r.json();
}

export async function fetchChatHistory(sessionId?: string): Promise<{
  messages: ChatMessage[];
  session_id: string;
}> {
  const q = sessionId ? `?session=${encodeURIComponent(sessionId)}` : "";
  const r = await fetch(`${apiBase()}/chat/history${q}`);
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
  const r = await fetch(`${apiBase()}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!r.ok) throw new Error(`chat ${r.status}`);
  return r.json();
}

export async function createChatSession(): Promise<string> {
  const r = await fetch(`${apiBase()}/chat/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!r.ok) throw new Error(`chat/new ${r.status}`);
  const data = await r.json();
  return data.session_id as string;
}

export async function selectChatSession(sessionId: string): Promise<{
  session_id: string;
  messages: ChatMessage[];
}> {
  const r = await fetch(`${apiBase()}/chat/select`, {
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

export function initialRoute(): string {
  const envRoute = import.meta.env.VITE_SHELL_ROUTE;
  if (envRoute) return envRoute;
  if (typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search);
    if (q.get("route")) return q.get("route")!;
  }
  return "home";
}
