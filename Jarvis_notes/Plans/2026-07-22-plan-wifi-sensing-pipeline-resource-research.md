---
id: "plan-plan-wifi-sensing-pipeline-resource-research"
title: "Plan - WiFi Sensing Pipeline Resource Research"
type: "plan"
status: "pending_review"
created: "2026-07-22T02:18:27Z"
updated: "2026-07-23T02:52:43Z"
project_id: "jarvis_notes"
source: "jarvis"
tags: ["plan", "workflow", "pending-approval", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-22T02:18:27Z"
review_after: ""
source_version: 1
content_hash: "c089c05d2fda761339905da479b6367fe1689ffe25f300827ed878dff83d8c3e"
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
approval_projection_hash: "3d1a9621e7781228b96fbb5d60b48fb90faed0e090d9bfca7c0a95ce393af796"
approval_state: "pending_review"
approved_action_ids: ["p01", "p02", "p03", "p04"]
decision_gates: []
execution_state: "not_started"
local_context_count: 2
manifest_hash: "3b75fa0d6246a2cc524e3c293f63f4c4f2fecde94b3231e317f3bc48a77fde55"
memory_tier: "short_term"
original_prompt: "conduct a deep research task and gather resources for using wifi for a sensing pipeline and how others are doing it, with or without a camera"
plan_version: 1
research_state: "complete"
run_bundle: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\runs\\plan-plan-wifi-sensing-pipeline-resource-research\\v1"
run_id: "plan-plan-wifi-sensing-pipeline-resource-research-v1"
schema_version: "jarvis_plan/v1"
web_source_count: 3
workflow_hash: "c31fdf030c1c5cd6b86114bd2fda208312c2029aa4275d894740dbff4b42aeeb"
workflow_id: "long_form_plan_execution"
---

# Plan - WiFi Sensing Pipeline Resource Research

## Summary

> [!abstract] Plan summary
> Draft long-form plan for: Conduct a deep research task and gather resources for using wifi for a sensing pipeline an.

This plan is pending user review. It was generated from 2 local context result(s) and 3 cited web source(s).

## Research Notes

> [!info] Research posture
> This plan was created from a read-only planning pass. It may inspect local vault memory and cited web results, but it should not mutate project files until the user approves execution.

### Local Vault Context

- [1] Plan - Search online and find potential resources for analysing intel 5300 csi packets [note:plan-plan-search-online-and-find-potential-resources-for-analysing-intel-5300]: # Plan - Search online and find potential resources for analysing intel 5300 csi packets ## Summary > [!abstract] Plan summary > Draft long-form plan for: Search online and find potential resources for analysing intel 5300 csi packets. This plan is pending user review. It was...
- [2] Execution Run - Plan - Search online and find potential resources for analysing intel 5300 csi packets - v1 [note:jarvis-20260721T234621Z-c6e33d41]: # Execution Run - Plan - Search online and find potential resources for analysing intel 5300 csi packets > [!success] Start Plan gate opened > The user explicitly started this plan. This authorizes JARVIS to begin non-destructive execution and delegation through existing confi...

### Web Research Context

1. StevenMHernandez/ESP32-CSI-Tool (GitHub), retrieved: 2026-07-22T02:18:27Z, backend: github_repositories
   https://github.com/StevenMHernandez/ESP32-CSI-Tool

2. Retsediv/WIFI_CSI_based_HAR (GitHub), retrieved: 2026-07-22T02:18:27Z, backend: github_repositories
   https://github.com/Retsediv/WIFI_CSI_based_HAR

3. joelewis012/CSIght (GitHub), retrieved: 2026-07-22T02:18:27Z, backend: github_repositories
   https://github.com/joelewis012/CSIght

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

1. [parallel] Collect cited web sources for the approved objective: conduct a deep research task and gather resources for using wifi for a sensing pipeline and how others are doing it, with or without a camera
2. [parallel] Query local vault context for the approved objective: conduct a deep research task and gather resources for using wifi for a sensing pipeline and how others are doing it, with or without a camera
3. Synthesize the gathered evidence, preserve citations, and identify unresolved contradictions.
4. Record research artifacts, accepted takeaways, source links, and remaining gaps in the vault.

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

1. StevenMHernandez/ESP32-CSI-Tool (GitHub), retrieved: 2026-07-22T02:18:27Z, backend: github_repositories
   https://github.com/StevenMHernandez/ESP32-CSI-Tool

2. Retsediv/WIFI_CSI_based_HAR (GitHub), retrieved: 2026-07-22T02:18:27Z, backend: github_repositories
   https://github.com/Retsediv/WIFI_CSI_based_HAR

3. joelewis012/CSIght (GitHub), retrieved: 2026-07-22T02:18:27Z, backend: github_repositories
   https://github.com/joelewis012/CSIght

## Change Log

- 2026-07-22T02:18:27Z: Initial plan created by JARVIS planning workflow.

## Executable Work Items

| ID | Sequence | Action | Target | Risk | Side effects | Depends on |
| --- | ---: | --- | --- | --- | --- | --- |
| p01 | 1 | Collect cited web sources for the approved objective: conduct a deep research task and gather resources for using wifi for a sensing pipeline and how others are doing it, with or without a camera | `web_search` | T1 | external_read | none |
| p02 | 2 | Query local vault context for the approved objective: conduct a deep research task and gather resources for using wifi for a sensing pipeline and how others are doing it, with or without a camera | `jarvis_memory` | T1 | local_read | none |
| p03 | 3 | Synthesize the gathered evidence, preserve citations, and identify unresolved contradictions | `web_search` | T1 | external_read | p01, p02 |
| p04 | 4 | Record research artifacts, accepted takeaways, source links, and remaining gaps in the vault | `vault_create_note` | T2 | local_write | p03 |

> [!warning] Approval boundary
> Only the IDs shown in this table may be dispatched. New child work requires a visible plan revision and renewed approval.
