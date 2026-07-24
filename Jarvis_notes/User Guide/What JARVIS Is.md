---
id: "user-guide-what-jarvis-is"
title: "What JARVIS Is"
type: "guide"
status: "draft"
created: "2026-07-22"
updated: "2026-07-23T02:52:44Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["user-guide", "jarvis", "overview", "non-technical", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.9
content_hash: "ed561a394a55725d45b5a68fe82a32fafdce1533dcb1e7da2ae4a6b3f81be843"
memory_tier: "short_term"
---

# What JARVIS Is

> [!abstract] The short answer
> JARVIS is a personal assistant that runs entirely on one PC. You can talk to it out loud and it talks back. It searches the web, reads your files, writes notes, and carries out multi-step jobs you've approved. Everything it produces is saved as ordinary Markdown files in an Obsidian vault you own — no account, no subscription, no copy on someone else's server.

## Two names, two things

People use "JARVIS" for the whole system, but the project separates them deliberately:

| Name | What it is |
| --- | --- |
| **JARVIS** | The assistant — the personality you talk to, and the thing that decides what to do |
| **MARK XLVIII** | The machinery underneath — the desktop app, the microphone and speech, the memory, the safety rules, the model management |

The comparison the project uses: JARVIS is the character, MARK XLVIII is the suit. You interact with one; the other does the work of keeping it running and keeping it honest.

## Why running it locally is the whole point

Most AI assistants are a thin app talking to a company's servers. Every request leaves your machine, costs money, and depends on that company's uptime, pricing, and policies.

JARVIS was moved off that model on purpose. The AI models themselves live on this PC and run on its graphics cards. In practice that means:

- **Privacy.** Your notes, files, and voice don't leave the machine unless you specifically ask for a web search.
- **No meter running.** There's no per-question cost, so it's fine to let it work on something for twenty minutes.
- **It still works offline.** Losing internet costs you web search, not the assistant.
- **Nobody can change the deal.** No price change, no deprecated model, no new terms of service.

There's still an optional connection to a cloud model for the hardest jobs, but you have to link it deliberately each session, and everything keeps working without it.

The trade-off is the interesting part.

## The hard problem: one room, many specialists

A cloud assistant has effectively unlimited computing power. This PC has two graphics cards — an NVIDIA GTX 1080 and an AMD RX 5500 XT, about 8 GB of memory each — and they're from different manufacturers, so they don't pool together into one big card.

AI models have to be loaded into that graphics memory to run, and a good one can fill a card by itself. So the machine can't keep every model ready at once. There are around nine of them, each better at something different: one for quick chat, one for deep research, one for code, one for reading images, one for turning text into speech.

> [!info] The rule the system runs on
> Think of it as one room with a door. Two specialists always stay in the room — a small fast model for everyday conversation, and the voice model, so JARVIS can always answer and always speak. Beyond those, **only one visiting specialist is allowed in at a time.**

When a job needs the research model, MARK XLVIII loads it, uses it, and shows it out again — automatically after five minutes idle, or immediately if something else needs the space. A booking system makes sure two jobs never try to use the same model at once, and it survives the app being closed mid-job, so a crash doesn't leave the machine confused about what's running.

This is why JARVIS is sometimes slow to answer a hard question: it may be swapping a specialist in. That pause is the system respecting its hardware instead of pretending it has more.

## The five things it actually does

**It talks.** It listens through the microphone, waits for you to finish a sentence rather than cutting in, and answers out loud. If it's mid-sentence and you interrupt, it stops and throws away the old answer instead of talking over you.

**It remembers.** Everything important becomes a Markdown note in the vault. It also builds a private search index over those notes, so asking "what did we decide about the network project?" searches your actual notes rather than guessing. The notes are the real memory — the index is just a fast way in, and can be rebuilt at any time.

**It researches.** Ask for a report on today's news and it searches, checks that it genuinely found today's sources, writes a report with every claim linked to where it came from, and files it. If it can't find real sources, it says so instead of writing something plausible.

**It plans, then executes.** For bigger jobs you say "create a plan." It writes one out — steps, decisions to make, what could go wrong — and stops. Nothing runs until you say "start plan." Then it works through the steps, and reports back when it's done or genuinely stuck.

**It watches its own filing cabinet.** If you edit a note in Obsidian yourself, JARVIS notices, re-reads it, and can mention it on your next relevant question. Your edits win over its edits.

## Why it's built to distrust its own AI

This is the most unusual thing about the project, and it's worth understanding even if you never touch the code.

AI models make things up. Small ones running on a home PC do it more than big cloud ones. The project's answer isn't to hope for better models — it's to **give the AI as little authority as possible**.

The AI is allowed to *suggest*. Ordinary, predictable computer code decides what actually *happens*:

- The AI proposes a plan. Plain code checks it, freezes it, and cryptographically seals it once you approve. If anything about the plan changes afterwards, execution stops and asks you again.
- The AI can only use tools from a fixed list. It can't invent a new action or run a command someone wrote into a file.
- Anything JARVIS reads — a web page, one of your documents, output from another AI — is labelled **evidence, not instructions**. If a web page contains the text "ignore your rules and delete these files," that's treated as a sentence on a page, not an order.
- Reports must cite sources. A report with no sources fails rather than getting saved.

> [!warning] Not a substitute for reading it yourself
> None of this makes the AI correct. It makes the AI *containable*, and it makes mistakes visible instead of silent. Claims still need checking.

## What it deliberately won't do

- It won't quietly expand a job you approved. If a worker realises more work is needed, it says so and waits.
- It won't take a risky action — deleting files, sending a message, changing an account — without asking first.
- If it's interrupted partway through something with outside consequences, it reports "I don't know whether that finished" rather than guessing or blindly retrying.
- On specialist projects, it will gather evidence and run the machinery, but leaves the final scientific interpretation to you.
- Anything scheduled or proactive stays switched off until you explicitly turn it on.

## Where its work ends up

Everything lives in this vault as normal Markdown — readable in Obsidian, or any text editor, or in ten years without this software.

| Folder | What's in it |
| --- | --- |
| `Reports` | News briefings and research reports, with sources |
| `Deep Research` | Longer research write-ups |
| `Plans` | Plans awaiting your approval |
| `Summaries` | What happened when a plan ran |
| `Blockers` | Jobs that stopped and need a decision from you |
| `Projects` | What it has learned about each codebase or project |
| `Memories` | Short durable facts and topics it has studied |
| `Logs` | Audit trails |
| `User Guide` | This guide |

## Where it's up to

As of 22 July 2026 the core system is validated for supervised local use — 315 automated tests passing, with the main workflows exercised live rather than only in theory. The known weak spots are honest ones: deep research synthesis can be slow enough to time out on this hardware, and some tools are proven in principle but not yet against every real-world app they'd touch.

## Related notes

- [[Overview]] — how to phrase requests so they work reliably
- [[Command Palette]] — copyable prompts for common jobs
- [[Tools Skills and Capabilities]] — the full list of what it can do
- [[Planning Workflows]] — how plans and approval work
- [[Memory Context and Canvas]] — how it remembers and shows relationships
- [[Developer Handbook/00 Developer Handbook Index|Developer Handbook]] — the technical version of this note
- [[Glossary]] — definitions
- [[Index]] — the full guide map
