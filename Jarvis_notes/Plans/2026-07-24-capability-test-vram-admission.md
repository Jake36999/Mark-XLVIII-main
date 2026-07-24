---
id: "plan-capability-test-vram-admission"
title: "Capability Test - VRAM Admission"
type: "plan"
status: "pending_review"
created: "2026-07-24T01:41:33Z"
updated: "2026-07-24T01:59:41Z"
project_id: "jarvis_notes"
source: "jarvis"
tags: ["plan", "workflow", "pending-approval", "tier-short-term", "capability-test"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T01:41:33Z"
review_after: ""
source_version: 1
content_hash: "7c3974a812d2f6e29a2ea2cc606bcfd208b17be2be9eca367e497f4daaf4aade"
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
agent_permission: "propose"
approval_projection_hash: "23320268debeb564a930fe8982fd89c147d102428085a3e2f7cef0bec2ebe0c8"
approval_state: "pending_review"
approved_action_ids: ["p01", "p02", "p03", "p04"]
decision_gates: []
execution_state: "not_started"
local_context_count: 5
manifest_hash: "84fe2401432741274d9cd48a31cb1f506a3f11d17c73588c29ebde52c79f4405"
memory_tier: "short_term"
original_prompt: "Design VRAM-aware model admission for MARK. Right now max_task_models_loaded is a flat count of 1, even though model_registry.MODEL_PROFILES already declares vram_gb per model and runtime.json declares a full lmstudio_host_profile with two GPUs (an 8GB GTX 1080 and an 8GB RX 5500 XT), neither of which is read by any selection or load path today. Replace the count-based budget with a byte-based budget so a small worker model and a larger VL model can coexist when their combined VRAM fits, treating the two GPUs as separate pools given the mixed-vendor Vulkan backend. Produce an actionable plan."
plan_version: 1
research_state: "complete"
run_bundle: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\runs\\plan-capability-test-vram-admission\\v1"
run_id: "plan-capability-test-vram-admission-v1"
schema_version: "jarvis_plan/v1"
web_source_count: 0
workflow_hash: "e0947ebf00426a6d6cfb5c66c9b6bd555322ff750ab41ecdfecb7fa1db79b5da"
workflow_id: "long_form_plan_execution"
---

# Capability Test - VRAM Admission

## Summary

> [!abstract] Plan summary
> Draft long-form plan for: Design VRAM-aware model admission for MARK. Right now max_task_models_loaded is a flat cou.

This plan is pending user review. It was generated from 5 local context result(s) and 0 cited web source(s).

## Research Notes

> [!info] Research posture
> This plan was created from a read-only planning pass. It may inspect local vault memory and cited web results, but it should not mutate project files until the user approves execution.

### Local Vault Context

- [1] Memory Context and Canvas [note:user-guide-memory-context-canvas]: > [!info] Mixed-vendor runtime > The selected Vulkan llama.cpp runtime sees the NVIDIA GTX 1080 and AMD RX 5500 XT. LM Studio controls the actual layer distribution. Its REST v1 load endpoint does not expose a per-device tensor-split field, so JARVIS does not claim exact GPU p...
- [2] Models, Credentials, Speech, and Resource Lifecycle [note:developer-models-credentials-speech]: > [!abstract] Split compute model > High-capability models plan, synthesize, and review. Smaller local models handle bounded work. Model lifecycle leases and quality floors prevent the runtime from treating every installed model or LM Studio parallel slot as an active agent.
- [3] Implementation Log and Known Boundaries [note:developer-implementation-log-boundaries]: - Added Create Plan, revision, decision gates, Start Plan, cancellation, summaries, and blockers. - Added strict `jarvis_dual_orchestrator/v1` YAML, legacy preview adapter, topological compiler, and immutable JSON manifest. - Added Markdown/YAML/JSON parity checks and DPAPI-ba...
- [4] JARVIS Remaining Features Live Validation Report [note:validation-jarvis-remaining-features-2026-07-22]: 1. LM Studio embedding loads incorrectly included LLM-only parameters. Embedding payloads now use their own supported profile. 2. OpenClaw delegation used the interactive TUI path, then encountered Windows `.cmd` argument truncation. It now uses the headless agent command and...
- [5] Obsidian Memory, RAG, Tasks, and Canvas [note:developer-obsidian-memory-rag-canvas]: > [!abstract] Canonical memory rule > `F:\Mark-XLVIII-main\Jarvis_notes` is the durable human-readable record. The local RAG database is a rebuildable index over eligible notes. Canvas is a visual projection. Neither can grant execution permission.

### Web Research Context

- No cited research results found for: Design VRAM-aware model admission for MARK. Right now max_task_models_loaded is a flat count of 1, even though model_registry.MODEL_PROFILES already declares vram_gb per model and runtime.json declares a full lmstudio_host_profile with two GPUs (an 8GB GTX 1080 and an 8GB RX 5500 XT), neither of which is read by any selection or load path today. Replace the count-based budget with a byte-based budget so a small worker model and a larger VL model can coexist when their combined VRAM fits, treating the two GPUs as separate pools given the mixed-vendor Vulkan backend. Produce an actionable plan.

## Desired Outcome

> [!success] Desired outcome
> A reviewed, executable plan with clear scope, milestones, gates, and summary expectations.

## Definition Of Done

- [ ] Plan reviewed in Obsidian.
- [ ] Scope and out-of-scope items are clear.
- [ ] Execution milestones are ordered.
- [ ] Blockers and design decision points are explicit.
- [ ] Approval gates are visible.
- [ ] Completion summary requirements are defined.

## Scope

### In scope

- Read-only research and context gathering.
- Plan, task, workflow, and delegation design.
- Vault note creation and local RAG indexing.
- Gated execution after user approval.

### Out of scope

- Destructive actions without confirmation.
- Heavy compute jobs without explicit approval.
- Treating generated plans as final user decisions.

## Task Ownership Assessment

> [!note] Ownership assessment
> No canonical Markdown task note was supplied for read-only classification.

## Milestones

| Milestone | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Research and context | JARVIS/User | Not started | |
| Plan review | JARVIS/User | Not started | |
| Approved execution | JARVIS/User | Not started | |
| Validation | JARVIS/User | Not started | |
| Summary and handoff | JARVIS/User | Not started | |

## Workflow Plan

1. Inspect the approved local context and capability health for: Design VRAM-aware model admission for MARK. Right now max_task_models_loaded is a flat count of 1, even though model_registry.MODEL_PROFILES already declares vram_gb per model and runtime.json declares a full lmstudio_host_profile with two GPUs (an 8GB GTX 1080 and an 8GB RX 5500 XT), neither of which is read by any selection or load path today. Replace the count-based budget with a byte-based budget so a small worker model and a larger VL model can coexist when their combined VRAM fits, treatin
2. Execute the approved objective through the safest registered capability.
3. Validate the result against the plan definition of done.
4. Create an execution summary or blocker note with evidence.

## Subagent Delegation

> [!warning] Delegation gate
> Subagents should not start until the user approves the plan.

| Worker | Use for | Default count | Gate |
| --- | --- | --- | --- |
| JARVIS router | Orchestration, status, tool selection | 1 | Always available |
| Local worker model | Routine summarization, extraction, classification | 1 | Use when local context is enough |
| High-tier planner | Ambiguous architecture, hard tradeoffs, final review | 1 | Use when cost is justified |
| OpenClaw | Coding continuity between Codex/Claude sessions | 1 | Requires explicit approval |

## Risks And Blockers

- Search results may be incomplete or stale.
- Local project context may be missing unless a project path is supplied.
- Execution may require user choices around scope, model cost, or safety gates.
- Subagents can drift without a visible plan and summary note.

## Decision Points

- Which parts of the plan are in scope for automated execution?
- Which project or folder is authoritative for implementation work?
- Which tasks require local-only models, high-tier models, or human review?
- What should stop execution and return to the user?

## Approval Gates

> [!danger] Stop before
> Delete, overwrite, move, broad refactors, browser submissions, purchases, account changes, heavy compute jobs, or multi-agent delegation.

- [ ] Plan approved by user.
- [ ] Destructive actions explicitly confirmed.
- [ ] High-cost model use approved when needed.
- [ ] Subagent delegation approved when needed.

## Next Actions

- [ ] User reviews this plan in Obsidian.
- [ ] User requests edits or approves execution.
- [ ] JARVIS updates the plan if the goal changes.
- [ ] JARVIS creates a summary or blocker note after execution starts.

## Sources

- No cited research results found for: Design VRAM-aware model admission for MARK. Right now max_task_models_loaded is a flat count of 1, even though model_registry.MODEL_PROFILES already declares vram_gb per model and runtime.json declares a full lmstudio_host_profile with two GPUs (an 8GB GTX 1080 and an 8GB RX 5500 XT), neither of which is read by any selection or load path today. Replace the count-based budget with a byte-based budget so a small worker model and a larger VL model can coexist when their combined VRAM fits, treating the two GPUs as separate pools given the mixed-vendor Vulkan backend. Produce an actionable plan.

## Change Log

- 2026-07-24T01:41:33Z: Initial plan created by JARVIS planning workflow.

## Executable Work Items

| ID | Sequence | Action | Target | Risk | Side effects | Depends on |
| --- | ---: | --- | --- | --- | --- | --- |
| p01 | 1 | Inspect the approved local context and capability health for: Design VRAM-aware model admission for MARK. Right now max_task_models_loaded is a flat count of 1, even though model_registry.MODEL_PROFILES already declares vram_gb per model and runtime.json declares a full lmstudio_host_profile with two GPUs (an 8GB GTX 1080 and an 8GB RX 5500 XT), neither of which is read by any selection or load path today. Replace the count-based budget with a byte-based budget so a small worker model and a larger VL model can coexist when their combined VRAM fits, treatin | `local_worker` | T1 | none | none |
| p02 | 2 | Execute the approved objective through the safest registered capability | `local_worker` | T1 | none | p01 |
| p03 | 3 | Validate the result against the plan definition of done | `local_worker` | T1 | none | p02 |
| p04 | 4 | Create an execution summary or blocker note with evidence | `vault_create_note` | T2 | local_write | p03 |

> [!warning] Approval boundary
> Only the IDs shown in this table may be dispatched. New child work requires a visible plan revision and renewed approval.

## Approval Decision

Mark exactly one box below, then save this note.

- [ ] **Approve** — execute the plan exactly as compiled.
- [ ] **Correct** — the plan needs changes before it can run.
- [ ] **Deny** — do not execute this plan.

> [!note] Correction details (only read if **Correct** is checked)
> Describe what should change.

> [!note] Reason for denial (only read if **Deny** is checked)
> Explain why this plan should not run.
