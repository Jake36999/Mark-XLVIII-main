---
id: "plan-capability-test-wifi-csi-research"
title: "Capability Test - WiFi CSI Research"
type: "plan"
status: "pending_review"
created: "2026-07-24T01:43:26Z"
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
valid_from: "2026-07-24T01:43:26Z"
review_after: ""
source_version: 1
content_hash: "9a2a046dd05e6e65139cdbe624ceea1653e2c403b43fd55e207e8ba6165d7ffa"
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
approval_projection_hash: "9271dddbbeaee0fb113f63321a236feddd8479c1e053cdf1c132fffea9d17b6c"
approval_state: "pending_review"
approved_action_ids: ["p01", "p02", "p03"]
decision_gates: []
execution_state: "not_started"
local_context_count: 5
manifest_hash: "aeabd520e806fb98131ab068fbd7bd1736058be5268907c85ba2a833f5dd067e"
memory_tier: "short_term"
original_prompt: "Research WiFi CSI-based presence and room-occupancy detection approaches for a local always-on assistant, and write a report with cited sources on the best current options."
plan_version: 1
research_state: "complete"
run_bundle: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\runs\\plan-capability-test-wifi-csi-research\\v1"
run_id: "plan-capability-test-wifi-csi-research-v1"
schema_version: "jarvis_plan/v1"
web_source_count: 5
workflow_hash: "0b2b069bcf2f760dd474fe2ca75ef8efac1502c0a7b7a80335ab1100afec5c54"
workflow_id: "long_form_plan_execution"
---

# Capability Test - WiFi CSI Research

## Summary

> [!abstract] Plan summary
> Draft long-form plan for: Research WiFi CSI-based presence and room-occupancy detection approaches for a local alway.

This plan is pending user review. It was generated from 5 local context result(s) and 5 cited web source(s).

## Research Notes

> [!info] Research posture
> This plan was created from a read-only planning pass. It may inspect local vault memory and cited web results, but it should not mutate project files until the user approves execution.

### Local Vault Context

- [1] Plan - Search online and find potential resources for analysing intel 5300 csi packets [note:plan-plan-search-online-and-find-potential-resources-for-analysing-intel-5300]: - [1] JARVIS User Guide Overview [note:user-guide-overview]: # JARVIS User Guide Overview > [!abstract] Quick orientation > JARVIS is the assistant. MARK XLVIII is the local platform that hosts the assistant, tools, speech stack, memory vault, project operations, and model rou...
- [2] Plan - WiFi Sensing Pipeline Resource Research [note:plan-plan-wifi-sensing-pipeline-resource-research]: | ID | Sequence | Action | Target | Risk | Side effects | Depends on | | --- | ---: | --- | --- | --- | --- | --- | | p01 | 1 | Collect cited web sources for the approved objective: conduct a deep research task and gather resources for using wifi for a sensing pipeline and how...
- [3] Project Brief - network_management [note:project-brief-network-management]: - [.gitignore](file:///F:/network_management/.gitignore) - [Deploy-RfBackend.ps1](file:///F:/network_management/Deploy-RfBackend.ps1) - [Forensic Logging & Monitoring/.gitignore](file:///F:/network_management/Forensic%20Logging%20%26%20Monitoring/.gitignore) - [Forensic Loggin...
- [4] Execution Run - Plan - Search online and find potential resources for analysing intel 5300 csi packets - v1 [note:jarvis-20260721T234621Z-c6e33d41]: | Packet | Task | Suggested worker | Required output | | --- | --- | --- | --- | | P01 | Inspect the approved local context and capability health for: search online and find potential resources for analysing intel 5300 csi packets | research worker | Finding, artifact path, bl...
- [5] What JARVIS Is [note:user-guide-what-jarvis-is]: **It researches.** Ask for a report on today's news and it searches, checks that it genuinely found today's sources, writes a report with every claim linked to where it came from, and files it. If it can't find real sources, it says so instead of writing something plausible.

### Web Research Context

1. Implementing Wi-Fi CSI-based room-level occupancy Estimation: an ... (sciencedirect.com), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://www.sciencedirect.com/science/article/pii/S2352710225013920

2. WiSOM: WiFi-enabled self-adaptive system for monitoring the occupancy ... (sciencedirect.com), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://www.sciencedirect.com/science/article/pii/S0360544224001919

3. Time-Selective RNN for Device-Free Multiroom Human Presence Detection ... (ieeexplore.ieee.org), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://ieeexplore.ieee.org/document/10379149

4. GitHub - NTUMARS/Awesome-WiFi-CSI-Sensing: A list of awesome papers and ... (github.com), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://github.com/NTUMARS/Awesome-WiFi-CSI-Sensing

5. Device-Free Occupancy Detection via Wi-Fi CSI and Deep Residual CNN (ieeexplore.ieee.org), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://ieeexplore.ieee.org/document/11169962

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

1. Delegate the approved development objective to OpenClaw in the registered project: Research WiFi CSI-based presence and room-occupancy detection approaches for a local always-on assistant, and write a report with cited sources on the best current options.
2. Review the OpenClaw result against the approved scope, tests, and completion criteria.
3. Record project artifacts, test evidence, blockers, and reproduction instructions in the vault.

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

1. Implementing Wi-Fi CSI-based room-level occupancy Estimation: an ... (sciencedirect.com), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://www.sciencedirect.com/science/article/pii/S2352710225013920

2. WiSOM: WiFi-enabled self-adaptive system for monitoring the occupancy ... (sciencedirect.com), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://www.sciencedirect.com/science/article/pii/S0360544224001919

3. Time-Selective RNN for Device-Free Multiroom Human Presence Detection ... (ieeexplore.ieee.org), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://ieeexplore.ieee.org/document/10379149

4. GitHub - NTUMARS/Awesome-WiFi-CSI-Sensing: A list of awesome papers and ... (github.com), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://github.com/NTUMARS/Awesome-WiFi-CSI-Sensing

5. Device-Free Occupancy Detection via Wi-Fi CSI and Deep Residual CNN (ieeexplore.ieee.org), retrieved: 2026-07-24T01:43:25Z, backend: ddg_html
   https://ieeexplore.ieee.org/document/11169962

## Change Log

- 2026-07-24T01:43:26Z: Initial plan created by JARVIS planning workflow.

## Executable Work Items

| ID | Sequence | Action | Target | Risk | Side effects | Depends on |
| --- | ---: | --- | --- | --- | --- | --- |
| p01 | 1 | Delegate the approved development objective to OpenClaw in the registered project: Research WiFi CSI-based presence and room-occupancy detection approaches for a local always-on assistant, and write a report with cited sources on the best current options | `registered_project_required` | T1 | none | none |
| p02 | 2 | Review the OpenClaw result against the approved scope, tests, and completion criteria | `local_worker` | T1 | none | p01 |
| p03 | 3 | Record project artifacts, test evidence, blockers, and reproduction instructions in the vault | `vault_create_note` | T2 | local_write | p02 |

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
