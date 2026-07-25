---
id: "jarvis-20260725T144229Z-ec0c0b80"
title: "Workflow 2: Memory Tiering and Graphify Location Index"
type: "report"
status: "active"
created: "2026-07-25T14:42:29Z"
updated: "2026-07-25T15:00:22Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["workflows", "memory", "tiering", "rag", "graphify", "shipped", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T14:42:29Z"
review_after: ""
source_version: 1
content_hash: "ca4c85d330e1d83a30ffc690e5f97f279a9873b413533b3a20fea9e90f0168a3"
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
> Workflow 2 of 3 (see [[Overview]]). Formalizes the tier memory model the owner restated 2026-07-25, adds a physical `workflows/` vault directory, proposes graphify as an archive-tier location index, and scopes a RAG-vs-knowledge-graph profiling pass. Builds directly on the graphify work already shipped this session: [[2026-07-25-graphify-repo-learning-centrality]] (Part A), [[2026-07-25-graphify-query-tool-part-b]] (Part B), [[2026-07-25-graphify-live-validation-comprehensive]] (live validation + two production bugs found and fixed).

> [!danger] Correction — this is not a new design, and the first version of this document didn't say so
> The original version of this document presented the tier model below as though it were being proposed fresh in this conversation. It isn't. Checked directly against the vault and a prior session transcript rather than assumed:
> - **The idea is the owner's own, from 2026-07-23**, not something built for MARK from scratch. It traces to the owner's own prior project, `D:\remember_me` (`project-Mnemosyne-main`) — a complete, working memory-partitioning/RAG-cartridge system the owner built before this project. The owner proposed the pattern for MARK, then the specific Tier 2 (general index/overview/event-log vs. cartridge detail) framing in conversation; I then read `D:\remember_me` directly and formalized it into `Mark-XLVIII-main/docs/superpowers/plans/2026-07-23-mark-project-knowledge-cartridges.md` (source repo, outside this vault — not a vault note, so not wikilinked) — a complete 5-phase build plan, still fully unbuilt (confirmed: it's explicitly listed as a "scoped-but-unbuilt plan" as recently as 2026-07-24, and nothing touched since).
> - **Tier numbering resolved (owner, 2026-07-25): 0-3 is authoritative.** The existing plan's "Tier 0-4" was a mistype at the time, not a deliberate fifth tier. The reconciliation table below turned out to be exactly right on the first pass: old Tier 1 (general categories) and old Tier 2 (index/overview/event log) merge into one Tier 1 ("general documentation"), old Tier 3 (project cartridge) becomes Tier 2, old Tier 4 (archive) becomes Tier 3.
> - **The plan doc already scopes the exact `memory_tier` naming collision this document's "open questions" ran into independently**: `memory_tier: short_term | long_term | archive` is a *lifecycle* axis, separate from the *structural* tier axis, and the existing plan's own Phase 0 is a rename of `memory_tier` → `lifecycle` to stop the two words colliding. This document rediscovered the same collision from a different angle (the `workflow_id` filter question below) without noticing the plan that already resolved it.
> - **[[06 Obsidian Memory RAG Tasks and Canvas]]** (`Jarvis_notes/User Guide/Developer Handbook/`) does describe the *general* memory-layer architecture (vault Markdown, SQLite index, `query_local`, tasks, canvas) accurately and is good background — but checked directly, it does **not** mention cartridges, Mnemosyne, or a structural tier axis anywhere. The cartridge plan doc above is the actual source for that; citing the handbook page for it was imprecise.

## Tier 0-3 (authoritative, confirmed 2026-07-25) mapped against the 2026-07-23 plan

| Tier 0-3 (authoritative) | Contents | 2026-07-23 plan's original label | Note |
| --- | --- | --- | --- |
| **0** immediate context | `.json` config, system prompts, tool manifests, dot-prefixed folders | control plane — `.jarvis/`, dual-orchestrator YAML, `project_registry.json` | Same idea; the dotfolder-naming detail is new and useful, wasn't in the original |
| **1** general documentation | overviews, trackers, indexes | general categories **+** index/overview/event log (two separate tiers in the 2026-07-23 draft) | **The 0-4 draft's real mistake**: these were two tiers there; confirmed 2026-07-25 they're one |
| **2** project / workflow-specific | compartmentalized cartridge, now also per-workflow | project knowledge (cartridge) | Same concept, cartridge = compartmentalized info |
| **3** archive | user-led, graphify-indexed, permission-gated recall | archive — `lifecycle: archive` + `rag_index: false` | Same concept |

## Status: fully shipped, 2026-07-25. Tier reconciliation resolved, `workflows/` convention live, archive registered + wired, RAG-vs-KG profiling done, and Phase 0's `lifecycle` rename executed (backed up, dry-run counted, applied, integrity clean, code updated, live-verified — see below).

This document's genuinely *new* contribution — the `workflows/` directory convention, graphify as an archive-tier index, and the RAG-vs-KG profiling pass — is built. The pre-existing 5-phase plan's Phase 0 (the `memory_tier` → `lifecycle` rename) is also done, executed with the owner's explicit confirmation after the backup and dry run this document originally scoped it around.

## Current state vs. the tier model

> [!warning] Read this before assuming any of this is already implemented
> `jarvis_memory.py` has a real, working tier mechanism today: **three named lifecycle values** (`short_term` / `long_term` / `archive`, now stored under the `lifecycle` frontmatter key as of Phase 0's 2026-07-25 rename), not the structural 0-3 axis. Checked directly against the code, not assumed.

- **Structural Tier 0 (immediate context)** — not a memory-system concept in code today. `.obsidian`, `.jarvis`, etc. exist as plain filesystem/Obsidian convention; nothing in JARVIS treats them as a distinct, named tier.
- **Structural Tier 1 (general documentation)** — closest existing match is the `short_term` lifecycle tier, also `note_tier()`'s fallback default for any note with no explicit `lifecycle`. Not a deliberate mapping, just the closest thing that exists. The `vault_activity` journal the old plan names as the event-log source is real and already running; nothing currently surfaces it as a bounded per-project log the way Phase 3 of the existing plan describes.
- **Structural Tier 2 (project cartridge / project-workflow compartmentalization)** — **partially real, and the part that's real is softer than "compartmentalized" implies.** `query_local()` (`actions/jarvis_memory.py:2144`) runs lexical FTS and semantic vector search against **one unified SQLite index covering every note in the vault** — no physically separate index or collection per project, exactly matching what the existing plan's own "Storage decision" section already found and recommended keeping (**"namespaced," matching Mnemosyne's own actual approach — not a gap, a confirmed-sufficient design**). A `project_id` filter is applied to results *after* retrieval, and only compartmentalizes when the caller passes it — an unscoped query is eligible to surface notes from every project. Workflow-level compartmentalization (a `workflow_id` filter alongside `project_id`) doesn't exist anywhere in `query_local`'s signature today, and isn't in the original plan either — it's new, prompted by [[terminology-and-planning-schema/Plan|Workflow 1]]'s vocabulary.
- **Structural Tier 3 (archive)** — the `archive` lifecycle tier is real and already down-weighted in retrieval scoring (`_tier_score_multiplier`, `actions/jarvis_memory.py:2132`) when `memory_tiers_enabled` is on (confirmed on in `config/runtime.json`). What's **not** built, in either the original plan or since: graphify indexing of the archive, and — the same gap the original plan didn't fully resolve either — **no enforcement anywhere today of "never promote archive content into active memory without permission."** Down-weighting a tier in search ranking is not the same guarantee as gating promotion out of it.

## Proposed work

### 1. Phase 0 of the existing plan: `memory_tier` → `lifecycle` rename — done

> [!success] Executed 2026-07-25, with explicit confirmation, after backup + dry run
> Backed up (`Jarvis_notes_backup_2026-07-25_pre_lifecycle_migration`, 18 MB), dry-run counted (115 of 160 notes would be touched: 113 `short_term`, 1 `archive`, 1 `long_term`, 45 with no field at all left untouched), then executed via the new `scripts/migrate-lifecycle-field.py --apply`.
>
> **Result**: exactly the 115 notes the dry run predicted were renamed, 0 unreadable, 0 corrupted. Post-migration `core.note_integrity.scan_vault()` self-check: **clean** (160 notes scanned, only the 3 pre-existing info-level `bare_file_citation` notices — the same ones already known-benign from the earlier YAML-hardening pass — zero `doubled_frontmatter`/`unparsable_frontmatter`/`exploded_tags`/`unreadable` errors). The CRLF corruption class `[[parse-frontmatter-crlf-trap]]` warned about did not recur.
>
> **Code updated to match, not just the data**: `actions/jarvis_memory.py` (`note_tier()`, `create_note()`, `move_note()` — parameter renamed `memory_tier` → `lifecycle` — and `query_local()`'s result dicts), `actions/memory_consolidation.py` (internal dict keys and its `create_note`/`move_note` calls), `main.py`'s tool schema. The model-facing `jarvis_memory` tool's `move_note` operation accepts `lifecycle` as the primary parameter name, with `memory_tier`/`tier` kept as accepted synonyms specifically on that tool-calling surface (not in vault data or internal `metadata_extra` dicts, which got a clean cutover with no compatibility shim). `scripts/migrate-memory-tiers.py` (the *other*, earlier, still-active backfill script for notes missing a tier entirely) updated to write `lifecycle` too, so it can't reintroduce the old field name on a future run.
>
> **Live-verified end to end, not just unit-tested**: read a real already-migrated vault note directly (`lifecycle: short_term` present, `memory_tier` absent) — confirmed `note_tier()` and `query_local()` both resolve and surface it correctly against the real index. Created a real note, moved it with the new `lifecycle=` keyword, and separately called the `jarvis_memory` tool dispatcher itself with the *old* `memory_tier` key to confirm the legacy tool-call synonym still works. 5 new tests in `tests/test_jarvis_memory.py` (`LifecycleFieldMigrationTests`: dry-run makes no writes, apply renames and preserves the value, an already-migrated note is left alone, a note with neither field stays untouched, re-running is a true no-op).
>
> **Scope boundary, stated explicitly**: only the frontmatter *field* was renamed. Internal function/constant names that use the generic word "tier" (`note_tier()`, `tier_root()`, `_tier_score_multiplier()`, the `MEMORY_TIERS` constant, the `memory_tiers_enabled` config flag) and the `#tier/short-term`-style Obsidian tag convention (`tier_tags()`) were deliberately left alone — renaming those too would be a much larger, differently-scoped refactor than "rename the frontmatter field," which is what was actually asked for.

### 2. The `workflows/` vault directory convention

`Jarvis_notes/workflows/` already exists (empty as of this session, populated by this document set as its first real instance). Convention going forward: every JARVIS "workflow" (per [[terminology-and-planning-schema/Plan|Workflow 1]]'s proposed vocabulary) gets its own subfolder here.

This is also a direct, concrete answer to **the existing plan's own open question #2** ("what are the 4-5 clear overarching categories you want at root?" — never answered as of 2026-07-23): `workflows/` is a real candidate for one of those root-level categories, alongside `Projects/`. Recommend treating it as a second, independent compartmentalization axis at the *same* structural tier as project cartridges — a workflow can span projects, a project can have many workflows — rather than a new tier of its own. This should be confirmed as part of resolving question 1 above, not decided unilaterally here.

### 3. Graphify as an archive-tier location index — built

> [!success] Shipped 2026-07-25
> `archive` registered in `config/project_registry.json` pointing at `Jarvis_notes/Archive`, with `safe_operations: []` (every `project_operator` operation against it defaults to requiring confirmation — verified with a dedicated test, not assumed). Live-checked the archive's actual current contents first rather than building blind: as of this pass it holds exactly one placeholder note (`Archive Map.md`, 908 bytes) — not enough real content for a `graphify extract` to be worthwhile yet, so extraction was deliberately **not** run. What *was* verified live: `graphify_query({"project_id": "archive", ...})` correctly resolves the real registry entry and returns a clean "no knowledge graph is built yet... run `graphify extract`" guard message rather than a confusing failure — the wiring works end to end, ready for whenever `memory_consolidation` or manual archiving actually populates the folder. 2 new tests (`test_project_operator.py`, `test_graphify_query.py`, the latter against the real registry with no mocks).
>
> The permission-gate gap noted above (nothing stops an agent recording archive content into active memory without permission) is **still open** — this increment only made the archive *findable*, it didn't add the enforcement gate. Still a real prerequisite for later, not resolved by this piece.

### 4. RAG vs. knowledge-graph profiling — built

> [!success] Shipped 2026-07-25
> Ran the exact methodology below for real: 4 question types, 1 live question each, both `jarvis_memory.query_local` and `graphify_query` called unmodified, no mocks. Full results, including the imperfect ones (a real RAG near-miss confusing WS4b/WS4c reports, and a case neither tool actually answered well), written up in [[2026-07-25-rag-vs-knowledge-graph-profiling]]. Headline routing heuristic: structural/symbol-named questions and "related to \<symbol\>" questions -> `graphify_query` first (measured 5x faster and more precise); "what did we decide/discuss" questions -> RAG first, but don't over-trust the top-1 result blindly; neither tool substitutes for a dedicated decision log when a past decision specifically needs to be reliably recallable.

<details><summary>Original methodology (for reference — see the linked report for what was actually run)</summary>

1. A pure structural question ("what calls X"), a pure semantic/associative question ("what did we decide about Y and why"), a mixed question ("find files related to Z"), and a narrative/historical question ("what happened during the WS4b live test").
2. Run each through both tools unmodified, no prompt engineering to favor either.
3. Score on precision, latency, and payload cost.
4. Write up findings, derive a routing heuristic.
5. Feed that heuristic into the tool-selection layer discussed in [[contracts-compartmentalization-and-synergy/Plan|Workflow 3]] (the same `_router_tool_names_for_text` mechanism already fixed this session for `graphify_query`'s discoverability) — not built as part of this pass; the heuristic exists, wiring it into the router is a natural next increment.

</details>

## Open questions

- ~~Confirm the tier-numbering reconciliation (0-4 vs. 0-3).~~ **Resolved 2026-07-25: 0-3.**
- ~~Phase 0's `lifecycle` rename.~~ **Resolved 2026-07-25: executed**, with explicit confirmation, backup, dry run, and a clean post-migration integrity check — see above.
- Does "workflow" need its own `workflow_id` field threaded through `query_local`/`create_note`, or is folder-path scoping (`workflows/<slug>/`) sufficient on its own? Affects whether this is a schema change or a pure documentation/convention change.
- Should the archive-permission-gate be enforced at the `jarvis_memory` write layer (e.g. a check when a note's *source* traces back to an archive-tier note) or left as a standing instruction for the agent to self-police? The former is a real guarantee; the latter is exactly the kind of soft rule this whole audit was trying to move away from.
- Registering the archive as a `project_registry.json` entry for `graphify_query` reuse — any naming collision risk with a real future project literally named "archive"?
- The existing plan's own open questions #1 (namespaced vs. per-file — recommended namespaced, not yet confirmed) and #3 (`knowledge_expansion`'s deep-research step: reuse `deep_research_report` or wrap external tooling) are both still open too and unaffected by anything in this document.

## Related

[[Overview]]
[[terminology-and-planning-schema/Plan]]
[[contracts-compartmentalization-and-synergy/Plan]]
[[06 Obsidian Memory RAG Tasks and Canvas]]
[[2026-07-25-graphify-repo-learning-centrality]]
[[2026-07-25-graphify-query-tool-part-b]]
[[2026-07-25-graphify-live-validation-comprehensive]]
[[Planning Subsystem Roadmap]]
