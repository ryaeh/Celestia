type ChatInputProps = {
  onSend: (message: string) => void;
  disabled?: boolean;
  busy?: boolean;
};

export default function ChatInput({ onSend, disabled, busy }: ChatInputProps) {
  const locked = disabled || busy;

  return (
    <div className="chat-input-wrap">
      <form
        className="chat-input-form"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const input = form.elements.namedItem("message") as HTMLInputElement;
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
          type="text"
          name="message"
          className="chat-input"
          placeholder={busy ? "Thinking…" : "Ask Celestia anything…"}
          disabled={locked}
          aria-label="Message Celestia"
        />
        <button
          type="submit"
          className="chat-send"
          disabled={locked}
          aria-label="Send"
        >
          {busy ? "…" : "↑"}
        </button>
      </form>
      <p className="chat-disclaimer">
        Celestia may make mistakes — verify important information.
      </p>
    </div>
  );
}
