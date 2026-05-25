/**
 * In-chat vision confirm flow (CC-49).
 *
 * Shows a screenshot preview bubble with a question input and
 * Confirm / Cancel buttons before sending to the vision model.
 */
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Camera, X, Send, Loader2 } from "lucide-react";
import Avatar from "./Avatar";

type VisionPreviewProps = {
  captureId: string;
  base64: string;
  agentName: string;
  busy: boolean;
  onConfirm: (question: string) => void;
  onCancel: () => void;
};

export default function VisionPreview({
  captureId,
  base64,
  agentName,
  busy,
  onConfirm,
  onCancel,
}: VisionPreviewProps) {
  const [question, setQuestion] = useState("Describe this screenshot.");
  const inputRef = useRef<HTMLInputElement>(null);

  function handleConfirm() {
    const q = question.trim() || "Describe this screenshot.";
    onConfirm(q);
  }

  return (
    <div className="vision-preview-wrap">
      {/* Screenshot bubble */}
      <article className="chat-bubble chat-bubble-user vision-bubble">
        <div className="chat-bubble-body">
          <div className="vision-img-wrap">
            <img
              src={`data:image/png;base64,${base64}`}
              alt="Screenshot"
              className="vision-img"
            />
            <span className="vision-img-label">
              <Camera size={11} style={{ display: "inline", marginRight: 4 }} />
              Screenshot captured
            </span>
          </div>
        </div>
      </article>

      {/* Confirm prompt */}
      <article className="chat-bubble vision-confirm-bubble">
        <Avatar name={agentName} size="sm" />
        <div className="chat-bubble-body">
          {busy ? (
            <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <Loader2 size={14} className="animate-spin" />
              Analysing…
            </div>
          ) : (
            <>
              <p className="text-sm mb-2 text-[var(--text-muted)]">
                Screenshot captured. What would you like to know?
              </p>
              <div className="flex gap-2">
                <Input
                  ref={inputRef}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleConfirm();
                    if (e.key === "Escape") onCancel();
                  }}
                  placeholder="Describe this screenshot."
                  className="flex-1 h-8 text-sm bg-[var(--bg-input)] border-[var(--border-light)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus-visible:ring-[var(--ring)]"
                  autoFocus
                />
                <Button
                  type="button"
                  size="sm"
                  className="h-8 gap-1 shrink-0"
                  onClick={handleConfirm}
                >
                  <Send size={12} />
                  Send
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0 shrink-0 text-[var(--text-muted)] hover:text-red-400"
                  onClick={onCancel}
                >
                  <X size={14} />
                </Button>
              </div>
            </>
          )}
        </div>
      </article>
    </div>
  );
}
