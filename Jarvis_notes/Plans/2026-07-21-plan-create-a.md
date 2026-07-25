---
id: "plan-plan-create-a"
title: "Plan - Create a"
type: "plan"
status: "pending_review"
created: "2026-07-21T10:54:53Z"
updated: "2026-07-25T14:33:56Z"
project_id: "jarvis_notes"
source: "jarvis"
tags: ["plan", "workflow", "pending-approval", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "f063b466227a46777ace3a4e3c207a350dfbe46f821f390955a3f34c331b681d"
approval_state: "pending_review"
execution_state: "not_started"
lifecycle: "short_term"
local_context_count: 5
original_prompt: "create a"
research_state: "complete"
web_source_count: 5
workflow_id: "long_form_plan_execution"
---

# Plan - Create a

## Summary

> [!abstract] Plan summary
> Draft long-form plan for: Create a.

This plan is pending user review. It was generated from 5 local context result(s) and 5 cited web source(s).

## Research Notes

> [!info] Research posture
> This plan was created from a read-only planning pass. It may inspect local vault memory and cited web results, but it should not mutate project files until the user approves execution.

### Local Vault Context

- [1] Planning Workflows [note:user-guide-planning-workflows]: # Planning Workflows > [!abstract] Purpose > Planning workflows let JARVIS create a long-form Obsidian plan before attempting a complex task. The plan is reviewable, editable, and approval-gated. ## Flow | Stage | What JARVIS does | Artifact | | --- | --- | --- | | Create plan...
- [2] Command Palette [note:user-guide-command-palette]: # Command Palette > [!abstract] Copyable prompt library > Use these prompts directly. They are written to trigger the right JARVIS tool or workflow without needing to know implementation details. > [!tip] Strong prompt formula > `action + target + output format + destination +...
- [3] User Guide Index [note:user-guide-index]: # User Guide Index > [!abstract] Guide map > This note is the table of contents for the JARVIS user guide. Each linked note is vault-native Markdown and is indexed for local RAG. ## Core Notes | Note | What it answers | | --- | --- | | [[Overview]] | What JARVIS is, how MARK X...
- [4] Tools Skills and Capabilities [note:user-guide-tools-skills-capabilities]: # Tools Skills and Capabilities > [!abstract] Registry-backed overview > This note summarizes the current JARVIS capability registry. Tools are direct calls. Workflows are ordered patterns that may use multiple tools. Skills are reusable task patterns exposed through the route...
- [5] Welcome [note:Welcome]: This is your new *vault*. Make a note of something, [[create a link]], or try [the Importer](https://help.obsidian.md/Plugins/Importer)! When you are ready, delete this note and make the vault your own.

### Web Research Context

1. Create a Gmail account - Google Help (support.google.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://support.google.com/mail/answer/56256?hl=en

2. Create a Google Account - Computer - Google Account Help (support.google.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://support.google.com/accounts/answer/27441?hl=en&co=GENIE.Platform=Desktop

3. Website Builder - Create a Free Website In Minutes | Wix.com (wix.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://www.wix.com/

4. Set up a private limited company: Register your company - GOV.UK (gov.uk), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://www.gov.uk/limited-company-formation/register-your-company

5. Canva: Visual Suite for Everyone (canva.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://www.canva.com/

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

## Milestones

| Milestone | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Research and context | JARVIS/User | Not started | |
| Plan review | JARVIS/User | Not started | |
| Approved execution | JARVIS/User | Not started | |
| Validation | JARVIS/User | Not started | |
| Summary and handoff | JARVIS/User | Not started | |

## Workflow Plan

1. Confirm objective, constraints, and success criteria with the user.
2. Collect read-only local context from the vault, relevant files, project registry, and capability manifest.
3. Collect cited web research when the task depends on current or external information.
4. Draft the plan as an Obsidian Markdown artifact and wait for review.
5. Revise the plan until scope, risks, and decision points are clear.
6. After approval, execute one milestone at a time using existing guarded tools and subagent delegation only when useful.
7. Update the plan when the goal changes, blockers appear, or major design choices are made.
8. Create an execution summary note when the work is complete or blocked.

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

1. Create a Gmail account - Google Help (support.google.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://support.google.com/mail/answer/56256?hl=en

2. Create a Google Account - Computer - Google Account Help (support.google.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://support.google.com/accounts/answer/27441?hl=en&co=GENIE.Platform=Desktop

3. Website Builder - Create a Free Website In Minutes | Wix.com (wix.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://www.wix.com/

4. Set up a private limited company: Register your company - GOV.UK (gov.uk), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://www.gov.uk/limited-company-formation/register-your-company

5. Canva: Visual Suite for Everyone (canva.com), retrieved: 2026-07-21T10:54:52Z, backend: ddg_html
   https://www.canva.com/

## Change Log

- 2026-07-21T10:54:53Z: Initial plan created by JARVIS planning workflow.
