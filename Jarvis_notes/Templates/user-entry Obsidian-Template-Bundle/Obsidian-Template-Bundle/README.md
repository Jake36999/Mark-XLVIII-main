---
title: "Obsidian Template Bundle Guide"
updated: "2026-07-21T12:56:30Z"
tags: ""
index_state: "indexed_local"
content_hash: "27337899b72a1d02475f83825ce7def5345e50be3efc6cfc28222d863f63ae85"
---

# Obsidian Template Bundle

A focused, plugin-free template system for journaling, knowledge management, projects, meetings, reviews, and decisions.

The templates use only Obsidian's core **Templates** and **Daily Notes** plugins. No community plugins are required.

## Included templates

| Template | Use it for |
| --- | --- |
| `01 Daily Journal.md` | Planning the day, logging events, and reflecting in the evening |
| `02 Knowledge Note.md` | Turning information into a clear, reusable idea in your own words |
| `03 Fleeting Note.md` | Capturing an idea quickly before deciding what it should become |
| `04 Source Note.md` | Processing a book, article, video, podcast, paper, or course |
| `05 Map of Content.md` | Organizing a topic through curated links rather than a rigid folder tree |
| `06 Project Note.md` | Defining an outcome, milestones, next actions, and project decisions |
| `07 Meeting Note.md` | Preparing an agenda and recording decisions and assigned actions |
| `08 Weekly Review.md` | Closing the week, reviewing commitments, and planning the next one |
| `09 Decision Record.md` | Preserving the context, alternatives, and reasoning behind a decision |

## Quick setup

1. Copy the `Templates` folder into your Obsidian vault.
2. Open **Settings -> Core plugins** and enable **Templates**.
3. Open **Settings -> Templates** and select the copied `Templates` folder.
4. Enable **Daily Notes** under **Core plugins**.
5. In **Settings -> Daily Notes**:
   - Set the date format to `YYYY-MM-DD`.
   - Choose where daily notes should be created.
   - Select `01 Daily Journal` as the daily-note template.
6. Optionally assign a hotkey to **Templates: Insert template**.

## Suggested vault folders

| Folder | Contents |
| --- | --- |
| `Daily` | Daily journal notes |
| `Inbox` | Fleeting notes awaiting review |
| `Knowledge` | Durable, idea-centered notes |
| `Sources` | Notes about books, articles, videos, papers, and courses |
| `Maps` | Maps of content and topic hubs |
| `Projects` | Active and completed project notes |
| `Meetings` | Meeting records |
| `Reviews` | Weekly and other periodic reviews |
| `Decisions` | Decision records |
| `Templates` | The templates in this bundle |
| `Attachments` | Images, PDFs, audio, and other files |

This structure is optional. The templates also work in a flatter vault.

## Recommended workflow

| Stage | Template | What happens |
| --- | --- | --- |
| Capture | Fleeting Note | Record the thought without slowing down to organize it |
| Process | Source Note | Extract meaning from something you read, watch, or hear |
| Develop | Knowledge Note | Express one durable idea in your own words |
| Connect | Map of Content | Place useful notes into a navigable topic structure |
| Execute | Project Note and Meeting Note | Turn intentions and conversations into actions |
| Decide | Decision Record | Preserve important choices and their rationale |
| Reflect | Daily Journal and Weekly Review | Learn from experience and reset priorities |

## Naming suggestions

- **Daily notes:** `YYYY-MM-DD`
- **Knowledge notes:** Use a specific claim or concept, such as `Retrieval practice strengthens long-term memory`
- **Source notes:** `Author - Title`
- **Maps of content:** `MOC - Topic`
- **Projects:** `Project - Outcome`
- **Meetings:** `YYYY-MM-DD - Topic`
- **Decisions:** `Decision - Short description`

## Properties used in the bundle

The YAML properties are intentionally simple and consistent:

- `type` identifies the note's role.
- `status` shows where the note is in its lifecycle.
- `created` records when the note began.
- `updated` can be changed manually after significant edits.
- `tags` provide broad grouping; use links inside the note for richer relationships.
- `related`, `project`, `source`, and similar properties connect relevant notes.

Delete any property you do not find useful. A smaller system you maintain is better than a detailed system you ignore.

## Core template variables

These placeholders are replaced by Obsidian when a template is inserted:

- `{{title}}` - the current note title
- `{{date:YYYY-MM-DD}}` - the current date
- `{{date:dddd, D MMMM YYYY}}` - a readable date
- `{{time:HH:mm}}` - the current time

## A few useful conventions

- Use `[[internal links]]` to connect ideas, people, projects, and sources.
- Keep each Knowledge Note centered on one idea whenever practical.
- Promote useful Fleeting Notes; delete or archive the rest during reviews.
- Put actionable tasks in Project, Meeting, Daily, or Review notes rather than scattering them everywhere.
- Record decisions separately when forgetting the reasoning would be costly.
- Review the system weekly so it stays trustworthy.
