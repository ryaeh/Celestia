import { useState } from "react";
import { Brain, ChevronDown, ChevronRight } from "lucide-react";
import type { ProvenanceEntry } from "../api";
import { originLabel } from "@/lib/memoryOrigin";

/**
 * "Why did you say that?" — an expandable row under a reply showing the memory
 * and knowledge-graph entries that were injected into the turn's context.
 * Renders nothing when the turn used no stored context.
 */
export default function MemoryProvenance({ entries }: { entries: ProvenanceEntry[] }) {
  const [open, setOpen] = useState(false);
  if (!entries || entries.length === 0) return null;

  return (
    <div className="provenance">
      <button
        type="button"
        className="provenance-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        title="What Celestia was remembering for this reply"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Brain size={12} />
        <span>
          {open ? "What I was remembering" : `What I was remembering (${entries.length})`}
        </span>
      </button>
      {open && (
        <ul className="provenance-list">
          {entries.map((e, i) => (
            <li key={`${e.id || e.kind}-${i}`} className="provenance-item">
              <span className={`provenance-kind provenance-kind-${e.source}`}>{e.kind}</span>
              <span className="provenance-text">{e.text}</span>
              {originLabel(e.origin) && (
                <span className="provenance-origin" title="Where this memory came from">
                  from {originLabel(e.origin)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
