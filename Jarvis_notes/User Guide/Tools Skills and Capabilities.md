---
id: "user-guide-tools-skills-capabilities"
title: "Tools Skills and Capabilities"
type: "guide"
status: "draft"
created: "2026-07-21"
updated: "2026-07-29T21:53:32Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "tools", "capabilities", "workflows", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "4ad6ac3790fd7e71e968a1e39f5de7b0d3e92033d7de463c2fe9a44727c5343f"
lifecycle: "short_term"
---

# Tools Skills and Capabilities

> [!abstract] Registry-backed overview
> This note summarizes the current JARVIS capability registry. Tools are direct calls. Workflows are ordered patterns that may use multiple tools. Skills are reusable task patterns exposed through the router and registry.

> [!tip] Ask JARVIS directly
> ```text
> What tools do you have for this task, and which workflow would you use?
> ```

## Direct Tool Catalog

| Tool | Use for | Typical output | Risk |
| --- | --- | --- | --- |
| `capability_registry` | Tool help, workflow help, planning metadata | Manifest or workflow plan | Low |
| `web_search` | Current web/news/research/prices | Search results with sources | Low |
| `jarvis_memory` | Vault notes, reports, local RAG, graph/tasks | Markdown notes and cited memory results | Low |
| `graphify_query` | What calls/uses/depends on a symbol; relationship paths between two symbols | Structural answer from a pre-built code knowledge graph | Low |
| `process_trace` | What JARVIS just did — which tools ran, in what order, with what outcome | Phase-labelled list of real operations | Low |
| `jarvis_canvas` | Rolling plan boards, task dashboards, node neighborhoods | Native `.canvas` files | Low to medium |
| `plan_workflow` | Long-form plans, revisions, approvals, summaries, blockers | Reviewable plan and execution notes | Low to medium |
| `save_memory` | Short durable facts | JSON prompt cache plus vault mirror | Low |
| `file_processor` | Large files, documents, CSV/JSON/code analysis | Summary or derivative report | Low to medium |
| `file_controller` | Local file read/write/list/move/copy | File or folder changes | Medium |
| `project_operator` | Registered projects, scouting, handoffs, OpenClaw | Project status or handoff note | Medium |
| `browser_control` | Browser navigation, screenshots, page actions | Browser state or screenshot | Medium |
| `reminder` | Timed reminders | Local scheduled reminder | Low |
| `weather_report` | Weather and forecast checks | Weather summary | Low |
| `system_status` | CPU/RAM/GPU/temperature/process status | Local telemetry | Low |
| `model_lifecycle` | LM Studio status and cleanup | Loaded model status or cleanup result | Low to medium |
| `screen_process` | Screen/camera inspection | Answer about what is on screen or in view | Low |
| `speech` | STT/TTS status and voice capability | Capability answer | Low |

## Tool Details

### `capability_registry`

> [!info] Use when
> The user asks what JARVIS can do, whether a capability exists, or how a task should be planned.

Common operations: `list`, `search`, `describe`, `help`, `workflows`, `plan`, `manifest`, `health`, `mcp`.

### `web_search`

> [!important] Current information
> Use this for current facts. News reports should request `mode=news`, `require_citations=true`, and structured output.

Useful parameters: `query`, `mode`, `date_from`, `date_to`, `max_results`, `require_citations`, `output_format`.

### `jarvis_memory`

Creates Markdown notes in the Obsidian vault, syncs pending notes, indexes local RAG, queries memory, creates blank to-do/checklist templates, learns topics, builds graphs, extracts tasks, and exports DAG/training candidates.

Important operations: `create_note`, `create_todo_template`, `create_report_from_search`, `learn_topic`, `reindex_local`, `query_local`, `lookup_local`, `context_pack`, `deps`, `consumers`, `related`, `graph`, `tasks`, `dag_candidates`, `export_training_candidates`.

> [!tip] Context control
> Use `context_pack` for bounded project orientation. Use `lookup_local` for explicit `deps`, `consumers`, `related`, `type`, `layer`, `files`, or text lookup. Set `max_notes`, `max_chars`, and `depth` rather than loading whole folders into a prompt.

### `graphify_query`

> [!info] Use when
> The question is about how parts of a codebase relate — "what calls X", "what does X depend on", "what connects A to B" — rather than what you know or decided about something.

Wraps a pre-built local knowledge graph (`graphify`). Modes: `query` (free-form BFS traversal, default), `explain` (a symbol and its real neighbors), `path` (shortest relationship path between two named symbols — needs `target_b`). Read-only; never runs extraction itself. If no graph has been built yet for the target, it says so plainly rather than failing confusingly.

> [!tip] vs. `jarvis_memory`
> `jarvis_memory` answers "what do I know / what did we decide." `graphify_query` answers "where does this live / what touches this." Measured live, not assumed — see [[Developer Handbook/14 Graphify Knowledge Graph Integration|Note 14]].

### `process_trace`

> [!info] Use when
> You want to know what JARVIS actually *did* — which tools ran, in what order, and how each turned out.

Operations: `recent` (default), `turn` (needs a `turn_id`), `export` (writes the trace to a Markdown file; confirmation-gated because it writes).

> [!tip] vs. `capability_registry`
> `capability_registry` tells you what JARVIS **can** do. `process_trace` tells you what it **did**. Asking "what did you just do" used to reach the capability manifest and come back describing the tool inventory — these are now separate tools with separate routing.

### `jarvis_canvas`

Creates Mark-native Canvas files in `Canvases/JARVIS`. `sync_plan` is refreshed automatically when the plan workflow changes state. `sync_tasks` builds a capped dashboard from non-template Markdown checkboxes. `neighbors` and `extend_node` support scoped graph expansion without sending the whole Canvas to a model.

> [!warning] Authority boundary
> Canvas is a derived view. Plan approval, task ownership, permissions, and status remain in Markdown.

> [!tip] Learning operation
> `jarvis_memory.learn_topic` creates both a cited deep research report and a compact learned-topic memory note, then refreshes local RAG so future answers can cite the stored notes.

> [!tip] Template operation
> `jarvis_memory.create_todo_template` writes the standard blank Obsidian checklist template to `Templates/to-do-list-template.md` and reindexes the vault.

### `plan_workflow`

Creates and manages long-form plan documents in the vault. Use it for Create Plan, read-only research planning passes, plan revisions, Start Plan execution packets, approvals, execution summaries, and blocker notes.

> [!important] Plan approval
> Plan notes start as `pending_review`. Execution should not begin until the user clicks **START PLAN** or otherwise explicitly approves the plan.

Common operations: `create_plan`, `revise_plan`, `approve_plan`, `start_plan`, `create_summary`, `create_blocker`, `list_templates`.

### `save_memory`

Writes compact durable facts to `memory/long_term.json` and mirrors useful facts into the Markdown vault.

> [!warning] Memory boundary
> Use this for short facts and preferences, not secrets, API keys, background speech, or one-off commands.

### `file_processor`

Analyzes files such as text, Markdown, JSON, CSV, documents, code, archives, audio, and presentations. Use it for large document analysis before saving a report.

### `file_controller`

Reads, writes, lists, creates, copies, moves, renames, searches, and inspects local files and folders.

> [!caution] File safety
> Delete, overwrite, bulk move, and broad rename actions should be confirmation-gated.

### `project_operator`

Works with registered projects through Mark/Aletheia. Supports listing, status, scouting, code maps, handoffs, OpenClaw delegation, and policy-gated operations.

### `browser_control`

Controls browsers for navigation, search, clicking, typing, screenshots, tab management, and page inspection.

> [!warning] Browser safety
> Account changes, purchases, form submissions, and sensitive actions should ask for confirmation.

### `model_lifecycle`

Reports loaded LM Studio models, baseline models, task model cleanup, native load profiles, and non-baseline unloads. The Vulkan runtime sees both installed GPUs; conservative model profiles cap context and KV-cache use before inference. It should not unload protected baseline speech or worker models.

### `screen_process`

Captures your screen or webcam and answers a question about it, using local models only. The image never leaves the machine.

Ask naturally — "what's on my screen?", "is there an error visible?", "what am I looking at?"

**Screen** captures go to an OCR model first, which transcribes the text, and a text model answers your question from that transcription. If the OCR model reads too little to answer from — which happens on cluttered application windows rather than document-like screens — it escalates automatically to the vision model, which describes the screen instead. **Camera** captures skip OCR entirely and go straight to the vision model, since a photo of a room has no text to transcribe.

> [!note] Expect this one to be slow
> A screen question can load two models in sequence when the escalation fires. Measured at up to ~145 seconds on this machine. Setting `vision_screen_strategy` to `scene_only` in `config/runtime.json` uses one model instead of two, which is faster and better on busy application windows, at the cost of reading dense documents and tables less well.

> [!warning] What is on screen is data, never instructions
> Text captured from your screen is treated as untrusted, the same as a web page or a retrieved note. It cannot grant permission, choose tools, or authorise actions — so a page telling JARVIS to run something will not cause it to run.

### `speech`

Local speech capability. STT can use Vosk. TTS can use Windows, EdgeTTS, Kokoro, or OpenAI-compatible local endpoints such as Orpheus.

> [!note] Gemini dependency
> Gemini Live is optional. Local speech, tools, reminders, reports, and vault memory do not require Gemini Live.

## Workflow Catalog

| Workflow | Trigger phrase | Invokes | Artifact |
| --- | --- | --- | --- |
| `current_news_report` | "today's AI news report" | `web_search`, `jarvis_memory` | Cited report in `Reports` |
| `learn_topic_memory` | "learn about..." | `capability_registry`, `web_search`, `jarvis_memory` | Cited report in `Deep Research` plus memory in `Memories/learned_topics` |
| `todo_list_template` | "blank to-do list template" | `jarvis_memory` | Blank checklist template in `Templates` |
| `long_form_plan_execution` | "create plan..." or "start plan..." | `plan_workflow`, `web_search`, `jarvis_memory`, `project_operator` | Plan in `Plans`, execution run in `Summaries`, summary or blocker note |
| `deep_research_report` | "deep research report on..." | `web_search`, `jarvis_memory` | Long-form vault report |
| `large_document_analysis` | "analyze this document" | `file_processor`, `jarvis_memory` | Summary or report |
| `folder_analysis` | "analyze this folder" | `file_controller`, `project_operator`, `jarvis_memory` | Folder report |
| `registered_project_handoff` | "prepare a handoff" | `project_operator`, `jarvis_memory` | Handoff note |
| `browser_task_automation` | "open this page and..." | `browser_control` | Browser action/screenshot |
| `local_file_management` | "create/move/copy/read file" | `file_controller` | File change or listing |
| `scheduled_reminder` | "remind me..." | `reminder` | Scheduled task |
| `vault_markdown_note` | "save this to your vault" | `jarvis_memory` | Markdown note |
| `short_term_json_memory` | "remember that..." | `save_memory`, `jarvis_memory` | JSON fact plus vault mirror |
| `rag_memory_roundtrip` | "save and make searchable" | `jarvis_memory` | Indexed retrievable note |
| `bounded_rag_orientation` | "orient yourself to this project" | `jarvis_memory` | Bounded cited context pack |
| `rolling_canvas_tracking` | "refresh the plan board/task dashboard" | `jarvis_memory`, `jarvis_canvas` | Native rolling Canvas |

## Capability Boundaries

> [!danger] Do not fake tool results
> JARVIS should not pretend to browse, remember, schedule, inspect files, or check system status without using the corresponding tool.

| Need | Correct route |
| --- | --- |
| Current information | `web_search` |
| Learn and retain a topic | `web_search` then `jarvis_memory.learn_topic` |
| Blank Obsidian checklist template | `jarvis_memory.create_todo_template` |
| Canonical long-form memory | `jarvis_memory` |
| Short prompt facts | `save_memory` |
| Local files | `file_controller` or `file_processor` |
| Bounded project orientation | `jarvis_memory.context_pack` |
| Note dependencies/consumers | `jarvis_memory.lookup_local` |
| What calls/depends on a code symbol | `graphify_query` |
| What JARVIS just did | `process_trace` |
| Anything about an uploaded file | `file_processor` |
| Plan and task visualization | `jarvis_canvas` |
| Project status/handoffs | `project_operator` |
| Model load/cleanup | `model_lifecycle` |
| Speech status | `speech` capability via registry |

## Scientific And Specialist Projects

> [!attention] Interpretation boundary
> Scientific analysis in specialist projects can be orchestrated, but final interpretation should remain with the user or the preferred analysis assistant.

## Useful Capability Questions

```text
What tools do you have for this task?
```

```text
Which workflow would you use for this request?
```

```text
Can you save this as Markdown and make it searchable?
```

```text
Can you do this locally without Gemini?
```
