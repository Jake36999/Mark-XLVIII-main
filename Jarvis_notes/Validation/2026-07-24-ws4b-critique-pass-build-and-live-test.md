---
id: "jarvis-20260724T195901Z-811aa669"
title: "WS4b: Plan Critique Pass and Weighted Refine Loop — Build and Live Test"
type: "report"
status: "active"
created: "2026-07-24T19:59:01Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "ws4b", "canvas-planning", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T19:59:01Z"
review_after: ""
source_version: 1
content_hash: "a37986eba338062b2e8324499522f40f0ede2c87b8266d9cd72b8f0cdb39895b"
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
> Second slice of **WS4** (the reasoning-backed planning capstone) from [[Planning Subsystem Roadmap]]: the **critique pass** and **D5's weighted refine loop**, built directly on [[2026-07-24-ws4a-decomposition-build-and-live-test]]. Nothing about WS4a, T1–T7, or the earlier workstreams changed; this adds a second planner-role review layer on top of a freshly decomposed (or hand-drawn) canvas, before it ever reaches the human T4 approval gate.

## What got built

- `critique_canvas_plan(canvas_path, *, goal="", cfg=None)` — reads *any* canvas back off disk (hand-drawn or WS4a-decomposed, it doesn't distinguish), reconstructs each node's role/directives/instruction/`depends_on` using the exact same WS1 parsing helpers `compile_canvas` itself uses (`_resolve_role`, `_node_directives`, `_instruction_text`), and asks a second planner-role model call to judge the decomposition as a whole. Returns a structured verdict: `approve`, `caution`, `re_review`, or `reject`, plus `missing_steps`, `concerns`, and a `rationale`. Purely advisory — never writes or changes the canvas itself.
- **A deterministic backstop underneath the model's judgment** (`_plan_role_ordering_violations`, mirroring WS2's own "model output + real-receipt post-check" pattern): checks whether every `verification`-role node has at least one `implementation`-role node among its transitive dependencies. If not — and the model's own verdict was weaker than `re_review` — the verdict is force-escalated and the violation is folded into `concerns`. This exists because the live test below caught the model missing exactly this, twice.
- `critique_and_propose_plan(goal, ...)` — the D5 weighted-refine orchestrator: decompose → critique → (`re_review` loops back into a fresh decomposition seeded with the critique's own `missing_steps`/`concerns`, bounded by `max_rewrites`, default 2) → propose. Only `caution` and `reject` pull a human in, per D5 — `re_review` is fully automatic. An unresolved `re_review` after the rewrite budget runs out is treated the same as `reject`: no plan is proposed, and the critique note is the artifact a human looks at.
- Critique is written as a **linked Obsidian note** (`Plans/canvas-critique-<workflow_id>-r<revision>.md`), matching D5's "Obsidian's linking is the right substrate, not a JARVIS-UI panel." The link is **always** attached to the resulting T4 approval note (`**Plan critique:** [[...]]`) regardless of verdict — a `caution` verdict additionally prepends a visible `[!warning]` callout with the rationale, so the human approver sees it without having to go looking.

## A real gap the live test caught, and the fix

The first live test deliberately fed the critic a thin, broken hand-drawn canvas: a `verification` node wired directly off the `plan` node, with the `implementation` node it was supposed to verify sitting *downstream* of it — i.e. the plan would run tests before the thing being tested existed. **The model approved it anyway, twice in a row** (once cold, once warm), even remarking the ordering was "logical." This is exactly the kind of structural, mechanically-checkable defect D5 wants caught automatically rather than shipped to a human — but it's not the kind of thing worth trusting a single model call to always notice, any more than WS2 trusted a model's own summary to correctly report "tests passed." Added the deterministic backstop above; re-ran the identical scenario and it now correctly escalates to `re_review` with the concern named explicitly, regardless of what the model itself concluded.

A second, milder gap found while writing this up rather than by the model: the first version only linked the critique note into the approval note on a `caution` verdict, which under-delivers on D5's "connected to the plan by inline wikilinks" as a general property, not a caution-only one. Fixed so the link is always present; the warning callout remains the caution-specific addition.

## Test coverage

12 new unit tests: well-formed critique parsing (including confirming the critic sees the plan's real structure, not just the goal text), non-JSON and unrecognised-verdict rejection, empty-canvas short-circuit, the ordering-violation backstop (both the broken case that must escalate and a correctly-ordered case that must *not* trigger a false positive), and the full refine loop (`approve` proposes cleanly with the always-on link and no spurious warning callout; `caution` proposes with the warning callout; `reject` does not call `propose_canvas_plan` at all; `re_review` loops back with the critique's own feedback threaded into the rewrite prompt, confirmed via the actual call arguments; an unresolved `re_review` after exhausting the rewrite budget is treated as reject; a critique-stage failure short-circuits cleanly without ever proposing). Full suite green (770 → see [[2026-07-24-ws4a-decomposition-build-and-live-test]] for the pre-WS4b baseline; this session's run confirmed no regressions).

## Live tests: real goal, real local model, real pipeline

1. **Deliberately broken plan, direct `critique_canvas_plan` call.** A 3-node hand-drawn canvas (`plan → verify → build`, verification wired before implementation). Model verdict: `approve` both times tried (72s cold, 9s warm) — the deterministic backstop escalated to `re_review` both times, correctly.
2. **Full `critique_and_propose_plan` loop, real goal.** *"Write a script that lists every Python test file under tests/ that has no corresponding source module in actions/ or core/."* Decomposition failed WS4a's own orphan-node validation (the model left a node with no `depends_on`) — correctly caught before ever reaching the critique stage, nothing written. Expected model variance, not a WS4b defect (WS4a's validator is exactly what this is for).
3. **Full loop, second real goal.** *"Write a small read-only script that reports how many local models are configured in each route in config/runtime.json."* Decompose (30–73s depending on model residency) → critique (`approve`, rationale: "logically ordered, covers analysis, implementation, verification, and review, and respects the read-only requirement") → proposed cleanly through the normal T4 gate, with the critique note linked. See [[canvas-critique-ws4b_live_test3-r1]] and the resulting approval note for the real artifacts.

## Assessment

The critique pass and refine loop work as designed and are wired into the existing T4 gate without disturbing it. The more interesting result is the live test doing its actual job: it surfaced a real reasoning gap (structural ordering blindness) rather than just rubber-stamping a synthetic goal, which is what "confirm the critique genuinely catches something" was checking for. The fix — a cheap, deterministic backstop under the model's judgment — follows the same design precedent WS2 already established (trust the model's structured proposal, verify the checkable parts against ground truth) rather than inventing a new pattern.

**Not yet built:** the north-star recursion/research-gap capability (nestable sub-plans, critique emitting research nodes) remains explicitly future work per the roadmap; nothing here changes that scope.

## Related

[[Planning Subsystem Roadmap]] · [[2026-07-24-ws4a-decomposition-build-and-live-test]]
