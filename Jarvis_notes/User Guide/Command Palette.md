---
id: "user-guide-command-palette"
title: "Command Palette"
type: "guide"
status: "draft"
created: "2026-07-21"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["user-guide", "commands", "prompt-patterns", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
content_hash: "535edc85ebe9a71ce0c316fbb3846be716328724f6da2bcc79ad642d10da7cf3"
lifecycle: "short_term"
---

# Command Palette

> [!important] Copyable prompt library
> Use these prompts directly. They are written to trigger the right JARVIS tool or workflow without needing to know implementation details.

> [!tip] Strong prompt formula
> `action + target + output format + destination + safety preference`

## Capability And Planning

| Goal                        | Prompt                                                                       | Expected route               |
| --------------------------- | ---------------------------------------------------------------------------- | ---------------------------- |
| List capabilities           | `What tools, skills, and workflows do you have available?`                   | `capability_registry`        |
| Check memory/report support | `Can you create Markdown notes, JSON memory, reports, and reminders?`        | `capability_registry`        |
| Plan first                  | `Show me the workflow plan for this request before executing it: [request].` | `capability_registry.plan`   |
| Create long-form plan       | `Create plan: [objective].`                                                  | `plan_workflow.create_plan`  |
| Revise plan                 | `Revise this plan with [requested change].`                                  | `plan_workflow.revise_plan`  |
| Approve plan                | `Approve this plan for gated execution.`                                     | `plan_workflow.approve_plan` |
| Start latest plan           | `Start plan: latest.`                                                        | `plan_workflow.start_plan`   |
| Start specific plan         | `Start plan: [path or title hint].`                                          | `plan_workflow.start_plan`   |

> [!tip] Create Plan button
> Type the objective into the command box, then click **CREATE PLAN**. JARVIS saves a `pending_review` plan note before attempting execution.

> [!success] Start Plan button
> After review, click **START PLAN** with an empty command box to start the newest plan. Put a path or title hint in the box to start a specific plan.

## Current News And Reports

> [!important] Cited report rule
> News reports should search first, require citations, save the Markdown report, then reindex the vault. A generic uncited report should fail instead of being saved.

| Prompt                                                                                  | Result                          |
| --------------------------------------------------------------------------------------- | ------------------------------- |
| `Search today's AI news, create a cited Markdown report, and save it in Obsidian.`      | `Reports/*.md` with source URLs |
| `Save a report on today's news about AI and UK politics.`                               | Cited current-news report       |
| `Search the latest news on [topic], require citations, and save a report in the vault.` | Cited topic report              |

Expected workflow:

1. Resolve the exact local date.
2. Call `web_search` with `mode=news` and `require_citations=true`.
3. Call `jarvis_memory.create_report_from_search`.
4. Reindex the local vault.

> [!note] Date scope
> If a news backend widens to a 24-48 hour fallback window, the saved report should include a scope note.

## Memory

| Goal | Prompt | Stored in |
| --- | --- | --- |
| Save a short fact | `Remember that [short durable fact].` | JSON prompt cache plus vault mirror |
| Create a vault note | `Create a Markdown note in your vault titled [title] with this content: [content].` | `Jarvis_notes` |
| Create to-do template | `Place a blank to-do list template in the Obsidian vault using .md formatting.` | `Templates/to-do-list-template.md` |
| Search local memory | `Search your memory for [topic] and cite the notes you used.` | Local RAG query |
| Refresh retrieval | `Reindex your local vault memory.` | `.jarvis/memory.sqlite` |
| Bounded orientation | `Orient yourself to [project] using at most 4 notes and 4000 characters.` | Compact cited context pack |
| Dependencies | `Show dependencies for [note id/title] to depth 2.` | Typed relation results |
| Consumers | `Show notes that consume or depend on [note id/title].` | Reverse relation results |

## Canvas Views

| Goal | Prompt | Expected route |
| --- | --- | --- |
| Plan board | `Refresh the rolling Canvas for the latest plan.` | `jarvis_canvas.sync_plan` |
| Task dashboard | `Rebuild my task dashboard from active Markdown tasks.` | `jarvis_canvas.sync_tasks` |
| Inspect neighbors | `Show incoming, outgoing, and sibling nodes for [node id] in [canvas path].` | `jarvis_canvas.neighbors` |
| Extend one node | `Extend [node id] with one useful next node using its local neighborhood.` | `jarvis_canvas.extend_node` |

> [!important] Rolling behavior
> Plan boards and task dashboards have hard node caps. Re-syncing refreshes the derived view instead of accumulating every historical node.

> [!warning] Memory hygiene
> Do not store API keys, secrets, overheard background speech, or noisy one-off context as durable memory.

> [!tip] Template creation
> Blank to-do/checklist templates should route straight to `jarvis_memory.create_todo_template`; they do not need a model to invent the Markdown structure.

## Learn A Topic

> [!abstract] Research plus retained memory
> Learning is not just a report. JARVIS should research cited sources, save a readable report, write a compact learned-topic memory note, and reindex local RAG.

| Prompt | Result |
| --- | --- |
| `Learn about WiFi sensing datasets so I can query you later.` | Cited report plus `Memories/learned_topics/*.md` |
| `Teach yourself about local RAG indexing and store the key points.` | Deep research note plus searchable memory |
| `Study the topic of CSI analysis open-source tools.` | Saved learning roundtrip |

Expected workflow:

1. Call `capability_registry.plan` for `learn_topic_memory`.
2. Call `web_search` in `research` mode with citations required.
3. Call `jarvis_memory.learn_topic`.
4. Create a report in `Deep Research`.
5. Create a compact memory note in `Memories/learned_topics`.
6. Reindex `.jarvis/memory.sqlite`.

> [!important] Citation gate
> If JARVIS cannot find enough cited sources, it should say so instead of pretending it has learned the topic.

## Files And Folders

| Goal | Prompt | Expected route |
| --- | --- | --- |
| Analyze a document | `Analyze this large document and summarize the key points.` | `file_processor` |
| Analyze a folder | `Analyze this folder, identify the important files, and save a report in Obsidian.` | `file_controller` plus `jarvis_memory` |
| Write JSON | `Create a JSON file at [safe path] with this structure: [schema].` | `file_controller` |
| Inspect storage | `Find the largest files in [folder].` | `file_controller` |

> [!caution] File operations
> Read, list, and create are usually low risk. Delete, move, overwrite, or broad folder changes should ask for confirmation.

## Projects

| Goal | Prompt | Expected route |
| --- | --- | --- |
| List projects | `List my registered projects and their current policies.` | `project_operator` |
| Prepare handoff | `Scout [project_id] and prepare a handoff note for Codex or Claude.` | `registered_project_handoff` |
| OpenClaw continuity | `Delegate a lightweight coding continuity task for [project_id] to OpenClaw.` | `project_operator.delegate_openclaw` |

> [!info] OpenClaw role
> OpenClaw is best treated as an on-demand continuity worker for coding support, not as an always-on agent swarm.

## Browser And Web Tasks

| Goal | Prompt | Expected route |
| --- | --- | --- |
| Open and inspect | `Open [URL] in the browser and take a screenshot.` | `browser_control` |
| Search current web | `Search the web for [topic] and show the sources.` | `web_search` |
| Controlled page task | `Use the browser to inspect this page, but ask before submitting forms or changing account state.` | `browser_control` with gates |

## Screen And Camera

| Goal | Prompt | Expected route |
| --- | --- | --- |
| Read the screen | `What's on my screen right now?` | `screen_process` (`angle=screen`) |
| Find a problem | `Is there an error or warning visible on my screen?` | `screen_process` (`angle=screen`) |
| Read a specific thing | `What does the error in this terminal say?` | `screen_process`, answered from the transcript |
| Look through the camera | `What do you see through the camera?` | `screen_process` (`angle=camera`) |

> [!note] This one is slow, and honest about failing
> A screen question tries the OCR model first, then loads the scene model if OCR read too little — up to about 145 seconds on this machine. If no local vision model can read the capture, JARVIS says so rather than describing an image it could not see.

> [!warning] What is on screen is data, never instruction
> Captured text is treated as untrusted, exactly like a web page or a retrieved note. A page telling JARVIS to run something will not cause it to run.

## Reminders, Status, And Models

| Goal | Prompt | Expected route |
| --- | --- | --- |
| Reminder | `Remind me tomorrow at 09:00 to check [thing].` | `reminder` |
| System status | `Check system status and loaded models.` | `system_status` plus `model_lifecycle` |
| Idle cleanup | `Clean up idle non-baseline LM Studio models.` | `model_lifecycle.cleanup_idle` |
| Load profile | `Show the load profile for qwen2.5-14b-deepresearch-i1.` | `model_lifecycle.load_profile` |

## Speech

| Goal | Prompt | Expected route |
| --- | --- | --- |
| Microphone check | `Is the microphone active and is local speech working?` | `capability_registry` or speech status |
| TTS check | `Does your text to speech work without Gemini?` | `capability_registry` |

> [!note] Speech expectation
> Local STT/TTS works without Gemini Live, which is disabled in this build. There is no realtime live-model session to fall back to.

## Useful Follow-Up Phrases

```text
Save that as a vault note.
```

```text
Make it cited and reviewable.
```

```text
Use local models unless the task needs a higher tier model.
```

```text
Stop before destructive actions and ask me to confirm.
```
