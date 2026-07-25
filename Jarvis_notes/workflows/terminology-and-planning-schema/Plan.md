---
id: "jarvis-20260725T135838Z-51cde1b1"
title: "Workflow 1: Terminology and Planning Schema Refactor"
type: "report"
status: "active"
created: "2026-07-25T13:58:38Z"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["workflows", "terminology", "planning", "canvas-plan", "shipped", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T13:58:38Z"
review_after: ""
source_version: 1
content_hash: "c70d0b41c6c34d04c1e9739728bba4fd845693d9738ee34a3a6aa30e21f14d1e"
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
> Workflow 1 of 3 (see [[Overview]]). Formalizes the owner's 2026-07-25 terminology proposal — replacing overloaded "goal"/"task" usage with a four-level hierarchy: **workflow -> goal -> task -> subtask**, plus a `user_workflow` mode of `research` or `development`.

## Status: built, tested, live-verified (2026-07-25)

> [!success] Shipped
> `actions/canvas_plan.py` gained `role: workflow` (alias for `plan`, additive per the recommendation below), `task:` (alias for `branch:`), and an optional `mode:` directive on the anchor node, threaded into `workflow["variables"]["mode"]`. `decompose_goal_to_canvas` gained an optional `user_workflow_mode` parameter that writes the `mode:` directive onto the generated anchor node. Developer handbook Note 13 and `capability_registry.py`'s `canvas_plan` entry updated. 7 new tests (`tests/test_canvas_plan.py`: role/directive aliasing, `mode:` parsing, `mode` threading present and absent, `user_workflow_mode` reaching the written canvas and surviving a real `compile_canvas` round-trip). Full suite 859 passed (852 -> 859, zero regressions).
>
> **Live-verified**, not just unit-tested: compiled a real two-task canvas through `compile_canvas` directly (`role: workflow` on the anchor, `mode: research`, `task: A`/`task: B` on two independent branches, a `review` node depending on both) with no mocks. Result: `workflow["variables"]["mode"] == "research"`; the anchor correctly resolved to `step_type: gate`; both task branches correctly depended only on the anchor; the review node correctly depended on both branch heads. Confirms the vocabulary is real, not just documented.

## The problem this fixes

Today "goal" means two different things depending on which system you're in:

- In `canvas_plan.py`, `_ROLE_ALIASES` maps `"goal"` (alongside `"root"` and `"milestone"`) as a synonym for the single `"plan"`-role node that anchors an entire canvas (`actions/canvas_plan.py:142-143`). One canvas has exactly one of these.
- In conversation and in `decompose_goal_to_canvas(goal: str, ...)`'s own parameter naming, "goal" means the free-text ask that kicks the whole thing off — the thing a canvas gets built *from*, not a node *in* it.
- Nowhere today is there a name for "one of several sub-objectives inside a larger effort" or "the individual steps under one of those" — everything downstream of the anchor is just "steps" or "nodes," flattening exactly the distinction the owner wants surfaced.

## Corrected blast-radius estimate

> [!warning] Revising an earlier estimate
> When this was first raised in conversation, the assumption was that this touches `canvas_plan.py`'s role table, `plan_workflow.py`, and the `dual_orchestrator` workflow schema all at once. Having now actually checked the code rather than estimated from memory: **`config/workflows/jarvis_dual_orchestrator.schema.json` contains zero literal `goal`/`task`/`subtask` fields** — the execution schema already speaks purely in `step`/`step_type`/`role`, so it isn't touched by this at all. `plan_workflow.py` (Mode 1) doesn't use the literal word "goal" anywhere in its code either. The actual footprint is much smaller than first thought: this is concentrated in `canvas_plan.py`'s role-alias table, `decompose_goal_to_canvas`'s parameter/prose, and documentation — not a schema migration.

## The best finding: WS4c's branch fan-out already *is* the task/subtask shape

This is the load-bearing discovery for scoping this cheaply. WS4c (already shipped, see [[Planning Subsystem Roadmap]]) added `branch:` tagging: a goal with 2+ largely-independent macro components gets laid out in columns, each branch's own root node at the top, deeper prerequisites stacking downward. That is *already exactly* "macro pillars, with a y-axis expansion of clearly noted subtasks" — it just doesn't have that name yet.

Mapped onto the new vocabulary:

```
workflow                    (was: the single "plan"-role canvas anchor / decompose_goal_to_canvas's "goal" param)
 └─ goal(s)                 (new concept — one workflow can define 1+ goals; the single-note case below is a workflow with exactly one goal)
     └─ task = branch       (already exists as WS4c's `branch:` column — just needs the label)
         └─ subtask = node  (already exists as individual nodes stacking down a branch column — just needs the label)
```

If this holds up under actual implementation, the mechanical/compiler changes are close to zero — this is overwhelmingly a **naming and prompt-language change**, not a structural rebuild. That should be validated before committing to the estimate, not assumed.

## `user_workflow` mode: research / development

The owner's framing: the system first decides whether a request is a **single-note problem** (a quick, still-planning-mode-engaged pass — e.g. a bounded online search and source compilation) or a **large task** needing full decomposition (canvas expansion). Both cases are objectively "a research workflow" or "a development workflow" being engaged — the mode is orthogonal to size.

Proposed shape: `user_workflow.mode` = `"research" | "development"`, set once at workflow creation, independent of whether it resolves to a single-note pass or a full canvas. This gives a clean discriminator for downstream logic (e.g. a `research`-mode single-note case might route straight to `web_search` + `jarvis_memory.create_note`, while a `development`-mode single-note case might route to `code_helper` directly) without needing the full canvas machinery to make that call.

## What got built, mapped to the original proposal

1. **Vocabulary formalized** — this document, plus `capability_registry.py`'s `canvas_plan` entry (`details` and `keywords`) and Developer Handbook Note 13 (new "Terminology" section, directive table, and role table both updated).
2. **`"workflow"` added as a role alias, not a rename** — resolved the open question below: `_ROLE_ALIASES` gained `"workflow": "plan"` alongside the existing `root`/`goal`/`milestone` synonyms. `"goal"` as a genuinely distinct node role (a real layer *between* workflow and task) was **not** built — see "Deliberately not built" below.
3. **`task:` shipped as an alias for `branch:`**, not a rename — `_DIRECTIVE_ALIASES` gained `"task": "branch"`. Same fan-out layout, same tests, zero behaviour change for existing canvases.
4. **`user_workflow.mode` shipped as purely descriptive metadata** — resolved the third open question below in favour of "descriptive, never enforced": `decompose_goal_to_canvas(..., user_workflow_mode="")` writes a `mode:` directive onto the generated anchor node when given; `compile_canvas` reads it (from either a generated or hand-drawn canvas) into `workflow["variables"]["mode"]`. Nothing currently reads that variable back out — it exists for a future routing decision to consume, exactly as scoped.
5. **Developer handbook updated** (Note 13).
6. **Live-tested** — see the success callout above. Not re-tested against the "~2 times in 6" multi-branch success-rate benchmark specifically, since nothing about decomposition's model-facing prompt (`_DECOMPOSE_SYSTEM_PROMPT`) changed — the new vocabulary is additive at the alias layer, so the model still emits (and is still asked to emit) the original `plan`/`branch` terms; only a *human* hand-authoring a canvas, or code calling `decompose_goal_to_canvas` with `user_workflow_mode`, exercises the new spellings.

## Deliberately not built

- **A genuinely distinct "goal" role or layer.** The original proposal's `workflow -> goal -> task -> subtask` implies a real layer between workflow and task, but no mechanism for grouping multiple tasks under one of several goals within a single workflow was built. For now a workflow remains 1:1 with its own goal (the anchor node's own prose *is* the goal), exactly as the second open question below anticipated and resolved. This is worth flagging as a real limitation if the owner's actual intent was multi-goal decomposition within one workflow, not just a vocabulary change.
- **Changing what the decomposition model itself is asked to emit.** `_DECOMPOSE_SYSTEM_PROMPT`'s JSON schema still asks for `"role": "plan|research|..."`, not `"workflow"`, and still asks for `"branch"`, not `"task"`. Deliberately conservative: changing the model-facing schema risks perturbing the measured ~2-in-6 multi-branch success rate for a vocabulary change with no functional benefit to the model itself. If the owner wants the model to prefer the new terms too, that's a separate, explicitly-scoped follow-up with its own live re-test.

## Open questions — resolved

- ~~Rename `"plan"` role to `"workflow"`, or keep `"plan"` internal and add `"workflow"`/`"goal"` as new wrapper concepts around it?~~ **Resolved: additive alias, not a rename** (built as described above).
- ~~Does a single-note pass get its own lightweight schema, or run through the same compiler as "one workflow, one goal, one task, one subtask"?~~ **Resolved: the latter, by construction** — no new schema was built, so this was never actually a choice; a single-note case is just a small canvas through the existing compiler.
- ~~Should `user_workflow.mode` be enforced or purely descriptive?~~ **Resolved: purely descriptive.** Never validated against a fixed value set, never blocks compilation or decomposition, absent by default.

## Related

[[Overview]]
[[memory-tiering-and-graphify-index/Plan]]
[[contracts-compartmentalization-and-synergy/Plan]]
[[13 Canvas Planning Engine and Reasoning-Backed Decomposition]]
[[Planning Subsystem Roadmap]]
