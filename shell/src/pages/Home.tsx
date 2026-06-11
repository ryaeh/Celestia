import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchChatHistory,
  fetchPttStatus,
  fetchStatus,
  pttCancel,
  pttStart,
  pttStop,
  streamChatMessage,
  visionCapture,
  visionAnalyze,
  type ChatMessage,
  type Status,
  type VisionCapture,
  type VisionCaptureMode,
} from "../api";
import StatusHeader from "../components/StatusHeader";
import ChatInput from "../components/ChatInput";
import Aura from "../components/Aura";
import VisionPreview from "../components/VisionPreview";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

const STARTER_CHIPS = [
  "What can you do?",
  "Read my screen",
  "Help me focus today",
  "Remember something for me",
];

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
  const [visionPending, setVisionPending] = useState<VisionCapture | null>(null);
  const [visionBusy, setVisionBusy] = useState(false);
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
  }, [messages, chatBusy, pttListening, visionPending]);

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

  async function onVisionCapture(mode: VisionCaptureMode = "fullscreen") {
    if (chatBusy || pttListening) return;
    setChatBusy(true);
    setError(null);
    try {
      const cap = await visionCapture(mode);
      setVisionPending(cap);
    } catch (e) {
      setError(String(e));
    } finally {
      setChatBusy(false);
    }
  }

  // Read screen = capture the active window, but through the same preview +
  // confirm flow as the camera menu (you see the shot and can add a question
  // before it's analyzed). The instant, no-confirm path lives in the global
  // read-screen hotkey (Feature 07), not on an in-chat button.
  function onReadScreen() {
    return onVisionCapture("active_window");
  }

  async function onVisionConfirm(question: string) {
    if (!visionPending) return;
    setVisionBusy(true);
    setError(null);
    try {
      const result = await visionAnalyze(visionPending.id, question, sessionId);
      setMessages(result.messages);
      onSidebarRefresh?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setVisionBusy(false);
      setVisionPending(null);
    }
  }

  function onVisionCancel() {
    setVisionPending(null);
    setVisionBusy(false);
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
  const visionEnabled = status?.vision_enabled ?? false;
  const showWelcome = messages.length === 0 && !chatBusy && !sessionLoading && !pttListening && !visionPending;
  const lastIdx = messages.length - 1;

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
          ) : showWelcome ? (
            <div className="chat-welcome" key={threadAnim}>
              <div className="welcome-aura-wrap">
                <Aura state="idle" size="hero" />
              </div>
              <h1 className="welcome-title">
                {statusReady ? `Hi, I'm ${name}.` : "Connecting…"}
              </h1>
              <p className="welcome-sub">
                Your on-device companion — chat, memory, voice, and screen awareness,
                all running locally. What's on your mind?
              </p>
              <div className="welcome-chips">
                {STARTER_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    className="welcome-chip"
                    onClick={() => onSend(chip)}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="chat-thread chat-thread-enter" key={threadAnim}>
              {messages.map((msg, i) =>
                msg.role === "user" ? (
                  <div key={`${i}-user-${msg.content.slice(0, 24)}`} className="msg msg-user">
                    <div className="msg-user-body">
                      <p>{msg.content}</p>
                    </div>
                  </div>
                ) : (
                  <div key={`${i}-asst-${msg.content.slice(0, 24)}`} className="msg msg-assistant">
                    <Aura
                      className="msg-aura"
                      size="chat"
                      state={i === lastIdx && streamingTokens ? "speaking" : "idle"}
                    />
                    <div className="msg-assistant-body">
                      <p>{msg.content}</p>
                    </div>
                  </div>
                ),
              )}

              {pttListening && (
                <div className="msg msg-assistant msg-listening">
                  <Aura className="msg-aura" size="chat" state="listening" />
                  <div className="msg-assistant-body">
                    <p>Listening… click the mic again to send.</p>
                  </div>
                </div>
              )}

              {visionPending && (
                <VisionPreview
                  captureId={visionPending.id}
                  base64={visionPending.base64}
                  agentName={name}
                  busy={visionBusy}
                  onConfirm={onVisionConfirm}
                  onCancel={onVisionCancel}
                />
              )}

              {chatBusy && !pttListening && !streamingTokens && !visionPending && (
                <div className="msg msg-assistant">
                  <Aura className="msg-aura" size="chat" state="thinking" />
                  <div className="msg-assistant-body">
                    <div className="thinking-dots">
                      <span /><span /><span />
                    </div>
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </ScrollArea>

      <ChatInput
        onSend={onSend}
        disabled={(!!error && messages.length === 0 && !sessionLoading) || !!visionPending}
        busy={chatBusy}
        pttListening={pttListening}
        onPttStart={onPttStart}
        onPttStop={() => onPttEnd(false)}
        onPttCancel={() => onPttEnd(true)}
        visionEnabled={visionEnabled}
        onVisionCapture={onVisionCapture}
        readScreenEnabled={visionEnabled}
        onReadScreen={onReadScreen}
      />
    </div>
  );
}
