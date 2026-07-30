---
id: "developer-implementation-log-boundaries"
title: "Implementation Log and Known Boundaries"
type: "log"
status: "active"
created: "2026-07-22"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "implementation-log", "validation", "known-boundaries", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.98
content_hash: "2e7f08c6d8046d0d7faf21acde707cc82925b7deb607df2367d9112f1066dd17"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Implementation Log and Known Boundaries

> [!abstract] Snapshot
> This note records the implemented architecture as validated on 2026-07-22. It is a status document, not a promise that every native integration has been exercised against every external application.

## Milestone Log

### Local-first runtime and provider routing

- Decoupled router mode, tools, STT, and TTS from mandatory Gemini Live startup.
- Added LM Studio OpenAI-compatible routing and explicit quick/main/reasoning/code/vision/research/worker routes.
- Added session-only OpenAI credential linking with validation and local fallback.
- Kept JARVIS as the assistant identity and MARK XLVIII as the platform identity.

### Speech and turn safety

- Added local Vosk STT with English defaults and longer silence-based turn formation.
- Added Orpheus FastAPI TTS bridge, ordered chunking, a bounded utterance queue, and Windows fallback.
- Added stale-turn suppression, interruption, post-TTS cooldown, and filler idle gating.

### Capability and MCP layer

- Added registry-backed tools, workflows, L0 cards, L1 manifests, progressive schemas, and health.
- Added loopback MCP stdio/HTTP server with guarded `tools/call`.
- Restored web, weather, reminder, browser, file, project, system, speech, memory, model, and workflow awareness.

### Obsidian and memory

- Made `Jarvis_notes` canonical and retained JSON as a compact prompt cache.
- Added frontmatter templates, atomic writes, local FTS/vector RAG, project scoping, graph/tasks, tombstones, and watcher reindexing.
- Added report, deep research, learning, project brief, project memory, summary, blocker, and productivity artifacts.
- Added bounded Canvas projections while keeping Markdown authoritative.

### Model lifecycle

- Added native LM Studio list/load/unload management and task TTL.
- Kept Qwen 4B and Orpheus as baselines and limited the loaded task-model budget to one.
- Added persistent generation leases, timeout draining, idle cleanup, model provenance, and quality floors.
- Added on-demand Nomic Q4 embeddings with lexical degradation when unavailable.

### Planning and execution

- Added Create Plan, revision, decision gates, Start Plan, cancellation, summaries, and blockers.
- Added strict `jarvis_dual_orchestrator/v1` YAML, legacy preview adapter, topological compiler, and immutable JSON manifest.
- Added Markdown/YAML/JSON parity checks and DPAPI-backed approval envelopes.
- Added dependency-ready worker fan-out, model/OpenClaw resource slots, review verdicts, repair budgets, leases, checkpoints, idempotency, compensation, and crash recovery.

### Research and project learning

- Added structured, date-aware search results and citation-required report generation.
- Added resumable large-document extraction and chunk/map/reduce reports.
- Added read-only repository inventory, representative reading, cited synthesis, snapshot caching, and compact RAG takeaways.
- Added report-quality checks that reject unknown citations, uncited architecture, inventory contradictions, and truncated takeaways.

### Vision (2026-07-30)

- Added image content parts to the router; before this the payload had no field an image could occupy.
- Added `call_vision()`, local-only by construction, and `actions/vision_pipeline.py`.
- Replaced the dead Gemini injection branch in `main.py` with a local path that returns a real answer as the tool result.
- Added transcript cleanup for grounding markers, placeholder regions, and decode loops; added escalation from OCR to the scene model when the transcript is too thin to answer from.
- Corrected capture sizing from stream-appropriate (1280×720/JPEG 82/BILINEAR) to capture-appropriate (2560×1440/JPEG 92/LANCZOS).

## Current Validation

> [!success] Automated suite
> The complete MARK test suite passed on 2026-07-30: **1041 passed**, in 126s under `pytest-xdist` (`addopts = -n auto`), with the existing Python `audioop` deprecation warning. The suite was 292 tests on 2026-07-22 and 880 before the finalisation work began.
>
> `pytest.ini` deliberately sets **no** `testpaths`. Setting it to `tests` silently dropped six vendored tests from `jarvis-ui-components` — making the run faster must not make it smaller.

> [!tip] Run the configuration audit alongside the suite
> `python scripts/config_audit.py` reports where declared configuration and effective behaviour disagree. Green tests do not catch a value that was written in `config/runtime.json` and quietly transformed before use — two real defects this cycle were exactly that shape. Current state: no contradictions, 11 checks passed, 7 expected-transform notes.

Validated behaviors include:

- strict workflow schema and dependency checks;
- approval and hash drift detection;
- bounded fan-out and model/OpenClaw resource serialization;
- review, repair, escalation, cancellation, compensation, and recovery states;
- MCP discovery and guarded dispatch;
- vault creation, reconciliation, watcher behavior, RAG, graph, tasks, and Canvas;
- model lifecycle and routing fallbacks;
- speech queue, chunking, turn transitions, and noise/cooldown behavior;
- web report and repository-learning quality contracts.

Live RAG validation on the Knowledge Compiler Engine confirmed:

- project-scoped hybrid retrieval;
- 768-dimensional Nomic Q4 embeddings;
- query-relevant snippets and citations;
- correct retrieval of the audited `bypass_math.py` warning;
- 37 eligible indexed notes and 55 intentional exclusions at that snapshot;
- cleanup back to only the Qwen and Orpheus baseline models.

## Intentional Boundaries

### Model output remains fallible

Schemas, evidence checks, and review reduce errors; they do not make a local model authoritative. High-impact interpretation and unsupported claims still require evidence or user review.

### Scientific interpretation remains gated

JARVIS may inventory, orchestrate runs, gather resources, and prepare evidence for specialist projects. Final scientific interpretation remains with the user or designated analysis assistant when project policy says so.

### Dynamic child work is proposal-only

Workers can propose new work but cannot dispatch it. Scope expansion requires a visible amendment and renewed approval.

### Document maps are sequential inside one job

The large-document workflow checkpoints every chunk but currently maps chunks sequentially to protect the local model. Parallel source branches should be separate workflow items.

### Canvas is not a continuous task database

Canvas synchronization is bounded and explicit. Proposed Canvas edits require comparison and application back to Markdown. Markdown remains canonical.

### Scheduled productivity behavior is opt-in

Task scanning works on demand. Recurring reviews and notifications run only after explicit user permission and cadence configuration.

### Optional services remain optional

Aletheia, Remember Me, OpenClaw, and the dashboard are not required for Mark-native RAG and workflow execution. Their live availability should be checked before a workflow depends on them.

### Gemini Live is disabled, and anything behind it is dead code

`_gemini_live_enabled()` ends in `return bool(wants_gemini and False)`, so `self.session` is always `None`. This is stronger than "optional", and the distinction has already cost real capability: **screenshot understanding was non-functional for the entire local-first era** because its only live path sat behind `if self._pending_vision and self.session:`. It captured the screen, told the user the image was arriving next turn, and then answered from no visual input at all.

Fixed on 2026-07-30 (see [[07 Models Credentials Speech and Resource Lifecycle]]), but the class of defect is the lesson: a feature whose live path is behind a permanently-false guard reports success, produces plausible output, and passes review. When auditing capability, grep for `self.session` before trusting it.

### Native external tools require environment-specific validation

Browser automation, desktop control, messaging, media tools, weather providers, and reminders are registered and tested at the contract level. Live behavior still depends on the active browser, OS permissions, network, accounts, and external applications.

### Local hardware is capacity-constrained

Two GPUs improve model placement, but the safe runtime policy remains one active task generation and one loaded specialist. LM Studio parallel slots must not be treated as independent workers.

## Next Live-Validation Focus

- Exercise one complete deep-research plan from plan creation through cited report and RAG takeaway.
- Exercise one approved OpenClaw development handoff with an actual project change and test evidence.
- Interrupt a non-retry-safe external test action and inspect `UNKNOWN_OUTCOME` handling.
- Validate browser, reminder, weather, and desktop tools against the current host session.
- Exercise a user edit to an active plan and verify three-way reconciliation and renewed approval.
- Validate Canvas task changes flowing back into Markdown under explicit permission.

## Change Discipline

When implementation changes invalidate this handbook:

1. update the affected deep-dive note;
2. update this status snapshot;
3. run the focused tests and full suite;
4. reindex the vault;
5. query the changed subsystem through `jarvis_memory.query_local` to confirm JARVIS can retrieve the new contract.

## Related Notes

- [[00 Developer Handbook Index]]
- [[03 Planning Approval and Dual Orchestration]]
- [[04 Fan-Out Workers Review and Recovery]]
- [[08 Storage Configuration and Operations]]
