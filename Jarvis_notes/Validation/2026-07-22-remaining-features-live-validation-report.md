---
id: "validation-jarvis-remaining-features-2026-07-22"
title: "JARVIS Remaining Features Live Validation Report"
type: "report"
status: "complete"
created: "2026-07-22T00:09:02+01:00"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "codex-live-validation"
tags: ["jarvis", "mark-xl-viii", "live-validation", "release-readiness", "openclaw", "rag", "mcp", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.97
valid_from: "2026-07-22"
review_after: "2026-08-05"
source_version: 1
content_hash: "61feedad472d94f78df1f3b4e9a53f95cb6fdf59dd0679dcb2143e7c2b435ce3"
related: ["[[2026-07-21-jarvis-implementation-progress-report]]", "[[2026-07-21-live-validation-ai-and-uk-politics-news-2026-07-21]]", "[[2026-07-21-openclaw-delegation-jarvis-openclaw-live-validation]]"]
lifecycle: "short_term"
workflow_id: "jarvis-finalization-live-validation"
---

# JARVIS Remaining Features Live Validation Report

> [!summary] Release conclusion
> **The core v1 implementation is live-validated and ready for supervised local use.** No required validation blocker remains. The remaining work is limited to explicitly deferred speech testing, optional media/document adapters, selected real-world side effects, and quality tuning for the Marco research fallback.

> [!important] Scope
> This run validated the features that remained after implementation. **STT and TTS were excluded by request** and are not represented as passing or failing here. JARVIS is the assistant; MARK XLVIII is the platform and interface.

## Decision

| Decision | Result |
|---|---|
| Core v1 go/no-go | **GO for supervised local use** |
| Required live blockers | **0** |
| Core automated regression | **244 passed** |
| ClawTeam/OpenClaw affected regression | **86 passed, 5 expected xfails** |
| Final MARK runtime | **One desktop process; dashboards healthy** |
| Final LM Studio task-model state | **Zero task models and zero generation leases** |

## Validation Matrix

| Area | Live result | Evidence summary |
|---|---|---|
| MARK and LM Studio runtime | **PASS** | MARK, LM Studio, dashboards, Aletheia, and OpenClaw reachable; duplicate MARK processes removed. |
| MCP capability server | **PASS** | Authentication, origin checks, discovery, read call, and write confirmation gate exercised externally. |
| Aletheia bridge | **PASS** | Live JSON-RPC capability call returned three verified executable pipeline capabilities. |
| Dual orchestrator and recovery | **PASS** | Real bounded fan-out, dependency sequencing, repair review, acceptance, and cancellation observed. |
| OpenClaw delegation | **PASS** | One bounded read-only worker returned a grounded terminal result and wrote a handoff note. |
| Skill acquisition lifecycle | **PASS** | Self-approval rejected; user-approved skill enabled, discovered, then deprecated. |
| Vault, local RAG, graph, tasks, Canvas | **PASS** | Write, reindex, hybrid retrieval, citations, relationships, task parsing, guarded Canvas update, and conflict record observed. |
| Embedding retrieval | **PASS** | LM Studio embedding endpoint returned 768-dimensional vectors with the corrected 2,048-token load profile. |
| Large document/folder workflow | **PASS** | Three mixed files mapped and reduced; second run resumed all three chunks from the same checkpoint. |
| Deep-research model lifecycle | **PASS with one degraded fallback** | Qwen 14B passed cleanly; Marco 8B responded but was repetitive and exhausted its output budget. Models ran sequentially. |
| Current web/news report | **PASS with fallback** | Seven same-day cited AI/UK-politics results persisted as a quality-checked Obsidian report. |
| Native reminders/browser/weather/desktop | **PASS for tested paths** | Temporary reminder lifecycle, live Edge control, Open-Meteo forecast, and read-only desktop operations passed. |
| Messaging | **SAFETY PASS** | Missing-recipient request stopped before side effects; no real message was sent. |
| Broad media/OCR adapters | **DEFERRED** | Optional binaries and representative media fixtures were not available. |
| STT/TTS | **EXCLUDED** | Deliberately outside this validation run. |

## Runtime Closure

The final restart removed competing MARK instances and launched the current code as one desktop process:

- MARK desktop: `pythonw.exe`, PID `8112` at validation close.
- Dashboard: `https://127.0.0.1:8000/` returned HTTP `200`, 26,564 bytes.
- Manual dashboard endpoint: `https://127.0.0.1:8001/` returned HTTP `200`, 26,564 bytes.
- LM Studio: `127.0.0.1:1234`, PID `8196`.
- Aletheia bridge: `127.0.0.1:8765`, PID `23252`.
- OpenClaw gateway: `127.0.0.1:18789`, PID `4532`.
- Exactly one MARK `main.py` process remained.

> [!success] Model cleanup
> The final lifecycle cleanup unloaded the stale DeepSeek task instance. Only baseline `qwen/qwen3-4b-2507` remained loaded. LM Studio reported `task_loaded_count: 0`, active generation count `0`, and no persistent leases. Its displayed `parallel: 4` is one loaded model configuration, not four agents or four model instances.

## MCP and Aletheia

The standalone MCP validation used a temporary local HTTP endpoint on port `8766` and proved:

- unauthenticated requests returned `401`;
- an invalid origin returned `403`;
- authenticated health and discovery succeeded using protocol `2025-11-25`;
- 30 guarded MARK tools were discoverable;
- a read-only external `tools/call` succeeded;
- an unapproved reminder write was rejected.

The currently running Aletheia TCP bridge accepted a live newline-delimited JSON-RPC `tools.call` request. `mcp_list_capabilities` returned:

1. `pipeline.code_review` v0.1.0;
2. `pipeline.investigation` v1.1.0;
3. `pipeline.patch_plan` v1.1.0.

The bridge's administrative health method remained disabled without a configured shared secret, which is the intended security posture. The broader skill scan retained ten verified skills and quarantined two ambiguous legacy definitions rather than executing them.

## Orchestration, Review, and Recovery

The workflow harness demonstrated real execution rather than manifest-only intent:

- independent non-model steps ran concurrently within the bounded fan-out limit;
- dependencies prevented early downstream dispatch;
- deterministic checks ran before model review;
- the reviewer returned `REPAIR`, a bounded correction ran, then review returned `ACCEPT`;
- cancellation stopped dependent dispatch and released active state;
- approval drift, parity, hidden-child rejection, orphan leases, idempotency, and crash recovery remain covered by automated tests.

> [!note] External side-effect boundary
> Recovery was proven for the local queue and controlled fixtures. No destructive or irreversible external operation was manufactured solely for testing. Such actions retain `UNKNOWN_OUTCOME`, confirmation, checkpoint, and human-review controls.

## OpenClaw Development Delegation

The final live handoff passed after correcting the Windows and lifecycle integration:

- team: `jarvis-live-1784673039917102000`;
- worker: `openclaw-live-validation-1-0d63ab`;
- named OpenClaw agent: `jarvis-worker`;
- model: baseline `qwen/qwen3-4b-2507`;
- worker count: one;
- task: read-only inspection of `runtime_validation\openclaw-live`;
- terminal result: directory correctly reported empty, with a safe next step and confidence `0.9`;
- elapsed time: approximately 73 seconds.

The worker was constrained to read/execute tools, denied write/edit/browser/messaging operations, and used one-shot completion rather than a polling loop. The multiline Windows prompt path now invokes the OpenClaw Node entry point directly, preserving arguments that `.cmd` wrapping previously truncated.

Evidence:

- [[2026-07-21-openclaw-delegation-jarvis-openclaw-live-validation]]
- `C:\Users\jakem\.openclaw\agents\jarvis-worker\sessions\clawteam-jarvis-live-1784673039917102000-openclaw-live-validation-1-0d63ab.jsonl`

## Vault, RAG, Graph, Tasks, and Canvas

A real vault note completed the canonical round trip:

1. atomic Markdown write with frontmatter;
2. local SQLite reindex;
3. cited hybrid retrieval using text, tags, links, relationships, recency, and semantic candidates;
4. 768-dimensional LM Studio embeddings;
5. typed graph and checkbox/task extraction;
6. rejection of an unconfirmed Canvas proposal;
7. application after confirmation;
8. visible conflict creation when concurrent content changed.

The bounded Canvas fixture produced 53 nodes and 52 edges. Markdown remains authoritative; Canvas is a managed visualization and proposal surface. Evidence: [[2026-07-21-live-vault-roundtrip]].

## Large Document and Folder Workflow

The live map/reduce fixture contained Markdown, plain text, and JSON files.

| Metric | First run | Resume run |
|---|---:|---:|
| Files considered | 3 | 3 |
| Segments | 3 | 3 |
| Chunks | 3 | 3 |
| Chunks resumed | 0 | 3 |
| Duration | 138.422 s | 30.469 s |
| Diagnostics | 0 | 0 |

Both runs used the same checkpoint:

`F:\Mark-XLVIII-main\Jarvis_notes\.jarvis\file_jobs\c9e160228b198c4d94b777e1ef513b2afa363bb116352424fef37295cedc292e.json`

The final report contained structured findings and source-grounded content. Result record: `F:\Mark-XLVIII-main\Mark-XLVIII-main\runtime_validation\results\document-workflow.json`.

## Deep-Research Models

Both research models were explicitly loaded, called, released, and unloaded **sequentially**. At no point did more than one task model remain loaded.

### Qwen2.5 14B DeepResearch i1

> [!success] Preferred local research synthesizer
> Load: 19.297 s. Generation: 12.234 s. Response: 20 tokens, concise and instruction-compliant. Result: **PASS**.

### Marco DeepResearch 8B

> [!warning] Functional fallback requiring prompt/output tuning
> Load: 11.422 s. Generation: 88.813 s. It returned useful text, but repeated the instruction and several `READY` sections until reaching the 384-token cap. Result: **FUNCTIONAL BUT DEGRADED**.

The production route correctly keeps Qwen 14B first and Marco second. Marco should remain a fallback until a stop sequence, lower reasoning budget, or model-specific response template controls repetition. Result record: `F:\Mark-XLVIII-main\Mark-XLVIII-main\runtime_validation\results\research-models.json`.

## Web Research and Reports

A live exact-date search for AI and UK politics returned seven cited results and generated:

[[2026-07-21-live-validation-ai-and-uk-politics-news-2026-07-21]]

The report retained URLs, source names, publication/retrieval provenance, source count, exact date scope, and quality validation. The optional DDGS package was unavailable, so Google News RSS supplied the clearly identified live fallback. No uncited generic filler was saved.

## Native Tool Checks

- **Reminder:** a temporary Windows reminder was created, listed, and cancelled.
- **Browser:** Edge opened a real page, exposed readable content, created a tab, and closed it.
- **Weather:** keyless Open-Meteo geocoding and forecast returned structured London data.
- **Desktop/computer:** read-only system status and safe random-data operations completed.
- **Messaging:** a missing-recipient request was stopped before dispatch; no real person was contacted.
- **Media:** `ffmpeg` and `ffprobe` were not found, so audio/video extraction remains optional and deferred.

## Defects Found and Corrected During Validation

1. LM Studio embedding loads incorrectly included LLM-only parameters. Embedding payloads now use their own supported profile.
2. OpenClaw delegation used the interactive TUI path, then encountered Windows `.cmd` argument truncation. It now uses the headless agent command and direct Node entry point.
3. One-shot OpenClaw workers inherited polling/commit instructions. Their prompt now has a bounded terminal-result contract.
4. OpenClaw session snapshots collided under concurrent Windows writes. Unique temp files, flush/fsync, and bounded lock retries were added.
5. Skill hashes differed after Windows newline normalization. Hashing now remains stable across the write/read cycle.
6. Browser, desktop, weather, and subprocess diagnostics contained CP1252-unsafe output. Runtime logging was made ASCII-safe.
7. The restart audit found two MARK instances. They were stopped after active leases cleared and replaced by one current-code desktop process.
8. A stale DeepSeek task model remained loaded after user activity. Final lifecycle cleanup removed it without interrupting work.

## Automated Regression

> [!success] MARK suite
> `244 passed, 1 warning in 38.60s`. The warning is Python's planned `audioop` deprecation, not a test failure.

> [!success] ClawTeam/OpenClaw affected suite
> `86 passed, 5 xfailed in 100.88s`, with unhandled-thread warnings promoted to errors. The five xfails are existing documented upstream/fork expectations.

## Deferred and Residual Work

These items do **not** block the core v1 supervised-use decision:

- STT turn-length, microphone capture, and TTS chunk ordering: excluded by request.
- Marco model quality tuning: functional but repetitive under the current generic probe.
- OCR/scanned PDF, presentation, archive, audio/video, and extreme-size fixture coverage.
- Long-duration large-vault performance and watcher soak testing.
- A real messaging send, which requires an explicit disposable recipient and user approval.
- Destructive or irreversible external recovery drills.
- Migration or permanent retirement of two quarantined ambiguous legacy Aletheia skills.
- Optional installation of DDGS and `ffmpeg`/`ffprobe`; current web fallback is functional without DDGS.

## Evidence Index

### Vault notes

- [[2026-07-21-jarvis-implementation-progress-report]]
- [[2026-07-21-live-validation-ai-and-uk-politics-news-2026-07-21]]
- [[2026-07-21-openclaw-delegation-jarvis-openclaw-live-validation]]
- [[2026-07-21-live-vault-roundtrip]]
- [[live-validation-read-only-gate]]

### Validation harnesses

- `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\live-validate-mcp.py`
- `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\live-validate-vault.py`
- `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\live-validate-workflow.py`
- `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\live-validate-skill.py`
- `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\live-validate-openclaw.py`
- `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\live-validate-document-workflow.py`
- `F:\Mark-XLVIII-main\Mark-XLVIII-main\scripts\live-validate-research-models.py`

## Final Assessment

> [!success] Closure
> The claim that "only live validation remained" was correct for the defined core v1 scope. Those remaining core validations are now complete. JARVIS can proceed to supervised day-to-day use, with the deferred adapters and speech checks treated as separate follow-up validation tracks rather than hidden release blockers.
