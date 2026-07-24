---
id: "jarvis-20260724T014735Z-d61254ea"
title: "Canvas Plan Approval — Capability Test - Speech Fallback"
type: "plan"
status: "pending_review"
created: "2026-07-24T01:47:35Z"
updated: "2026-07-24T01:59:41Z"
project_id: "jarvis_notes"
source: "canvas_plan"
tags: ["canvas-plan", "approval", "capability-test-speech", "tier-short-term", "capability-test"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T01:47:35Z"
review_after: ""
source_version: 1
content_hash: "88f5869992a74ec85adfb0c7e7332326f3a01f76a80b8ecc8783878eb6945fe8"
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
related: []
deleted: false
deleted_at: ""
approval_path: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\canvas_approvals\\capability_test_speech\\v1\\approval.json"
approval_signature: "2a9e50e5bbdf4379f250d1f3c658ec8eea00d785a4c87f36307d632a979c7030"
approval_state: "approved"
approved_at: "2026-07-24T01:47:35Z"
bundle_path: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\canvas_approvals\\capability_test_speech\\v1"
canvas_path: "Canvases/JARVIS/capability-test-speech-fallback.canvas"
execution_state: "blocked"
manifest_hash: "63fb340f3d2f042e9498968a357ee93bdd2b17a6796b8e2ddb2f4ce4de3058f8"
memory_tier: "short_term"
plan_fingerprint_hash: "59a0263b2feb8be88948572dbeb604fcc910bc30872b6445cce5196b5220f3ea"
plan_version: 1
run_id: "capability_test_speech-v1"
workflow_hash: "29fd34add706da6ef4695485fd2ca4e7e47586538dba5ff8ce3ac8a2df7a07a0"
workflow_id: "capability_test_speech"
workflow_name: "Capability Test - Speech Fallback"
---

# Capability Test - Speech Fallback — Canvas Plan Review

**Workflow id:** `capability_test_speech`
**Steps:** 3

## Compiled Execution Order

| Order | Step | Type | Resource | Risk | Side effects | Confirm |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | MARK currently uses Vosk for local speech-to-text. Briefly research one realistic local alternative or fallback STT engine MARK could add if Vosk fails to load, and name the single most promising opti | model_reasoning | model | T1 | none | no |
| 2 | Review the research above: is the suggested fallback STT option genuinely realistic for a local-only Windows desktop assistant, or does it require cloud access / heavy new dependencies? | review | model | T1 | none | no |
| 3 | Given the reviewed finding, name in one sentence what would be needed to actually wire this fallback into MARK's existing speech pipeline. | model_reasoning | model | T1 | none | no |

## Approval Decision

Mark exactly one box below, then save this note.

- [x] **Approve** — execute the plan exactly as compiled.
- [ ] **Correct** — the plan needs changes before it can run.
- [ ] **Deny** — do not execute this plan.

> [!note] Correction details (only read if **Correct** is checked)
> Describe what should change.

> [!note] Reason for denial (only read if **Deny** is checked)
> Explain why this plan should not run.
