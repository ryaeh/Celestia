import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Mic, MicOff, ArrowUp, Square, Camera, ScanEye, Sparkles, Monitor, Crop, AppWindow } from "lucide-react";
import { cn } from "@/lib/utils";

type CaptureMode = "fullscreen" | "region" | "active_window";

const CAPTURE_MODES: { mode: CaptureMode; label: string; Icon: typeof Monitor }[] = [
  { mode: "fullscreen", label: "Full screen", Icon: Monitor },
  { mode: "region", label: "Select region", Icon: Crop },
  { mode: "active_window", label: "Active window", Icon: AppWindow },
];

type ChatInputProps = {
  onSend: (message: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  busy?: boolean;
  pttEnabled?: boolean;
  pttListening?: boolean;
  onPttStart?: () => void;
  onPttStop?: () => void;
  onPttCancel?: () => void;
  visionEnabled?: boolean;
  onVisionCapture?: (mode: CaptureMode) => void;
  readScreenEnabled?: boolean;
  onReadScreen?: () => void;
};

export default function ChatInput({
  onSend,
  onStop,
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
  const [captureMenu, setCaptureMenu] = useState(false);

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
          <div className="relative shrink-0">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={cn("chat-ptt h-8 w-8", captureMenu && "chat-ptt-active")}
              disabled={locked || pttListening}
              aria-label="Capture screenshot"
              aria-haspopup="menu"
              aria-expanded={captureMenu}
              title="Capture screenshot"
              onClick={() => setCaptureMenu((v) => !v)}
            >
              <Camera size={16} />
            </Button>
            {captureMenu && (
              <>
                {/* click-away backdrop */}
                <button
                  type="button"
                  aria-hidden
                  className="fixed inset-0 z-40 cursor-default"
                  tabIndex={-1}
                  onClick={() => setCaptureMenu(false)}
                />
                <div
                  role="menu"
                  className="absolute bottom-full right-0 mb-2 z-50 min-w-[168px] rounded-lg border border-[var(--border-light)] bg-[var(--bg-panel)] p-1 shadow-lg"
                >
                  {CAPTURE_MODES.map(({ mode, label, Icon }) => (
                    <button
                      key={mode}
                      type="button"
                      role="menuitem"
                      className="flex w-full items-center gap-2 rounded px-3 py-1.5 text-left text-sm text-[var(--text)] hover:bg-[var(--bg-input)]"
                      onClick={() => {
                        setCaptureMenu(false);
                        onVisionCapture?.(mode);
                      }}
                    >
                      <Icon size={14} className="shrink-0 text-[var(--text-muted)]" />
                      {label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
        {readScreenEnabled && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="chat-ptt h-8 w-8 shrink-0"
            disabled={locked || pttListening}
            aria-label="Read active window"
            title="Read active window (preview, then confirm)"
            onClick={() => onReadScreen?.()}
          >
            <ScanEye size={16} />
          </Button>
        )}
        {busy && onStop ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="chat-send chat-stop h-8 w-8 shrink-0"
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop generating"
          >
            <Square size={14} />
          </Button>
        ) : (
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
        )}
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
