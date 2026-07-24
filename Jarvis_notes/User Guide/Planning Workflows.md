---
id: "user-guide-planning-workflows"
title: "Planning Workflows"
type: "guide"
status: "draft"
created: "2026-07-21"
updated: "2026-07-23T03:00:54Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "planning", "workflows", "subagents", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "565df03680e4d46ab9e59964096f7183c1dfc3104c22f505e6745f60c8da174b"
memory_tier: "short_term"
---

# Planning Workflows

> [!abstract] Purpose
> Planning workflows let JARVIS create a long-form Obsidian plan before attempting a complex task. The plan is reviewable, editable, and approval-gated.

## Flow

| Stage | What JARVIS does | Artifact |
| --- | --- | --- |
| Create plan | Runs a read-only local/context pass plus cited web research when enabled | `Jarvis_notes/Plans/*.md` |
| User review | User requests edits or approves execution | Updated plan frontmatter |
| Start Plan | JARVIS marks the plan in progress, injects the plan prompt, and creates an execution run packet | `Jarvis_notes/Summaries/*.md` |
| Execution | JARVIS works through sequenced packets using guarded tools and useful subagents | Work artifacts |
| Summary or blocker | JARVIS writes a completion summary or returns to user for a decision | `Summaries/*.md` or `Blockers/*.md` |
| Refinement | If the goal changes, JARVIS updates the plan | Revised plan |

## Create Plan Button

> [!tip] UI behavior
> Type the task into the command box, then click **CREATE PLAN**. JARVIS submits it as `create plan: [your prompt]`.

Example:

```text
Improve JARVIS report generation so current-news reports are always cited, reviewable, and saved in Obsidian.
```

JARVIS should then create a plan note in `Jarvis_notes/Plans`.

## Start Plan Button

> [!success] Deployment gate
> After reviewing the plan in Obsidian, click **START PLAN** to submit `start plan: latest`. If the command box contains a plan path, title, or hint, JARVIS uses that target instead.

Starting a plan does three things:

- Marks the source plan as `approved` and `in_progress`
- Creates an execution run note with system prompt injection, ordered packets, worker delegation rules, and synthesis instructions
- Refreshes the local vault index so the run packet is searchable

> [!caution] Still gated
> **START PLAN** does not approve destructive filesystem actions, high-cost model use, account/browser submissions, purchases, credential changes, heavy compute jobs, or extra subagents. Those still require explicit confirmation.

## Plan Template

A plan note should include:

- Summary
- Research Notes
- Desired Outcome
- Definition Of Done
- Scope
- Milestones
- Workflow Plan
- Subagent Delegation
- Risks And Blockers
- Decision Points
- Approval Gates
- Next Actions
- Sources
- Change Log

> [!important] Review gate
> A plan starts as `pending_review`. JARVIS should not execute the plan until the user clicks **START PLAN** or otherwise explicitly approves execution.

## Execution Run Packet

When a plan starts, JARVIS creates a run note containing:

- System Prompt Injection
- Sequenced Work Packets
- Agent Delegation
- Research Collection Protocol
- Subagent Report Protocol
- Synthesis Protocol
- Stop Conditions
- Sources
- Change Log

> [!example] Start latest plan
> `start plan: latest`

## Execution Rules

| Rule | Reason |
| --- | --- |
| Keep planning read-only | Avoid accidental system changes during research |
| Write the plan to the vault | Make the plan visible and editable in Obsidian |
| Use milestones | Keep execution resumable across Codex, Claude, OpenClaw, and local workers |
| Use subagents only when useful | Avoid unnecessary model load and duplicated work |
| Stop for important choices | Preserve user control over design direction |
| Write summaries/blockers | Keep continuity visible |

## Subagent Delegation

> [!warning] Delegation gate
> Subagents should not start until the user approves the plan.

| Worker | Best use | Default |
| --- | --- | --- |
| JARVIS router | Tool selection and orchestration | Always available |
| Local worker model | Routine extraction, summaries, small transforms | 1 worker |
| High-tier planner | Architecture, tradeoffs, final review | Use when justified |
| OpenClaw | Coding continuity between Codex/Claude sessions | 1 worker unless multi-agent is approved |

## Completion Notes

Use an execution summary when work completes:

```text
Create an execution summary for the approved plan.
```

Use a blocker note when work cannot continue:

```text
Create a blocker note explaining what decision is needed before continuing.
```

## Related Notes

- [[Command Palette]]
- [[Tools Skills and Capabilities]]
- [[Overview]]
