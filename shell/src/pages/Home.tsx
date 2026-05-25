import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchChatHistory,
  fetchPttStatus,
  fetchStatus,
  pttCancel,
  pttStart,
  pttStop,
  streamChatMessage,
  type ChatMessage,
  type Status,
} from "../api";
import StatusHeader from "../components/StatusHeader";
import ChatInput from "../components/ChatInput";
import Avatar from "../components/Avatar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

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
  const [streamingTokens, setStreamingTokens] = useState(false);
  const [pttListening, setPttListening] = useState(false);
  const [threadAnim, setThreadAnim] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pttLocal = useRef(false);
  const pttEnding = useRef(false);
  const streamingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetchStatus()
      .then((s) => { if (!cancelled) { setStatus(s); setStatusReady(true); } })
      .catch(() => { if (!cancelled) setStatusReady(true); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const t = setInterval(async () => {
      try { setStatus(await fetchStatus()); } catch { /* ignore */ }
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

  useEffect(() => { loadSession(sessionId); }, [sessionId, loadSession]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatBusy, pttListening]);

  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const st = await fetchPttStatus();
        if (!pttLocal.current) setPttListening(st.listening);
        if (st.busy && st.phase === "transcribing") setChatBusy(true);
      } catch { /* API down */ }
    }, 250);
    return () => clearInterval(t);
  }, []);

  async function onPttStart() {
    pttLocal.current = true;
    setError(null);
    setPttListening(true);
    try {
      await pttStart();
    } catch (e) {
      setError(String(e));
      setPttListening(false);
      pttLocal.current = false;
    }
  }

  async function onPttEnd(cancel = false) {
    if (pttEnding.current) return;
    if (!pttLocal.current && !pttListening) return;
    pttEnding.current = true;
    pttLocal.current = false;
    if (cancel) {
      setPttListening(false);
      try { await pttCancel(); } catch { /* ignore */ } finally { pttEnding.current = false; }
      return;
    }
    setPttListening(false);
    setChatBusy(true);
    try {
      const result = await pttStop(sessionId);
      if (result.messages) { setMessages(result.messages); onSidebarRefresh?.(); }
    } catch (e) {
      setError(String(e));
    } finally {
      setChatBusy(false);
      pttEnding.current = false;
    }
  }

  async function onSend(text: string) {
    setChatBusy(true);
    setStreamingTokens(false);
    streamingRef.current = false;
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);

    try {
      for await (const event of streamChatMessage(text, sessionId)) {
        if ("token" in event) {
          if (!streamingRef.current) {
            streamingRef.current = true;
            setStreamingTokens(true);
            setMessages((prev) => [...prev, { role: "assistant" as const, content: event.token }]);
          } else {
            setMessages((prev) => {
              const msgs = [...prev];
              const last = msgs[msgs.length - 1];
              if (last?.role === "assistant") msgs[msgs.length - 1] = { ...last, content: last.content + event.token };
              return msgs;
            });
          }
        } else if ("done" in event && event.done) {
          setMessages(event.messages);
          onSidebarRefresh?.();
        } else if ("error" in event) {
          setError(event.error);
          setMessages((prev) => {
            const msgs = [...prev];
            if (streamingRef.current) msgs.pop();
            msgs.pop();
            return msgs;
          });
        }
      }
    } catch (e) {
      setError(String(e));
      setMessages((prev) => {
        const msgs = [...prev];
        if (streamingRef.current) msgs.pop();
        msgs.pop();
        return msgs;
      });
    } finally {
      setChatBusy(false);
      setStreamingTokens(false);
      streamingRef.current = false;
    }
  }

  const name = status?.display_name ?? "Celestia";
  const showWelcome = messages.length === 0 && !chatBusy && !sessionLoading && !pttListening;
  const welcomeText = !statusReady
    ? "Connecting…"
    : `Hi — I'm ${name}. Ask me anything; your chats appear in the sidebar.`;

  return (
    <div className="home-view flex flex-col h-full overflow-hidden">
      <StatusHeader status={status} />

      {/* Error banner */}
      {error && !chatBusy && (
        <div className="chat-error flex items-center gap-2 px-4 py-2 bg-[var(--armed)]/10 border-b border-[var(--armed)]/30 text-sm">
          <p className="error flex-1 m-0">{error}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 border-[var(--armed)]/40 text-[var(--armed)] hover:bg-[var(--armed)]/10"
            onClick={() => loadSession(sessionId)}
          >
            Retry
          </Button>
        </div>
      )}

      {/* Chat thread */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="chat-main px-4 py-3">
          {sessionLoading && messages.length === 0 ? (
            <div className="chat-loading muted text-sm">Loading chat…</div>
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
                  className={cn("chat-bubble", msg.role === "user" && "chat-bubble-user")}
                >
                  {msg.role === "assistant" && <Avatar name={name} size="sm" />}
                  <div className="chat-bubble-body">
                    <p>{msg.content}</p>
                  </div>
                </article>
              ))}

              {pttListening && (
                <article className="chat-bubble chat-bubble-listening">
                  <Avatar name={name} size="sm" />
                  <div className="chat-bubble-body">
                    <p className="muted">Listening… release mic or hotkey to send</p>
                  </div>
                </article>
              )}

              {chatBusy && !pttListening && !streamingTokens && (
                <article className="chat-bubble">
                  <Avatar name={name} size="sm" />
                  <div className="chat-bubble-body">
                    <div className="thinking-dots">
                      <span /><span /><span />
                    </div>
                  </div>
                </article>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </ScrollArea>

      <ChatInput
        onSend={onSend}
        disabled={!!error && messages.length === 0 && !sessionLoading}
        busy={chatBusy}
        pttListening={pttListening}
        onPttStart={onPttStart}
        onPttStop={() => onPttEnd(false)}
        onPttCancel={() => onPttEnd(true)}
      />
    </div>
  );
}
