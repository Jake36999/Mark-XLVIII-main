---
id: "user-guide-index"
title: "User Guide Index"
type: "guide"
status: "draft"
created: "2026-07-21"
updated: "2026-07-23T02:52:44Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "index", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "bc02580cc770ce74d2b5519126fa6d2a53abd0d3bb759824fa82110839dffc7a"
memory_tier: "short_term"
---

# User Guide Index

> [!abstract] Guide map
> This note is the table of contents for the JARVIS user guide. Each linked note is vault-native Markdown and is indexed for local RAG.

## Core Notes

| Note | What it answers |
| --- | --- |
| [[What JARVIS Is]] | Plain-language explanation of the project for a non-technical reader |
| [[Overview]] | What JARVIS is, how MARK XLVIII fits, and how to phrase reliable requests |
| [[Command Palette]] | Copyable prompts for common workflows |
| [[Planning Workflows]] | Create Plan, Start Plan, execution run packets, summaries, and blockers |
| [[Tools Skills and Capabilities]] | Tool catalog, workflow catalog, boundaries, and examples |
| [[Memory Context and Canvas]] | Bounded RAG orientation, note relationships, Canvas views, and LM Studio load profiles |
| [[Vault Awareness and Process Trace]] | External Obsidian edits, one-time turn awareness, trace privacy, and keyboard controls |
| [[Canvas Preview Layout and Relationships]] | Safe layout previews, revision-bound commits, pinned nodes, and cross-Canvas lookup |
| [[Developer Handbook/00 Developer Handbook Index|Developer Handbook]] | In-depth runtime architecture, workflows, fan-out, memory, models, and operations |
| [[Glossary]] | Definitions for platform, memory, model, speech, and report terms |

## Common Jobs

| Job | Best route | Output |
| --- | --- | --- |
| Save a short fact | `save_memory` | `memory/long_term.json` plus a mirrored vault note |
| Save a Markdown note | `jarvis_memory.create_note` | A note in `Jarvis_notes` |
| Create a blank to-do template | `jarvis_memory.create_todo_template` | `Templates/to-do-list-template.md` |
| Learn a topic | `web_search` then `jarvis_memory.learn_topic` | Report in `Deep Research` plus memory in `Memories/learned_topics` |
| Search memory | `jarvis_memory.query_local` | Cited local RAG results |
| Orient with a hard context budget | `jarvis_memory.context_pack` | Compact cited context payload |
| Traverse note dependencies | `jarvis_memory.lookup_local` | Bounded typed relation graph |
| Refresh a plan/task Canvas | `jarvis_canvas` | Rolling `.canvas` view under `Canvases/JARVIS` |
| Create a plan | `plan_workflow.create_plan` | Reviewable plan in `Plans` |
| Start a plan | `plan_workflow.start_plan` | Execution run packet in `Summaries` |
| Create a cited news report | `web_search` then `jarvis_memory.create_report_from_search` | Markdown report in `Reports` |
| Analyze a document | `file_processor` | Summary or saved report |
| Analyze a folder | `file_controller`, `project_operator`, `jarvis_memory` | Folder summary or handoff note |
| Set a reminder | `reminder` | Local scheduled reminder |
| Check model load | `model_lifecycle` | Loaded model status and cleanup options |

## Stored Artifacts

> [!info] Vault layout
> `Jarvis_notes` is the source of truth for long-form memory. The JSON memory file is only a compact prompt cache.

| Artifact | Location |
| --- | --- |
| Reports | `Jarvis_notes/Reports` |
| Templates | `Jarvis_notes/Templates` |
| Plans | `Jarvis_notes/Plans` |
| Execution runs | `Jarvis_notes/Summaries` |
| Logs | `Jarvis_notes/Logs` |
| User guide | `Jarvis_notes/User Guide` |
| Plan and task Canvas views | `Jarvis_notes/Canvases/JARVIS` |
| Local RAG index | `Jarvis_notes/.jarvis/memory.sqlite` |
| Compact prompt cache | `memory/long_term.json` |

## Workflow Registry

| Workflow | Use for |
| --- | --- |
| `current_news_report` | Cited reports about today's/latest/current news |
| `learn_topic_memory` | Research, report, compact memory note, and RAG reindex for a topic |
| `todo_list_template` | Blank Obsidian checklist template creation |
| `long_form_plan_execution` | Reviewable long-form plans followed by gated execution |
| `deep_research_report` | Longer sourced research notes |
| `large_document_analysis` | Summaries and analysis of large files |
| `folder_analysis` | Folder scans and project summaries |
| `registered_project_handoff` | Codex/Claude/OpenClaw continuity notes |
| `browser_task_automation` | Browser navigation and page interaction |
| `local_file_management` | Reading, writing, moving, and inspecting local files |
| `scheduled_reminder` | Local timed reminders |
| `vault_markdown_note` | Canonical vault note creation |
| `short_term_json_memory` | Compact durable facts |
| `rag_memory_roundtrip` | Save, index, and retrieve a memory |
| `bounded_rag_orientation` | Select active tasks and relevant notes within hard context limits |
| `rolling_canvas_tracking` | Keep plan/task Canvas views current without unbounded node growth |

## Useful Meta Prompts

> [!example] Capability check
> ```text
> What tools and workflows do you have for this task?
> ```

> [!example] Workflow planning
> ```text
> Plan the workflow for this request before executing it: [request].
> ```
