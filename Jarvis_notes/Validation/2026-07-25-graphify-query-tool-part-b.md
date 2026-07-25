---
id: "jarvis-20260725T092823Z-fd15cd18"
title: "Graphify Phase 2 Part B: graphify_query Tool — Build and Live Test"
type: "report"
status: "active"
created: "2026-07-25T09:28:23Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "graphify", "tool-registration", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T09:28:23Z"
review_after: ""
source_version: 1
content_hash: "86bfdd42724ddec92fb61a34a0d2e148425b295831c18a6280456f708cee5076"
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
> Phase 2, Part B: give JARVIS's own models a callable tool for ad-hoc structural questions against the pre-built `graphify` knowledge graph, mirroring how the `/graphify` skill is used in Claude Code (Phase 1) and complementing [[2026-07-25-graphify-repo-learning-centrality|Part A's]] deterministic repo-learning boost.

## What got built

New module `actions/graphify_query.py`: `graphify_query(parameters, player=None, *, run=subprocess.run)` wraps the `graphify` CLI's `query` (free-form BFS traversal), `explain` (plain-language node summary), and `path` (shortest relationship path, needs `target_b`) subcommands as a bounded subprocess call. Follows the codebase's established read-only-subprocess pattern exactly: list-form args only, `subprocess.run(..., capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=...)`, `TimeoutExpired`/`FileNotFoundError`/generic `Exception` all caught and turned into a plain string rather than raised, output capped at 6000 chars. `run` is dependency-injected (mirrors `project_operator.delegate_openclaw`'s `run: Any = subprocess.run`) so every path is unit-testable without touching a real subprocess.

**Existence guard**: resolves the target project's root via `project_operator.load_registry()` (default project id `mark_platform`, i.e. this repo), looks for `<root>/graphify-out/graph.json`, and returns a clear "no knowledge graph is built yet" message — never a confusing subprocess failure — when it's missing. An explicit `graph_path` parameter or a `graphify_graph_path` config override both take precedence over that default.

**Config**: `config/runtime.json` gained `graphify_enabled` (kill switch, default true), `graphify_bin` (absolute path to the installed CLI, since it's a global `uv tool install` outside the repo tree — not on PATH by default, confirmed live), `graphify_timeout_seconds` (default 30).

**Full registration chain**, traced from `weather_report` earlier this session and now mirrored exactly:
1. `capability_registry.py` `CAPABILITY_HELP["graphify_query"]` — L0 discovery card, placed next to `file_processor`.
2. `capability_registry.py` `CAPABILITY_POLICY["graphify_query"]` — `risk_level: "low"`, `side_effects: ["local_read"]`, `requires_confirmation: False`, alphabetically between `game_updater` and `jarvis_memory`.
3. `main.py` `TOOL_DECLARATIONS` — description wording follows the one existing "prefer this over X" precedent (`web_search`'s "always prefer this over guessing"): "prefer this over reading or grepping multiple files when the question is about how parts of a codebase relate."
4. `main.py` async dispatch case + `core/tool_dispatcher.py` `_handler()` case, and both `READ_ONLY_TOOLS` and `HEADLESS_TOOLS` sets — verified directly (not just by inspection) that `classify_effect("graphify_query", {})` resolves to `{"effect": "read", "requires_approval": False}` automatically as a result.

## Test coverage

12 new tests in `tests/test_graphify_query.py`: missing question, unknown mode, `path` mode without `target_b`, the config kill-switch short-circuiting before any subprocess call, the missing-graph guard short-circuiting before any subprocess call, exact command construction for `query` (including `--budget`) and `path` (including `target_b` positional), timeout handling, missing-binary handling, a non-zero exit surfacing stderr, an explicit `graph_path` override taking precedence, and a `test_tool_is_declared_and_routed` case mirroring the existing pattern in `test_memory_consolidation.py::RegistrationTests` that checks `main.TOOL_DECLARATIONS`, `tool_dispatcher.HEADLESS_TOOLS`, `tool_dispatcher.READ_ONLY_TOOLS`, and `classify_effect` together. All 12 pass; the four subprocess-guard tests assert via a `run` that raises `AssertionError` if called at all, so a guard silently failing to short-circuit would fail loudly, not pass by accident.

## Live test: real CLI, real graph, no mocks

Ran `graphify_query` directly against the actual `Mark-XLVIII-main` graph, all three modes:
- `mode="query", question="how does tool dispatch work"` — real BFS traversal, correctly rooted at `ToolDispatcher`/`ToolDispatchError`/`DispatchContext`, truncation notice included as designed.
- `mode="explain", question="ToolDispatcher"` — correct node metadata (`core/tool_dispatcher.py:L310`, degree 10) and real edges (its own test file, `get_tool_dispatcher()`, `.call()`, `.list_tools()`).
- `mode="path", question="ToolDispatcher", target_b="capability_registry.py"` — correct 2-hop path through `get_tool_dispatcher()`.
- `project_id="nonexistent_project"` fell back to the repo root correctly (via `BASE_DIR.parent`) rather than erroring, and still found the real graph.
- A follow-up ad-hoc question (`"what calls select_reading_set"`) also traversed correctly, confirming this isn't cherry-picked against one known-good query.

## Deliberately not built this pass

- `affected`/`god-nodes` CLI subcommands exist in `graphify` but weren't in the original Part B scope (`query`/`explain`/`path` only) — left out to avoid scope creep; adding either later is a small, additive change to the same `_MODES` set if the need comes up.
- No change to `core/prompt.txt` — the tool's own description string carries the "prefer this over grepping" steering, per this codebase's only existing precedent (`web_search`), not the standing system prompt.

## Related

[[2026-07-25-graphify-repo-learning-centrality]]
[[Planning Subsystem Roadmap]]
