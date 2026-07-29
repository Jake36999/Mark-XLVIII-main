---
id: "user-guide-glossary"
title: "Glossary"
type: "guide"
status: "draft"
created: "2026-07-21"
updated: "2026-07-29T21:53:32Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "glossary", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "3d31672c2f48ef278813a836a60f15565f9278db42fe79c843cec6cbe04efb99"
lifecycle: "short_term"
---

# Glossary

> [!abstract] Terms used by JARVIS
> This glossary explains the words used across MARK XLVIII, the Obsidian vault, local models, tools, workflows, speech, and reports.

## Assistant And Platform

| Term | Meaning |
| --- | --- |
| JARVIS | The assistant personality and tool-using agent |
| MARK XLVIII | The local platform or shell that hosts JARVIS, the dashboard, tools, speech, memory, project operations, and model routing |
| Router Mode | The default local assistant mode using local or OpenAI-compatible models and tools |
| Gemini Live | Optional realtime Live backend |

> [!important] Identity distinction
> JARVIS is the assistant. MARK XLVIII is the platform. JARVIS should not identify as MARK XLVIII.

> [!note] Gemini Live
> Gemini Live is not required for local speech, tools, reminders, memory, reports, or project operations.

## Memory

| Term | Meaning |
| --- | --- |
| Obsidian Vault | Canonical Markdown memory store at `F:\Mark-XLVIII-main\Jarvis_notes` |
| Vault Note | Markdown note with frontmatter and body content |
| Prompt Cache | Compact JSON memory file at `memory/long_term.json` |
| RAG | Retrieval augmented generation using local vault search |
| Local Index | SQLite index at `Jarvis_notes/.jarvis/memory.sqlite` |

> [!tip] Memory rule
> Long-form or reviewable memory belongs in the vault. Short durable facts can be mirrored into the JSON prompt cache.

Generated vault notes should include frontmatter fields such as:

| Field | Purpose |
| --- | --- |
| `id` | Stable note identifier |
| `title` | Human-readable note title |
| `type` | Note type such as `memory`, `report`, `log`, or `guide` |
| `status` | Draft, reviewed, or other lifecycle state |
| `created` / `updated` | Timestamps |
| `project_id` | Project or vault namespace |
| `source` | User, daemon, Codex, or workflow source |
| `tags` | Searchable note tags |
| `sync_state` | Local/backend sync status |
| `index_state` | Local RAG index status |
| `remember_note_id` | Optional Remember Me backend id |
| `lifecycle` | How long a note has been useful — `short_term`, `long_term`, or `archive` (renamed from `memory_tier` 2026-07-25; see "Lifecycle vs. Structural Tier" below) |

> [!warning] Lifecycle vs. Structural Tier
> `lifecycle` (above) is a per-note field. A separate, unrelated idea — "structural tier" (Tier 0-3: immediate context, general documentation, project/workflow-specific, archive) — describes *where* a category of information sits, not any one note's own age. Both use the word "tier" in conversation; they are not the same axis.

## Tools And Workflows

| Term | Meaning |
| --- | --- |
| Tool | Direct callable capability such as `web_search`, `jarvis_memory`, or `reminder` |
| Workflow | Ordered multi-step pattern that may call more than one tool |
| Plan Workflow | A reviewable plan-first workflow saved to `Jarvis_notes/Plans` before execution |
| Capability Registry | Manifest used to answer capability questions and plan workflows |
| Command Palette | Prompt examples that map to tools and workflows |
| Confirmation Gate | Safety pause before destructive, expensive, account-changing, or policy-controlled actions |
| Approval State | Plan frontmatter value showing whether a plan is pending review, revised, approved, or ready |
| Blocker Note | Vault note explaining why execution cannot continue without user input |
| Execution Summary | Vault note recording completed work, evidence, artifacts, and follow-ups |
| Knowledge Graph | A pre-built local map of a codebase's structure (via `graphify_query`) — answers "what calls/depends on X," not "what do you know about X" |
| Turn Phase | Which stage of a turn JARVIS is in: *processing your request*, *completing an operation*, or *communicating to you*. The hand-off is one-way, so replies answer the question rather than narrating the machinery |
| Process Trace | The record of what actually ran — reachable by asking, via `process_trace`. Distinct from the capability manifest, which lists what *could* run |
| Direct Answer | A turn where a tool's own output is already the answer, so no second model is asked to paraphrase it. Faster, and on this hardware it often avoids swapping models |
| Warm Model | A model already loaded in LM Studio. Picking a warm model over a cold one avoids a multi-gigabyte load, which is the single biggest cost on a local-only host |

> [!example] Workflow example
> `current_news_report` resolves the date, searches cited news, creates a Markdown report, and reindexes the vault.

> [!example] Planning example
> `long_form_plan_execution` creates a plan note, waits for review, then executes approved milestones through existing guarded tools.

### Canvas Planning Terms (Mode 2)

> [!warning] "Workflow" now means two related-but-distinct things
> Above, "Workflow" is a registered multi-tool pattern like `current_news_report` (Mode 1). Below, "Workflow" is the top-level anchor of a Mode 2 canvas plan. Both are real, current usages — context (which mode you're in) disambiguates which one is meant; this glossary isn't picking a winner between them.

| Term | Meaning |
| --- | --- |
| Workflow (Mode 2) | A canvas's own single anchor — the top-level unit of Mode 2 planning (`role: workflow`, was called `plan`/`goal`/`root` interchangeably before 2026-07-25) |
| Goal | The workflow's own stated objective — currently 1:1 with the workflow itself |
| Task | A macro pillar — a `branch:`-tagged group of largely-independent nodes (`task:` is now the preferred spelling of `branch:`) |
| Subtask | An individual node within a task/branch |
| Mode | Optional `research`/`development` framing on a workflow's anchor node — purely descriptive, never enforced |

> [!note] Vocabulary is additive, not a rename
> `role: workflow` and `task:` are new accepted spellings, not replacements — a canvas written with the older `role: plan`/`branch:` words still works identically. See [[Developer Handbook/13 Canvas Planning Engine and Reasoning-Backed Decomposition|Note 13]].

## Models And Speech

| Term | Meaning |
| --- | --- |
| LM Studio | Local model server used for OpenAI-compatible chat, worker, and speech endpoints |
| Baseline Model | Lightweight always-warm model used for quick routing and simple assistant tasks |
| Task Model | Specialist model loaded only when a larger task requires it |
| STT | Speech to text |
| TTS | Text to speech |

> [!info] Speech expectation
> JARVIS can use local STT/TTS without Gemini Live. TTS should chunk long replies and avoid duplicate playback.

## Reports

| Term | Meaning |
| --- | --- |
| Cited Report | Markdown report with structured source records and source URLs |
| Scope Note | Report note explaining widened date scope, such as a last-48-hours fallback |
| Deep Research Report | Longer structured report combining search, synthesis, sources, and vault persistence |

> [!warning] Report quality
> A current-news report should not be saved if it has no cited sources. It should fail clearly and ask whether to retry or broaden the search.
