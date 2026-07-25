---
id: "jarvis-20260725T144323Z-d697127e"
title: "Overview"
type: "report"
status: "active"
created: "2026-07-25T14:43:23Z"
updated: "2026-07-25T15:00:22Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["workflows", "roadmap", "index", "architecture", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T14:43:23Z"
review_after: ""
source_version: 1
content_hash: "b698a955dd9459d480666d54b07e8bee48ac4c85d63ddf9b4e3ed86be0c1f1ae"
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
> Index and walkthrough for three proposed workflows arising from a 2026-07-25 discussion about graphify's information contracts, planning-vocabulary ambiguity, and memory architecture. This is the first real use of `Jarvis_notes/workflows/` as a physical location — each workflow below has its own subfolder here, per the convention [[memory-tiering-and-graphify-index/Plan|Workflow 2]] formalizes.

## Why three, and why these three

A single conversation raised five or six distinct proposals at once (terminology, memory tiering, context compression, `repo_slicer` synergy, planning-agent delegation, plus an ingestion-contracts audit). Bundling all of it into one document would make it hard to pick any one piece up independently, so it's split along where the actual seams are — **how we talk about plans**, **how we store and retrieve memory**, and **how the underlying tools are governed and combined**:

| # | Workflow | Answers | Status |
| --- | --- | --- | --- |
| 1 | [[terminology-and-planning-schema/Plan\|Terminology & Planning Schema]] | What do we call a unit of work, and how do goals decompose into tasks and subtasks without the vocabulary blending together? | **Shipped** — role/directive aliases + mode metadata built, tested (859 passed), live-verified |
| 2 | [[memory-tiering-and-graphify-index/Plan\|Memory Tiering & Graphify Location Index]] | Where does information live, at what tier, and how does graphify help find it without an agent grepping Obsidian links by hand? | **Shipped** — tier numbering resolved (0-3), archive registered + wired, RAG-vs-KG profiling done, and the `memory_tier` -> `lifecycle` migration executed (115 notes, integrity clean, live-verified) |
| 3 | [[contracts-compartmentalization-and-synergy/Plan\|Contracts, Compartmentalization & Tool Synergy]] | What's actually true today about what graphify and JARVIS ingest and expose, and where do the underlying tools (graphify, `repo_slicer`, local vs. cloud agents) compound each other? | **Shipped** — audit, `repo_slicer` synergy, and the `graphify update` git hook all built, tested (852 passed), live-verified |

## Walkthrough

**Workflow 3 is done, not just started** — a live audit of graphify's ingestion contract and MARK's own repo-learning pipeline (checked directly against the running code and the actual repo, not asserted from design docs or memory), plus two real, shipped build targets. The audit found two things worth knowing regardless of what happens with the other two workflows: this repo has no root-level `.gitignore` (so graphify's gitignore-inheritance protection is mostly inactive here), and there's a still-open credential-exposure audit from 2026-07-21 that needs the account owner's attention. The two build targets: graphify's edge data now ranks *which* code slices `repo_slicer` prioritizes within a selected file (live-verified re-ranking a real file against the real graph), and a `.git/hooks/post-commit` hook now keeps the graph itself from silently going stale — building the hook live caught a real gotcha (`graphify update <path>` writes output relative to `<path>`, not the repo root, which would have created a stray duplicate graph directory had it shipped naively). Also included: a near/far-term plan for planning-agent delegation informed by this session's own measured local-model tool-calling reliability (3 of 4 correct, one real miss, zero false positives — a fresh, concrete instance of the model-characterization benchmark's earlier finding), and a scope clarification that "fully automated" means batch execution of already-approved work, never automatic approval itself.

**Workflow 1 is shipped.** The headline finding held up under implementation: WS4c's existing `branch:` fan-out already *was* the "macro pillar with a y-axis of subtasks" shape, so this landed as almost pure vocabulary — `role: workflow` (alias for the existing anchor role), `task:` (alias for `branch:`), and an optional, purely descriptive `mode: research|development` directive, all additive and backward-compatible. (An earlier verbal estimate in this same conversation overstated the blast radius — corrected once the actual schema was checked, and the correction held through implementation.) Live-verified: a real two-task canvas compiled through the actual `compile_canvas` function, no mocks, correctly fanning out two independent task branches from one `mode: research`-tagged anchor and rejoining at a review node. Deliberately not built: a genuinely distinct "goal" layer between workflow and task (a workflow stays 1:1 with its own goal for now), and changing what the decomposition model itself is asked to emit (kept conservative to protect the measured multi-branch success rate).

**Workflow 2 was corrected, then fully shipped.** Its first version presented the tier model as a fresh design when it isn't one — the idea traces to the owner's own prior project, `D:\remember_me` (`project-Mnemosyne-main`), formalized on 2026-07-23 into a complete, still-unbuilt 5-phase plan. The corrected document flagged a genuine numbering mismatch (the old plan's "Tier 0-4" vs. this conversation's "Tier 0-3") as a hypothesis needing confirmation; the owner confirmed 2026-07-25 that 0-4 was a mistype and 0-3 is authoritative, which matched the reconciliation table's own first-pass guess exactly. With that resolved, the genuinely new pieces shipped: `workflows/` is now a live convention, `archive` is registered in `project_registry.json` so `graphify_query` can resolve it (verified live — it correctly reports no graph exists yet, since the archive currently holds one placeholder note, not enough content to extract), and a real RAG-vs-knowledge-graph profiling pass ran 4 question types through both tools with no mocks — see [[2026-07-25-rag-vs-knowledge-graph-profiling]] for the full results, including an honest near-miss (RAG confused two similarly-named historical reports) and a question type neither tool handles well ("what did we decide," which needs a dedicated decision log, not better retrieval). The pre-existing plan's Phase 0 (`memory_tier` → `lifecycle` field rename) — the one piece originally held back pending explicit confirmation given `[[parse-frontmatter-crlf-trap]]`'s prior corruption incident on this same vault — is now done too: backed up, dry-run counted (115 notes), executed via a new `scripts/migrate-lifecycle-field.py`, and a post-migration integrity self-check came back clean with no corruption. The matching code (`jarvis_memory.py`, `memory_consolidation.py`, `main.py`'s tool schema) was updated in the same pass and live-verified end to end, including that the tool-calling surface still accepts the old `memory_tier` name as a synonym.

## Relationship to what's already shipped

All three build on graphify Phase 1 (Claude Code integration) and Phase 2 (Parts A + B: deterministic repo-learning centrality, and the `graphify_query` tool) from earlier the same day — see [[2026-07-25-graphify-repo-learning-centrality]], [[2026-07-25-graphify-query-tool-part-b]], and [[2026-07-25-graphify-live-validation-comprehensive]] for the live-validation pass that found and fixed two real production bugs in that work. None of the three workflows here are asking "should we use graphify" — that's answered and shipped. They're asking "now that it's shipped and validated, how does it change the shape of memory, vocabulary, and tool governance around it."

## Related

[[Planning Subsystem Roadmap]]
