import { useCallback, useEffect, useState } from "react";
import {
  createChatSession,
  deleteChatSession,
  fetchChatSessions,
  getIncognito,
  searchChatSessions,
  selectChatSession,
  setIncognito,
  type ChatSearchResult,
  type ChatSession,
} from "../api";
import { usePersistedState } from "../hooks/usePersistedState";
import type { Route } from "../App";
import Aura from "./Aura";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { Plus, Activity as ActivityIcon, Brain, ListTodo, Settings, ChevronLeft, ChevronRight, Trash2, Check, X, Eye, EyeOff, Search } from "lucide-react";

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
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [incognito, setIncognitoState] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ChatSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const trimmedQuery = query.trim();

  // Debounced conversation search (Feature 03 / #86). Fires at >= 2 chars.
  useEffect(() => {
    if (trimmedQuery.length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const handle = setTimeout(() => {
      searchChatSessions(trimmedQuery)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 220);
    return () => clearTimeout(handle);
  }, [trimmedQuery]);

  useEffect(() => {
    getIncognito()
      .then(setIncognitoState)
      .catch(() => setIncognitoState(false));
  }, []);

  const toggleIncognito = useCallback(async () => {
    const next = !incognito;
    setIncognitoState(next); // optimistic
    try {
      setIncognitoState(await setIncognito(next));
    } catch {
      setIncognitoState(!next); // revert on failure
    }
  }, [incognito]);

  const loadSessions = useCallback(async () => {
    try {
      const data = await fetchChatSessions();
      setSessions(data.sessions);
    } catch {
      setSessions([]);
    }
  }, []);

  const confirmDelete = useCallback(
    async (item: ChatSession) => {
      setPendingDelete(null);
      try {
        const res = await deleteChatSession(item.id);
        await loadSessions();
        // If we deleted the chat we were viewing, follow the server's fallback.
        if (item.id === activeSessionId && res.active_id) {
          onSelectSession(res.active_id);
        }
      } catch {
        await loadSessions();
      }
    },
    [activeSessionId, loadSessions, onSelectSession],
  );

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
            <button
              type="button"
              className="incognito-toggle"
              aria-pressed={incognito}
              onClick={toggleIncognito}
              title={
                incognito
                  ? "Incognito — learning paused (chat still works). Click to resume."
                  : "Learning on. Click to pause memory + graph + activity."
              }
              aria-label={incognito ? "Resume learning" : "Pause learning (incognito)"}
            >
              {incognito ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
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

          {/* Conversation search (Feature 03 / #86) */}
          <div className="sidebar-search">
            <Search size={14} className="sidebar-search-icon" />
            <input
              type="text"
              className="sidebar-search-input"
              placeholder="Search chats…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search past conversations"
            />
            {query && (
              <button
                type="button"
                className="sidebar-search-clear"
                aria-label="Clear search"
                onClick={() => setQuery("")}
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* History / search results */}
          <div className="sidebar-section flex-1 min-h-0">
            <span className="sidebar-label">{trimmedQuery ? "Results" : "History"}</span>
            <ScrollArea className="h-full">
              <ul className="history-list">
                {trimmedQuery ? (
                  results.length === 0 ? (
                    <li className="muted sidebar-empty">
                      {searching ? "Searching…" : "No matches"}
                    </li>
                  ) : (
                    results.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          className={cn(
                            "history-item search-result w-full",
                            item.id === activeSessionId && "active",
                          )}
                          onClick={async () => {
                            await selectChatSession(item.id);
                            onNavigate("home");
                            onSelectSession(item.id);
                          }}
                        >
                          <span className="history-title">{item.title}</span>
                          <span className="search-snippet">{item.snippet}</span>
                          <span className="history-when">{item.when}</span>
                        </button>
                      </li>
                    ))
                  )
                ) : sessions.length === 0 ? (
                  <li className="muted sidebar-empty">No chats yet</li>
                ) : (
                  sessions.map((item) => (
                    <li key={item.id} className="group relative">
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
                      {pendingDelete === item.id ? (
                        <span className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-1 rounded-md bg-[var(--bg-panel)] px-1 py-0.5 shadow">
                          <button
                            type="button"
                            title="Delete — keeps what Celestia learned"
                            aria-label={`Confirm delete: ${item.title}`}
                            className="grid h-6 w-6 place-items-center rounded text-red-400 hover:bg-[var(--bg-input)]"
                            onClick={(e) => {
                              e.stopPropagation();
                              confirmDelete(item);
                            }}
                          >
                            <Check size={13} />
                          </button>
                          <button
                            type="button"
                            title="Cancel"
                            aria-label="Cancel delete"
                            className="grid h-6 w-6 place-items-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-input)]"
                            onClick={(e) => {
                              e.stopPropagation();
                              setPendingDelete(null);
                            }}
                          >
                            <X size={13} />
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          title="Delete chat — keeps what Celestia learned"
                          aria-label={`Delete chat: ${item.title}`}
                          className="absolute right-1 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded text-[var(--text-muted)] opacity-0 transition-opacity hover:bg-[var(--bg-input)] hover:text-red-400 focus:opacity-100 group-hover:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            setPendingDelete(item.id);
                          }}
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
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
              className={cn("sidebar-foot-btn", route === "todos" && "active")}
              onClick={() => onNavigate("todos")}
            >
              <span className="foot-icon"><ListTodo size={15} /></span>
              To-do
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
