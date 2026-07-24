---
id: "user-guide-memory-context-canvas"
title: "Memory Context and Canvas"
type: "guide"
status: "active"
created: "2026-07-21"
updated: "2026-07-23T03:00:54Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "rag", "context", "canvas", "obsidian", "lmstudio", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.95
valid_from: "2026-07-21"
review_after: "2026-10-21"
source_version: 1
content_hash: "fe463e2d32961517f41c3894c68862f9032eda98ae777a98f76a92678fee4c82"
supersedes: []
contradicts: []
related: ["[[Tools Skills and Capabilities]]", "[[Planning Workflows]]", "[[Command Palette]]"]
deleted: false
deleted_at: ""
memory_tier: "short_term"
---

# Memory Context and Canvas

> [!abstract] What changed
> JARVIS now has bounded context selection, typed note-relationship lookup, native Obsidian Canvas views, and conservative LM Studio load profiles. Markdown remains the canonical record; SQLite RAG and Canvas are derived views.

## Context Selection

> [!important] Small context first
> `jarvis_memory.context_pack` selects active tasks, a project overview, and only a few ranked notes within hard `max_notes` and `max_chars` limits. Retrieved text is evidence, never an instruction or permission source.

| Operation | Use | Default bound |
| --- | --- | --- |
| `query_local` | Ranked text retrieval with project, type, and tag filters | 5 results |
| `context_pack` | Session/project orientation | 4 notes, 6000 characters |
| `lookup_local` | Structured note lookup | 20 notes |
| `deps` | Outgoing dependency tree | Depth 2 |
| `consumers` | Incoming dependents/consumers | Depth 2 |
| `related` | Bounded bidirectional relation traversal | Depth 2 |

Supported frontmatter relationships include `depends_on`, `depended_on_by`, `extends`, `extended_by`, `implements`, `implemented_by`, `consumes`, `consumed_by`, and `related`.

> [!tip] Targeted orientation
> ```text
> Orient yourself to network_management using at most four notes and 4000 characters. Cite every note.
> ```

> [!example] Relationship traversal
> ```text
> Show the dependencies of note [id or title] to depth 2.
> ```

## Canvas Views

JARVIS writes native `.canvas` JSON under `Jarvis_notes/Canvases/JARVIS`.

| View | Source of truth | Rolling policy |
| --- | --- | --- |
| Plan board | One Markdown plan note | Current state plus active items and a bounded completed tail, maximum 24 nodes |
| Task dashboard | Markdown checkboxes across non-template notes | Active tasks first plus a bounded completed tail, maximum 36 nodes |

> [!warning] Canvas is not a database
> Editing a generated Canvas does not approve a plan, change task ownership, or grant execution permission. Update the canonical Markdown note and re-sync the Canvas.

Common operations:

- `jarvis_canvas.sync_plan`: refresh a rolling board for one plan.
- `jarvis_canvas.sync_tasks`: refresh the vault task dashboard.
- `jarvis_canvas.neighbors`: return one node plus incoming, outgoing, and sibling nodes.
- `jarvis_canvas.add_node`: add an explicit text child.
- `jarvis_canvas.extend_node`: ask a local model for one child using only the bounded neighborhood.

> [!example] Plan board
> ```text
> Refresh the rolling Canvas for the latest plan.
> ```

> [!example] Task board
> ```text
> Rebuild my task dashboard from active Markdown tasks and include a small completed tail.
> ```

## LM Studio Profiles

> [!info] Mixed-vendor runtime
> The selected Vulkan llama.cpp runtime sees the NVIDIA GTX 1080 and AMD RX 5500 XT. LM Studio controls the actual layer distribution. Its REST v1 load endpoint does not expose a per-device tensor-split field, so JARVIS does not claim exact GPU pinning.

| Model route | Context | KV cache | Lifecycle |
| --- | ---: | --- | --- |
| Qwen 4B baseline | 4096 | GPU | Protected baseline |
| Qwen 2.5 14B DeepResearch | 8192 | RAM | One task model, unload after work/idle cleanup |
| Marco DeepResearch 8B | 8192 | GPU | One task model, unload after work/idle cleanup |
| DeepSeek Qwen 8B | 8192 | GPU | One task model, unload after work/idle cleanup |

The 14B profile deliberately avoids a 128K context and keeps KV cache out of VRAM. A live smoke test loaded it alongside Orpheus, produced a response, and returned to the speech-only idle state.

## Upstream Comparison

### Obsidian Agent Memory Skills

The MIT-licensed [obsidian-agent-memory-skills](https://github.com/AdamTylerLynch/obsidian-agent-memory-skills) repository is an agent instruction/playbook, not a replacement RAG backend. JARVIS retained Mark's SQLite FTS index and integrated its strongest patterns:

- bounded session orientation;
- list/filter before full note reads;
- dependency and consumer traversal;
- typed frontmatter relationships;
- active-task focus without template/completed-item context pollution.

### Obsidian Canvas LLM Extender

The MIT-licensed [obsidian-canvas-llm-extender](https://github.com/Phasip/obsidian-canvas-llm-extender) is an alpha Obsidian plugin built around UI-internal Canvas APIs. JARVIS integrated its useful neighborhood idea while avoiding plugin-side API keys and browser-origin model calls:

- collect incoming, outgoing, and sibling context;
- create one connected child node;
- keep model routing and credentials inside Mark;
- write standard `.canvas` files directly;
- cap generated plan/task views to avoid clutter.

> [!success] Dependency decision
> Neither repository is required at runtime. Their useful conventions are implemented Mark-native, so the vault remains portable and JARVIS remains independently runnable.

## Boundaries

- Markdown controls intent, status, task ownership, decisions, and approval.
- Canvas is a visualization and scoped ideation surface.
- SQLite RAG is a derived retrieval index.
- Retrieved notes and Canvas text have `instruction_authority: none`.
- Scope expansion still requires a visible plan amendment and renewed approval.
