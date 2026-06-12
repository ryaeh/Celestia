import { useCallback, useEffect, useState } from "react";
import { fetchChatSessions, initialRoute } from "./api";
import Sidebar from "./components/Sidebar";
import Activity from "./pages/Activity";
import Home from "./pages/Home";
import Memory from "./pages/Memory";
import Placeholder from "./pages/Placeholder";
import Settings from "./pages/Settings";
import Todos from "./pages/Todos";
import "./App.css";

export type Route = "home" | "settings" | "personality" | "activity" | "memory" | "todos";

function normalizeRoute(raw: string): Route {
  if (
    raw === "settings" ||
    raw === "personality" ||
    raw === "activity" ||
    raw === "memory" ||
    raw === "todos"
  ) {
    return raw;
  }
  return "home";
}

function SecondaryPage({ route, onNavigate }: { route: Route; onNavigate: (r: Route) => void }) {
  switch (route) {
    case "settings":
      return <Settings onNavigate={onNavigate} />;
    case "memory":
      return <Memory />;
    case "todos":
      return <Todos />;
    case "personality":
      return (
        <Placeholder
          title="Personality"
          blurb="Edit and switch personality YAML safely — coming later."
        />
      );
    case "activity":
      return <Activity />;
    default:
      return null;
  }
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => normalizeRoute(initialRoute()));
  const [prevRoute, setPrevRoute] = useState<Route>("home");
  const [activeSessionId, setActiveSessionId] = useState("");
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const displayName = "Celestia";

  function navigate(to: Route) {
    setPrevRoute(route);
    setRoute(to);
  }

  function goBack() {
    // Don't go back to another non-home secondary page — fall back to home.
    const dest = prevRoute === "home" || prevRoute === "settings" ? prevRoute : "home";
    setPrevRoute(route);
    setRoute(dest);
  }

  useEffect(() => {
    fetchChatSessions()
      .then((d) => setActiveSessionId(d.active_id))
      .catch(() => setActiveSessionId(""));
  }, []);

  const bumpHistory = useCallback(() => {
    setHistoryRefresh((n) => n + 1);
  }, []);

  return (
    <div className="app-shell">
      <Sidebar
        route={route}
        activeSessionId={activeSessionId}
        onNavigate={navigate}
        onNewChat={(id) => {
          setActiveSessionId(id);
          bumpHistory();
        }}
        onSelectSession={(id) => {
          setActiveSessionId(id);
        }}
        refreshToken={historyRefresh}
        displayName={displayName}
      />

      <div className="main-column">
        {route === "home" && activeSessionId ? (
          <Home
            sessionId={activeSessionId}
            onSidebarRefresh={bumpHistory}
          />
        ) : route === "home" ? (
          <main className="secondary-page muted">Loading chat…</main>
        ) : (
          <main className="secondary-page">
            <header className="secondary-page-head">
              <button
                type="button"
                className="back-home"
                onClick={goBack}
              >
                ← {prevRoute === "settings" ? "Settings" : "Chat"}
              </button>
            </header>
            <SecondaryPage route={route} onNavigate={navigate} />
          </main>
        )}
      </div>
    </div>
  );
}
