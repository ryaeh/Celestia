# 03 — Local RAG over your stuff

**Pitch:** Point Celestia at a folder (and/or clipboard history + screenshot OCR) and ask
questions over it — fully offline. "Ask my files." "What did that contract say about
termination?" Your documents never leave the machine.

## Why this is a Celestia feature

Chroma is already in the stack for memory. The privacy story — *your documents are indexed
and queried entirely on-device* — is the entire pitch and the thing cloud RAG can't offer.

## How it works

- **New: corpus indexer** — walks configured workspace folders, chunks + embeds files into
  a dedicated Chroma collection (separate from memory). Incremental: re-index only changed
  files (mtime/hash).
- **Reuses:** the same embed/retrieve substrate as `skills/memory/store.py`; the security
  `scope.py` allowlist decides which folders are indexable.
- **Sources beyond files:** clipboard history and screenshot OCR text become first-class
  corpora — "where did I copy that command from?"
- **Retrieval → answer:** standard retrieve-then-read injected into the agent turn as
  context, with citations back to file paths/line ranges.

## Data & config

```yaml
rag:
  enabled: false
  corpora:
    - path: "C:/Users/me/Documents/notes"
      include: ["*.md", "*.txt", "*.pdf"]
  index_clipboard: false
  index_screenshots: false
  max_chunks_in_context: 8
```

## Security & privacy

- Indexable paths must be inside the `scope.py` workspace allowlist — no indexing outside
  approved folders.
- Clipboard/screenshot indexing is opt-in and respects the global pause toggle.
- Citations let the user see exactly what was retrieved.

## Integrates with

- **02 Time machine (●●●):** the episodic timeline is just another corpus — same
  index+retrieve code serves both; "ask my day" and "ask my files" unify.
- **04 Autonomy (●●):** RAG grounds multi-step tasks ("using my setup notes, configure X").
- **07 Hotkey (●●):** screenshot OCR from the read-hotkey feeds the screenshot corpus.
- **06 Affect (●●):** retrieval over past conversations sharpens personalized replies.

## Effort / risk

Medium. The retrieval half is mostly there; the indexer (chunking, incremental updates,
PDF parsing) is the new work. Phase 2, right after the episodic store so they share code.

## Open questions

- Embedding model: reuse memory's, or a dedicated one tuned for documents?
- PDF/Office parsing — which local libs stay lightweight enough for the lazy-import rule?
