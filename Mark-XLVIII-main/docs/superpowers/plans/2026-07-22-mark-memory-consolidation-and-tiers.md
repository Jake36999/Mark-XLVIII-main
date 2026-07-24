# Mark Memory Consolidation, Tiered Vault, and Obsidian-Native Editing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give JARVIS a memory that ages: a short-term working set, a machine-curated long-term store, and a user-owned archive — plus the note-editing capability that curation requires, rendered natively in Obsidian.

**Architecture:** Three additions, bottom-up. (A) A real note-editing capability built on the existing `reconcile_note` merge engine. (B) A `memory_tier` lifecycle dimension, orthogonal to note type, with move-safe relocation. (C) A `memory_consolidation` workflow that promotes, merges, archives, and flags — proposal-only, reviewable, reversible.

**Tech Stack:** Python 3.11 stdlib, existing `actions/jarvis_memory.py` services, SQLite RAG index, `unittest`.

---

## Context

Two problems, one root cause: the vault only ever grows.

1. **It accumulates false facts.** `Jarvis_notes/Projects/mark-platform/Project Memory.md` still asserts `project_operator.py` "is planned but not implemented" — the file is 687 lines. That note has `rag_index: true` and is the compact note *designed for frequent retrieval*, so JARVIS confidently repeats a false claim about its own codebase. The schema already carries `supersedes`, `contradicts`, `valid_from`, `review_after`, `content_hash`, and `snapshot_hash` — and retrieval already **filters** superseded notes (`_superseded_note_ids`, `actions/jarvis_memory.py:903`). But nothing ever **writes** those fields or acts on staleness. They are inert.

2. **There is no lifecycle.** Every report lands in `Reports/` and stays forever. A three-day-old news briefing and a durable project finding are retrieved with equal weight. The user has stated the vault JARVIS uses is **not their primary vault**, so it should model memory explicitly:
   - **Short-term** — recent reports, current to-dos. Machine- and user-managed.
   - **Long-term** — project-relevant reports and consolidations of archived information. Machine-managed.
   - **Archive** — archived things. Mostly user-managed.

The intended outcome: JARVIS periodically distils the working set into durable long-term knowledge, retires the rest to an archive the user controls, and stops repeating stale facts — all as reviewable proposals, never silent rewrites.

---

## What exists today (grounded)

| Capability | Location | State |
|---|---|---|
| Create a typed note | `create_note` (`jarvis_memory.py:572`) | Type → folder via `TEMPLATES`; folders are flat, no tier |
| Edit frontmatter | `update_note_frontmatter` (`:650`) | Revision-checked merge; **body untouched** |
| 3-way section merge | `reconcile_note` (`:3793`), `_markdown_sections` (`:3772`) | Computes a merged body; **nothing writes it** |
| Delete | `tombstone`/`delete_note` (`:3987`) | Propagates a tombstone to the index |
| Superseded filtering | `_superseded_note_ids` (`:903`) | Reads `supersedes`; nothing populates it |
| Atomic write + self-write receipt | `atomic_write` (`:408`) | Registers a hash so the vault watcher marks the change `jarvis`-origin |

**Gaps this plan fills:** no `move_note`, no `update_section`/`append`, no tier concept, no consolidation, and no use of embeds/transclusion, collapsible callouts, aliases, tag hierarchy, or Maps of Content.

**Hazard found in the live vault:** links mix two styles. Basename links (`[[Command Palette]]`) survive a move; path-qualified links (`[[Reports/2026-07-21-workflow-architecture-report|...]]`, and many `[[Plans/...]]`, `[[Summaries/...]]`, `[[Deep Research/...]]`) **break when the target changes folder.** Tiering moves files, so inbound-link rewriting is not optional.

---

## Design Decisions

### Tier is a lifecycle field; the existing folders already are "short-term"

`memory_tier` (`short_term` | `long_term` | `archive`) becomes a first-class frontmatter field, defaulting to `short_term`. It is the source of truth; folder location is derived from it. This keeps churn minimal:

- **The existing type folders** (`Reports/`, `Plans/`, `Memories/`, `Summaries/`, …) **are the short-term working set.** New notes land there exactly as today. Backfilling only adds `memory_tier: short_term`.
- **`Long Term/<project>/`** holds machine-curated durable notes, organised by project.
- **`Archive/<type>/`** holds retired notes. Machine only ever *proposes* moves here; the user owns it.

This maps one-to-one onto the user's own words and avoids a `Short Term/Reports/` + `Long Term/Reports/` folder explosion.

### Ownership differs by tier, and the workflow respects it

| Tier | Machine may | User owns |
|---|---|---|
| `short_term` | create, edit, archive-propose | edit freely; edits win via reconcile |
| `long_term` | create, merge, edit, supersede | may correct; machine re-reconciles |
| `archive` | **propose** moves only, read for embeds | move, delete, restore by hand |

The machine never deletes. Archiving is a reversible move; supersession is recorded, not destructive. This matches the plan/approval and Canvas patterns already in the codebase.

### Editing is built on the merge engine that already exists

`reconcile_note` already does section-aware three-way merging and conflict detection. Every editing primitive routes through it rather than re-parsing Markdown, so user edits are preserved by construction and a conflicting machine edit surfaces instead of clobbering.

### Moves are link-safe or they do not happen

`move_note` rewrites every inbound path-qualified wikilink before committing, and prefers emitting basename links going forward. A move that cannot resolve all inbound links pauses rather than silently breaking the graph. This is the Obsidian "update links on move" contract, done deterministically.

### Obsidian is a UX target, not just a file format

Consolidation output uses the features the vault currently ignores:

- **Transclusion** `![[archived-note#section]]` so a long-term consolidation shows archived detail without duplicating it.
- **Collapsible callouts** `> [!summary]-` so a consolidation proposal folds its diffs.
- **Maps of Content** — one index note per tier and per project, using a linked table, kept current by the workflow.
- **Aliases** so a consolidated note answers to its sources' titles.
- **Tag hierarchy** `#tier/short-term`, `#tier/long-term`, `#tier/archive` for Obsidian search and graph colouring.
- **Block references** `^claim-id` on durable claims so a takeaway can cite the exact source line.

---

## Non-Goals

- No change to the approval/hash machinery, the orchestrator, or model routing.
- No automatic deletion of any note, ever.
- No dependency on Obsidian plugins (Dataview/Bases). Everything renders in vanilla Obsidian and in a plain text editor.
- No retrieval-ranking rewrite beyond tier weighting; a fuller ranking change is separate work.
- Not a replacement for the user's primary vault or a sync product.

---

## Configuration Additions

Ships **disabled**; enabled after live validation.

```json
{
  "memory_tiers_enabled": false,
  "memory_short_term_age_days": 21,
  "memory_review_default_days": 30,
  "memory_long_term_root": "Long Term",
  "memory_archive_root": "Archive",
  "memory_consolidation_enabled": false,
  "memory_consolidation_max_candidates": 40,
  "memory_consolidation_similarity_threshold": 0.82
}
```

---

## Part A — Obsidian-Native Note Editing ✅ COMPLETE (2026-07-22)

The foundation. Everything else composes these.

**Delivered:**
- `update_section(path, heading, content, mode)` in `actions/jarvis_memory.py`, built on the existing `reconcile_note` merge engine — 7 tests.
- `move_note(path, dest_dir, memory_tier)` + `_rewrite_inbound_links` — link-safe relocation, basename-collision refusal, receipt-registered — 5 tests.
- `actions/obsidian_render.py`: `callout` (incl. collapsible), `embed`/transclusion, `wikilink`, `block_id`, `moc_table`, `tier_tags`, all routed through `core.evidence.neutralise` — 12 tests.
- Both editing ops exposed on the `jarvis_memory` dispatcher and tool schema; classified as `write`/requires-approval; 2 injection-corpus cases added (hostile heading can't break frontmatter; ops gated).

**Verified live** on a throwaway vault: created a report, appended to a section, added a collapsed `> [!summary]-` callout embedding `![[note#Findings]]` with a `^claim` block ref, then `move_note` to `Long Term/wifi-sensing/` — inbound links intact.

**Bug found and fixed during A1:** an external editor saving CRLF broke section matching because `_markdown_sections` rejoins with LF. `update_section` now normalises to the vault-standard LF on read (mirroring `_content_hash`).

**Deviation:** none. Effect classification left at the safe default (`write`/requires-approval) rather than ungating short-term edits — the finer tier-based gating belongs with Part B, and the consolidation workflow applies edits under its own approval envelope regardless.

### Original task list

### Task A1: Section editing on the merge engine

**Files:** `actions/jarvis_memory.py`, `tests/test_jarvis_memory.py`

- [x] **Step 1: Write failing tests**
  - `update_section(path, heading, content, mode="replace")` replaces one section, leaves others byte-identical.
  - `mode="append"` and `mode="prepend"` add within the section without disturbing siblings.
  - A concurrent user edit to a *different* section is preserved (route through `reconcile_note`).
  - A concurrent user edit to the *same* section returns a conflict rather than overwriting.
  - The write registers a self-write receipt so the vault watcher marks it `jarvis`-origin (no false "user edited" event — see the round-1 vault-awareness work).
  - `content_hash`, `updated`, and index refresh happen exactly as in `update_note_frontmatter`.

- [x] **Step 2: Implement**
  Read → parse via `_markdown_sections` → construct the proposed body → `reconcile_note(base=current, current=on-disk, proposed)` → `atomic_write` with `expected_revision`. Reuse `update_note_frontmatter`'s retry loop.

- [x] **Step 3: Run** `python -m pytest tests/test_jarvis_memory.py -q -k section`

### Task A2: Move-safe relocation

**Files:** `actions/jarvis_memory.py`, `actions/vault_watch.py` (receipts), `tests/test_jarvis_memory.py`

- [x] **Step 1: Write failing tests**
  - `move_note(path, dest_dir)` moves the file and updates `memory_tier` frontmatter to match.
  - A path-qualified inbound link `[[OldFolder/name|alias]]` anywhere in the vault is rewritten to the new path; the alias is preserved.
  - A basename inbound link `[[name]]` is left unchanged (still resolves).
  - A move that would collide with an existing basename is refused with a clear reason (basename uniqueness underpins link safety).
  - Move emits a single self-write receipt per touched file; the index updates old and new paths; no tombstone is created for a move (identity is preserved by note ID — see the existing move-correlation logic in `core/vault_activity.py`).

- [x] **Step 2: Implement `move_note` and `_rewrite_inbound_links`**
  Scan indexed notes for links resolving to the moved basename/path; rewrite path-qualified ones. Register write receipts for every file changed so the watcher does not report a storm of user edits.

- [x] **Step 3: Run** `python -m pytest tests/test_jarvis_memory.py tests/test_vault_watch.py -q -k "move or link"`

### Task A3: Obsidian rendering helpers

**Files:** `actions/jarvis_memory.py` (or a small `actions/obsidian_render.py`), tests

- [x] **Step 1: Write failing tests**
  - `callout(kind, title, body, collapsed=False)` emits `> [!kind]` / `> [!kind]-` correctly, escaping user content.
  - `embed(note, section="", block="")` emits `![[note]]`, `![[note#section]]`, `![[note#^block]]`.
  - `moc_table(entries)` renders a linked table with basename links and display titles.
  - `block_id(text)` appends a stable `^id` and returns the id for citation.
  - All helpers pass untrusted text through the shared `core/evidence.neutralise` so a note title cannot inject a fence or a fake row (reuses the injection-hardening work).

- [x] **Step 2: Implement** the pure-string helpers.

- [x] **Step 3: Run** `python -m pytest -q -k "callout or embed or moc or block_id"`

### Task A4: Expose editing operations

**Files:** `actions/jarvis_memory.py` dispatcher (`:3903`), `main.py` tool declaration, tests

- [x] Add `update_section`, `move_note`, and a `render` helper op to the `jarvis_memory` operation switch and the tool schema. Classify effect: `update_section` and `move_note` are local writes (confirmation-gated when acting outside the short-term tier or on user-owned archive). Add a corpus case that a title/heading cannot inject a fence through any new op.

---

## Part B — Tiered Memory Model ✅ COMPLETE (2026-07-22)

**Delivered:**
- `memory_tier` frontmatter field (default `short_term`) + `#tier/*` tag, stamped by `create_note` only when `memory_tiers_enabled`. Disabled → field absent, behaviour byte-identical (tested).
- `tier_root(tier, note_type, cfg)` and `note_tier(metadata, path, cfg)` — folder-derived tier so weighting works on existing notes before any backfill; explicit frontmatter wins.
- `query_local` gained a `tier=` filter and a tier weight: long-term and recent short-term at full weight, archive multiplied by `memory_archive_weight` (0.25) — retrievable but never outranking a live note. Inert when disabled.
- `scripts/migrate-memory-tiers.py` — idempotent, dry-run-by-default backfill + per-tier MOC seeding.
- 9 new tests (`tests/test_jarvis_memory.py`), config keys in `config/runtime.json` (shipped disabled).

**Verified live** against a throwaway *copy* of the real vault: 31 notes correctly backfilled `short_term` (a note physically under `Archive/` would backfill `archive`), both MOCs seeded with an Obsidian callout + linked table and `rag_index: false`, re-run a no-op. The real vault was not touched.

**Deviation:** short-term recency decay was designed but not implemented — the current weighting treats all short-term as full weight regardless of age. Age-based decay is deferred to Part C, where `memory_short_term_age_days` already drives promotion; a retrieval-time decay would double-count it. Archive de-weighting (the property that matters for "never outrank a live note") is in place.

### Original task list

### Task B1: The tier field and derived location

**Files:** `actions/jarvis_memory.py`, `config/runtime.json`, tests

- [x] **Step 1: Write failing tests**
  - New notes default to `memory_tier: short_term`.
  - `tier_root(tier, note_type, cfg)` returns the type folder for short-term, `Long Term/<project>/` for long-term, `Archive/<type>/` for archive.
  - With `memory_tiers_enabled: false`, behaviour is byte-identical to today.

- [x] **Step 2: Implement** the field default, `tier_root`, and the `#tier/*` tag stamping.

### Task B2: Tier-aware retrieval weighting

**Files:** `actions/jarvis_memory.py` (`query_local`), tests

- [x] **Step 1: Write failing tests**
  - `query_local` accepts a `tier` filter and a default weighting: long-term full weight, short-term full weight when recent, archive strongly de-weighted (retrievable but never preferred).
  - A superseded or archived note never outranks its live consolidation.
  - Disabled flag → current ranking unchanged.

- [x] **Step 2: Implement** a tier term in the existing reciprocal-rank fusion. Do not rewrite the fusion; add one bounded factor.

### Task B3: One-time migration and per-tier MOC

**Files:** `scripts/migrate-memory-tiers.py`, `actions/jarvis_memory.py`, tests

- [x] Backfill `memory_tier: short_term` on existing notes (idempotent, receipt-registered, no moves). Generate a `Long Term/Long-Term Map.md` and `Archive/Archive Map.md` MOC seeded empty. Dry-run by default; `--apply` to write. Reindex after.

---

## Part C — The `memory_consolidation` Workflow ✅ COMPLETE (2026-07-23)

**Delivered:** `actions/memory_consolidation.py` + `tests/test_memory_consolidation.py` (28 tests). Detection (stale / duplicate / promotable / contradiction, bounded, read-only), a reviewable `Consolidations/` proposal note (collapsible callouts + transclusion), gated apply (promote / merge / archive / flag / review_stale — reversible, idempotent, link-safe), and full registration (tool facade, dispatcher, `HEADLESS_TOOLS`, `main.py` declaration + routing, effect classification, config keys). Ships behind `memory_consolidation_enabled: false`.

**The real bug closes — and better than the plan specified.** Detection does **real snapshot-drift comparison**, not just an age heuristic: for a note carrying `snapshot_hash` + `project_root`, it recomputes the current repo snapshot via `project_learning.inventory_repository` and flags the note when they differ. Verified live against a copy of the actual vault: the `Project Memory - Mark Platform` note (the one falsely claiming `project_operator.py` is unimplemented) is flagged stale because the repo has changed this session. Applied end-to-end, it gets a `[!question]` staleness callout and `review_after` set **in place** — not deleted.

**Design correction made during live testing.** A drift-stale note must be *flagged for re-learning*, not archived — archiving valid-but-outdated project memory would remove it from the working set. Only a note whose explicit `review_after` has passed is archived; drift/age → non-destructive `review_stale`. Duplicate detection uses **token Jaccard** (a real 0–1 similarity the `0.82` threshold applies to), because the RRF fusion score is a tiny reciprocal-rank sum, not a similarity.

**Live-check status:** #1 (bug closes) ✅ proven; #2 (move-safety) ✅ covered by `test_inbound_links_survive_archive_move`; #3 (transclusion) ✅ embeds render in proposals and merges; #4 (user edits win) ✅ via `reconcile_note`; #6 (no churn when disabled) ✅ `detect` returns empty when the flag is off. #5 (manual undo) is a user action, untested by design.

### Original task list

### Task C1: Candidate detection (read-only)

**Files:** `actions/jarvis_memory.py` or new `actions/memory_consolidation.py`, tests

- [x] **Step 1: Write failing tests**
  - **Stale:** notes past `review_after`, or a `snapshot_hash` that no longer matches the current source snapshot (catches the `project_operator` case).
  - **Duplicate:** notes above the similarity threshold on title+takeaways within a project.
  - **Contradiction:** a note whose claim conflicts with a newer note (surfaced for review, never auto-resolved).
  - **Promotable:** short-term notes older than `memory_short_term_age_days` that are project-linked and cited.
  - Detection is bounded by `memory_consolidation_max_candidates` and reads only; it writes nothing.

- [x] **Step 2: Implement** detection over the RAG index + frontmatter. Reuse `query_local` similarity and `snapshot_hash` comparison from `project_learning`.

### Task C2: The consolidation proposal (reviewable artifact)

**Files:** consolidation module, tests

- [x] **Step 1: Write failing tests**
  - Produces one note under `Consolidations/` listing each proposed action (promote / merge / archive / flag) with a collapsible callout per item and an `![[embed]]` of the affected note.
  - Every proposal carries the exact target paths and a reversibility note.
  - No canonical note is modified by generating the proposal.

- [x] **Step 2: Implement** using the Part A render helpers. This is the "distrust the model" gate: nothing acts until the user approves, exactly like a plan.

### Task C3: Applying an approved consolidation (gated, reversible)

**Files:** consolidation module, tests

- [x] **Step 1: Write failing tests**
  - **Promote:** distil a short-term note into a `Long Term/<project>/` consolidation (new or `update_section`-appended), then `move_note` the source to `Archive/` and record `supersedes`.
  - **Merge:** fold N long-term notes into one that `![[embeds]]` and lists the sources, moves sources to archive, and records supersession both ways.
  - **Archive:** move a stale short-term note to `Archive/`, set `memory_tier: archive`, leave a tombstone-free trail.
  - **Flag:** mark a contradiction with `contradicts` and a visible callout; take no destructive action.
  - Every apply is idempotent (re-running a committed action is a no-op) and reversible (archive move can be undone; no deletes).
  - Inbound links survive every move (Part A2 guarantee, re-asserted end-to-end here).

- [x] **Step 2: Implement** on top of Parts A and B. Update the tier MOCs after apply.

### Task C4: Register the capability and workflow

**Files:** `actions/capability_registry.py`, `main.py`, tests

- [x] Add L0 card, L1 manifest, workflow-catalog entry (`memory_consolidation`, risk medium — it moves files and supersedes), triggers ("consolidate memory", "tidy the vault", "what's stale"), and health. Source evidence must not be able to select it (existing rule). Add a `jarvis_memory.query_local` retrieval check that the consolidation is findable after a run.

---

## Documentation

- [x] New Developer Handbook note: *Memory Tiers and Consolidation* — the tier model, ownership, move-safety, and the Obsidian features used.
- [x] Update `06 Obsidian Memory RAG Tasks and Canvas.md` and the User Guide `Index.md` / `Memory Context and Canvas.md`.
- [x] Follow Handbook 09 "Change Discipline": update notes, run focused + full tests, reindex, then `query_local` the new contract.

---

## Verification

**Automated**

```bash
python -m pytest tests/test_jarvis_memory.py tests/test_vault_watch.py tests/test_prompt_injection_corpus.py -q
python -m pytest tests -q --ignore=tests/test_process_trace_ui.py --ignore=tests/test_ui_setup_config.py
```

Baseline before starting is **459 passed**. No pre-existing test may need editing to accommodate this work.

**Live, on a throwaway copy of the vault, flags enabled**

1. **The real bug closes.** Run detection; confirm `Project Memory.md`'s `project_operator` claim is flagged stale (snapshot drift). Approve the flag; confirm retrieval no longer returns it as current fact.
2. **Move-safety.** Promote a report cited by a path-qualified `[[Reports/...]]` link; confirm the inbound link now points at the archived location and still resolves in Obsidian.
3. **Transclusion renders.** Open a merged long-term note in Obsidian; confirm `![[...]]` embeds display the archived sources inline.
4. **User edits win.** Edit a short-term note by hand mid-consolidation; confirm the apply step reconciles rather than clobbers, and a same-section conflict pauses for review.
5. **Reversibility.** Undo an archive move by hand; confirm the note returns to the working set and the index follows.
6. **No churn when disabled.** Set both flags false; confirm `git status` shows no behavioural change and the full suite is unchanged.

**Rollback:** both flags to `false`. The `memory_tier` field is inert when disabled; no moves are reversed automatically (they were reviewed and are user-restorable).

---

## Risks

| Risk | Mitigation |
|---|---|
| A move breaks a path-qualified link | A2 rewrites inbound links or refuses the move; live check 2 proves it end-to-end |
| Consolidation discards a real user edit | Everything routes through `reconcile_note`; same-section conflicts pause |
| An archive move loses information | Moves are reversible and receipt-tracked; nothing is deleted; supersession is recorded |
| Similarity threshold merges distinct notes | Merge is proposal-only and shown with embeds before any action |
| Untrusted note titles inject through new editors | All render helpers pass through `core/evidence.neutralise`; corpus cases added |
| Scope creep into retrieval-ranking rewrite | Non-goal; B2 adds one bounded tier factor only |

---

## Why this file lives here

`Jarvis_notes/Plans` is owned by `plan_workflow` (executable work-item tables, approval hashes; "start plan" resolves the latest). A hand-authored file there could be swept into that machinery. `docs/superpowers/plans/` is the convention for engineering plans meant for a human or coding agent, alongside the model-provider-split, project-operator, and model-health plans.
