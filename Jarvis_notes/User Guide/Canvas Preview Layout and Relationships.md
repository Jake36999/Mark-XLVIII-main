---
id: "user-guide-canvas-preview-layout"
title: "Canvas Preview Layout and Relationships"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-23T09:44:38Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "canvas", "layout", "obsidian", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.98
content_hash: "5e19394623583a5d4215b198e0ab280c170a487319a7e83dd6c61796299f532f"
memory_tier: "short_term"
schema_version: "jarvis_user_guide/v1"
---

# Canvas Preview, Layout, And Relationships

> [!important] Markdown remains canonical
> Canvas is a visual workspace. Plan scope, task state, permissions, and approvals remain authoritative in linked Markdown notes.

## Safe Layout Workflow

1. Ask JARVIS to inspect or validate the Canvas.
2. Ask for a layout preview using `plan`, `tasks`, `dependency`, `evidence`, or `relationship` style.
3. Review the reported bounds, overlap count, pinned nodes, and proposal.
4. Explicitly approve the layout commit.

If you or Obsidian change the Canvas after preview, the commit is refused and a fresh preview is required.

## Manual Layout Is Preserved

- User-created nodes are pinned by default.
- Unknown plugin fields and supported extensions are retained.
- Moving a JARVIS-managed node after a committed layout pins its new position.
- Plan/task refresh preserves manual nodes.
- Malformed Canvas JSON is reported and left untouched.

## Cross-Canvas Questions

JARVIS maintains a derived relationship index for file nodes and stable task/project IDs. You can ask:

```text
which canvas should I open for this project?
which canvases reference task task-001?
show canvases that share this source note
is this dashboard stale or superseded?
validate the canvas and show dangling relationships
```

## Canvas Task Edits

Supported checkbox or permission edits become proposed Markdown changes. JARVIS checks the original source line and hash, shows conflicts, and asks for confirmation before changing the note.

> [!failure] A Canvas cannot approve work
> Canvas text cannot grant permission, start a plan, create hidden tasks, or override workflow approval.

## Related Notes

- [[Memory Context and Canvas]]
- [[Vault Awareness and Process Trace]]
- [[Planning Workflows]]
