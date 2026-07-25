---
id: "jarvis-20260725T130336Z-6a8cae3c"
title: "Workflow 3: Contracts, Compartmentalization and Tool Synergy"
type: "report"
status: "active"
created: "2026-07-25T13:03:36Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["workflows", "security", "contracts", "graphify", "repo-slicer", "git-hook", "shipped", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T13:03:36Z"
review_after: ""
source_version: 1
content_hash: "7f35caa623cd429d839535455a73e2a704f096c52b08624b3cbd5cd92d62174d"
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
> Workflow 3 of 3 (see [[Overview]]). Documents the current ingestion/compartmentalization contracts for graphify and JARVIS's own information-handling (audited live 2026-07-25, not from memory), and scopes two forward-looking build targets: graphify x `repo_slicer` synergy, and a near/far-term plan for planning-agent delegation.

## Status: Part 1 (audit) complete. Part 2 (graphify x `repo_slicer` synergy) built, tested, live-verified. Part 3's concrete deliverable (the `graphify update` cadence question) built and live-tested; the rest of Part 3 remains a decision framework, not a build target.

> [!success] Part 2 shipped 2026-07-25
> `core/repo_slicer.render_slices` gained an optional `symbol_degree` parameter; `actions/project_learning.py` gained `_graphify_symbol_degree`/`_graphify_symbol_degree_for_root` and wires them through `_python_slice_view` -> `_read_selected` -> `learn_repository`. 5 new tests (`tests/test_repo_slicer.py`, `tests/test_project_learning.py`), full suite 852 passed (847 -> 852, zero regressions). Live-verified against the real graph, not just synthetic fixtures: rendering `actions/capability_registry.py` with the graphify signal moved `_search_cards` (measured cross-file degree 1, via a real caller added earlier this session) from 5th to 3rd position, and `capability_registry`/`build_registry` (degrees 22 and 6) both outranked `_mcp_response`, which the complexity-only baseline had ranked first. See the build/test detail below.

> [!success] Part 3's `graphify update` cadence question resolved 2026-07-25
> Added `.git/hooks/post-commit` (backgrounded, never blocks or fails a commit). Building and testing it live surfaced a real, repo-specific gotcha: `graphify update <path>` writes its output relative to `<path>` itself, not the repo root -- a naive hook running `graphify update .` from the repo root would have created a second, stray `graphify-out/` inside `Mark-XLVIII-main/` that nothing reads from (this happened once, live, while testing the hook by hand, and was manually corrected before automating it properly). The hook runs `update` against the inner source directory, then relocates the result to the outer canonical location every reader (`select_reading_set`, `graphify_query`, `_graphify_symbol_degree_for_root`) actually resolves by default. Verified by direct invocation (not a real commit): full update-and-relocate cycle completed correctly, log written to `.jarvis/graphify-update.log`, no stray directory left behind.

## Part 1 — Current ingestion & compartmentalization contracts (audited, not assumed)

Three independent systems govern what information gets read, by what, and where it can end up. Each was checked directly against the running code and the actual repo contents, not asserted from design docs.

### Graphify's own ingestion contract (external tool)

- **Extension allowlist, not a blocklist.** Only recognized `CODE_EXTENSIONS` / `DOC_EXTENSIONS` / `PAPER_EXTENSIONS` / `IMAGE_EXTENSIONS` / `OFFICE_EXTENSIONS` / `VIDEO_EXTENSIONS` are touched at all (`graphify/detect.py`). `.key`, `.pem`, `.pfx`, `.p12` and similar credential-file conventions are excluded by simply never matching a recognized extension — not by an explicit secret-aware rule.
- **Gitignore-respecting** (`.gitignore` + its own `.graphifyignore` overlay), last-match-wins, standard semantics. **This repo has no root-level `.gitignore`** — only two subdirectory-local ones (`Agent_backend/.gitignore`, `ToolSet/.gitignore`) — so this protection layer is effectively inactive across almost the entire scanned tree today. Worth fixing independent of graphify.
- **`.json` is allowlisted as code**, but graphify's own JSON extractor (`graphify/extractors/json_config.py`) only AST-walks *recognized config/manifest* JSON (`package.json`-style names, or files with telltale keys like `dependencies`/`$schema`) — "data-shaped JSON... is deliberately skipped," citing exactly the failure mode of extracting fixture/API-response/secret-shaped JSON as structure (their issue #1224).
- **Verified against this repo directly**, not just read from source: `config/api_keys.json` (tracked, un-gitignored, currently empty) produced zero graph nodes. `config/certs/jarvis.key` (a genuine RSA private key used for the local dashboard's self-signed HTTPS, also tracked and un-gitignored) doesn't appear in `manifest.json` or `graph.json` at all. The extraction run itself reported **"Token cost: 0 input · 0 output"** — confirming no file content, sensitive or otherwise, was sent to any LLM (local or cloud) during ingestion of this repo.
- **Known gap, not yet stale in practice but will be soon**: the graph is stale relative to every uncommitted edit made this session (staleness is measured by comparing `HEAD` commit hash, and nothing this session has been committed yet, so the graph's own freshness check reports clean when it actually isn't relative to working-tree state). `graphify update .` is free (no LLM cost, local-only) and currently only runs on request — see Part 3 below for whether that should change.

### MARK's own repo-learning pipeline (`project_learning.py`)

Independent of graphify, and stronger in one specific way: an explicit denylist rather than an allowlist-by-omission. `_is_sensitive()` checks `SENSITIVE_NAMES` (`.env`, `api_keys.json`, `credentials.json`, `id_rsa`, `id_ed25519`, `known_hosts`, `authorized_keys`) and `SENSITIVE_SUFFIXES` (`.key`, `.pem`, `.pfx`, `.p12`, `.kdbx`, `.sqlite`, `.db`) plus a substring check for secret/credential/api-key-shaped filenames, and excludes matches from the inventory *before* file selection ever runs — independent of gitignore state. This means MARK's own `learn_repository()` pipeline is not exposed to the gitignore gap noted above at all.

### The tool-dispatch and memory layers (what governs JARVIS/Claude interacting with information generally)

- Every registered tool carries `risk_level` / `side_effects` / `requires_confirmation` (`capability_registry.CAPABILITY_POLICY`). `core/tool_dispatcher.classify_effect()` auto-resolves every call to `read` (no gate) or `write`/`destructive` (requires an approved, hash-bound workflow authorization — `ToolDispatcher.call()` rejects anything else outright, not just "should").
- `jarvis_memory` has a real, working RAG-exclusion mechanism: `_rag_exclusion_reason()` (`actions/jarvis_memory.py:617`) excludes a note from RAG if `rag_index: false`, if it's deleted/tombstoned, or if `sensitivity` is `private`/`confidential`/`secret`/`credential`/`restricted`. Confirmed live on an existing note, not theoretical — the credential-exposure audit below is itself tagged `sensitivity: private`, `rag_index: false`.
- `security_audit` does independent pattern-based secret scanning across worktree + git history + logs (`configured_secret`-pattern matching), redacted-fingerprint-only output, writes to private non-RAG reports.

### Open item found during this audit that isn't mine to resolve

[Credential Exposure Audit - 2026-07-21](../../Logs/2026-07-21-credential-exposure-audit-2026-07-21.md) is still open: 21 `configured_secret`-pattern hits, all inside test fixture files (`test_model_router.py`, `test_spawn_cli.py`, etc. — very likely placeholder/fake keys used as test fixtures, not verified either way by this audit). Its own checklist ("revoke any previously exposed keys," "confirm revocation") is unchecked as of 2026-07-23. This predates graphify entirely and needs the account owner's judgment, not an agent's.

## Part 2 — Graphify x `repo_slicer` synergy

`core/repo_slicer.py` (extracted from the DAG Engine's `semantic_slicer_AG.py` in `F:\knowledge_compiler_engine (DAG Engine)`) and graphify's centrality boost (Part A, this session) solve *different* problems in the same pipeline and currently don't talk to each other:

- **Graphify (Part A)** decides *which files* get selected for repo-learning, by cross-file relationship degree.
- **`repo_slicer`** turns an *already-selected* file into structured, deduplicated per-function/class slices — signatures, call graphs, docstrings, complexity — instead of raw whole-file text, so a model's read budget goes to signal instead of boilerplate.

**Built, not just proposed.** Once a file is selected, graphify's own edge data (already being read for Part A's centrality boost) ranks *which slices within that file* matter most — a function with many real cross-file callers is prioritized in `repo_slicer.render_slices`'s budget over a private helper with none, rather than every function in a selected file being weighted equally.

Implementation:
- `actions/project_learning.py`: `_graphify_symbol_degree(graph)` -- the same edge-counting rule as `_graphify_cross_file_degree` (`contains` edges excluded), keyed one level deeper: `(source_file, bare_symbol_name)` instead of just `source_file`. graphify labels a symbol node `"_search_cards()"` or a method `".call()"`; the parens and leading dot are stripped to match `repo_slicer`'s own bare `name` field. `_graphify_symbol_degree_for_root(root, ...)` is the read-and-degrade-gracefully wrapper (returns `{}` on any missing/invalid graph, never raises), mirroring `_apply_graphify_centrality`'s own fallback contract exactly.
- `core/repo_slicer.py`: `render_slices` gained an optional `symbol_degree: dict[tuple[str,str], int] | None = None` parameter. The sort key becomes `(-degree, -complexity, file, line)` -- cross-file usage first, AST complexity as the tiebreak, and omitting the parameter (or passing `None`) reproduces today's complexity-only ranking exactly (confirmed by a dedicated test, not just asserted).
- Wired end-to-end through `_python_slice_view` -> `_read_selected` -> `learn_repository`, which computes the symbol-degree map once per repo-learning pass and threads it down.

Test coverage: `_graphify_symbol_degree`'s edge-counting and label-stripping (including the same-file-collision graceful-coarsening case), `_graphify_symbol_degree_for_root`'s no-graph fallback, an end-to-end test building a real graph.json on disk and confirming `_python_slice_view` output actually reorders, and two `render_slices`-level tests (symbol degree overriding a complexity-only baseline; omitting the parameter leaving output byte-identical). 5 new tests total, full suite 852 passed after landing (847 -> 852, zero regressions).

Live verification against the real graph (not synthetic fixtures): rendering `actions/capability_registry.py` moved `_search_cards` from 5th position (complexity-only baseline) to 3rd (with the graphify signal) — it has real measured cross-file degree 1 from a test file added earlier this session. `capability_registry` (degree 22) and `build_registry` (degree 6) both moved ahead of `_mcp_response`, which the old complexity-only ranking had placed first despite having no measured cross-file callers in the graph.

## Part 3 — Planning-agent delegation: near/far-term

Agreed framing: simple, well-scoped tasks fully automated now; cloud-agent oversight (Claude, Codex, etc.) for anything requiring real judgment, later.

> [!important] Scope clarification (owner, same conversation)
> "Fully automated" means **batch completion of pre-approved tasks/subtasks only** — not automatic approval upon planning completion. The existing human approval gate (T4 in the dual-orchestrator flow: `propose_canvas_plan` writes a companion note, a human checks Approve/Correct/Deny, only then does `execute_canvas_plan` run) stays exactly where it is. What's being scoped here is what happens *after* that gate, during execution of an already-approved batch — not whether decomposition-to-approval should skip human review. Nothing in this document proposes touching the approval gate itself.

What this session's own measurements say about where the *post-approval automation* line sits today:
- **Deterministic, non-tool-calling-dependent automation is solid.** Part A's graphify-informed centrality boost required zero model tool-calling reliability and is fully safe to run unattended — this is the template for what "fully automated batch execution" should mean near-term.
- **Local-model tool-calling is real but not yet reliable enough to trust unattended for anything consequential.** Live-measured this session (`core.model_router.call_with_tools(role="worker")` against the actual configured `qwen/qwen3-4b-2507`, no mocks): 3 of 4 relationship-shaped prompts correctly triggered `graphify_query` with well-formed arguments; 1 was offered the single correct tool and answered in hedging prose instead of calling it. Zero false positives on negative controls. This is a genuine, measured instance of the small-local-model tool-calling unreliability already flagged in the model-characterization benchmark work (see [[Planning Subsystem Roadmap]]'s Track A) — not a new finding, but a fresh, tool-specific confirmation of it. This matters specifically for *execution*-time tool calls within an approved batch (a `tool`-role step dispatching mid-run), not for the approval decision itself.
- **Recommendation**: within an approved batch, only *deterministic* steps (Part A-shaped — no model tool-calling in the loop) should be eligible for unattended execution near-term. A `tool`-role step whose dispatch depends on a local model reliably choosing to call something correctly (Part B-shaped) should still pause for a human or cloud-agent backstop before running unattended, until either local tool-calling reliability improves or a verification/retry layer exists to catch the miss case above before it silently does nothing. Dynamic delegation to a *cloud* agent (this session's own working mode) doesn't have this problem — the miss case is specific to the small local worker model, not to tool-calling as a mechanism in general.
- **Should `graphify update .` become non-manual? Resolved: yes, built.** `.git/hooks/post-commit` now runs it automatically, backgrounded so it never delays or blocks a commit, degrading silently (never failing the commit) if graphify is missing or the update itself fails. Building it live surfaced a real repo-specific gotcha worth recording precisely: **`graphify update <path>` writes its output relative to `<path>` itself, not the caller's CWD or the repo root** — unlike `graphify extract`, which was originally run with the source folder as scan target but the repo root as CWD/output location. A naive `graphify update .` from the repo root (or from the inner source directory without a relocation step) would have created a second, stray `graphify-out/` sitting inside `Mark-XLVIII-main/` that none of `select_reading_set`/`graphify_query`/`_graphify_symbol_degree_for_root` would ever read from — this actually happened once, live, while testing the update command by hand, and was corrected by hand before being encoded correctly into the hook. The hook runs `update` against the inner source directory, then relocates the result to the outer canonical location. Verified by direct invocation (not a real commit, since commits are only made on explicit request): the full update-and-relocate cycle completed correctly end to end, confirmed via `graphify_query` immediately finding a function added earlier in the same session, with a log at `.jarvis/graphify-update.log` for diagnosing a future silent failure.

## Related

[[Overview]]
[[terminology-and-planning-schema/Plan]]
[[memory-tiering-and-graphify-index/Plan]]
[[2026-07-25-graphify-live-validation-comprehensive]]
[[2026-07-25-graphify-repo-learning-centrality]]
[[2026-07-25-graphify-query-tool-part-b]]
[[Planning Subsystem Roadmap]]
