---
id: "developer-canvas-planning-engine"
title: "Canvas Planning Engine and Reasoning-Backed Decomposition"
type: "guide"
status: "active"
created: "2026-07-25"
updated: "2026-09-24T18:22:21Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["developer-handbook", "canvas-plan", "planning", "mode-2", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.9
content_hash: "df52789f3eb30c6d2760b4414b3ec4055baaca90f7ea3ced705879542b1af032"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Canvas Planning Engine and Reasoning-Backed Decomposition

> [!abstract] Mode 2 planning
> [[03 Planning Approval and Dual Orchestration|Note 03]] documents Mode 1: `plan_workflow.create_plan` turns a prompt into Markdown + YAML + JSON via a fixed keyword router, with no model reasoning about task shape. **Mode 2** is a parallel, model-reasoned path: a goal (or a hand-drawn `.canvas` graph) becomes a real Obsidian Canvas of dual-purpose nodes, gets critiqued and automatically refined, and only then compiles onto the *same* `jarvis_dual_orchestrator/v1` schema, approval envelope, and `WorkflowRuntime` that Mode 1 already uses. All of Mode 2 lives in `actions/canvas_plan.py` (2400+ lines) and `core/canvas_layout.py`. [[11 Safe Canvas Service and Relationships|Note 11]] covers the structural Canvas service (`canvas_document.py`/`canvas_index.py`) this builds on; it does not cover planning logic.

## Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Decomposed: decompose_goal_to_canvas (WS4a)
    Decomposed --> Critiqued: critique_canvas_plan (WS4b)
    Critiqued --> Decomposed: re_review (bounded, automatic)
    Critiqued --> PendingReview: approve / caution -> propose_canvas_plan (T4)
    Critiqued --> HumanNeeded: reject / re_review budget exhausted
    PendingReview --> Approved: evaluate_canvas_approval
    Approved --> Running: execute_canvas_plan (T6)
    Running --> Running: T5 review gate, T2 status write-back, T3 completion SOP
    Running --> Completed: every item accepted
    Running --> Blocked: item rejected / escalated
    Completed --> [*]
```

A hand-drawn `.canvas` can enter at `Critiqued` or `PendingReview` directly — decomposition is optional, not a gate. Every stage after decomposition treats a model-generated canvas and a hand-drawn one identically; nothing downstream knows which one produced the file.

## D1: every node is dual-purpose

A canvas node is simultaneously a compiled workflow step and a complete, self-contained prompt for whichever agent executes it. Leading `key: value` lines are directives; the first non-directive line starts the prose the executing agent actually reads (`_parse_node_directives`, `canvas_plan.py`):

```
role: implementation
branch: A
project: mark_platform
scope: tests/test_foo.py
file: actions/foo.py
recommended model: developer (openclaw)

Build the thing. This line and below is the agent's actual instruction.
```

| Directive | Applies to | Compiles into |
| --- | --- | --- |
| `role:` / `type:` | all | step type via `_ROLE_SPECS` (below) |
| `scope:` / `test:` | verification | `inputs.args` |
| `project:` | implementation (**required**) | `inputs.project_id` (a `plan`-role node's own `project:` sets the canvas-wide default; a node-level value overrides it) |
| `file:` | reference / implementation | `inputs.file` |
| `recommended model:` | any | `inputs.recommended_model` — a visible, editable hint (D2), inert on dispatch |
| `branch:` / `task:` | any (WS4c) | fan-out column grouping — see below |
| `mode:` | the `plan`/`workflow`-anchor node only | `workflow["variables"]["mode"]` — purely descriptive `research`/`development` routing metadata, never validated or enforced |

> [!danger] An implementation node with no project target is a compile-time blocker (2026-07-30)
> This used to compile happily and then do nothing. Nothing set `project_id`, and `project_operator` reads a missing one as `operation=list` — returning the registered project list with `ok: true`. So an **approved** implementation node reported success having delegated no work at all. The node's prose was not forwarded either; that half (`intent`) was fixed by WS4d.
>
> `compile_canvas` now refuses, naming the node and listing the registered project ids so the gap is fixable in Obsidian. It blocks rather than defaulting: choosing a project automatically would silently authorise OpenClaw against a live repository the moment a human approves, which is a far larger blast radius than a loud failure. Failing at compile time means it surfaces in the preview and plan note *before* any approval exists.
>
> `decompose_goal_to_canvas` pins its `project_hint` onto the plan anchor for this reason — leaving the directive to model discretion would make generated plans fail to compile whenever the model declined to repeat it. The decomposition schema now states `project` is required on implementation nodes.

> [!important] D2 — targeting is a visible recommendation, not a silent default
> `recommended model:` is rendered on the node and in the T4 approval preview. Left unedited, it counts as accepted; edited, the plan fingerprint changes and re-triggers approval. Nothing about targeting is a silent default a human never sees.

## Terminology (2026-07-25): workflow → goal → task → subtask

The owner's vocabulary pass gives distinct names to concepts this engine already had, mostly without changing any mechanics:

- **workflow** — the canvas's own single anchor node. `role: workflow` is now the preferred spelling; `root`/`goal`/`milestone`/`plan` all still resolve to the exact same internal `"plan"` role and behaviour (`_ROLE_ALIASES`) — this is a vocabulary addition, not a rename, so no existing hand-drawn canvas needs to change.
- **goal** — a workflow's own stated objective. For now this is 1:1 with the workflow itself (most workflows have exactly one goal); genuine multi-goal decomposition within one workflow is a real but not-yet-built extension, deliberately deferred rather than half-built into the schema.
- **task** — a macro pillar, i.e. a WS4c `branch:`. `task:` is now an accepted alias for `branch:` in a node's directive lines (`_DIRECTIVE_ALIASES`) — same fan-out column grouping, same layout behaviour, just the intended word.
- **subtask** — an individual node stacked within a task/branch's own column.

`user_workflow.mode` (`research` | `development`) is optional and purely descriptive: set it via `decompose_goal_to_canvas`'s new `user_workflow_mode` parameter (written as a `mode:` directive onto the generated anchor node) or by hand-typing `mode: development` on a hand-drawn canvas's own anchor node. Nothing currently reads or enforces it — it exists so a future routing decision has somewhere real to look, not to gate anything today.

## Role → step compilation

`_ROLE_SPECS` maps each role to a step template; an absent or unrecognised role resolves to the least-privileged `research` default — a canvas can never silently mint a side-effecting step.

| Role | step_type | Side effects | Notes |
| --- | --- | --- | --- |
| `plan` (write `role: workflow`) | gate | none | anchors the graph; exactly one required |
| `research` | model_reasoning | none | `inputs.role` set to `"research"` so dispatch actually uses `model_router`'s dedicated `research` route rather than falling back to `worker` (2026-09-24 fix — see below); carries `allowed_tools`/`suggested_tools` (below) |
| `note` | *(excluded)* | none | WS4c pass-forward fact; never dispatched — `compile_canvas` resolves any `depends_on` through it to the real upstream step |
| `review` | review | none | T5 dual critic (below) |
| `reference` | gate | local_read | |
| `verification` | command **or** closing_check | local_read | `command`/`pytest_focused` when the node's ancestry reaches an `implementation` node anywhere (code may have been touched, safe default); **`closing_check`/`document_completeness` instead when it doesn't** — a document-completeness check against what a `document` ancestor actually produced, replacing a meaningless full-suite run against nothing relevant to it. Routed purely from graph structure at compile time (`_ancestor_roles_and_documents`), never from a runtime log (2026-09-24) |
| `document` | artifact | local_write | `vault_create_note`; a plain vault-note write, distinct from `implementation` — added because `implementation` used to be the *only* role that could write anything durable, forcing pure documentation goals through OpenClaw's project-gated delegation path for no reason |
| `implementation` | tool | external_write | `project_operator` → `delegate_openclaw`; `requires_confirmation: true` |

### Dispatch-time additions (2026-09-24)

- **Tool-call intent check.** Every `step_type: "tool"` dispatch now goes through `WorkflowRuntime._check_tool_intent` before `_dispatch_tool` runs it — a larger/planner-tier model judges the resolved arguments against the item's declared intent and can deny the call outright (converting straight to `REPAIR`/`REJECT_REPLAN`) before it ever executes, not just after. Additive to the existing T4 human approval gate, never a substitute for it; fails closed on any error. Injectable via `intent_checker=` on `WorkflowRuntime`, mirroring `reviewer=`.
- **`retry_rejected_item(run_id, item_id)`.** `REJECT_REPLAN` is deliberately terminal within a run — `execute_run`'s dispatch loop never revisits it automatically, unlike `ESCALATE` (which `execute_canvas_plan` already retries on every call). This is the explicit, human-invoked escape hatch for the narrow case where a human has confirmed the rejection was an infrastructure/operator problem (a run dispatched against an unlinked credential, say) rather than a genuine plan or model failure. Never called automatically.
- **`propose_canvas_plan(..., force=True)`.** The plan fingerprint only ever tracks human-authored canvas content — it has no way to see that `compile_canvas`'s own logic changed. `force=True` skips the fingerprint check and produces a fresh `pending_review` note even on a byte-identical canvas, for exactly that case (a compiler fix or newly-wired feature that needs to reach an already-proposed plan). Still produces a genuine new decision to make, never a re-approval shortcut.

## WS1 — anti-fabrication in the approval preview

The T4 approval table's "Resolved target" column shows what will *actually* run, not the node's prose — `⚠ no project target` / `⚠ no scope — runs the entire suite` when a directive that side-effecting role needs is missing, rather than describing an action the compiled step can't take.

## WS4a — `decompose_goal_to_canvas(goal, ...)`

Calls `call_text(role="planner")` (cloud-tiers-to-local per D3, [[07 Models Credentials Speech and Resource Lifecycle|Note 07]]) with a schema prompt, validates the response (`_validate_decomposition`: exactly one `plan` node, no orphans, valid `branch`/`deliverables` format), lays it out (`core.canvas_layout.layout_document`), and writes a real `.canvas` file. Non-authoritative and read-only beyond that file — nothing downstream is proposed, approved, or executed automatically.

Takes an optional `max_attempts` (default 3): on a parse or validation failure, the specific problems are fed back into the next attempt's prompt rather than surfacing a one-shot failure — live testing found the local overseer succeeding on multi-branch goals roughly 2 times in 6 without this. A dependency cycle is a one-shot failure, deliberately not retried (a different failure class).

## WS4b — critique pass and the weighted refine loop (D5)

`critique_canvas_plan(canvas_path, ...)` extends T5's per-node dual-critic pattern to whole-plan level: a second planner-role call judges the decomposition itself (`approve` / `caution` / `re_review` / `reject`), backed by a deterministic post-check (`_plan_role_ordering_violations`) that force-escalates a verification node wired before its own implementation — live testing showed the model itself approving that ordering bug, twice.

`critique_and_propose_plan(goal, ...)` is the D5 loop:

- `re_review` rewrites the plan with the critique's own findings folded in and re-critiques, bounded by `max_rewrites`, fully automatic.
- `caution` / `reject` are the only paths that pull a human in. `caution` still proposes through the normal T4 gate with a `[!warning]` callout prepended to the approval note; `reject` (or an unresolved `re_review` after the rewrite budget runs out) does not call `propose_canvas_plan` at all.
- Critique is a linked Obsidian note (`Plans/canvas-critique-<id>-r<n>.md`), always wikilinked from the resulting approval note — Obsidian's own linking is the substrate (D5), not a JARVIS-UI panel.

## WS4c — branch-aware fan-out

`branch:` groups nodes into columns for a goal with 2+ largely-independent macro components. Layout (`core/canvas_layout.py`, `"dependency"` profile): each branch's own root (its most-synthesized node) sits at the top of its column, deeper prerequisites stack downward — the opposite of normal top-to-bottom reading, because decomposition reads outward on both axes while execution flows back toward the goal. **A node's own explicit `branch:` tag always wins its column placement, regardless of what feeds it** — a node with no tag of its own is the only kind eligible for the fan-out's other rule, sitting at the x-midpoint between whichever tagged branches feed it (a genuine shared/wrap-up node, e.g. a final integration step depending on two branches' output).

Zero or one distinct `branch` value is a strict backward-compatible fallback to the original single-chain layout, pinned by dedicated regression tests.

## WS4d — context inheritance and deliverables

Only `review` steps ever got automatic context from a dependency (T1's `evidence` binding, `result.summary`). Every other node ran on self-authored prose alone. `_context_preamble()` assembles a deterministic, ~220-char-per-fragment-capped block from prose already on the canvas — the plan's goal, the node's own branch purpose, one line per sibling branch — injected into `inputs.prompt` (research/review) or prepended onto `inputs.intent` (implementation), the exact fields dispatch already reads. No new model call.

Evidence-binding extends beyond review, but only to dependencies whose own role produces a reliably `summary`-shaped result (`research`/`note`/`review`/`plan`/`reference`) — `command`/`tool` results have no common `summary` field, so binding one would silently resolve to `None`.

Optional `deliverables` per node compiles into real, node-specific `step["acceptance_criteria"]["deliverables"]`, replacing the previously universal, unfalsifiable `{"required": true}`.

> [!success] Live-measured, not just structurally present
> Two focused before/after comparisons (same node, same model, bare prose vs. the real compiled preamble) found a genuine architectural-consistency failure without context: a frontend node with no visibility into a sibling backend branch's stated constraint ("the frontend never sees the OAuth token directly") recommended storing the token client-side. With the sibling-branch line present, the same node correctly honored the constraint throughout. See [[2026-07-25-ws4d-execution-quality-evaluation]].

## WS3 — cloud tiering (superseded 2026-09-23/24 — see [[07 Models Credentials Speech and Resource Lifecycle|Note 07]])

The OpenAI/Anthropic-first, LM-Studio-fallback description this section originally had is no longer how routing works. `planner_provider`, `worker_provider`, `research_provider`, and `reviewer_provider` are now all pinned to `deepinfra` in `config/runtime.json` (decoupled from LM Studio for cost — DeepInfra's measured per-token price undercut local hosting enough to make the switch, not a reliability concern). There is currently no automatic cross-provider fallback chain if DeepInfra is unavailable; a dead/unlinked route surfaces as a dispatch failure through the normal REPAIR/REJECT_REPLAN path rather than silently degrading to LM Studio. Note 07 has the full provider architecture.

### Two real bugs found live in this routing, both fixed 2026-09-24

- **`research` nodes dispatched on the `worker` route, not `research`, for their entire existence until this fix.** `dual_orchestrator.py`'s `model_reasoning` dispatch reads `inputs["role"]` to pick the `model_router` role, defaulting to `"worker"` when absent — and `compile_canvas` never set it. Every research-role canvas node silently ignored the dedicated `research_provider`/`research_model` config, running on the cheaper worker-tier model instead. A shallow research output that traced back to this, not (only) the retry-budget gap below, is what surfaced it.
- **The `research` role had no repair budget.** No `retry_policy` on `_ROLE_SPECS["research"]` meant it inherited the schema default (`max_attempts: 1`) — so a `REPAIR` verdict from T5's independent reviewer (e.g. "did not provide the required structured outline of all functions and classes") converted straight to `REJECT_REPLAN` without the step ever getting a real second attempt. Now `{"safe": true, "max_attempts": 2}` — safe to retry since the step has no side effects.

## The Centralised Capability Schema (2026-09-24)

`core/capability_schema.py` is a new, stable data source — one canonical `Capability` shape (`id`, `kind`, `keywords`, `risk_tier`, `requires_confirmation`, `allowed_roles`, `health_eligible`) that several previously-scattered, independently-drifting lists now read from instead of hardcoding their own copies: `core/tool_catalogue.py`'s `DISPATCHABLE_TOOL_IDS`, `canvas_plan.py`'s `_KNOWN_MODEL_ROUTER_ROLES` and `_ROLE_SPECS["research"]["allowed_tools"]`, and the compiled workflow schema's `target` enum (generated at schema-load time whenever `step_type == "tool"`, closing a gap where `target` used to be unconstrained free text). `core/tool_catalogue.py` itself ranks candidate tools by fused lexical + semantic relevance (Reciprocal Rank Fusion) and surfaces the result as a research node's `inputs.suggested_tools` — visible in the approval preview, not yet consumed by dispatch. `scripts/derive_capability_keywords.py` is a separate, offline, two-step blind LLM pipeline (never run at compile/dispatch time) that derives `keywords` from a capability's own functional description rather than hand-typing them, written to `config/derived_capability_keywords.json` and kept as `derived_keywords` — deliberately never merged into the hand-authored `keywords` field.

## Known boundaries

- Multi-branch decomposition succeeds roughly 2 times in 6 live attempts even with the retry wrapper's help on some goals — validation always refuses a malformed attempt cleanly (nothing bad is ever written), but this is real, measured model-reliability variance, not eliminated.
- Evidence-binding does not cover `verification`/`implementation` dependencies (command/tool results have no common `summary` field) — would need normalizing `dual_orchestrator.py`'s shared result-construction code, deliberately not done given its blast radius across Mode 1 workflows too.
- The WS4d execution-quality finding is two illustrative comparisons, not a statistically controlled study.
- VRAM-aware model admission (a byte-budget alternative to the flat `max_task_models_loaded` count) remains unbuilt — see [[07 Models Credentials Speech and Resource Lifecycle|Note 07]].
- `model_reasoning`/`review` dispatch never calls `call_with_tools` — a research node has zero live tool-calling ability at dispatch time regardless of `suggested_tools`; that field is currently visible-but-inert (same shape as `recommended_model`'s original gap). Wiring a bounded, single-round tool-calling loop into dispatch is the natural next step, not yet built.
- The `closing_check`/document-completeness routing only covers the case a canvas's ancestry is fully code-free; an `implementation` ancestor anywhere still falls back to `pytest_focused` against the whole suite, because `delegate_openclaw` reports no structured touched-files list a "blast radius" could scope a narrower test run against. A real fix needs git-diff snapshotting around the delegation, not yet designed.
- `derive_capability_keywords.py`'s output is measurably unreliable run-to-run on identical prompts (a real run reproduced this: `jarvis_memory` scored 7 good scenarios once, zero on an identical retry) — one retry-on-empty is built in, but the derived keywords should still be read as a first draft, not authoritative, until compared against the hand-authored `keywords` by a person.

## Related Notes

- [[03 Planning Approval and Dual Orchestration]] — the Mode 1 system this compiles onto
- [[11 Safe Canvas Service and Relationships]] — the structural Canvas layer underneath
- [[04 Fan-Out Workers Review and Recovery]] — T5/T6's shared execution machinery
- [[Planning Subsystem Roadmap]] — the design log (D1-D5) and workstream build history
