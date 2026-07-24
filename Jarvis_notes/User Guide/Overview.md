---
id: "user-guide-overview"
title: "JARVIS User Guide Overview"
type: "guide"
status: "draft"
created: "2026-07-21"
updated: "2026-07-23T02:52:44Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "jarvis", "overview", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "cb8e24e04d20cc020af1b03dd45818da1a9fb6477d32c5fe0b2ec36099347b73"
memory_tier: "short_term"
---

# JARVIS User Guide Overview

> [!abstract] Quick orientation
> JARVIS is the assistant. MARK XLVIII is the local platform that hosts the assistant, tools, speech stack, memory vault, project operations, and model routing.

> [!tip] Best first move
> Start with [[Command Palette]] when you want a copyable prompt. Use [[Tools Skills and Capabilities]] when you want to understand what JARVIS can actually do.

## Navigation

| Note | Purpose | Use when |
| --- | --- | --- |
| [[What JARVIS Is]] | Plain-language project explainer | You want the non-technical picture of what this is and why |
| [[Index]] | Map of the guide | You want the full document structure |
| [[Command Palette]] | Prompt patterns | You want to ask JARVIS to do something |
| [[Tools Skills and Capabilities]] | Capability catalog | You want to know which tools and workflows exist |
| [[Developer Handbook/00 Developer Handbook Index|Developer Handbook]] | Architecture and implementation guide | You want to understand or extend the system |
| [[Glossary]] | Term definitions | You want a quick definition |

## What This Guide Covers

- How to ask for reports, memory saves, project handoffs, file analysis, web searches, reminders, model status, and speech checks.
- How to ask for vault-native Obsidian templates such as blank Markdown to-do lists.
- How to ask JARVIS to learn a topic by creating a cited report, retaining key points in RAG memory, and reusing those notes in later answers.
- How JARVIS should decide between tools, workflows, local models, and optional cloud models.
- Where generated artifacts are stored in the vault.
- Which actions are low risk and which should pause for confirmation.

## Operating Model

> [!info] Local-first by default
> Router mode can use local speech, local models, OpenAI-compatible endpoints, tools, reminders, browser/file operations, and vault memory without Gemini Live.

| Layer | Role |
| --- | --- |
| JARVIS | Assistant identity and tool-using agent |
| MARK XLVIII | Local shell/platform |
| `Jarvis_notes` | Canonical Obsidian vault |
| `memory/long_term.json` | Compact prompt-cache memory |
| `.jarvis/memory.sqlite` | Local RAG index |
| LM Studio | Local model runtime for chat/workers/speech |

JARVIS should use tools before guessing. Current news, prices, weather, files, project state, reminders, and local system status should be routed through tools rather than answered from memory alone.

## Prompt Pattern

> [!example] Reliable request shape
> Ask for the target, action, output format, and destination.

```text
Search today's AI news, make a cited Markdown report, and save it in Obsidian.
```

```text
Analyze this folder, summarize the important files, and save a project handoff note.
```

```text
Remember that network_management uses Intel 5300 CSI receivers and should avoid destructive automation.
```

```text
Learn about WiFi sensing datasets so I can query you about them later.
```

```text
Place a blank to-do list template in the Obsidian vault using .md formatting.
```

## Safety Model

> [!warning] Confirmation gates
> JARVIS should stop and ask before destructive, high-impact, account-changing, expensive, or policy-controlled actions.

| Usually low risk | Should be gated |
| --- | --- |
| Search the web | Delete or overwrite files |
| Read selected files | Move folders in bulk |
| Create vault notes | Launch heavy training jobs |
| Reindex local RAG | Submit forms or change accounts |
| Check system/model status | Delegate multi-agent coding work |

## Related Notes

- [[Index]]
- [[Command Palette]]
- [[Tools Skills and Capabilities]]
- [[Glossary]]
