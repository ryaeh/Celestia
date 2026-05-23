import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchChatHistory,
  fetchStatus,
  sendChatMessage,
  type ChatMessage,
  type Status,
} from "../api";
import StatusHeader from "../components/StatusHeader";
import ChatInput from "../components/ChatInput";
import Avatar from "../components/Avatar";

type HomeProps = {
  sessionId: string;
  onSidebarRefresh?: () => void;
};

export default function Home({ sessionId, onSidebarRefresh }: HomeProps) {
  const [status, setStatus] = useState<Status | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusReady, setStatusReady] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [chatBusy, setChatBusy] = useState(false);
  const [threadAnim, setThreadAnim] = useState(0);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchStatus()
      .then((s) => {
        if (!cancelled) {
          setStatus(s);
          setStatusReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) setStatusReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        setStatus(await fetchStatus());
      } catch {
        /* ignore */
      }
    }, 5000);
    return () => clearInterval(t);
  }, []);

  const loadSession = useCallback(async (sid: string) => {
    setSessionLoading(true);
    setError(null);
    try {
      const hist = await fetchChatHistory(sid);
      setMessages(hist.messages);
    } catch (e) {
      setError(String(e));
      setMessages([]);
    } finally {
      setSessionLoading(false);
      setThreadAnim((n) => n + 1);
    }
  }, []);

  useEffect(() => {
    loadSession(sessionId);
  }, [sessionId, loadSession]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, chatBusy]);

  async function onSend(text: string) {
    setChatBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    try {
      const result = await sendChatMessage(text, sessionId);
      setMessages(result.messages);
      onSidebarRefresh?.();
    } catch (e) {
      setError(String(e));
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setChatBusy(false);
    }
  }

  const name = status?.display_name ?? "Celestia";
  const showWelcome = messages.length === 0 && !chatBusy && !sessionLoading;
  const welcomeText = !statusReady
    ? "Connecting…"
    : `Hi — I'm ${name}. Ask me anything; your chats appear in the sidebar.`;

  return (
    <div className="home-view">
      <StatusHeader status={status} />

      <div className="chat-main" ref={threadRef}>
        {error && !chatBusy && (
          <div className="chat-error panel">
            <p className="error">{error}</p>
            <button type="button" onClick={() => loadSession(sessionId)}>
              Retry
            </button>
          </div>
        )}

        {sessionLoading && messages.length === 0 ? (
          <div className="chat-loading muted">Loading chat…</div>
        ) : (
          <div className="chat-thread chat-thread-enter" key={threadAnim}>
            {showWelcome && (
              <article className="chat-bubble">
                <Avatar name={name} size="sm" />
                <div className="chat-bubble-body">
                  <p>{welcomeText}</p>
                </div>
              </article>
            )}

            {messages.map((msg, i) => (
              <article
                key={`${i}-${msg.role}-${msg.content.slice(0, 24)}`}
                className={`chat-bubble ${msg.role === "user" ? "chat-bubble-user" : ""}`}
              >
                {msg.role === "assistant" && <Avatar name={name} size="sm" />}
                <div className="chat-bubble-body">
                  <p>{msg.content}</p>
                </div>
              </article>
            ))}

            {chatBusy && (
              <article className="chat-bubble chat-bubble-typing">
                <Avatar name={name} size="sm" />
                <div className="chat-bubble-body">
                  <p className="muted">Thinking…</p>
                </div>
              </article>
            )}
          </div>
        )}
      </div>

      <ChatInput
        onSend={onSend}
        disabled={!!error && messages.length === 0 && !sessionLoading}
        busy={chatBusy}
      />
    </div>
  );
}
