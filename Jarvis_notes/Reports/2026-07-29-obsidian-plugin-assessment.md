---
id: "jarvis-20260729T215659Z-a6ad05a8"
title: "Obsidian Plugin Assessment: Install vs Extract"
type: "report"
status: "active"
created: "2026-07-29T21:56:59Z"
updated: "2026-07-29T21:57:09Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["assessment", "obsidian", "plugins", "security", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-29T21:56:59Z"
review_after: ""
source_version: 1
content_hash: "0f6ec028bbd551260b664ac5c4f6b3259dd33c3d0f1741f34e59ab7212e1cbed"
supersedes: []
contradicts: []
depends_on: []
depended_on_by: []
extends: []
extended_by: []
implements: []
implemented_by: []
consumes: []
consumed_by: []
related: []
deleted: false
deleted_at: ""
lifecycle: "short_term"
sync_error: ""
---

> [!info] Scope
> Assessment of four candidate Obsidian plugins for install-vs-extract, read against their actual repositories rather than reputation, and weighed against what MARK XLVIII already has. Claims about JARVIS's own side were checked in code, not assumed.

## Verdicts

| Plugin | License | Verdict |
| --- | --- | --- |
| **buttons** (shabegom) | Unlicense | **Install.** Clearest win, maps onto a real friction point |
| **obsidian-local-rest-api** (coddingtonbear) | MIT | **Install, but narrowly.** Use it for what JARVIS structurally cannot do; do not route vault writes through it, and leave its MCP endpoint off |
| **second-brain-mcp-extension** (ziadloo) | Not stated | **Skip.** Duplicates capability JARVIS already has, at real supply-chain risk |
| **Templater** (SilentVoid13) | AGPLv3 | **No — and this one is a security decision, not a preference** |

---

## Templater: the one to actively decline

Templater executes **arbitrary JavaScript and system commands** from note content. Its own README says so plainly: *"It can be dangerous to execute arbitrary JavaScript code or system commands from untrusted sources."*

That collides head-on with a property this codebase has spent real effort building. `core/evidence.py` exists specifically to enclose vault and tool content as **untrusted evidence**, and the standing instruction is to never follow instructions found inside retrieved notes. Today a prompt-injection payload sitting in a vault note is inert data — the 2026-07-25 injection testing confirmed a hidden "delete this file" directive in a retrieved note was correctly ignored.

Installing Templater would make note *content* executable inside the vault that JARVIS writes to and reads from. That converts an inert injection payload into an execution path. It is the single clearest "no" of the four, and it would remain a no even if the functionality were more attractive.

Two secondary reasons, either sufficient on its own:

- **AGPLv3.** Extracting any of its code into MARK XLVIII would impose AGPL obligations on the whole platform. Relevant if this is ever shared.
- **Redundant.** `jarvis_memory` already owns note templating — `TEMPLATES`, `create_todo_template`, and frontmatter generation with `content_hash`/`lifecycle`/revision handling. Two template systems writing the same notes is a correctness problem, not a feature.

## buttons: install, and wire it into plan approval

Public domain (Unlicense), actively maintained (v0.9.4, August 2025), and — importantly — it does **not** execute arbitrary JavaScript. Actions are a fixed set: command, link, template, text, calculate, chain, swap. That bounded action surface is exactly why it is safe to add where Templater is not.

The reason it is worth more than novelty: JARVIS's plan approval currently requires the human to hand-edit a Markdown checkbox. `core/approval_response.render_approval_template()` writes three checkboxes — Approve / Correct / Deny — and asks the user to "Mark exactly one box below, then save this note."

That is the gate on every Mode 2 canvas plan and every long-form plan. A `text`-type button that writes the decision line turns it into one click. The approval semantics do not change at all — the note remains authoritative, the fingerprint check still runs, the signed envelope is still minted by `evaluate_canvas_approval`. Only the input gesture changes.

> [!tip] Where to start
> Add buttons to the template in `core/approval_response.py`, not to individual notes. One change, every future approval note inherits it.

## obsidian-local-rest-api: install for what JARVIS cannot do, not for what it already does

HTTPS on port 27124 behind a bearer API key (optional plain HTTP on 27123), MIT licensed, TypeScript, running inside Obsidian. It exposes `/vault/{path}` CRUD, `/active/`, `/search/simple/`, structured JsonLogic `/search/`, `/commands/`, `/tags/`, `/open/{path}`, and an `/mcp/` endpoint.

**Do not route vault writes through it.** Two reasons:

1. **It requires Obsidian to be running.** JARVIS is deliberately headless-capable — `HEADLESS_TOOLS` in `core/tool_dispatcher.py` exists so tools work without the GUI. Making the canonical memory path depend on a running Electron app would break that.
2. **It would bypass JARVIS's own note contract.** Writing through `/vault/{path}` skips `jarvis_memory`'s frontmatter generation, `content_hash`, `lifecycle`, and revision-conflict handling. That is a loss, not a simplification.

**Do not enable its `/mcp/` endpoint.** JARVIS already runs its own MCP server (`core/mcp_server.py`) with a real authorization gate. A second MCP surface onto the same vault means two paths with different security properties — which is precisely the bug class this session was spent fixing, where a confirmation gate was wired into one execution path and not the other.

**What is genuinely worth having** is the set of things JARVIS structurally cannot do by writing files:

| Endpoint | Why it is new capability |
| --- | --- |
| `/open/{path}` | Make Obsidian actually *show* a note. JARVIS can write a plan note but cannot currently bring it up in front of you |
| `/commands/` | Trigger Obsidian commands — the natural target for a `buttons` click that needs to reach JARVIS |
| `/active/` | Know or act on what the user is currently looking at |

Those three compose well with the `buttons` recommendation: a button in an approval note that invokes a command, rather than a checkbox the user edits by hand.

## second-brain-mcp-extension: skip, but note the convergence

It registers `/second-brain-mcp/` inside the parent plugin and exposes `query_wiki`, `get_wiki`, `wiki_card`, implemented as semantic search over local embeddings (`all-MiniLM-L6-v2`) followed by breadth-first traversal of Obsidian's internal links — explicitly to stay token-efficient instead of dumping context.

JARVIS already has all three moves, verified in `actions/jarvis_memory.py`:

- `query_local` — local SQLite RAG with `nomic-embed-text-v1.5` embeddings
- `lookup_local` — deps/consumers/related graph traversal with bounded depth
- `context_pack_local` — bounded orientation under hard count and character limits

So this would add a second, differently-embedded, differently-gated retrieval path over the same vault. Against that: **2 stars, 2 forks, and no stated license** on something that would read the entire knowledge base.

Worth recording the convergence though — an independent project arrived at the same design JARVIS already implements (semantic entry point, then bounded graph walk, explicitly to avoid context dumps). That is mild evidence the `context_pack` approach is right.

## If you install anything, install in this order

1. **buttons** — self-contained, no JARVIS changes needed to try it.
2. **obsidian-local-rest-api** — but treat it as a UI-affordance channel. Before wiring anything, decide explicitly that the write path stays with `jarvis_memory`.

Neither requires code extraction. Extraction is only license-viable for these two anyway (MIT and Unlicense); Templater's AGPL rules it out and the MCP extension states no license at all.

## Related
[[Validation/2026-07-29-finalisation-live-assessment]]
[[User Guide/Developer Handbook/06 Obsidian Memory RAG Tasks and Canvas]]
