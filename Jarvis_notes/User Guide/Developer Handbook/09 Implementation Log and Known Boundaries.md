---
id: "developer-implementation-log-boundaries"
title: "Implementation Log and Known Boundaries"
type: "log"
status: "active"
created: "2026-07-22"
updated: "2026-09-24T18:22:21Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "implementation-log", "validation", "known-boundaries", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.98
content_hash: "4b0a10b963d5923728750db0eaed239665445de422dc5cd9a31c0eb6fb292775"
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

### Gemini Live removal (2026-07-30)

- Deleted ten `JarvisLive` methods reachable only from a connection loop that could not run, plus the loop itself and the `_VisionSession` class in `screen_processor`.
- Replaced `types.FunctionResponse` with a local `ToolResponse`, removing a `google-genai` dependency from the live tool path.
- Removed the 8-second session poll from the dashboard command relay.
- Added `test_no_gemini_live_session_path_remains` so the path cannot return unnoticed.

### DeepInfra provider migration and cost-driven LM Studio decoupling (2026-09-23)

- Wired DeepInfra as a full `core/model_router.py` provider (text, tools, TTS); fixed a credential-broker link-probe bug (OpenAI's `/responses` shape doesn't work for DeepInfra) and a hardcoded `provider="openai"` mislabelling bug in the tool-call path.
- Flipped `planner`/`worker`/`research` routes from `lmstudio` to `deepinfra`, driven by measured cost, not a reliability finding — see [[07 Models Credentials Speech and Resource Lifecycle|Note 07]].
- Added `core/session_key_store.py` (opt-in persistent "remember this key") and `core/tts.py`'s `DeepInfraTTSEngine`.
- Fixed `WorkflowRuntime`'s model-concurrency semaphore, hardcoded to one slot regardless of `max_workers` since the only prior provider was LM Studio holding one local model in VRAM — no longer correct against a cloud provider, now defaults to `max_workers`.

### Canvas Mode 2 hardening: a document-writing role, dispatch bugs, and a centralised capability schema (2026-09-23/24)

- Added the `document` role (`_ROLE_SPECS`) — a plain vault-note write, distinct from `implementation`'s OpenClaw-gated path, closing a gap where a pure documentation goal had no role that could write anything durable without going through project-gated delegation for no reason.
- Found and fixed two real dispatch bugs live: `research`-role nodes were dispatching on the generic `worker` model tier, never the dedicated `research` route, because nothing set `inputs["role"]`; and the `research` role had no repair budget at all (`max_attempts: 1` by schema default), converting the first `REPAIR` verdict straight to `REJECT_REPLAN`.
- Added `WorkflowRuntime.retry_rejected_item` (a deliberate, human-invoked-only escape hatch for `REJECT_REPLAN`, mirroring `retry_escalated_item`) and a pre-dispatch tool-call intent check (`_check_tool_intent`) — see [[04 Fan-Out Workers Review and Recovery|Note 04]].
- Found `reviewer_provider` was never configured at all, silently falling through to a dead LM Studio default — fixed alongside the DeepInfra migration above.
- Added a `closing_check` step_type: a `verification` node whose ancestry never reaches an `implementation` node now gets a deterministic document-completeness check instead of running the full test suite against nothing relevant to it, routed purely from canvas graph structure at compile time.
- Added `core/capability_schema.py` — a single, stable capability data source that `tool_catalogue.py`, `canvas_plan.py`'s role specs, and (new) the compiled workflow schema's `target` enum all read from, replacing several independently-drifting hardcoded lists. Built an offline, two-step blind LLM pipeline (`scripts/derive_capability_keywords.py`) to derive tool keywords from functional descriptions rather than hand-typing them; found and fixed a real data gap along the way (`capability_registry` had no `CAPABILITY_HELP` entry, so the pipeline hallucinated a plausible-but-wrong description for it) and a real reliability gap (added a retry after an identical prompt scored 7 good scenarios once and zero the next call). See [[13 Canvas Planning Engine and Reasoning-Backed Decomposition|Note 13]] and [[02 Capability Registry MCP and Safety|Note 02]].

## Current Validation

> [!success] Automated suite
> The complete MARK test suite passed on 2026-09-24: **1336 passed**, under `pytest-xdist`, with the existing Python `audioop` deprecation warning. The suite was 1041 tests on 2026-07-30, 292 on 2026-07-22, and 880 before the finalisation work began.
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

### Gemini Live has been removed

Deleted on 2026-07-30: **758 lines** across `main.py` and `actions/screen_processor.py`, including ten methods reachable only from a connection loop that could not run.

It had been hardcoded off (`return bool(wants_gemini and False)`) rather than removed, and the cost of that half-measure was concrete:

- **Screenshot understanding was non-functional for the entire local-first era** — its only live path sat behind `if self._pending_vision and self.session:`. It captured the screen, said the image was arriving next turn, and answered from nothing.
- **Every dashboard command paid an 8-second delay**, polling for a session that could never appear before falling through to the path that actually answers it.
- **Every tool call depended on `google-genai`** — `_execute_tool` returned `types.FunctionResponse`, and the import set `types = None` on failure, so a machine without that SDK would have raised `AttributeError` on any tool use. Replaced with a local `ToolResponse`.

The lesson generalises: **a feature whose live path is behind a permanently-false guard reports success, produces plausible output, and passes review.** Nothing catches it — not the compiler, not the type checker, not the test suite. Prefer deletion to a disabled flag.

`test_no_gemini_live_session_path_remains` fails the suite if `self.session`, `genai.Client`, `live.connect`, or `send_client_content` reappears in `main.py`.

> [!warning] Two features went inert with it and are still unwired
> `SystemMonitor` threshold alerts and `ProactiveEngine` idle check-ins were only ever started as Live background tasks. The engines are untouched in `actions/system_monitor.py` and `actions/proactive.py` and each just builds a prompt string, so rewiring to router mode is a small job. Deliberately left unwired rather than kept as dead attributes.

> [!note] The Gemini *generative* API is a separate, larger surface
> `code_helper`, `computer_control`, `computer_settings`, `desktop`, `file_processor`, `flight_finder`, `web_search`, and `youtube_video` each define their own `_get_api_key()` and construct a `genai.Client`. That is not Live and was **not** touched by this removal. Whether those paths are reachable is unaudited and worth a separate pass.

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
- Get a real canvas Mode 2 run through to completion end-to-end with the `document`/`closing_check` pair live (the notebook_packager_v3.1.py spec experiment is the in-progress case — approved but not yet observed completing a full run).
- Compare `derive_capability_keywords.py`'s output against the hand-authored `CAPABILITY_HELP` keywords for all four tools by hand; nothing has actually consumed `derived_keywords` for ranking yet.
- Exercise the tool-call intent check (`_check_tool_intent`) and `retry_rejected_item` against a genuine live failure, not just the unit-test harness — neither has been observed catching a real problem in production use yet.

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
