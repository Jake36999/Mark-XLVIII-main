---
id: "jarvis-20260725T141333Z-58e7f673"
title: "RAG vs Knowledge Graph: Live Profiling and Routing Heuristic"
type: "report"
status: "active"
created: "2026-07-25T14:13:33Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "graphify", "rag", "profiling", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T14:13:33Z"
review_after: ""
source_version: 1
content_hash: "4e92c92d239971821509e039c698c4414ce4006cd2ea98730fd36d3c68606679"
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
> Live comparison of `jarvis_memory.query_local` (RAG) against `graphify_query` (knowledge graph) on 4 representative question types, per the methodology scoped in [[memory-tiering-and-graphify-index/Plan|Workflow 2]]'s "RAG vs. knowledge-graph profiling" section. Real calls against the real vault and the real graph, no mocks, no cherry-picking — all 4 cases run once, reported as-is including the imperfect ones.

## Method

4 question types, 1 real question each, run through both tools unmodified: `query_local(question, limit=3)` and `graphify_query({"question": ..., "mode": ...})`. Scored on precision (does the top result actually answer the question), latency, and payload size.

## Results

| Type | Question | RAG top result | RAG time | KG result | KG time |
| --- | --- | --- | --- | --- | --- |
| Structural | "what calls select_reading_set" | "Memory Context and Canvas" (generic User Guide doc, score 0.014 — weak) | 5.8s | BFS traversal rooted at `select_reading_set()`, 74 real connected nodes | 1.1s |
| Semantic/associative | "what did we decide about the graphify hook mode" | "Workflow 3: Contracts..." (plausible but not the actual decision — likely conflates git "hook" with the Claude Code PreToolUse "hook" this question means) | 2.2s | Rooted at `HookSpec`/`.mode()` code symbols — structurally real, but answers "what is `mode()` in code," not "what did we decide," since the graph has no memory of conversational history at all | 0.8s |
| Mixed | "find files related to capability_registry" | "Tools Skills and Capabilities" (a real, plausible prose overview) | 2.2s | `explain` mode: the exact symbol node, with its real connected files | 0.7s |
| Narrative/historical | "what happened during the WS4b live test" | "WS4c: Branch-Aware Fan-Out..." — **wrong workstream letter** (WS4c, not WS4b) — a genuine near-miss, right kind of doc, wrong specific instance | 4.2s | Matched raw text fragments containing "WS4b" verbatim — fragmented, not a clean narrative answer | 0.8s |

## Honest read, not just clean wins

- **Structural clearly favors the knowledge graph.** "What calls X" is exactly graphify's design center — a real BFS traversal from the named symbol beats a generic doc match by a wide margin, and roughly 5x faster.
- **The "mixed" case leaned more structural than the original methodology assumed.** "Find files related to X" turned out to be closer to graphify's strength than RAG's — worth noting for anyone tuning a router off this report: "related to a named code symbol" should probably route to KG first, not stay genuinely ambiguous.
- **Neither tool is strong at "what did we decide."** RAG got a topically-adjacent doc, not the actual decision; the knowledge graph structurally *cannot* answer this class of question at all — it has zero access to conversational/decision history, only code and vault-note structure. This is the honest gap, not a tool-selection problem: recalling a past decision needs RAG pointed at the right note (or a decision specifically logged as its own indexed record), and no routing heuristic fixes a case where the right note doesn't clearly exist or wasn't retrieved.
- **The narrative case is a real near-miss worth fixing, not hiding.** RAG surfaced the right *kind* of report but the wrong specific one (WS4c instead of WS4b) — a precision problem in RAG's own ranking for closely-named, topically-similar reports, not something graphify would have done better (its result was messier text-fragment noise, not a clean win either).
- **Latency: knowledge graph consistently faster** (0.7-1.1s vs. 2.2-5.8s for RAG). Some of RAG's variance is a one-time embedding-model cold-load cost on the first call in a session, not necessarily representative of steady-state — worth re-measuring warm before treating the gap as fixed.

## Routing heuristic (derived from measured behavior, not assumed)

- **Question names or clearly implies a specific code symbol, file, or "what calls/uses/depends on X"** → `graphify_query` first. Measured precision win, and faster.
- **Question asks what was decided, discussed, or is otherwise about conversational/session history** → `jarvis_memory.query_local` first, but don't over-trust the top result blindly — this profiling pass found real ranking imprecision (the WS4b/WS4c mixup) even in RAG's own home territory. Worth a second look at top-3, not just top-1, for this question class specifically.
- **"Related to <named symbol>"-shaped questions** → lean `graphify_query` first, contrary to the original methodology's assumption that this category was genuinely ambiguous — the one real test case here favored the graph.
- **Neither tool is a substitute for a dedicated decision log.** If "what did we decide about X" needs to be reliably answerable, that's an argument for capturing decisions as their own indexed, distinctly-titled notes (which several validation reports this session already do informally via `> [!important]`/decision-log style callouts) rather than expecting retrieval to reconstruct a decision from a report that happens to mention the topic.

## Related

[[memory-tiering-and-graphify-index/Plan]]
[[Overview]]
[[2026-07-25-graphify-live-validation-comprehensive]]
