---
id: "developer-storage-configuration-operations"
title: "Storage, Configuration, and Operations"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "storage", "configuration", "operations", "troubleshooting", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.96
content_hash: "b6c215fc1b0ea1a25f2a2e5e32b9032fcefd558a09438aec3fc049662a747241"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Storage, Configuration, and Operations

> [!abstract] Operational map
> Human-readable artifacts live in the vault. Runtime databases and caches live under `.jarvis`. Non-secret behavior is configured in `config/runtime.json`. Session credentials live only in the credential broker process.

## Vault Layout

| Location | Contents |
| --- | --- |
| `Plans` | User-reviewable plans and approval fields |
| `Reports` | Current-news and general reports |
| `Deep Research` | Long-form sourced research |
| `Projects/<project>` | Project brief and compact project memory |
| `Memories` | Compact durable facts and learned-topic notes |
| `Skills` | Skill candidates, validation evidence, and state |
| `Progress` | Trackers and productivity records |
| `Summaries` | Execution run notes and completion summaries |
| `Blockers` | Runs awaiting repair, decision, or external change |
| `Canvases/JARVIS` | Bounded derived visual views |
| `Templates` | Machine and user-entry Obsidian templates |
| `User Guide` | User and developer documentation |
| `Logs` | Human-readable audits and workflow logs |

## Internal Runtime Storage

| Path | Purpose |
| --- | --- |
| `.jarvis/memory.sqlite` | Markdown metadata, FTS, vectors, relationships, tasks, tombstones |
| `.jarvis/workflows.sqlite` | Run state, work items, leases, events, checkpoints, idempotency results |
| `.jarvis/model-runtime.sqlite` | Cross-process LM Studio generation leases and lifecycle events |
| `.jarvis/runs/<run>` | Frozen YAML, JSON manifest, approval envelope, results |
| `.jarvis/project_learning/<project>.json` | Repository snapshot, reading set, mapping diagnostics |
| `.jarvis/file_jobs/<fingerprint>.json` | Large-document map/reduce checkpoints |
| `.jarvis/canvas_history` | Archived rolling Canvas views |
| `.jarvis/skills` | Installed skill runtime metadata |
| `.jarvis/approval-signing-key.bin` | DPAPI-protected local approval signing material |

`.jarvis` is excluded from Markdown RAG scanning.

## Application Configuration

`Mark-XLVIII-main/config/runtime.json` contains non-secret settings for:

- assistant and speech mode;
- STT/TTS engines, devices, chunk sizes, and cooldowns;
- provider roles and model route order;
- LM Studio endpoints, baselines, TTL, load profiles, and generation limits;
- embedding model and retrieval weight;
- vault watcher and task-review behavior;
- MCP and optional bridge endpoints;
- project and workflow policy.

`core/runtime_config.py` rejects secret-looking fields during serialization. OpenAI keys must not be added to this file.

## Project Registry

`config/project_registry.json` maps stable project IDs to roots and policy. A project entry can constrain destructive actions, OpenClaw use, scientific interpretation, command roots, or tool availability.

The `project_key` stored in vault notes should match this stable ID. `project_id: jarvis_notes` identifies the owning vault; it is not sufficient to distinguish registered projects.

## Local Services

| Service | Default endpoint | Required? |
| --- | --- | --- |
| LM Studio inference | `127.0.0.1:1234/v1` | Required for local model calls |
| LM Studio native management | `127.0.0.1:1234/api/v1` | Required for managed load/unload |
| Orpheus bridge | `127.0.0.1:5006/v1` | Primary TTS; Windows fallback is available |
| MARK MCP HTTP | `127.0.0.1:8766` | Optional external tool clients |
| Aletheia bridge | `127.0.0.1:8765` | Optional; MARK remains independent |
| Dashboard | Runtime-managed local service | Optional; check startup logs for actual bind state |

Remember Me is optional and disabled for normal MARK memory. If enabled later, it must use a non-conflicting port and explicit configuration.

## Health Checks Through JARVIS

| Need | Operation |
| --- | --- |
| Loaded model and active lease status | `model_lifecycle.status` |
| Remove specialists after validation | `model_lifecycle.unload_non_baseline` |
| Capability and native tool health | `capability_registry.health` |
| Local RAG and optional backend status | `jarvis_memory.health` |
| Vault watcher state | `jarvis_memory.watch_status` |
| Rebuild local index | `jarvis_memory.reindex_local` |
| Force vector regeneration | `jarvis_memory.reindex_local` with `force_embeddings=true` |
| Workflow state and checkpoints | `dual_orchestrator.status` or `plan_workflow.status` |
| TTS primary/fallback state | speech capability or TTS runtime status |

## Common Failure Patterns

### JARVIS says a model returned no text

Check LM Studio reachability, active generation leases, selected model availability, and timeout/drain events. The router should not convert empty output into a successful artifact.

### Too many models appear loaded

Remember that `parallel=4` describes one loaded instance. Use lifecycle status to count actual `loaded_instances`. After a task, trigger idle cleanup or wait for the 300-second TTL.

### RAG returns unrelated notes

Confirm the note has the correct `project_key`, reindex the vault, inspect lexical and semantic candidate counts, and verify that the note is not an unresolved template. Use a project-scoped query.

### RAG is lexical-only

Check whether the Nomic Q4 embedding model is installed and whether another protected model generation is active. Lexical degradation is expected during a resource conflict; retry after the active lease finishes.

### A report contains no citations

Treat it as incomplete. Check structured search results, source count, and report validation. Do not save a generic synthesis as current news.

### A plan is paused for drift

Compare Markdown, YAML, and JSON action IDs and hashes. Rebuild the bundle through plan revision and obtain fresh approval; do not edit frozen run artifacts by hand.

### Voice overlaps or repeats

Check the Orpheus bridge queue, TTS player pending count, and generation leases. Current configuration should show one TTS worker and one pending utterance.

### Microphone cuts a turn short

Inspect `stt_turn_silence_seconds`, input RMS, selected device, and mute state. Increasing the silence interval trades response latency for longer pauses within a turn.

## Adding a Workflow

1. Define the human purpose and authority boundary.
2. Add capability L0/L1 metadata.
3. Define strict YAML with stable IDs and dependencies.
4. Register all tools, hooks, and commands.
5. Add deterministic acceptance criteria and compensation where relevant.
6. Define plan/report/memory artifacts.
7. Add routing triggers without allowing source evidence to select the workflow.
8. Test schema rejection, preflight, approval drift, cancellation, and successful execution.
9. Add this handbook and user guide references.

## Related Notes

- [[02 Capability Registry MCP and Safety]]
- [[06 Obsidian Memory RAG Tasks and Canvas]]
- [[09 Implementation Log and Known Boundaries]]
