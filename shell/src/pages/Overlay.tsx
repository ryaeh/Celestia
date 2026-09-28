import { useCallback, useEffect, useRef, useState } from "react";
import { Maximize2, Mic, Minus, Send, Square, X } from "lucide-react";
import Aura, { type AuraState } from "../components/Aura";
import MessageBody from "../components/MessageBody";
import {
  cancelChat,
  fetchChatHistory,
  fetchChatSessions,
  fetchPttStatus,
  pttCancel,
  pttStart,
  pttStop,
  streamChatMessage,
  type ChatMessage,
} from "../api";
import { useLiveState } from "../hooks/useLiveState";
import {
  expandFromBubble,
  hideOverlaySelf,
  isOverlayVisible,
  placeCollapsed,
  setOverlayVisible,
  showMainWindow,
  startDrag,
  trackCollapsedPosition,
} from "../lib/overlayWindow";
import { applyTheme, getStoredTheme } from "../theme";

// ---------------------------------------------------------------------------
// Companion overlay bubble — Celestia present on the desktop while you work or
// play. Collapsed: just the Aura orb (drag to move, click to open, right-click
// to hide). Expanded: a mini chat on the active session with push-to-talk.
// Mirrors /ws/state for "thinking" and for the global show/hide hotkey.
// ---------------------------------------------------------------------------

const RECENT = 8; // messages shown in the mini chat
const DRAG_THRESHOLD = 4; // px of pointer travel before a press becomes a drag
const PTT_POLL_MS = 400;

export default function Overlay() {
  const [expanded, setExpanded] = useState(false);
  const expandedRef = useRef(false);
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pttListening, setPttListening] = useState(false);
  const [pttRemote, setPttRemote] = useState(false); // PTT started elsewhere (global hotkey)
  const pttLocal = useRef(false);
  const press = useRef<{ x: number; y: number; dragging: boolean } | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const { state: live } = useLiveState();

  // ── Window lifecycle ──────────────────────────────────────────────────────
  useEffect(() => {
    void placeCollapsed();
    let stop = () => {};
    let disposed = false;
    void trackCollapsedPosition(() => !expandedRef.current).then((u) => {
      if (disposed) u(); // unmounted before the listener registered
      else stop = u;
    });
    // Theme changes in the main window reach us via the storage event.
    const onStorage = () => applyTheme(getStoredTheme());
    window.addEventListener("storage", onStorage);
    return () => {
      disposed = true;
      stop();
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  // Global hotkey / tray: each change of overlay_seq flips visibility. The
  // first frame is the baseline, not a request.
  const lastSeq = useRef<number | null>(null);
  useEffect(() => {
    const seq = live.overlay_seq;
    if (seq === undefined) return;
    if (lastSeq.current === null) {
      lastSeq.current = seq;
      return;
    }
    if (seq === lastSeq.current) return;
    lastSeq.current = seq;
    void isOverlayVisible().then((v) => setOverlayVisible(!v));
  }, [live.overlay_seq]);

  // PTT phase (so a hotkey-driven recording ripples the orb too).
  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const st = await fetchPttStatus();
        setPttRemote(st.listening && !pttLocal.current);
      } catch {
        /* API down */
      }
    }, PTT_POLL_MS);
    return () => clearInterval(t);
  }, []);

  const loadChat = useCallback(async () => {
    try {
      const { active_id } = await fetchChatSessions();
      const hist = await fetchChatHistory(active_id);
      setSessionId(hist.session_id || active_id);
      setMessages(hist.messages);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, streaming, expanded]);

  async function open() {
    expandedRef.current = true;
    setExpanded(true);
    setError(null);
    await expandFromBubble();
    await loadChat();
  }

  async function collapse() {
    expandedRef.current = false;
    setExpanded(false);
    await placeCollapsed();
  }

  // ── Orb: drag vs click ────────────────────────────────────────────────────
  function onOrbPointerDown(e: React.PointerEvent) {
    if (e.button !== 0) return;
    press.current = { x: e.screenX, y: e.screenY, dragging: false };
  }

  function onOrbPointerMove(e: React.PointerEvent) {
    const p = press.current;
    if (!p || p.dragging) return;
    if (Math.abs(e.screenX - p.x) + Math.abs(e.screenY - p.y) > DRAG_THRESHOLD) {
      p.dragging = true;
      void startDrag(); // the OS takes over; no pointerup reaches us
      press.current = null;
    }
  }

  function onOrbPointerUp() {
    const p = press.current;
    press.current = null;
    if (p && !p.dragging) void open();
  }

  // ── Chat ──────────────────────────────────────────────────────────────────
  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    setStreaming("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    try {
      for await (const ev of streamChatMessage(text, sessionId || undefined)) {
        if ("token" in ev) setStreaming((s) => s + ev.token);
        else if ("error" in ev) setError(ev.error);
        else if ("done" in ev) {
          setMessages(ev.messages);
          if (ev.session_id) setSessionId(ev.session_id);
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setStreaming("");
      setBusy(false);
    }
  }

  async function stop() {
    if (sessionId) {
      try {
        await cancelChat(sessionId);
      } catch {
        /* ignore */
      }
    }
  }

  async function onPttDown() {
    if (busy || pttLocal.current) return;
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

  async function onPttUp(cancel = false) {
    if (!pttLocal.current) return;
    pttLocal.current = false;
    setPttListening(false);
    if (cancel) {
      try {
        await pttCancel();
      } catch {
        /* ignore */
      }
      return;
    }
    setBusy(true);
    try {
      const r = await pttStop(sessionId || undefined);
      if (r.error) setError(r.error);
      if (r.messages) setMessages(r.messages);
      if (r.session_id) setSessionId(r.session_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const auraState: AuraState =
    pttListening || pttRemote ? "listening" : busy || live.busy ? "thinking" : "idle";

  if (!expanded) {
    return (
      <div className="overlay-root overlay-collapsed">
        <button
          type="button"
          className="overlay-orb"
          title="Celestia — click to chat, drag to move, right-click to hide"
          aria-label="Open Celestia"
          onPointerDown={onOrbPointerDown}
          onPointerMove={onOrbPointerMove}
          onPointerUp={onOrbPointerUp}
          onContextMenu={(e) => {
            e.preventDefault();
            void hideOverlaySelf();
          }}
        >
          <Aura size="hero" state={auraState} className="overlay-aura" />
        </button>
      </div>
    );
  }

  const recent = messages.filter((m) => m.content?.trim()).slice(-RECENT);

  return (
    <div className="overlay-root overlay-expanded">
      <div className="overlay-card">
        <header className="overlay-head" data-tauri-drag-region>
          <Aura size="mark" state={auraState} />
          <span className="overlay-title" data-tauri-drag-region>
            Celestia
          </span>
          <button type="button" className="overlay-icon" title="Open full window" onClick={() => void showMainWindow()}>
            <Maximize2 size={14} />
          </button>
          <button type="button" className="overlay-icon" title="Back to bubble" onClick={() => void collapse()}>
            <Minus size={14} />
          </button>
          <button type="button" className="overlay-icon" title="Hide bubble" onClick={() => void hideOverlaySelf()}>
            <X size={14} />
          </button>
        </header>

        <div className="overlay-messages" ref={listRef}>
          {recent.length === 0 && !streaming && (
            <p className="overlay-empty">Tap the mic or type — I'm right here.</p>
          )}
          {recent.map((m, i) => (
            <div key={i} className={`overlay-msg overlay-msg-${m.role}`}>
              {m.role === "assistant" ? <MessageBody content={m.content} /> : m.content}
            </div>
          ))}
          {streaming && (
            <div className="overlay-msg overlay-msg-assistant">
              <MessageBody content={streaming} />
            </div>
          )}
          {pttListening && <p className="overlay-hint">Listening… click the mic to send</p>}
          {error && <p className="overlay-error">{error}</p>}
        </div>

        <form
          className="overlay-input-row"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <button
            type="button"
            className={`overlay-icon overlay-mic${pttListening ? " is-live" : ""}`}
            title={pttListening ? "Stop and send" : "Talk (click again to send)"}
            onClick={() => void (pttListening ? onPttUp(false) : onPttDown())}
            onContextMenu={(e) => {
              e.preventDefault();
              if (pttListening) void onPttUp(true); // right-click = discard
            }}
            disabled={busy && !pttListening}
          >
            <Mic size={15} />
          </button>
          <input
            className="overlay-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") void collapse();
            }}
            placeholder="Message Celestia…"
            autoFocus
          />
          {busy ? (
            <button type="button" className="overlay-icon" title="Stop" onClick={() => void stop()}>
              <Square size={14} />
            </button>
          ) : (
            <button type="submit" className="overlay-icon" title="Send" disabled={!input.trim()}>
              <Send size={14} />
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
