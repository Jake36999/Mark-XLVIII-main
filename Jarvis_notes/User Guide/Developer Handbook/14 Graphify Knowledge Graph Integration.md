---
id: "developer-graphify-knowledge-graph"
title: "Graphify Knowledge Graph Integration"
type: "guide"
status: "active"
created: "2026-07-25"
updated: "2026-07-25T14:54:37Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["developer-handbook", "graphify", "knowledge-graph", "repo-slicer", "rag", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.95
content_hash: "fc219f0d8c372d8abd9614dbbbbe024ea88a642f860341c49cfbe931670ef14d"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Graphify Knowledge Graph Integration

> [!abstract] What graphify is, here
> graphify (PyPI `graphifyy`, CLI `graphify`) is a third-party, external tool: a local, tree-sitter-based knowledge graph builder for a codebase. Fully free/local for code (zero LLM cost, confirmed live — "Token cost: 0 input · 0 output" on this repo's own extraction). It answers structural questions RAG is weak at: what calls a symbol, what a symbol depends on, and the shortest relationship path between two named things. MARK integrates it in two independent ways — a deterministic boost to existing repo-learning (Part A), and an on-demand tool a model can call directly (Part B) — plus a `repo_slicer` synergy and an automated freshness hook. All shipped and live-validated 2026-07-25.

## Deployment

- **Skill**: installed globally (`graphify install`), giving `/graphify` in Claude Code for any project, not just this one.
- **Graph**: `graphify-out/graph.json` at the repo root (`F:\Mark-XLVIII-main\graphify-out`), scanning the inner `Mark-XLVIII-main/` source tree. This split matters — see "The path-prefix bug" below.
- **Hook**: a Claude Code PreToolUse hook was briefly installed then removed per an explicit decision (soft-nudge wording was investigated as a possible prompt injection, confirmed genuine, then uninstalled anyway to keep the skill without the nudge).
- **Ingestion contract** (audited, not assumed): extension allowlist (unknown extensions like `.key`/`.pem` are never scanned at all, not via an explicit rule), gitignore-respecting (though this repo has no root-level `.gitignore` — a real, separate gap noted but not graphify's fault), and a JSON extractor that deliberately skips "data-shaped" JSON (config/manifest files only) rather than extracting arbitrary API-response or secret-shaped JSON as structure.

## Part A — deterministic repo-learning centrality boost

`actions/project_learning.py`'s `select_reading_set()` already scored files by structural importance via `_apply_centrality()` — a same-process, per-run, **import-only** dependency graph rebuilt from scratch every call. `_apply_graphify_centrality()` (added alongside it, not replacing it) reads the pre-built graphify graph once and folds in cross-file relationship degree (`calls`/`inherits`/`references`, not just `imports`) as an additional score boost. `contains` edges are deliberately excluded (a file "containing" its own functions is just file size, already covered by the existing code-mass term).

**Strictly additive by construction**: `_read_graphify_graph()` returns `None` — never raises — on any missing file, unreadable file, invalid JSON, or unexpected shape. A project with no graph gets byte-identical behavior to before this existed.

> [!danger] The path-prefix bug (found live, fixed same day)
> `project_operator.py` calls `learn_repository()` with a project's *registered* root (`F:\Mark-XLVIII-main`, the outer wrapper directory) — one level above where `graphify extract` actually scanned from (`F:\Mark-XLVIII-main\Mark-XLVIII-main`). The graph's own `source_file` paths are relative to its extraction root, so an inventory record built from the registered root carried an extra leading path segment the graph never had. The exact-match lookup silently missed on **every single file** — not a crash, not the designed "no graph" fallback, just quiet zero effect on the one root the real production entrypoint actually uses.
>
> **Fix**: `_graphify_lookup_degree()` strips one leading path segment at a time (bounded to 4 attempts) before giving up. **Proven live**, not just unit-tested: a full `learn_repository()` run before the fix produced `files_read_count=28` with none of the graph-boosted files present; the identical run after the fix produced `files_read_count=35` with `test_web_search.py` and a UI `theme.py` file correctly present — exactly the predicted delta.

## Part B — `graphify_query`, an on-demand tool

`actions/graphify_query.py` wraps `graphify query`/`explain`/`path` as a bounded, dependency-injectable subprocess call (`run: Any = subprocess.run`, mirroring `project_operator.delegate_openclaw`'s pattern). Registered through the full chain traced from `weather_report`:

| Step | Location |
| --- | --- |
| L0 help card | `capability_registry.CAPABILITY_HELP["graphify_query"]` |
| Risk policy | `capability_registry.CAPABILITY_POLICY["graphify_query"]` — `risk_level: low`, `requires_confirmation: False` |
| Tool schema | `main.py` `TOOL_DECLARATIONS` |
| Dispatch | `main.py`'s async handler + `core/tool_dispatcher.py`'s `_handler()`, `READ_ONLY_TOOLS`, `HEADLESS_TOOLS` |

Existence-guarded: if `<project_root>/graphify-out/graph.json` doesn't exist, it returns a clear message rather than a confusing subprocess failure. Config: `graphify_enabled`, `graphify_bin`, `graphify_timeout_seconds` in `config/runtime.json`.

> [!important] Local tool-calling reliability, measured not assumed
> Live-tested against the real configured worker model (`qwen/qwen3-4b-2507` via LM Studio, `core.model_router.call_with_tools(role="worker")`, no mocks): 3 of 4 relationship-shaped prompts correctly triggered `graphify_query` with well-formed arguments, including exact `mode`/`target_b` selection for a path-finding question. 1 miss: offered exactly the right (and only) tool, the model answered in hedging prose instead of calling it. Zero false positives on negative controls (weather, PDF summary). A concrete, fresh instance of this session's model-characterization finding that small local models are unreliable tool-callers — not a contradiction of it. This is exactly why Part A (deterministic, no tool-calling dependency) is the primary-ROI path and Part B is explicitly secondary/ad-hoc.

### Discoverability had to be fixed too

A new tool existing isn't the same as a model ever seeing its schema. Two real gaps were found and fixed:

- `capability_registry`'s L0 keyword scoring initially only matched graph jargon ("graphify", "structure", "path"), not the natural verbs people actually use ("what calls X", "what depends on Y"). Fixed by leading the keyword list with relationship verbs.
- `main.py`'s `_router_tool_names_for_text()` — the real token-efficiency router that decides which tool schemas a local model even sees for a turn — had **zero** rule-table entries routing to `graphify_query` at all. Added a dedicated rule for relationship-shaped phrasing, verified live across 11 realistic prompts.

Separately, this second discoverability check surfaced an unrelated, pre-existing bug in `capability_registry._search_cards()` (substring-counting instead of word-tokenized counting — see [[02 Capability Registry MCP and Safety]]), fixed the same day.

## `repo_slicer` synergy

`core/repo_slicer.py` (extracted from the DAG Engine's `semantic_slicer_AG.py`) turns an *already-selected* file into structured, deduplicated per-function/class slices for a model to read, ranked by AST complexity. `render_slices()` gained an optional `symbol_degree` parameter: `actions.project_learning._graphify_symbol_degree()` reads the same graph Part A uses, one level deeper (per-symbol instead of per-file cross-file degree), so a function with real cross-file callers now outranks a merely-complex-but-unused one. Omitting the parameter reproduces the old complexity-only ranking exactly (tested).

Live-verified: reranking `actions/capability_registry.py` moved `_search_cards` (measured cross-file degree 1) from 5th to 3rd position; `capability_registry`/`build_registry` (degrees 22/6) both overtook `_mcp_response`, which the old ranking had placed first despite zero measured cross-file callers.

## Keeping the graph fresh: the post-commit hook

`.git/hooks/post-commit` runs `graphify update` automatically after every commit, backgrounded so it never delays `git commit` returning. Building it live surfaced a real, repo-specific gotcha worth recording: `graphify update <path>` writes its output relative to `<path>` itself, not the repo root — unlike `extract`, which was originally run with the source folder as scan target but the repo root as the implicit output location. A naive hook running `update` from the repo root (or from the inner source dir without a relocation step) creates a second, stray `graphify-out/` inside `Mark-XLVIII-main/` that nothing reads from — this happened once, live, while testing the update command by hand. The hook runs `update` against the inner source dir, then relocates the result to the outer canonical location every reader (`select_reading_set`, `graphify_query`, `_graphify_symbol_degree_for_root`) actually resolves by default. Log at `.jarvis/graphify-update.log`; never blocks or fails a commit.

## RAG vs. knowledge graph: measured, not assumed

A live profiling pass ([[2026-07-25-rag-vs-knowledge-graph-profiling]]) ran 4 question types through both `jarvis_memory.query_local` and `graphify_query`, no mocks. Headline, honest results:

- **Structural/symbol-named questions**: graphify wins clearly — faster (0.7-1.1s vs. 2.2-5.8s) and more precise (a real BFS traversal beats a generic doc match).
- **"What did we decide" questions**: neither tool is strong. RAG got a topically-adjacent doc, not the actual decision; graphify structurally cannot answer this class at all (no access to conversational history). The fix is a dedicated decision log, not better retrieval.
- **A real RAG precision gap found in passing**: a narrative question about "the WS4b live test" surfaced the wrong specific report (WS4c) — same kind of doc, wrong instance. Worth knowing before over-trusting RAG's top-1 result for closely-named historical reports.

Derived routing heuristic: structural/relational and "related to \<symbol\>" questions → `graphify_query` first; "what did we decide/discuss" → RAG first, check top-3 not just top-1. Not yet wired into the router itself — this profiling pass produced the heuristic; applying it to `_router_tool_names_for_text` is a scoped future increment.

## Archive registration (Tier 3)

`config/project_registry.json` gained an `archive` entry (`root: Jarvis_notes/Archive`, `safe_operations: []` so every `project_operator` operation against it defaults to requiring confirmation) purely so `graphify_query(project_id="archive", ...)` can resolve it. Live-verified: correctly reports no graph exists yet, since the archive currently holds one placeholder note — not enough content to extract. See [[Jarvis_notes/workflows/memory-tiering-and-graphify-index/Plan|Workflow 2]] for the full tier model this fits into.

## Related Notes

- [[05 Research Reports and Repository Learning]]
- [[02 Capability Registry MCP and Safety]]
- [[06 Obsidian Memory RAG Tasks and Canvas]]
- [[Jarvis_notes/workflows/Overview|Workflows Overview]]
