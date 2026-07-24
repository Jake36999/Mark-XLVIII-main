---
id: "user-guide-glossary"
title: "Glossary"
type: "guide"
status: "draft"
created: "2026-07-21"
updated: "2026-07-23T03:00:54Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "glossary", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "0702114cbe46e21537e6869a1a629f2e870453a4e5f74f97cc56c361ded354e2"
memory_tier: "short_term"
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

> [!example] Workflow example
> `current_news_report` resolves the date, searches cited news, creates a Markdown report, and reindexes the vault.

> [!example] Planning example
> `long_form_plan_execution` creates a plan note, waits for review, then executes approved milestones through existing guarded tools.

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
