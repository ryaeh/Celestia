import { useCallback, useEffect, useState } from "react";
import {
  createChatSession,
  fetchChatSessions,
  selectChatSession,
  type ChatSession,
} from "../api";
import { usePersistedState } from "../hooks/usePersistedState";
import type { Route } from "../App";
import Aura from "./Aura";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { Plus, Activity as ActivityIcon, Brain, Settings, ChevronLeft, ChevronRight } from "lucide-react";

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
        className={cn("sidebar", open ? "sidebar-open" : "sidebar-closed")}
        aria-hidden={!open}
      >
        <div className="sidebar-inner flex flex-col h-full">
          {/* Brand */}
          <div className="brand">
            <Aura size="brand" state="idle" />
            <strong>{displayName}</strong>
          </div>

          {/* New chat */}
          <button
            type="button"
            className="sidebar-new-chat"
            onClick={async () => {
              const id = await createChatSession();
              await loadSessions();
              onNavigate("home");
              onNewChat(id);
            }}
          >
            <Plus size={16} /> New chat
          </button>

          <Separator className="bg-[var(--border-light)] my-1" />

          {/* History */}
          <div className="sidebar-section flex-1 min-h-0">
            <span className="sidebar-label">History</span>
            <ScrollArea className="h-full">
              <ul className="history-list">
                {sessions.length === 0 ? (
                  <li className="muted sidebar-empty">No chats yet</li>
                ) : (
                  sessions.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={cn(
                          "history-item w-full",
                          item.id === activeSessionId && "active",
                        )}
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
            </ScrollArea>
          </div>

          <Separator className="bg-[var(--border-light)] my-1" />

          {/* Footer nav */}
          <div className="sidebar-footer">
            <button
              type="button"
              className={cn("sidebar-foot-btn", route === "activity" && "active")}
              onClick={() => onNavigate("activity")}
            >
              <span className="foot-icon"><ActivityIcon size={15} /></span>
              Activity
            </button>
            <button
              type="button"
              className={cn("sidebar-foot-btn", route === "memory" && "active")}
              onClick={() => onNavigate("memory")}
            >
              <span className="foot-icon"><Brain size={15} /></span>
              Memory
            </button>
            <button
              type="button"
              className={cn("sidebar-foot-btn", route === "settings" && "active")}
              onClick={() => onNavigate("settings")}
            >
              <span className="foot-icon"><Settings size={15} /></span>
              Settings
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
        {open ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
      </button>
    </>
  );
}
