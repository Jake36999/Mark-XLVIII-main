---
id: "jarvis-20260724T213442Z-80a73862"
title: "WS4c: Branch-Aware Fan-Out Canvas Planning — Build and Live Test"
type: "report"
status: "active"
created: "2026-07-24T21:34:42Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "ws4c", "canvas-planning", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T21:34:42Z"
review_after: ""
source_version: 1
content_hash: "b134bfbace0641626a1936987f6bab9d732c1c80b3aa0a56b6b1d22c3da06b71"
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
> WS4c: branch-aware fan-out canvas planning, built from the owner's hand-drawn reference at `Canvases/JARVIS/user-made node planning example..canvas`. Extends [[2026-07-24-ws4a-decomposition-build-and-live-test]] and [[2026-07-24-ws4b-critique-pass-build-and-live-test]] with: a `branch` directive (columns for macro components), a `note` role (pass-forward facts with zero execution semantics), and a column/row fan-out layout in `core/canvas_layout.py`. A single-branch or no-branch canvas is a strict backward-compatible special case -- pinned directly with a dedicated regression test, not just inferred from the rest of the suite staying green.

## Deliberate scope cuts (agreed before building)

- No bidirectional-edge convention for the reference's node0↔branch-root relationship -- single-direction `depends_on` only, so cycle detection and the compiler never need a second edge meaning.
- No true per-branch surgical re-write. WS4b's `re_review` loop still regenerates the whole plan with the critique's feedback folded in; independent per-branch re-planning is real future work.
- No general "re-layout an existing hand-drawn canvas" tool -- this is about how JARVIS's own generated plans look.

## What got built

- **`branch` directive** (WS1-style, alongside `role:`/`scope:`/`project:`/`file:`/`recommended model:`) -- nodes without it fall into a single implicit branch, so every pre-existing single-chain canvas is untouched.
- **`note` role** -- a pass-forward fact with zero execution semantics. `compile_canvas` excludes every `note`-role node from the compiled steps entirely and resolves any `depends_on` that points *through* one to the real upstream step, rather than dispatching it. This had to be handled inside `compile_canvas` itself: `validate_workflow` (what `compile_canvas` calls) does not check that every `depends_on` id actually exists -- only `compile_workflow`, called later during proposal/execution, does -- so an unresolved reference would have surfaced as a confusing failure downstream instead of a clean one at compile time.
- **Branch-aware layout** in `core/canvas_layout.py`'s `"dependency"`/`"evidence"` profile: 2+ distinct branch values switch on column placement (one column per branch, in declaration order) with each branch's own chain stacked inside its column -- the branch's most-synthesized node (its root) at the top, deeper prerequisites below. A node's own explicit `branch` tag always wins and keeps it anchored to that column regardless of what feeds it; only a node with **no** branch tag of its own is a candidate for the reference's other placement rule -- sitting at the x-midpoint between whichever tagged branches feed it (a genuine shared/wrap-up node).
- **Decomposition prompt** (`_DECOMPOSE_SYSTEM_PROMPT`) teaches the branch/note concepts and the cross-branch `depends_on` convention (each branch's root depends on the next branch's root; the deepest branch's root depends on the plan node directly).
- **Critique prompt** (`_CRITIQUE_SYSTEM_PROMPT`) gained a rule to reason about cross-branch note/review pairing -- `_plan_summary_for_critique` needed no code change at all, since it already calls the generic `_node_directives()` helper, so `branch` flowed into the critique's view of the plan automatically once the directive existed.

## Two real bugs found and fixed during live testing (not caught by unit tests alone)

1. **Y-axis was inverted.** My first implementation put a branch's shallowest node (raw dependency layer 0 -- "no prerequisites," the *first* thing to run) at the top of its column. Re-deriving the reference example's actual edge directions by hand showed the opposite is correct: the branch's **root** (highest raw layer, since everything else in that branch must finish before it) belongs at the top, with deeper prerequisites stacking downward -- decomposition reads outward on both axes; execution flows the opposite way, back toward the goal. Caught before any live model call, via a direct unit test that measured the wrong y-ordering; fixed by inverting the depth-to-row mapping specifically for the per-branch axis (global/untagged-node rows deliberately kept in normal, non-inverted order, since those aren't part of that same visual language).
2. **An explicitly branch-tagged node could get bumped out of its own column.** The first attempt tried to distinguish "the fan-out's normal backbone" (a branch's root chaining to the next branch's root) from a "genuinely shared" cross-branch dependency using edge-counting/root-detection heuristics. A live decomposition immediately broke it: a branch's own **entry** node -- fed only by the plan node, from outside its column -- is topologically indistinguishable from a genuine cross-branch confluence under those heuristics, and got pulled to a midpoint between columns. Fixed by simplifying to the only truly unambiguous signal: **a node's own explicit `branch` tag always wins.** Only a node with no tag of its own is a candidate for midpoint placement. This is both more robust and much simpler than the heuristic it replaced -- the root-detection/backbone-exclusion code was deleted entirely.

## Test coverage

- `tests/test_canvas_plan.py::NoteRoleAndBranchCompileTests` (4 tests) -- note exclusion, multi-note chain resolution, dangling note, hashtag/alias role resolution.
- `tests/test_canvas_plan.py::DecomposeValidationBranchTests` (4 tests) -- branch format validation.
- `tests/test_canvas_plan.py::DecomposeBranchAndNoteTests` (2 tests) -- branch mirrored to a top-level key, distinct columns after layout, note round-trips and compiles.
- `tests/test_canvas_layout.py` (new file, 9 tests) -- 3 backward-compatibility pins (no-branch, all-same-branch, non-uniform node heights, all asserting byte-identical output to the pre-WS4c algorithm), 6 multi-branch fan-out tests (distinct columns, monotonic in-branch depth with root topmost, untagged cross-branch midpoint placement, tagged-node-stays-anchored regression test for bug #2 above, untagged-root-with-no-feeders positioning, zero overlaps).
- Full suite: **802 passed**, zero regressions (784 → 802 across the three increments).

## Live tests: real goals, real local model

1. **Direct layout replay** of a real (previously-failed-then-succeeded) live decomposition's raw JSON through the corrected algorithm: two clean columns, branch roots correctly topmost, the untagged wrap-up node correctly centered between both columns *and* below both roots (it depends on both), zero overlaps.
2. **Multi-branch decomposition, attempted 6 times total across the session** with a goal explicitly asking for two independent branches. The first 4 attempts failed WS4a's pre-existing orphan-node validation (a branch's entry node left with no `depends_on`) -- nothing was written each time, exactly as designed. This is a genuine, repeatable finding about the local overseer's reliability on multi-branch structure specifically, not a WS4c regression (the same validation, and the same failure *class*, was already documented in WS4a's own live test on a single-branch goal). Strengthened the decomposition prompt's wording on this specific point after the pattern became clear; two subsequent attempts succeeded, one with explicit `branch:` tags (verified via direct layout replay above) and one without (fell back cleanly to the ordinary single-chain layout -- also correct, just not exercising the new column geometry).
3. **Critique pass on real branch/note structure**: `critique_canvas_plan` correctly reasoned about the branch/note content in its rationale ("Branch A", "Branch B", the note's TTS finding), returning `approve` with no fabricated concerns.

## Assessment

The architecture holds up: `branch` is a strict opt-in generalization (three dedicated regression tests pin exact backward-compatible output), `note` nodes are invisible to execution but visible to review, and the column layout is correct on real model output. Both bugs found were geometry/graph-topology bugs caught by direct code inspection and targeted unit tests *before* they reached a live run costing real model time -- exactly the value of building the compiler and layout layers as independently testable increments (per the session's established WS4a/WS4b pattern) rather than wiring everything through the model in one shot.

The live-testing finding worth carrying forward: multi-branch decomposition reliability is meaningfully lower than single-branch (roughly 2/6 clean attempts vs. WS4a's already-documented ~50%+ single-branch reliability), concentrated specifically on branch entry nodes missing `depends_on`. The validation gate did its job every time -- nothing malformed was ever written -- but a real user experience improvement here would be either a bounded automatic retry wrapper around `decompose_goal_to_canvas` (not built this pass) or accepting that multi-branch goals may need 2-3 attempts today, same as WS4a's harder single-branch goals already do.

## Related

[[Planning Subsystem Roadmap]] · [[2026-07-24-ws4a-decomposition-build-and-live-test]] · [[2026-07-24-ws4b-critique-pass-build-and-live-test]]
