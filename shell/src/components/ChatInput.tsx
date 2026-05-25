import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Mic, MicOff, ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";

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
}: ChatInputProps) {
  const locked = disabled || busy;

  function handleMicClick() {
    if (pttListening) {
      onPttStop?.();
    } else if (!locked) {
      onPttStart?.();
    }
  }

  return (
    <div className="chat-input-wrap">
      <form
        className="chat-input-form"
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const input = form.elements.namedItem("celestia-chat-query") as HTMLInputElement;
          const text = input.value.trim();
          if (!text || locked) return;
          onSend(text);
          input.value = "";
        }}
      >
        <span className="chat-input-icon" aria-hidden>✦</span>
        <Input
          type="search"
          name="celestia-chat-query"
          id="celestia-chat-query"
          className={cn(
            "chat-input",
            "border-0 bg-transparent shadow-none focus-visible:ring-0 focus-visible:ring-offset-0",
            "text-[var(--text)] placeholder:text-[var(--text-dim)]",
          )}
          placeholder={
            pttListening ? "Listening… click mic to send" : busy ? "Thinking…" : "Ask Celestia anything…"
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
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn("chat-ptt h-8 w-8 shrink-0", pttListening && "chat-ptt-active")}
            disabled={locked && !pttListening}
            aria-label={pttListening ? "Click to send" : "Click to talk"}
            title={pttListening ? "Click to send" : "Click to talk"}
            onClick={handleMicClick}
          >
            {pttListening
              ? <MicOff size={16} className="text-red-400 animate-pulse" />
              : <Mic size={16} />
            }
          </Button>
        )}
        <Button
          type="submit"
          variant="ghost"
          size="icon"
          className="chat-send h-8 w-8 shrink-0"
          disabled={locked || pttListening}
          aria-label="Send"
        >
          {busy ? <span className="text-xs">…</span> : <ArrowUp size={16} />}
        </Button>
      </form>
      <p className="chat-disclaimer">
        Click <span className="chat-ptt-hint">mic</span> to start talking, click again to send.
        Hotkey: <code>ctrl+alt+shift+v</code> (hold). Celestia may make mistakes.
      </p>
    </div>
  );
}
