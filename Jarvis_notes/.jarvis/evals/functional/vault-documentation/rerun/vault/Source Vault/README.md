---
title: "JARVIS Obsidian Workflow Templates"
type: "system-guide"
status: "active"
updated: "2026-07-21T16:34:17Z"
tags: ""
index_state: "indexed_local"
content_hash: "0add21a227cf293be23a9310f3fca8c7af4cd1b2b23f9163d48147ef74670ecf"
---

# JARVIS Obsidian Workflow Templates

This bundle contains 25 workflow templates that turn an Obsidian vault into a two-way workspace shared by the user and JARVIS. The notes are designed to remain comfortable for a person to read and edit while exposing predictable properties and lifecycle states for agents, automation, RAG, and future DAG generation.

No community plugin is required. The templates use Obsidian's core **Templates** and **Daily Notes** syntax.

## Core architectural rule

> [!important]
> **Obsidian is the canonical record. RAG is a derived recall index.**
>
> RAG entries must point back to their source notes. Retrieved memory may guide JARVIS toward relevant material, but important claims, permissions, and current state should be verified against the canonical Markdown note.

## Included workflow packs

### 1. Deep Research and Planning

| Template | Purpose |
| --- | --- |
| `01 Research Plan` | Defines the question, scope, workstreams, outputs, risks, and consolidation strategy |
| `02 Research Work Item` | Tracks one bounded investigation or planning subtask |
| `03 Evidence Note` | Records a source, claim, observation, or result with provenance |
| `04 Research Report` | Produces a structured report from a workstream |
| `05 Development Handoff` | Delegates bounded implementation work to OpenClaw or another development agent |
| `06 Consolidated Synthesis` | Combines reports while preserving meaningful disagreement and thematic contrast |
| `07 Research Takeaway` | Stores compact, RAG-ready conclusions linked to full reports |

### 2. Learning and Skills

| Template | Purpose |
| --- | --- |
| `01 Learning Plan` | Defines the learning goal, curriculum, evidence of mastery, and review rhythm |
| `02 Definition Note` | Stores a precise term, definition, examples, and boundaries |
| `03 Interpretation Note` | Records the user's or agent's reasoned interpretation of material |
| `04 Learning Source Note` | Processes a book, paper, course, video, or documentation set |
| `05 Exercise or Experiment` | Tests understanding through practice or observation |
| `06 Knowledge Gap` | Makes uncertainty and missing knowledge visible and actionable |
| `07 Learning Review` | Assesses progress, misconceptions, connections, and next steps |
| `08 Skill Candidate` | Proposes an executable skill without enabling it |
| `09 Skill Validation` | Tests a proposed skill and records the user's activation decision |

### 3. Productivity and Task Management

| Template | Purpose |
| --- | --- |
| `01 Task Intake` | Captures a task and gathers the information needed to classify it |
| `02 To-Do List` | Provides a simple user-facing task list with an agent-assistance review area |
| `03 Project Tracker` | Maintains the canonical state of a multi-step outcome |
| `04 Task Dashboard` | Presents active work, ownership, blockers, and review dates |
| `05 Agent Capability Assessment` | Determines which work JARVIS can perform, assist with, or only advise on |
| `06 Delegated Work Plan` | Records the approved scope, actions, constraints, and confirmation gates |
| `07 Progress Update` | Appends a concise checkpoint without rewriting the project history |
| `08 Completion Record` | Captures results, evidence, residual work, and lessons at closure |
| `09 Productivity Review` | Reviews tasks, projects, agent commitments, and system trustworthiness |

## Installation

1. Copy the `Templates` folder into the Obsidian vault.
2. Enable **Templates** under **Settings -> Core plugins**.
3. Set the copied folder as the template folder under **Settings -> Templates**.
4. Keep `SCHEMA.md` somewhere JARVIS can always read.
5. Use **Templates: Insert template** when creating a workflow document.

## Suggested vault structure

| Folder | Contents |
| --- | --- |
| `00 System` | Schema, workflow indexes, policies, and agent instructions |
| `10 Research/Plans` | Research and planning control notes |
| `10 Research/Work Items` | Bounded research tasks |
| `10 Research/Evidence` | Evidence and source records |
| `10 Research/Reports` | Workstream and consolidated reports |
| `20 Learning/Plans` | Learning programs and curricula |
| `20 Learning/Concepts` | Definitions and interpretations |
| `20 Learning/Sources` | Learning source notes |
| `20 Learning/Exercises` | Exercises and experiments |
| `20 Learning/Gaps` | Unresolved knowledge gaps |
| `20 Learning/Skills` | Skill candidates and validations |
| `30 Productivity/Tasks` | Task intake and task notes |
| `30 Productivity/Projects` | Project trackers and work plans |
| `30 Productivity/Updates` | Checkpoints and completion records |
| `30 Productivity/Reviews` | Dashboards and periodic reviews |

The numbering is optional. Stable IDs and links matter more than folder location.

## Workflow lifecycles

### Research

`Request -> Research Plan -> Work Items -> Evidence -> Reports -> Consolidated Synthesis -> Research Takeaways`

Development work can branch from a Work Item into a Development Handoff. The result returns to the parent workflow as evidence or a report.

### Learning

`Learning Goal -> Learning Plan -> Sources and Concepts -> Exercises -> Gap Review -> Learning Review`

Executable skills use a separate gate:

`Skill Candidate -> Human Review -> Validation -> User Approval -> Enabled`

Learning about a topic does not automatically authorize a new executable skill.

### Productivity

`Task Intake -> Capability Assessment -> User Approval -> Delegated Work Plan -> Progress Updates -> Completion Record`

Multi-step work should be attached to a Project Tracker and surfaced through a Task Dashboard or Productivity Review.

## RAG policy in brief

- Index concise takeaways, stable definitions, approved plans, current project state, decisions, knowledge gaps, and verified completion records.
- Do not index raw logs, secrets, unreviewed claims, duplicated source text, or speculative skill instructions.
- Use `rag_mode: takeaways-only` unless the entire note is intentionally compact and stable.
- Every indexed item must retain its note ID and source link.
- When a canonical note changes, update or invalidate the corresponding RAG entry.
- Superseded conclusions should remain traceable but must not be retrieved as current truth.

## Agent permission policy in brief

- `propose-only`: JARVIS can analyze and suggest actions but cannot execute them.
- `execute-approved-scope`: JARVIS can perform only the actions recorded in an approved work plan.
- `operator-nondestructive`: JARVIS can perform non-destructive operations within the recorded scope; listed actions still require confirmation.
- `blocked`: JARVIS must not act.

Approval can be `not-requested`, `requested`, `approved`, `denied`, or `revoked`.

> [!warning]
> Approval is scoped to a specific workflow and action set. It must not be inferred from unrelated approvals. Destructive actions, expensive compute, external publication, credential access, and material deployment changes require explicit confirmation.

## Naming conventions

- Research plan: `Research - Question or outcome`
- Work item: `Research Task - Bounded question`
- Evidence: `Evidence - Source or claim`
- Report: `Report - Workstream or theme`
- Synthesis: `Synthesis - Research topic`
- Takeaway: `Takeaway - Atomic conclusion`
- Learning plan: `Learn - Topic or skill`
- Definition: `Definition - Term`
- Interpretation: `Interpretation - Claim or model`
- Knowledge gap: `Gap - Missing knowledge`
- Skill candidate: `Skill Candidate - Capability`
- Project: `Project - Outcome`
- Task: `Task - Actionable result`
- Decision or completion: use a short, specific description.

## Template variables

- `{{title}}` - current note title
- `{{date:YYYY-MM-DD}}` - current date
- `{{date:YYYYMMDDHHmmss}}` - timestamp used in generated IDs
- `{{time:HH:mm}}` - current time

## Operating expectations for JARVIS

1. Preserve unknown properties and user-authored sections.
2. Never silently broaden an approved scope.
3. Prefer appending checkpoint sections over rewriting history.
4. Update `updated` and increment `version` after material agent edits.
5. Keep relationship fields reciprocal when practical.
6. Record evidence for important conclusions and completion claims.
7. Ask before resolving an ambiguity that changes ownership, permissions, cost, risk, or output direction.
8. Treat Canvas files and dashboards as views over canonical Markdown state.

See [[SCHEMA]] for the full machine-readable contract.
