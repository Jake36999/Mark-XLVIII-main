---
id: "jarvis-20260724T193656Z-fcd03c28"
title: "WS4a: Goal-to-Canvas Decomposition — Build and Live Test"
type: "report"
status: "active"
created: "2026-07-24T19:36:56Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "ws4a", "canvas-planning", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T19:36:56Z"
review_after: ""
source_version: 1
content_hash: "709aff9e38370bf278294af08f0cb375559a603e6cbe16ae201e2b7810bff408"
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
> First implementation and live test of **WS4a** (goal-to-canvas decomposition) from [[Planning Subsystem Roadmap]] — the first slice of Workstream 4, the reasoning-backed planning capstone. `decompose_goal_to_canvas()` in `actions/canvas_plan.py` asks the planner model to turn a plain-English goal into a real, drawn `.canvas` file using WS1's dual-purpose node format (role/scope/project/file/recommended-model directives), then hands off to the *existing*, already-verified T1–T7 pipeline exactly as if a human had drawn the graph by hand. Nothing about T1–T7 changed; this only adds a new way to produce the input canvas.

## What got built

- `_DECOMPOSE_SYSTEM_PROMPT` — schema + rules given to the model: exactly one `plan` node anchoring the goal, every other node depends on at least one earlier node, directives are left out entirely rather than invented, 3–7 nodes.
- `_validate_decomposition()` — structural gate before anything touches disk: valid `nodes` list, no duplicate ids, recognised roles only, exactly one `plan` node, every `depends_on` resolves to a real id, **every non-plan node has at least one dependency** (added after the live test, see below).
- `decompose_goal_to_canvas(goal, *, project_hint="", canvas_name=None, cfg=None)` — calls the model (`role="planner"`), parses and validates the JSON, slugifies ids (with collision handling), rebuilds `depends_on` into real edges against the *actual* assigned ids (not the model's raw, pre-slug ids), lays the graph out via `core.canvas_layout.layout_document(profile="dependency")`, and writes the `.canvas` file. Non-authoritative and read-only beyond that one file write — it does not propose, approve, or execute anything.

## Bugs found and fixed during testing

1. **Layout pass was a silent no-op.** `layout_document(..., managed_prefix="__none__")` was meant to say "manage every node," but `_is_pinned()` (`core/canvas_layout.py:72`) pins any node whose id does **not** start with `managed_prefix` — a sentinel that matches nothing pins everything, so the whole layout pass never ran and every node stayed at its `(0, 0)` placeholder. Confirmed via a direct call before the fix (all 4 nodes at `0,0`) and after (`0,0` → `0,320` → `0,640` → `0,960`, one dependency layer per row). Fix: `managed_prefix=""` — every id starts with the empty string.
2. **New canvases escaped their own folder.** The call site pre-resolved `canvas_name or default_name` before handing it to `_safe_canvas_path()`, but that function's own "no path given → default to `canvas_root/default_name`" branch only fires on a *falsy* path — passing a resolved, truthy string every time meant the no-name-given case was interpreted as an absolute-from-vault-root path and skipped the `Canvases/JARVIS/` folder entirely. First live run wrote directly into the vault root; confirmed by inspecting every other `_safe_canvas_path` call site in the codebase, all of which pass the raw (possibly `None`) argument through unresolved. Fixed and re-verified: the retest landed correctly at `Canvases/JARVIS/<slug>.canvas`.
3. **Orphan non-plan node accepted.** The system prompt tells the model every non-plan node needs a dependency so the plan node actually anchors the graph, but nothing enforced it. The very first live decomposition demonstrated the gap directly: the model left `research_wikilink_format` with no `depends_on`, so `plan` had zero children and sat disconnected from the rest of the chain. Added the check to `_validate_decomposition`; a regression test pins the exact scenario.

## Test coverage

11 new unit tests in `tests/test_canvas_plan.py::DecomposeGoalToCanvasTests` (mocked `core.model_router.call_text`): well-formed assembly (node text, directive rendering, edge resolution, real layout coordinates, correct default file location), project-hint forwarding, empty goal short-circuits without calling the model, non-JSON response rejected with nothing written, missing/duplicate plan node rejected, unrecognised role rejected, dangling and orphan `depends_on` rejected, dependency cycle rejected, duplicate slugified ids disambiguated with edges still resolving correctly against the right (post-collision) node. Full suite: **770 passed**, no regressions.

## Live test: real goal, real local model, real pipeline

Goal given: *"Write a small read-only script that scans the Jarvis_notes vault for [[wikilinks]] that do not resolve to any real note, and report the broken ones."*

- `decompose_goal_to_canvas(goal)` — **17.2s**, local model (mistral-7b-instruct-v0.3 via the now-reliable route order), produced a clean 7-node fully-connected linear chain (`plan → research_vault_structure → identify_wikilink_pattern → validate_note_resolution → scan_wikilinks_for_breaks → generate_report → verify_output`), correctly landed at `Canvases/JARVIS/write_a_small_read_only_script_that_scan_a4f2e6.canvas`.
- `propose_canvas_plan()` — produced a normal T4 approval note (`Plans/canvas-approval-ws4a_live_test.md`) with the same compiled-preview table a hand-drawn canvas gets, correctly flagging `⚠ no project target — will not write anything` on the 3 implementation steps and `⚠ no scope — runs the entire suite` on verification, since the model correctly declined to invent a `project:`/`scope:` directive it wasn't given.
- Approved (checked the box, `evaluate_canvas_approval` → `approved`, signature recorded) and executed (`execute_canvas_plan`).
- **Result: `execution_state: "blocked"`.** T5's dual reviewer rejected the first research step's output as `insufficient_evidence` ("The provided evidence does not contain information about a publicly known or documented Jarvis_notes vault. Further investigation is required."); after the repair budget was exhausted the run correctly stopped rather than cascading forward on ungrounded output. T2's status write-back landed on the canvas itself (`plan` → accepted color, `research_vault_structure` → rejected color, everything downstream untouched). The 3 OpenClaw implementation steps and the full-suite verification step never ran — they were still `PENDING` behind the blocked dependency.

## Assessment

The architectural claim WS4a needed to prove — that a model-generated canvas is a first-class citizen of the existing T1–T7 pipeline, not a special case — held up completely: propose, approve, execute, review, and status-sync all behaved identically to a hand-drawn canvas, including correctly refusing to proceed on a shaky step. That refusal is also a genuine finding, not just a clean pass: research-role nodes compile to a pure `model_reasoning` step with no way to gather real evidence about the actual (private, local) vault, so any research node whose answer needs grounding in real files will hit the same wall. This is a pre-existing property of the T1 compiler's `research` role, not something WS4a introduced, and it's the same gap the roadmap's planned **critique pass** was already going to need to address by binding evidence directly from prior step output rather than expecting a model to freely re-derive it (see the roadmap's WS4 design notes, and the retrieval-false-negative finding, P11).

## Related

[[Planning Subsystem Roadmap]] · [[2026-07-24-runtime-delegation-fix-and-reverification]]
