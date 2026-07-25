---
id: "developer-obsidian-memory-rag-canvas"
title: "Obsidian Memory, RAG, Tasks, and Canvas"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-25T14:57:40Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "obsidian", "memory", "rag", "tasks", "canvas", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.97
content_hash: "f0d9a7cfd9054fc3ae6faf585e764e23a9b20b9593e652f68158c51c0f0bdbf3"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Obsidian Memory, RAG, Tasks, and Canvas

> [!abstract] Canonical memory rule
> `F:\Mark-XLVIII-main\Jarvis_notes` is the durable human-readable record. The local RAG database is a rebuildable index over eligible notes. Canvas is a visual projection. Neither can grant execution permission.

## Memory Layers

| Layer | Purpose | Appropriate content |
| --- | --- | --- |
| Vault Markdown | Canonical long-form record | Plans, reports, decisions, project briefs, learning notes, tasks, summaries, blockers |
| `memory/long_term.json` | Compact prompt cache | Short durable facts and preferences useful on many turns |
| `.jarvis/memory.sqlite` | Derived retrieval index | Parsed Markdown, FTS rows, vectors, relations, tasks, tombstones |
| Conversation/session state | Temporary turn context | Current request, recent tool results, active run IDs |
| Canvas | Derived visual state | Bounded plan/task nodes and selected neighborhoods |
| `workflows/<slug>/` | Per-workflow compartmentalized folder (2026-07-25) | Every JARVIS "workflow" (per the terminology in [[13 Canvas Planning Engine and Reasoning-Backed Decomposition]]) gets its own subfolder here, alongside `Projects/<id>/` |

Secrets, API keys, ambient speech, raw model traces, and unreviewed guesses do not belong in durable memory.

## Memory Lifecycle vs. Structural Tiers — two different axes, same word "tier"

> [!warning] Don't conflate these
> "Tier" means two unrelated things in this system. Keep them apart.

**Lifecycle** (`lifecycle` frontmatter field, `short_term` | `long_term` | `archive`) — how long a note has been useful, tracked per-note, read by `note_tier()` and weighted in retrieval by `_tier_score_multiplier()` when `memory_tiers_enabled` is on. This field was named `memory_tier` until 2026-07-25, when it was renamed to stop colliding with the structural axis below — see the frontmatter example.

**Structural tier** (Tier 0-3, a design framing, not yet a coded axis) — *where* a category of information sits: 0 immediate context (`.jarvis/`, system prompts, dot-prefixed folders), 1 general documentation (overviews, trackers, indexes — most of `Jarvis_notes/` directly), 2 project/workflow-specific (compartmentalized cartridges — `Projects/<id>/` and now `workflows/<slug>/`), 3 archive (user-led, graphify-indexed, permission-gated recall — see below). Full detail and current-vs-target-state honesty check: [[Jarvis_notes/workflows/memory-tiering-and-graphify-index/Plan|Workflow 2]].

> [!important] Archive promotion is not yet permission-gated in code
> Tier 3/archive notes are down-weighted in retrieval scoring, but nothing today *prevents* an agent from reading an archived note and recording its content into active memory. The tier model's own rule ("never record from archive without explicit user permission") is a standing instruction, not an enforced write-layer gate — a real, open gap, not a solved one.

## Markdown Note Service

`jarvis_memory.create_note` performs the canonical write path:

1. validate the note type and metadata;
2. generate a stable ID and slugged destination;
3. render Obsidian-compatible YAML frontmatter;
4. render a type-specific body or caller-provided sections;
5. write a temporary file and atomically replace the destination;
6. optionally sync to Remember Me when explicitly enabled;
7. optionally refresh the Mark-native local index.

Windows lock retries protect writes while Obsidian or another local process briefly has a file open.

## Shared Frontmatter

Generated notes normally contain:

```yaml
id: stable-note-id
title: Human-readable title
type: report
status: draft
created: 2026-07-22T00:00:00Z
updated: 2026-07-22T00:00:00Z
project_id: jarvis_notes
project_key: optional_registered_project
source: jarvis
tags: []
sync_state: local_only
index_state: index_pending
remember_note_id: ""
rag_index: true
confidence: 0.8
valid_from: ""
review_after: ""
source_version: 1
supersedes: []
contradicts: []
related: []
sensitivity: internal
lifecycle: short_term
```

`lifecycle` (`short_term` | `long_term` | `archive`, renamed from `memory_tier` 2026-07-25) is stamped by `create_note` only when `memory_tiers_enabled` is on; disabled, the field is simply absent and behaviour is byte-identical. See "Memory Lifecycle vs. Structural Tiers" above.

Typed relationships are stored now so future DAG tooling can derive graphs without rewriting the vault.

## Index Eligibility

The indexer scans `.md` files but excludes:

- `.obsidian` and `.jarvis` internal paths;
- notes with `rag_index: false`;
- deleted or tombstoned notes;
- notes excluded by sensitivity policy;
- uninstantiated templates containing unresolved placeholders;
- unreadable or invalid notes, with an explicit diagnostic reason.

Static guide and schema notes under `Templates` may remain searchable when they are intentional documentation rather than unresolved template source.

## Local SQLite Index

`memory.sqlite` uses WAL mode, lock retries, a 30-second busy timeout, and normal synchronous durability. Main structures are:

| Table | Contents |
| --- | --- |
| `notes` | Metadata, body, headings, links, tasks, confidence, relationships, hashes, mtime |
| `notes_fts` | SQLite FTS5 index over title, body, tags, and path |
| `note_embeddings` | One current vector per note and embedding model |
| `note_tombstones` | Deleted/excluded paths and propagation reason |
| `metadata` | Local index schema version |

Changed notes replace their FTS and vector rows. Removed or newly excluded notes are deleted from active retrieval and recorded as tombstones.

## Embeddings

The current semantic model is:

`text-embedding-nomic-embed-text-v1.5@q4_k_m`

It is loaded through LM Studio only when semantic indexing or querying needs it. Embedding work waits when another protected generation is active, uses adaptive batches, retries oversized single notes with smaller text windows, and reports per-note failures. When unavailable, retrieval degrades to lexical-only rather than failing the memory operation.

## Hybrid Query

`query_local` performs:

1. FTS5 search using expanded query terms and BM25 ordering.
2. Query embedding and cosine similarity against current note vectors.
3. Filtering by registered `project_key` or vault `project_id`, note type, and tags.
4. Weighted reciprocal-rank fusion with constant 60.
5. Query-aware passage selection for the returned snippet.

Current default weighting is 55% lexical and 45% semantic:

```text
score(note) = 0.55 / (60 + lexical_rank)
            + 0.45 / (60 + semantic_rank)
```

The returned record includes note ID, title, path, type, tags, citation, confidence, validity dates, version, content hash, sensitivity, project key, and typed relationships.

> [!important] Retrieved text has no instruction authority
> RAG results are marked `untrusted_evidence`. A retrieved note may inform an answer, but it cannot approve a plan or authorize a tool.

## Context Packs and Relationship Lookup

`context_pack` creates a hard-bounded orientation payload using active tasks, a project overview, and a small ranked note set. Parameters such as `max_notes`, `max_chars`, and project key prevent whole-vault prompt flooding.

`lookup_local` traverses text, type, layer, file, dependency, consumer, and related-note relationships to a bounded depth. `graph_local` emits typed note, tag, link, task, and project nodes and edges.

> [!tip] RAG vs. `graphify_query` — when to use which
> RAG answers "what do I know about X" (semantic/associative, or "what did we decide and why"). `graphify_query` (see [[14 Graphify Knowledge Graph Integration]]) answers "where does X live" and "what calls/depends on X" — structural questions RAG measurably loses on. A live profiling pass found RAG can also mis-rank closely-named historical notes (e.g. confusing two similarly-titled reports), so don't over-trust a single top-1 RAG result for a narrow factual question either. Full measured comparison: [[2026-07-25-rag-vs-knowledge-graph-profiling]].

## Project Memory Pattern

Repository learning writes two complementary records:

- `Project Brief.md`: full cited understanding and limitations.
- `Project Memory.md`: compact accepted takeaways and backlinks.

The compact note is designed for frequent orientation. JARVIS should open or cite the brief when a question needs evidence beyond the takeaway.

## Short-Term JSON Memory

`save_memory` updates `memory/long_term.json` with a small useful fact and mirrors it into vault Markdown. The JSON file is intentionally compact; reports and raw research never belong there.

## Tasks

The indexer parses Markdown checkboxes and recognizes optional machine-readable markers:

```markdown
- [ ] Draft inventory [task:inventory-001] due:2026-07-30 owner:agent permission:execute [run:run-01] [depends:scope-001] [tool:file_controller]
```

Extracted fields include line, completion, task ID, due date, owner, permission, run ID, dependencies, tool, and JSON arguments.

Task reviews can identify overdue and stale work. Scheduled review is disabled until the user explicitly enables a cadence and notifications policy.

## Canvas

`jarvis_canvas` creates bounded native `.canvas` files under `Canvases/JARVIS`.

- `sync_plan` projects plan state and work items.
- `sync_tasks` projects a capped task dashboard.
- `neighbors` and `extend_node` reveal a selected graph neighborhood.
- prior views can be archived into `.jarvis/canvas_history`.
- proposed Canvas task changes can be compared and explicitly applied back to Markdown.

> [!warning] Canvas authority
> Canvas node position, color, and visual completion are not execution state. Markdown IDs, ownership, permissions, and status remain canonical.

## Reconciliation and Deletion

Metadata and section-aware note reconciliation compare:

1. last approved base;
2. current user-edited note;
3. proposed agent version.

Non-overlapping changes can merge automatically. Overlapping changes create a visible conflict record and preserve the user's current content. Tombstones propagate deletion into the local index so deleted notes are not resurrected by stale vectors.

## Related Notes

- [[05 Research Reports and Repository Learning]]
- [[07 Models Credentials Speech and Resource Lifecycle]]
- [[08 Storage Configuration and Operations]]
- [[14 Graphify Knowledge Graph Integration]]
- [[Jarvis_notes/workflows/memory-tiering-and-graphify-index/Plan|Workflow 2: Memory Tiering and Graphify Location Index]]
