---
id: "user-guide-vault-awareness-process-trace"
title: "Vault Awareness and Process Trace"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "vault", "process-trace", "obsidian", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.98
content_hash: "c94178e278a52f5dad6f5b2dafdce2f9005a6ed0fe148dc9bb287f7a10f45240"
lifecycle: "short_term"
schema_version: "jarvis_user_guide/v1"
---

# Vault Awareness And Process Trace

> [!tip] Edit in Obsidian, then ask normally
> JARVIS watches Markdown in this vault. After you edit a note, ask about that note or ask “what changed in the vault?” The next relevant turn receives a short change summary automatically.

## What JARVIS Notices

- New, edited, moved, renamed, and deleted Markdown notes
- Changed headings and frontmatter fields
- Added or removed tasks and links
- A short substantive body diff when the note is eligible
- Whether lexical indexing and embeddings are current or pending

Rapid editor saves are combined. JARVIS writes are recognized and do not create a notification loop.

> [!warning] Private notes
> Notes marked private, confidential, secret, credential, or restricted expose change metadata only. Their body text is not added to turn context.

## Process Trace

When a turn starts, Router Mode opens a Process Trace above the answer. It can show selected workflows, tools, model route, vault context, retries, approvals, blockers, and completion.

The trace does **not** show hidden reasoning, prompts, keys, authorization headers, or complete note bodies.

| Control | Result |
| --- | --- |
| Category menu | Show one event category or all events |
| Pause/play | Pause or resume visual updates without discarding history |
| Follow | Keep the newest event visible |
| Clear | Clear this session's trace |
| Copy | Copy the selected safe summary |
| Export | Save a redacted, non-RAG Markdown trace |

## Keyboard Access

- `Ctrl+K`: command palette
- `Ctrl+Shift+O`: Operations and verified subsystem health
- `Esc`: interrupt the active turn
- `F4`: microphone mute
- `F11`: fullscreen

## Useful Requests

```text
what changed recently in the vault?
use my edits to the latest plan and revise it
is the vault index current?
show the model lifecycle status
validate my task dashboard canvas
which canvases reference this task?
```

## Related Notes

- [[Command Palette]]
- [[Canvas Preview Layout and Relationships]]
- [[Memory Context and Canvas]]
- [[Planning Workflows]]
