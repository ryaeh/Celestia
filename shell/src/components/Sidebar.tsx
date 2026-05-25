import { useCallback, useEffect, useState } from "react";
import {
  createChatSession,
  fetchChatSessions,
  selectChatSession,
  type ChatSession,
} from "../api";
import { usePersistedState } from "../hooks/usePersistedState";
import type { Route } from "../App";

type SidebarProps = {
  route: Route;
  activeSessionId: string;
  onNavigate: (route: Route) => void;
  onNewChat: (sessionId: string) => void;
  onSelectSession: (sessionId: string) => void;
  refreshToken?: number;
  displayName: string;
};

export default function Sidebar({
  route,
  activeSessionId,
  onNavigate,
  onNewChat,
  onSelectSession,
  refreshToken = 0,
  displayName,
}: SidebarProps) {
  const [open, setOpen] = usePersistedState("celestia.shell.sidebarOpen", true);
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  const loadSessions = useCallback(async () => {
    try {
      const data = await fetchChatSessions();
      setSessions(data.sessions);
    } catch {
      setSessions([]);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, refreshToken, activeSessionId]);

  return (
    <>
      <aside
        className={`sidebar ${open ? "sidebar-open" : "sidebar-closed"}`}
        aria-hidden={!open}
      >
        <div className="sidebar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden>
              ◆
            </span>
            <strong>{displayName}</strong>
          </div>

          <button
            type="button"
            className="btn-primary sidebar-new-chat"
            onClick={async () => {
              const id = await createChatSession();
              await loadSessions();
              onNavigate("home");
              onNewChat(id);
            }}
          >
            + New Chat
          </button>

          <div className="sidebar-section">
            <span className="sidebar-label">History</span>
            <ul className="history-list">
              {sessions.length === 0 ? (
                <li className="muted sidebar-empty">No chats yet</li>
              ) : (
                sessions.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`history-item ${item.id === activeSessionId ? "active" : ""}`}
                      onClick={async () => {
                        await selectChatSession(item.id);
                        onNavigate("home");
                        onSelectSession(item.id);
                      }}
                    >
                      <span className="history-title">{item.title}</span>
                      <span className="history-when">{item.when}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          </div>

          <div className="sidebar-footer">
            <button
              type="button"
              className={`sidebar-foot-btn ${route === "memory" ? "active" : ""}`}
              onClick={() => onNavigate("memory")}
            >
              Memory
            </button>
            <button
              type="button"
              className={`sidebar-foot-btn ${route === "settings" ? "active" : ""}`}
              onClick={() => onNavigate("settings")}
            >
              Settings
            </button>
            <button type="button" className="sidebar-foot-btn" disabled>
              Profile
              <span className="placeholder-tag">soon</span>
            </button>
          </div>
        </div>
      </aside>

      <button
        type="button"
        className="sidebar-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Hide sidebar" : "Show sidebar"}
        title={open ? "Hide sidebar" : "Show sidebar"}
      >
        {open ? "‹" : "›"}
      </button>
    </>
  );
}
