---
id: "jarvis-20260725T150903Z-ec17b914"
title: "Developer Handbook Documentation: Live Validation"
type: "report"
status: "active"
created: "2026-07-25T15:09:03Z"
updated: "2026-07-25T15:28:36Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "documentation", "graphify", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T15:09:03Z"
review_after: ""
source_version: 1
content_hash: "da3136cb8ff3bc41e51c8e9876f14745e47cde66b11a3c937660b4e0380a248b"
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
> Live validation of the Developer Handbook / User Guide documentation update (new Note 14, plus updates to Notes 00/02/05/06 and two User Guide pages). Every factual claim below was checked against the actually-running code or the actually-published vault, not re-asserted from the docs themselves — this is a documentation-accuracy audit, not a restatement.

## Method

15 checks, spanning: deployment state, the tool registration chain, live tool calls across all 3 `graphify_query` modes, live-executed vocabulary/directive aliasing, source-level confirmation of the two bug fixes documented in Notes 02 and 14, exact-value confirmation of the sensitive-file deny-lists documented in Note 05, and a re-run of the `repo_slicer` symbol-degree reranking numbers originally captured when Workflow 3 shipped — specifically re-run now, after further vault/code changes, to catch any drift the documentation might have silently gone stale against.

## Results — 15/15 passed, zero discrepancies

| # | Claim (doc) | Check | Result |
| --- | --- | --- | --- |
| 1 | Skill installed globally (Note 14) | `~/.claude/skills/graphify/SKILL.md` exists | Confirmed |
| 2 | Graph at repo root (Note 14) | `F:\Mark-XLVIII-main\graphify-out\graph.json` exists | Confirmed |
| 3 | PreToolUse hook removed (Note 14) | `.claude/settings.json` — `PreToolUse: []` | Confirmed |
| 4 | Config keys `graphify_enabled`/`graphify_bin`/`graphify_timeout_seconds` (Note 14) | Present in `config/runtime.json` | Confirmed |
| 5 | Post-commit hook present (Note 14, Workflow 3) | `.git/hooks/post-commit` exists, executable | Confirmed |
| 6 | `graphify_query` registered, read-only, no approval (Note 14, Tools Skills and Capabilities) | `ToolDispatcher().list_tools()` + `classify_effect()` | Confirmed: `available=True`, `effect=read`, `requires_approval=False` |
| 7 | `role: workflow`/`root`/`goal`/`milestone` all alias to `plan` (Glossary, Note 13) | `canvas_plan._ROLE_ALIASES` | Confirmed, all four map to `"plan"` |
| 8 | `task:` aliases to `branch:` (Glossary, Note 13) | `canvas_plan._DIRECTIVE_ALIASES` | Confirmed: `{"task": "branch", ...}` |
| 9 | `_search_cards` is word-tokenized, not substring-counted (Note 02) | Direct source read | Confirmed: `words.split()` + `words.count(variant)`, not `haystack.count(term)` |
| 10 | Sensitive-file deny-lists exact contents (Note 05) | `project_learning.SENSITIVE_NAMES`/`SENSITIVE_SUFFIXES` | Confirmed, matches documented lists exactly (10 names, 7 suffixes) |
| 11 | `graphify_query` `query`/`explain`/`path` modes all work (Note 14, Tools Skills and Capabilities) | 3 live calls, no mocks | Confirmed — real BFS traversal, real node explain, real 2-hop path |
| 12 | `memory_tiers_enabled` flag name unchanged by the lifecycle rename (Note 06) | `config/runtime.json` | Confirmed, still present as documented |
| 13 | `archive` resolves via `graphify_query`, correctly reports no graph yet (Note 14, Workflow 2) | Live call with `project_id="archive"` | Confirmed, exact guard message matches |
| 14 | A real note has `lifecycle`, not `memory_tier` (Note 06) | `read_note()` on Note 14 itself | Confirmed: `lifecycle="short_term"`, `memory_tier` absent |
| 15 | `repo_slicer` reranking numbers still hold (Note 14, Workflow 3) — re-run, not just re-cited | `_graphify_symbol_degree_for_root` + `_python_slice_view`, with vs. without | **Unchanged**: `capability_registry` degree 22, `build_registry` degree 6, `_search_cards` degree 1; `_search_cards` still moves from 5th to 3rd position with the signal applied |

## What this confirms

The documentation written this session describes the system as it actually behaves right now, not as it behaved at the moment of writing and possibly since drifted. Check #15 specifically re-ran a numeric claim after additional vault/code activity (the documentation pass itself, the lifecycle migration, several vault reindexes) rather than trusting the original capture — the numbers held exactly, which is real evidence the underlying mechanism is stable, not just that the first measurement was correct.

## Related

[[User Guide/Developer Handbook/14 Graphify Knowledge Graph Integration]]
[[Jarvis_notes/workflows/Overview|Workflows Overview]]
