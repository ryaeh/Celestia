import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Mic, MicOff, ArrowUp, Camera, ScanEye, Sparkles } from "lucide-react";
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
  visionEnabled?: boolean;
  onVisionCapture?: () => void;
  readScreenEnabled?: boolean;
  onReadScreen?: () => void;
};

export default function ChatInput({
  onSend,
  disabled,
  busy,
  pttEnabled = true,
  pttListening = false,
  onPttStart,
  onPttStop,
  visionEnabled = false,
  onVisionCapture,
  readScreenEnabled = false,
  onReadScreen,
}: ChatInputProps) {
  const locked = disabled || busy;
  const taRef = useRef<HTMLTextAreaElement>(null);

  function autosize() {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 168)}px`;
  }

  function submit() {
    const ta = taRef.current;
    if (!ta) return;
    const text = ta.value.trim();
    if (!text || locked || pttListening) return;
    onSend(text);
    ta.value = "";
    autosize();
  }

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
          submit();
        }}
      >
        <span className="chat-input-icon" aria-hidden><Sparkles size={16} /></span>
        <textarea
          ref={taRef}
          name="celestia-chat-query"
          id="celestia-chat-query"
          rows={1}
          className={cn("chat-input", "text-[var(--text)] placeholder:text-[var(--text-dim)]")}
          placeholder={
            pttListening ? "Listening… click mic to send" : busy ? "Thinking…" : "Ask Celestia anything…"
          }
          disabled={locked || pttListening}
          aria-label="Message Celestia"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          onInput={autosize}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter inserts a newline.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
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
        {visionEnabled && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="chat-ptt h-8 w-8 shrink-0"
            disabled={locked || pttListening}
            aria-label="Capture screenshot"
            title="Capture screenshot"
            onClick={() => onVisionCapture?.()}
          >
            <Camera size={16} />
          </Button>
        )}
        {readScreenEnabled && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="chat-ptt h-8 w-8 shrink-0"
            disabled={locked || pttListening}
            aria-label="Read screen"
            title="Read screen (auto-analyze active window)"
            onClick={() => onReadScreen?.()}
          >
            <ScanEye size={16} />
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
        Click <span className="chat-ptt-hint">mic</span> to start, click again to send.
        {visionEnabled && <> · <span className="chat-ptt-hint">Camera</span> to capture screen.</>}
        {readScreenEnabled && <> · <span className="chat-ptt-hint">Eye</span> to read active window.</>}
        {" "}Celestia may make mistakes.
      </p>
    </div>
  );
}
