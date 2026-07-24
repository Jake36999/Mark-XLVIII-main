---
id: "project-memory-quantule-mapper"
title: "Project Memory - quantule_mapper"
type: "memory"
status: "active"
created: "2026-07-22T02:57:00Z"
updated: "2026-07-23T09:35:03Z"
project_id: "jarvis_notes"
source: "F:\\Mark-XLVIII-main\\Jarvis_notes\\Projects\\quantule-mapper\\Project Brief.md"
tags: ["project-memory", "repository", "verified", "quantule-mapper", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.92
valid_from: "2026-07-22T03:46:34Z"
review_after: ""
source_version: 4
content_hash: "179847a44b514f109c7a7211aa8f596f6dbf8cd480359f1b57093c115d1b4d7f"
supersedes: []
contradicts: []
depends_on: []
depended_on_by: []
extends: []
extended_by: []
implements: []
implemented_by: []
consumes: []
consumed_by: []
related: ["project-brief-quantule-mapper"]
deleted: false
deleted_at: ""
audit_status: "verified_read_only"
memory_tier: "short_term"
project_root: "F:\\quantule_mapper"
snapshot_hash: "cc195e58fb39b0751a53d5decb5ed03a5f0ba2ba0a46e685d62921ae4786b6e5"
workflow_id: "project_repository_learning/v1"
---

# Project Memory - quantule_mapper

> [!info] Canonical report
> [[Projects/quantule-mapper/Project Brief|Project Brief - quantule_mapper]]

## Accepted Takeaways

- ASTE separates API/UI, orchestrator, and worker responsibilities and uses queued, lease-aware execution. [README.md](file:///F:/quantule_mapper/README.md)
- `app.py` is the main FastAPI control and telemetry surface. [app.py](file:///F:/quantule_mapper/app.py)
- The MCP server contains both read-only queries and explicitly labeled bounded write tools, requiring per-tool permission metadata. [mcp_server/server.py](file:///F:/quantule_mapper/mcp_server/server.py)
- `readme.json` contains a stale `G:` root; the current verified root is `F:/quantule_mapper`. [readme.json](file:///F:/quantule_mapper/readme.json)

## Retrieval Guidance

Use this compact note for orientation. Verify operational details against the canonical report and cited source files.
