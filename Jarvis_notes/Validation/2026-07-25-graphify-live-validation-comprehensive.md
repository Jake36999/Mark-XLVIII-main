---
id: "jarvis-20260725T103028Z-41446afb"
title: "Graphify Phase 2: Comprehensive Live Validation (Real Dispatch, Real Router, Real Local Model)"
type: "report"
status: "active"
created: "2026-07-25T10:30:28Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "graphify", "tool-registration", "project-learning", "bugfix", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T10:30:28Z"
review_after: ""
source_version: 1
content_hash: "35f06f1da4c8126fd452a45f58ff0d31b4f848cbaf2ef2c03829e1a596b1e63f"
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
> Comprehensive live validation of graphify Phase 2 (Parts A and B: [[2026-07-25-graphify-repo-learning-centrality]], [[2026-07-25-graphify-query-tool-part-b]]) against the running system rather than unit tests alone -- the real production dispatch chain, the real capability router, a real local model, and two full real repository-learning passes. This pass found and fixed two real production bugs that unit tests alone had not caught, plus one hygiene issue.

## What got exercised beyond the original build-and-test pass

Prior validation covered unit tests and direct function calls. This pass additionally exercised: `core.tool_dispatcher.ToolDispatcher.call()` (the real production dispatch class, not just `_handler()`), `core.mcp_server.JarvisMCPServer` (`tools/list` + `tools/call`, the actual MCP protocol surface an external agent would use), `actions.capability_registry.select_capability()` (the real L0 tool-selection layer), `main._router_tool_names_for_text()` (the real token-efficient local-model router), a real `graphify.exe` subprocess under live config toggles, and two full end-to-end `learn_repository()` passes against the real ~900-file multi-project workspace, each involving real local-model map/synthesis calls.

## Finding 1 (fixed): production path-prefix bug silently zeroed Part A's boost

`project_operator.py` calls `learn_repository(project["root"], ...)` using the project's *registered* root from `config/project_registry.json` -- for `mark_platform` that's `F:\Mark-XLVIII-main`, one directory *above* where `graphify extract` was actually run (`F:\Mark-XLVIII-main\Mark-XLVIII-main`). The graph's own `source_file` paths are relative to its extraction root (`actions/capability_registry.py`), but an inventory record built from the registered root carries an extra leading segment (`Mark-XLVIII-main/actions/capability_registry.py`). `_apply_graphify_centrality`'s exact-match dict lookup silently missed on every single file -- not a crash, not the designed "no graph" fallback, just quiet zero effect on the one root the real production entrypoint actually uses. Unit tests didn't catch this because they always used a matching root/graph pair.

**Confirmed live, twice**: a `select_reading_set` comparison with `root=F:\Mark-XLVIII-main` showed *zero* selection difference with vs. without the real graph before the fix, and identical to the earlier fix, matching the earlier finding exactly (`jarvis_memory.py`, `dual_orchestrator.py`, `model_lifecycle.py`, `theme.py`, `test_web_search.py` correctly boosted after).

**Fix**: `_graphify_lookup_degree()` in `actions/project_learning.py` -- an exact-suffix lookup that strips one leading path segment at a time (bounded to 4 attempts) before giving up, so a registered root one or more levels above the extraction root still resolves correctly. Never fuzzy-matches; a genuine miss stays a miss.

**Live end-to-end proof, not just the isolated function**: ran `learn_repository()` in full (real map/synthesis local-model calls, `force_refresh=True`) against `F:\Mark-XLVIII-main` twice -- once before the fix (1179.5s, `files_read_count=28`, no `test_web_search.py` or `theme.py`), once after (908.8s, `files_read_count=35`, both present). Exactly the predicted before/after delta, through the real production code path project_operator.py actually calls, not a synthetic test.

Added `test_graphify_centrality_tolerates_an_inventory_root_above_the_extraction_root` to `tests/test_project_learning.py` (36 tests now, all passing).

## Finding 2 (fixed): graphify's own output was polluting the file inventory

The same pre-fix live run swept `graphify-out/cache/ast/v0.9.26/<hash>.json` -- one of graphify's own internal AST cache blobs -- into `files_read`. `SKIP_DIRS` in `project_learning.py` (the directory-walk exclusion set) had no entry for `graphify-out`, unlike `.git`/`node_modules`/`__pycache__`/etc. Added `"graphify-out"` to `SKIP_DIRS`. Confirmed live: the post-fix run's `files_read` no longer contains any `graphify-out/` path. This is a hygiene issue introduced by installing graphify into this repo, not a graphify defect -- entirely mine to fix.

## Finding 3 (fixed): graphify_query was unreachable through the two real routing layers

Direct function calls always worked, but two layers a real turn actually passes through did not surface it:

- `actions.capability_registry.select_capability()` -- its underlying `_search_cards()` scores by *substring* counting rather than word-tokenized counting (an existing, pre-graphify defect: e.g. "in" matches twice inside "installing"). Rather than fight that scorer, strengthened `CAPABILITY_HELP["graphify_query"]`'s summary and keywords to lead with real relationship verbs (`calls`, `depends`, `connects`, `uses`, `imports`) instead of only graph jargon (`graphify`, `structure`, `path`). Confirmed live: `"what does ToolDispatcher depend on"` went from not appearing in the top 3 candidates to a competitive top-3 score.
- `main._router_tool_names_for_text()` -- the real hardcoded rule table gates which tool schemas a local model even sees for a turn (the actual token-efficiency mechanism this whole effort was meant to serve). It had zero entries routing to `graphify_query`. Added a dedicated rule for relationship-shaped phrasing (`"what calls"`, `"depends on"`, `"knowledge graph"`, `"shortest path between"`, etc.) and added `graphify_query` alongside `project_operator` in the existing project/codebase rule. Confirmed live across 11 realistic prompts: `graphify_query` now correctly offered for every relationship-shaped question tested, and correctly absent for unrelated ones (file reads, PDF summaries, web search).

Added two tests to `tests/test_router_mode.py` (52 tests now, all passing): `test_router_tool_schema_routes_relationship_questions_to_graphify_query`, `test_router_tool_schema_offers_graphify_query_alongside_project_operator`.

**Flagged, not fixed (out of scope)**: `_search_cards`'s substring-counting scorer itself is a pre-existing, systemic defect affecting every registered tool's L0 ranking, not just this one -- e.g. it ranked `memory_consolidation` (score 12, mostly from "on" matching inside "consolidation" repeatedly) above more relevant tools for one test query. Flagged as a separate background task rather than fixed inline; fixing the scorer's tokenization is a broader change affecting all ~40 tools' ranking and warrants its own dedicated review.

## Finding 4: real local-model tool-calling reliability, measured not assumed

Ran 6 real prompts through `core.model_router.call_with_tools(role="worker", ...)` against the actually-configured local worker model (`qwen/qwen3-4b-2507` via LM Studio), using the real `_router_tool_schema()` output for each prompt -- no mocks.

| Prompt | Offered | Called | Result |
|---|---|---|---|
| "What calls select_reading_set in this codebase?" | 5 tools | `graphify_query(question="select_reading_set", mode="query")` | correct |
| "What does the ToolDispatcher class depend on?" | 1 tool (exclusive match) | `graphify_query(question="ToolDispatcher", mode="explain")` | correct |
| "Explain how ToolDispatcher connects to capability_registry." | 2 tools | *(none -- answered in prose, declined)* | **miss** |
| "What is the shortest path between ToolDispatcher and capability_registry?" | 5 tools | `graphify_query(mode="path", target_b="capability_registry")` | correct |
| "What's the weather like in London today?" (negative control) | 1 tool | `weather_report` | correct |
| "Summarize the uploaded PDF for me." (negative control) | 1 tool | `file_processor` | correct |

3 of 4 relationship-shaped prompts correctly triggered `graphify_query` with well-formed arguments, including exact `mode`/`target_b` selection for the path-finding case. Both negative controls stayed clean -- zero false positives. One genuine miss: offered exactly the right (and only sensible) tool, the model answered in hedging prose instead of calling it. This is a live, concrete instance of this session's earlier benchmark finding that small local models are unreliable at consistently choosing to call a new tool -- not a contradiction of it. It's exactly why Part A's deterministic, model-independent centrality boost was built as the *primary* ROI path, with Part B's ad-hoc tool explicitly scoped as a secondary, imperfect-but-still-net-positive capability.

## Finding 5: full-stack plumbing, latency, and concurrency all clean

- `ToolDispatcher.call()`: schema validation, effect classification (`read`/no-approval, confirmed automatically), and handler dispatch all correct: valid calls succeed, missing required args are rejected with a clear schema error, an unknown `mode` value reaches the handler and returns a clean message rather than crashing.
- `JarvisMCPServer.call_method()`: `tools/list` surfaces `graphify_query`; `tools/call` executes it and returns real structural data -- confirms the MCP protocol surface (the path an external agent would actually use) works end-to-end.
- Config toggles against the real `config/runtime.json` (not mocks): `graphify_enabled=false` short-circuits cleanly before any subprocess; an artificially low `graphify_timeout_seconds` produces a real `subprocess.TimeoutExpired` handled gracefully; a bad `graphify_bin` path produces a real `FileNotFoundError` handled gracefully. Config restored to its intended values (`enabled=true`, `timeout=30`) after each test; `git diff` confirmed a clean 3-line final diff.
- Latency: 7 sequential real CLI calls averaged 0.77s (range 0.67-1.10s), well inside the 30s default timeout; an identical repeated query returned byte-identical output length, confirming no cross-call state drift.
- Concurrency: 5 simultaneous `graphify_query` calls via a thread pool each returned the correct answer for their own question with no cross-contamination.

## Test suite

36 tests in `test_project_learning.py` (+1 for the path-prefix fix), 52 in `test_router_mode.py` (+2 for the router-table fix), `test_graphify_query.py`, `test_capability_registry.py`, `test_tool_dispatcher.py`, `test_project_operator.py`, and `test_model_router.py` all passing. Full repository suite re-run after every fix in this pass; final count **845 passed** (842 before this pass, +3 for the new tests added, zero regressions), 5:14 wall time.

## Related

[[2026-07-25-graphify-repo-learning-centrality]]
[[2026-07-25-graphify-query-tool-part-b]]
[[Planning Subsystem Roadmap]]
