import { useCallback, useEffect, useState } from "react";
import { fetchChatSessions, initialRoute } from "./api";
import Sidebar from "./components/Sidebar";
import Home from "./pages/Home";
import Memory from "./pages/Memory";
import Placeholder from "./pages/Placeholder";
import Settings from "./pages/Settings";
import "./App.css";

export type Route = "home" | "settings" | "personality" | "activity" | "memory";

function normalizeRoute(raw: string): Route {
  if (raw === "settings" || raw === "personality" || raw === "activity" || raw === "memory") {
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
    case "personality":
      return (
        <Placeholder
          title="Personality"
          blurb="Edit and switch personality YAML safely — coming later."
        />
      );
    case "activity":
      return (
        <Placeholder
          title="Activity"
          blurb="Quiet system lines and tool activity — coming later."
        />
      );
    default:
      return null;
  }
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => normalizeRoute(initialRoute()));
  const [activeSessionId, setActiveSessionId] = useState("");
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const displayName = "Celestia";

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
        onNavigate={setRoute}
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
                onClick={() => setRoute("home")}
              >
                ← Chat
              </button>
            </header>
            <SecondaryPage route={route} onNavigate={setRoute} />
          </main>
        )}
      </div>
    </div>
  );
}
