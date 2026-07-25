---
id: "jarvis-20260725T090001Z-2310f1e5"
title: "Graphify Phase 2 Part A: Repo-Learning Centrality — Build and Live Test"
type: "report"
status: "active"
created: "2026-07-25T09:00:01Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "graphify", "project-learning", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T09:00:01Z"
review_after: ""
source_version: 1
content_hash: "94131568eab995bf2d7c7b5ce268e7f14ab04ea141444c2c828d59dab1cd0d37"
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
> Phase 2, Part A: give JARVIS's repository-learning file-selection the same knowledge-graph signal Claude Code now has via `graphify` (Phase 1, same day). Deterministic-only — no model call, no new tool-calling reliability risk, strictly additive.

## What got built

`actions/project_learning.py`'s `select_reading_set()` already folds import centrality + code mass into file scores via `_apply_centrality()` — but that function reconstructs a same-process, per-run, **import-only** dependency graph from scratch on every call (`_python_module_facts`, capped at 1200 files). A pre-built `graphify` graph is richer: real `calls`/`inherits`/`references` edges, not just `imports`, persisted once rather than rebuilt every run.

Added `_apply_graphify_centrality()`, called right alongside the existing `_apply_centrality()` in `select_reading_set`. It reads `<project_root>/graphify-out/graph.json` (or an explicit override via the new `graphify_graph_path` keyword) and counts **cross-file** relationship edges per file — deliberately excluding `contains` edges (a file "containing" its own functions is just file size, already covered by the existing code-mass term, and would otherwise swamp the genuine cross-file signal). The result folds into the same score field the keyword scorer and import-centrality already use, capped comparably (`_GRAPHIFY_MAX_BOOST = 150`, similar order to the existing `_CENTRALITY_MAX_BOOST = 120`).

**Strictly additive by construction**: `_read_graphify_graph` returns `None` (never raises) on a missing file, unreadable file, invalid JSON, or an unexpected shape — every project without a pre-built graph gets byte-identical behavior to before this existed. Verified directly, not just claimed: all 30 pre-existing `test_project_learning.py` tests (none of which build a graph fixture) passed unchanged.

## Test coverage

4 new tests: a real cross-file hub gets boosted correctly while a `contains`-only file doesn't; a strict no-op when no graph exists; graceful degradation on a corrupt `graph.json` (no crash, no partial mutation); and an end-to-end `select_reading_set` test confirming the `graphify_graph_path` override genuinely switches behavior. Full suite: **830 passed**, zero regressions (826 → 830).

## Live test: real repo-learning selection, real graph, real codebase

Ran `select_reading_set` against the actual `Mark-XLVIII-main` source (615 files inventoried) two ways: pointed at the real graph built in Phase 1, and with no graph. Every hub the augmentation flagged matches independent manual analysis of the same `graph.json` exactly: `jarvis_memory.py` (graphify_centrality 159), `dual_orchestrator.py` (96), `runtime_config.py` (83), `model_lifecycle.py` (63), `model_router.py` (50) — all correctly hit the score cap. File selection genuinely changed: `test_web_search.py` and a UI-components `theme.py` (both with real cross-file connectivity the import-only signal missed) entered the top 20 in place of two files with weaker cross-file signal.

(First attempt at this comparison produced a misleading result — reusing the same `inventory["files"]` list across both calls let in-place score mutations from the first call compound into the second, an artifact of the ad-hoc test script's shallow copy, not the production code path. Caught by cross-checking against the independently-computed graph degrees before trusting the result.)

## Deliberately not built this pass

- **Part B** (a callable `graphify_query` tool for ad-hoc model-initiated queries) — separate, already-scoped next increment.
- **JARVIS running its own graph extraction/updates** — both systems share the one graph already built; keeping it fresh is a future need, not addressed here.
- **Wiring this into `core/prompt.txt`** — unnecessary for this piece specifically, since the augmentation is fully deterministic and never depends on a model choosing to do anything.

## Related

[[Planning Subsystem Roadmap]]
