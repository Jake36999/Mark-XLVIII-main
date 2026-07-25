---
id: "jarvis-20260725T010627Z-810dfc65"
title: "WS4d: Deterministic Context Inheritance and Deliverables — Build and Live Test"
type: "report"
status: "active"
created: "2026-07-25T01:06:27Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "ws4d", "canvas-planning", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T01:06:27Z"
review_after: ""
source_version: 1
content_hash: "5c462582b67faecffaa04b30e23cad2e504d9b25b77b8cd1c48a30c94eae0845"
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
> WS4d: deterministic context inheritance + deliverables, from the owner's proposal to "coax the agents" running simplistic nodes with more context passed along both fan-out axes -- X (across branches: "this is part of system B, you'll need Y") and Y (within a branch: "this is part of X, part of B; the deliverables for success are..."). Built on [[2026-07-24-ws4c-fanout-planning-build-and-live-test]]. No new model calls: the preamble is assembled purely from prose already on the canvas at compile time.

## The gap this closes

Only `review`-role compiled steps got any automatic context from their dependencies (T1's `evidence` binding pulls a dependency's real `result.summary`). Every other node -- research, note, implementation -- ran entirely off its own self-authored prose, with zero visibility into the overall goal, which branch/component it served, what sibling branches were doing, or what "done" concretely looked like. D1's "every node is a self-contained prompt" put the whole burden on the decomposition model remembering to write a complete node every time.

## What got built

- **Context preamble** (`_context_preamble`/`_truncate` in `actions/canvas_plan.py`): a deterministic, budget-capped (220 chars/fragment) block assembled at compile time from prose already on the canvas -- the plan node's goal ("System goal: ..."), the node's own branch's root purpose ("This step is part of component A: ..."), and one line per sibling branch. Injected into `inputs.prompt` (research/review, which `dual_orchestrator.py`'s dispatch reads in preference to the bare step description) or prepended onto `inputs.intent` (implementation, already the field `delegate_openclaw` reads). No dispatch-side code changed -- the preamble reaches the executing model purely because `compile_canvas` populates the same fields those dispatch paths already read.
- **Evidence-binding extended beyond review-only**, but *not* uniformly: `dual_orchestrator.py`'s `command`/`tool` results have no common `summary` field (`ok`/`returncode`/`stdout`/`stderr` for commands; whatever each of 4 different tool targets natively returns), so binding `result.summary` from a verification/implementation dependency would just silently resolve to `None`. Evidence is only auto-bound to dependencies whose own role is `research`/`note`/`review`/`plan`/`reference` (reliably `summary`-shaped) -- confirmed correct in the live test below, where the first implementation node (depending on the plan node) got a real binding and the rest (depending on other implementation/tool nodes) correctly got none.
- **D2 visibility**: `_resolved_target_summary` (the T4 approval preview's "Resolved target" column) gets a `+ context` indicator whenever a step's `inputs` carry the preamble -- the full text stays out of the compact table (it's in the compiled step's `inputs.prompt`/`inputs.intent` for anyone who wants to inspect it), but a human approver can see at a glance that context was injected.
- **`deliverables`**: an optional per-node field (`_DECOMPOSE_SYSTEM_PROMPT`, format-checked in `_validate_decomposition`), mirrored onto a plain top-level `node["deliverables"]` key (same precedent as WS4c's `branch`, since a list doesn't fit the single-line WS1 directive convention) and rendered into the node's own text. Compiles into real, node-specific `step["acceptance_criteria"]["deliverables"]` -- replacing the universally-identical, unfalsifiable `{"required": True}` every step got before. Surfaced to the critique pass too (`_plan_summary_for_critique`, `_CRITIQUE_SYSTEM_PROMPT`).

## A real bug found and fixed during live testing

The first live attempt failed decomposition validation: the model wrote `"deliverables": "config loaded into memory as Python dict."` -- a bare string, not the one-item list the schema showed -- on every single node. A forgivable, common format slip, not a structural defect worth discarding the whole decomposition over. Added `_normalize_decomposition_payload()`, called right after JSON parsing and before validation, which coerces a bare-string `deliverables` into a one-item list in place. Retried immediately after the fix: succeeded, 15s (model already warm), with all four implementation nodes carrying real, distinct, useful deliverables.

## Deliberate scope cuts (stated up front, held to)

- Did not touch `dual_orchestrator.py`'s shared `command`/`tool` result-construction code to normalize in a `summary` field -- that's used by Mode 1 workflows too, a wider blast radius than justified for this pass. Flagged as a natural follow-up that would unblock evidence-binding for verification/implementation dependencies as well.
- Did not attempt to rigorously measure whether richer context improves node *execution* quality -- that needs a controlled before/after live-prompt comparison (in the spirit of the session's earlier 16-prompt test), a follow-up validation task, not part of building the mechanism.

## Test coverage

23 new unit tests: `ContextPreambleTests` (9 -- preamble assembly for single/multi-branch plans, a branch root never referencing itself, budget truncation, verification/reference roles correctly getting none, evidence extended correctly and correctly withheld from unreliable dependencies, the preview indicator), `DecomposeValidationDeliverablesTests` (6 -- format validation), `DecomposeDeliverablesTests` (5 -- round-trip through decomposition into real `acceptance_criteria` and the critique summary, plus the bare-string coercion regression test). Full suite: **822 passed**, zero regressions (802 → 822).

## Live test: real goal, real local model, real compiled JSON

Goal: *"Write a small read-only script that reports how many local models are configured in each route... For each node, include concrete deliverables describing what done looks like."* First attempt hit the string/list validation gap above; fixed; second attempt succeeded (15s) with 5 nodes, all 4 implementation nodes carrying genuine deliverables. Compiled the real output and inspected the actual step JSON (not mocks): every implementation node's `inputs.intent` correctly opens with `"System goal: ..."` followed by its own prose and its own deliverables text; `acceptance_criteria.deliverables` correctly holds the node-specific list; the `+ context` indicator would render in the approval preview; evidence-binding correctly applied only to the one dependency (the plan node) with a reliably-shaped result, correctly withheld from the tool-to-tool dependencies between implementation nodes.

## Assessment

Every piece of the mechanism is confirmed working on real, non-mocked output, not just test fixtures. The design held up without needing any changes to the actual injection logic once built -- the one real gap live testing found (string-vs-list deliverables) was a decomposition-schema-compliance issue, the same class of gap WS4a/b/c also found and fixed via lenient coercion or stronger prompt wording, not a flaw in the context-inheritance mechanism itself.

## Related

[[Planning Subsystem Roadmap]] · [[2026-07-24-ws4c-fanout-planning-build-and-live-test]]
