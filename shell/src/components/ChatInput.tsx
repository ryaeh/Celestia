import { useRef } from "react";

type ChatInputProps = {
  onSend: (message: string) => void;
  disabled?: boolean;
  busy?: boolean;
  pttEnabled?: boolean;
  pttListening?: boolean;
  onPttStart?: () => void;
  onPttStop?: () => void;
  onPttCancel?: () => void;
};

export default function ChatInput({
  onSend,
  disabled,
  busy,
  pttEnabled = true,
  pttListening = false,
  onPttStart,
  onPttStop,
  onPttCancel,
}: ChatInputProps) {
  const locked = disabled || busy;
  const pttHeld = useRef(false);

  const endPtt = () => {
    if (!pttHeld.current) return;
    pttHeld.current = false;
    onPttStop?.();
  };

  const cancelPtt = () => {
    if (!pttHeld.current) return;
    pttHeld.current = false;
    onPttCancel?.();
  };

  return (
    <div className="chat-input-wrap">
      <form
        className="chat-input-form"
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const input = form.elements.namedItem(
            "celestia-chat-query",
          ) as HTMLInputElement;
          const text = input.value.trim();
          if (!text || locked) return;
          onSend(text);
          input.value = "";
        }}
      >
        <span className="chat-input-icon" aria-hidden>
          ✦
        </span>
        <input
          type="search"
          name="celestia-chat-query"
          id="celestia-chat-query"
          className="chat-input"
          placeholder={
            pttListening
              ? "Listening… release mic to send"
              : busy
                ? "Thinking…"
                : "Ask Celestia anything…"
          }
          disabled={locked || pttListening}
          aria-label="Message Celestia"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          data-form-type="other"
          data-lpignore="true"
          data-1p-ignore="true"
        />
        {pttEnabled && (
          <button
            type="button"
            className={`chat-ptt ${pttListening ? "chat-ptt-active" : ""}`}
            disabled={locked && !pttListening}
            aria-label={pttListening ? "Release to send" : "Hold to talk"}
            title="Hold to talk"
            onPointerDown={(e) => {
              if (locked || pttListening) return;
              e.preventDefault();
              (e.target as HTMLElement).setPointerCapture(e.pointerId);
              pttHeld.current = true;
              onPttStart?.();
            }}
            onPointerUp={(e) => {
              e.preventDefault();
              endPtt();
            }}
            onPointerCancel={() => cancelPtt()}
            onLostPointerCapture={() => endPtt()}
          >
            {pttListening ? "◉" : "🎤"}
          </button>
        )}
        <button
          type="submit"
          className="chat-send"
          disabled={locked || pttListening}
          aria-label="Send"
        >
          {busy ? "…" : "↑"}
        </button>
      </form>
      <p className="chat-disclaimer">
        Hold <span className="chat-ptt-hint">🎤</span> to talk — same thread as typed chat.
        Celestia may make mistakes — verify important information.
      </p>
    </div>
  );
}
