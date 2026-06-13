import { useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// MessageBody — the single rendering pipeline for assistant replies (UI V2
// foundation). Renders GitHub-flavored markdown with syntax-highlighted code
// blocks (+ per-block copy) and externally-opened links.
//
// Security: react-markdown does NOT render raw HTML (no rehype-raw), so model
// output can't inject markup/script into the shell — consistent with the
// prompt-injection posture. Keep it that way.
// ---------------------------------------------------------------------------

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false);
  const onClick = () => {
    const text = getText();
    if (!text) return;
    navigator.clipboard.writeText(text).then(
      () => {
        toast.success("Copied to clipboard");
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1400);
      },
      () => toast.error("Couldn't copy"),
    );
  };
  return (
    <button
      type="button"
      className="md-copy"
      data-copied={copied ? "1" : undefined}
      onClick={onClick}
      aria-label="Copy code"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

function PreBlock({ children }: { children?: ReactNode }) {
  const ref = useRef<HTMLPreElement>(null);
  return (
    <div className="md-code-wrap">
      <CopyButton getText={() => ref.current?.innerText ?? ""} />
      <pre ref={ref}>{children}</pre>
    </div>
  );
}

export default function MessageBody({ content }: { content: string }) {
  return (
    <div className="md-body">
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: PreBlock,
          a: ({ href, children }) => (
            <a
              href={href}
              onClick={(e) => {
                e.preventDefault();
                if (href) openUrl(href).catch(() => {});
              }}
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
