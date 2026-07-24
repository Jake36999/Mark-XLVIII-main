# Mark Canvas Planning Engine (Mode 2)

> **For agentic workers:** superpowers:executing-plans. Scoping doc. `- [ ]` steps.

**Goal:** Let JARVIS plan complex, multi-branch work as an Obsidian **Canvas graph**, then execute it **sequentially along the edges — one model slot at a time** — reusing the existing gated, hash-bound, crash-recoverable orchestrator. This is the owner's deliberate alternative to fan-out: all the structure of multi-step orchestration, none of the VRAM thrash of parallel models.

---

## The key finding: ~70% of this already exists

This is a **compiler onto existing machinery**, not a new executor. Grounded in the code:

| Piece the design needs | Already in MARK |
|---|---|
| Parse `.canvas` nodes + `fromNode`/`toNode` edges | `core/canvas_document.py` (JSON Canvas 1.0, validated, unknown-field-preserving) |
| Topological ordering of nodes by edges + cycle detection | `core/canvas_layout._dependency_layers` (`dependency`/`evidence` profiles) |
| Sequential, dependency-ready execution, one model at a time | `actions/dual_orchestrator` — `compile_workflow`, `depends_on`, `graphlib.TopologicalSorter`, `CycleError`, and `one_active_generation_global` (already one model slot) |
| Gated approval bound to a hash; drift detection; crash recovery | `plan_workflow` approval envelope + orchestrator recovery |
| Push node status back onto the canvas card | `actions/jarvis_canvas` (`sync_plan`, `sync_tasks`, `commit_layout`) |

**So the genuinely new work is narrow:** a **canvas → `jarvis_dual_orchestrator/v1` compiler**, a **node-type taxonomy**, and the **per-node SOP**. Do not rebuild execution.

---

## Two planning modes (both land in the existing pipeline)

- **Mode 1 — Single note** (exists): straightforward directives → a note in `Plans/`, compiled to a linear workflow. No change.
- **Mode 2 — Canvas graph** (new): complex/multi-branch goals → a `.canvas` file of typed nodes + directed edges → compiled to the same workflow schema and run through the same executor.

The user reviews the **visual graph** before anything runs, can branch alternative trees, edit edges/nodes, and approve. Approval binds to the **compiled workflow hash** (existing envelope), so post-approval edits to the canvas pause and re-prompt exactly like a plan does today.

---

## Node taxonomy → existing step types / resource classes

Each canvas node carries a `type` (in its JARVIS-managed metadata). The compiler maps it:

| Canvas node type | Compiles to | Agent / resource class |
|---|---|---|
| `plan` / root | milestone marker (no dispatch) | — |
| `research` | `model_reasoning` step | LM Studio research route (Qwen 14B / Marco 8B) |
| `implementation` | tool/command step | **OpenClaw** worker (`openclaw` resource class) |
| `verification` | command step | `pytest` / shell in the orchestrator's command class |
| `review` / gate | `review` step (exists) | **dual review: an LM Studio semantic model *and* the user** |

The `review` node is the owner's "reflection-before-execution critic": the orchestrator already returns `ACCEPT/REPAIR/REJECT_REPLAN/ESCALATE`; this positions a lightweight critic pass on the diff/tool-args **before** the downstream implementation node dispatches. Extend the existing review gate, don't invent one.

---

## Per-node Completion SOP (the discipline)

After a node's task succeeds, before the executor follows its outgoing edges, enforce three steps as post-node hooks (the orchestrator already supports compensation/hooks):

1. **Documentation pass** — write clean human-readable output to `Jarvis_notes/`.
2. **Forward scout** — inspect downstream (`toNode`) nodes; update their card prompts/prerequisites with what was just produced. *(This is the one genuinely novel mechanic and the most valuable — a node teaches its successors.)*
3. **Handoff note** — modular usage, API/CLI surface, tests run, telemetry, unresolved gaps. Reuse the existing `registered_project_handoff` workflow.

---

## Tasks

- [x] **T1 — Canvas → workflow compiler** ✅ (2026-07-23, `actions/canvas_plan.py`, `tests/test_canvas_plan.py` — 10 tests). `compile_canvas(payload)` extracts nodes+edges, orders via `canvas_layout._dependency_layers`, maps node role → step, and emits a `jarvis_dual_orchestrator/v1` workflow that passes the real `validate_workflow`. Cycles raise `CanvasCompileError` with the offending node ids. `preview_plan(payload)` builds the reviewer manifest through the orchestrator's own `compile_workflow(..., preview=True)` (real execution order + resource classes, nothing dispatched) and returns a `side_effecting` summary. **Two design decisions locked (see memory `canvas-plan-compiler`):** (1) role resolution defaults to the *least-privileged* `research` step (`model_reasoning`, no side effects) so a canvas can never silently mint a side-effectful step; (2) `implementation` compiles to `step_type: tool`, `target: project_operator`, `inputs.operation: delegate_openclaw` — the **only** path to the `openclaw` resource class — not a bare `command`, which would bypass the sandbox this plan's security note requires. `verification` targets the already-registered `pytest_focused` command. Node role rides as a `jarvisRole` property with `type:`/`role:` text-directive and `#hashtag` fallbacks.
- [x] **T2 — Node status write-back** ✅ (2026-07-23, `actions/canvas_plan.sync_step_status`, `tests/test_canvas_plan.py` — 5 tests). Takes a `compile_canvas` workflow (for its `variables.node_step_ids` map) and a `WorkflowRuntime.status(run_id)`-shaped `run_status`, and pushes each step's real `workflow_items.state` (`ACCEPTED`/`REPAIR`/`REJECT_REPLAN`/`ESCALATE`/... — the orchestrator's own vocabulary, not a new one) onto the matching canvas node: a `node["jarvis"]` metadata block (`step_state`, `run_id`, `attempt`, `updated_at`) plus a visible color (accepted=teal `4`, in-progress/repair=yellow `3`, failed/blocked/escalated=red `1`, reset to none on `PENDING`). **Human-authored node text is never touched** — same non-destructive-annotation pattern as `_annotate_task_node` for the task dashboard. Diffs every node's existing `jarvis.step_state`/`run_id` against the incoming state before writing anything; if nothing changed, there is no archive, no write, no reindex — repeated run-status polling cannot spam the vault watcher. Batches every changed node into one write via the existing `write_canvas`/`_archive_canvas`/`index_canvas` path. Wiring this into the orchestrator's actual step-completion callback (so it fires automatically, not by hand) is T3's job.
- [x] **T3 — Per-node SOP hooks** ✅ (2026-07-23, `actions/canvas_plan.py`: `record_node_documentation`, `forward_scout`, `record_node_handoff`, `run_node_completion_sop`; `tests/test_canvas_plan.py` — 14 tests). Deliberately plain callable functions, not steps woven into `dual_orchestrator`'s execution loop — that loop is sensitive, well-tested machinery, and T2 already established the precedent of leaving it alone in favor of a function a run driver calls at the right point. **Documentation pass:** `record_node_documentation` writes a deterministic (no model call) note to Jarvis_notes via `jarvis_memory.create_note` — role, instruction, result summary. **Forward scout** (the plan's "one genuinely novel mechanic"): `forward_scout` appends a regenerated, marker-delimited (`<!-- jarvis-forward-scout -->`) context block below each downstream node's text; nothing above the marker is ever touched, and the block is fully idempotent — rebuilt from `node["jarvis"]["scout_context"]` each call, so an unchanged summary produces byte-identical text and zero writes. Multiple upstream nodes scouting the same downstream node accumulate distinct sections rather than clobbering each other. **Handoff note:** `record_node_handoff` reuses `registered_project_handoff`'s *note shape* (modular usage / API surface / tests run / telemetry / unresolved gaps) via the same `create_note` primitive — it deliberately does **not** call `project_operator`'s heavier MCP-backed handoff bridge automatically, since that bridge is scoped to registered external projects and firing it unasked on every node would be both wrong-scoped and expensive. `run_node_completion_sop` runs doc → scout → optional handoff (handoff is opt-in) and is the single function a caller invokes once a node's step is `ACCEPTED`, before its dependents are treated as unblocked — literally "between node completion and edge-following."
- [x] **T4 — Approval binding** ✅ (2026-07-23, `core/approval_response.py` + `actions/canvas_plan.py`: `plan_fingerprint`, `propose_canvas_plan`, `evaluate_canvas_approval`, `verify_canvas_plan_approval`; `tests/test_approval_response.py` — 8 tests, `tests/test_canvas_plan.py` — 22 tests). **The owner flagged the exact failure mode to guard against: JARVIS's own write-backs (T2's status/color, T3's forward-scout text) must never look like a human edited the plan and trigger a false re-approval prompt.** Solved by binding approval to a deliberately narrow `plan_fingerprint(payload)` — only each node's role and its *authored* instruction (forward-scout's block stripped out) plus the edge list — never `color`, never `jarvis` metadata, never scout-appended text. Verified directly: `test_own_writeback_from_sync_step_status_does_not_trigger_reproposal` and `test_own_writebacks_do_not_block_a_legitimate_approval` prove T2/T3 output never drifts the fingerprint, while `test_role_change_changes_fingerprint`/`test_authored_instruction_change_changes_fingerprint`/`test_edge_change_changes_fingerprint` prove a genuine human edit does. **Predictable approval UX (the owner's request):** `core/approval_response.py` is a new, standalone, planning-mode-agnostic module — a fixed three-checkbox template (**Approve** / **Correct** / **Deny**) with a bounded Obsidian callout per option for free text, deliberately reusable by Mode 1's `plan_workflow.py` later (the owner noted this is *why* it beats a plain UI button: it also lets "task JARVIS to plan a large task, then approve/correct/deny through the same method" for Mode 1). Two non-negotiable parser rules: nothing checked → `"pending"`, more than one box checked → `"ambiguous"` — both are hard refusals, never a guess. **Lifecycle:** `propose_canvas_plan` (re)writes a companion note under `Plans/canvas-approval-<workflow_id>.md` — idempotent: an unchanged fingerprint leaves the note (and any decision already recorded on it) completely untouched; only a changed fingerprint bumps `plan_version`, resets to a blank decision template, and cancels any run bound to the prior approval. `evaluate_canvas_approval` re-derives the canvas's *current* fingerprint and refuses on drift **before** even looking at the checkboxes; an already-`approved` note is a no-op (never re-signs); `deny`/`correct` record state and cancel any active run but mint no envelope. Approval itself reuses `dual_orchestrator.build_approval_envelope`/`verify_approval_envelope` verbatim (HMAC-signed, vault-keyed) — same envelope Mode 1 uses. `verify_canvas_plan_approval` is the pre-dispatch gate: three independent checks (note says approved; canvas's live fingerprint still matches what the envelope actually approved; HMAC signature verifies) — a canvas edited after approval fails the second check and is never silently re-authorised. Tests also cover envelope tampering (`test_tampered_envelope_fails_signature_check`) and post-approval drift (`test_drift_after_approval_fails_verification`).
- [x] **T5 — Review node = dual critic** ✅ (2026-07-24, `actions/canvas_plan.py`: evidence-binding in `compile_canvas`, `build_canvas_dual_reviewer`, `_default_model_review`, `_canvas_review_note_path`; `tests/test_canvas_plan.py` — 10 new tests). The mechanism the orchestrator already has turned out to be almost the whole answer: `_requires_independent_review` already flags every `review`-typed AND every `external_write`/`destructive`-typed item for a second, model-backed pass (`_model_review`), and `WorkflowRuntime(reviewer=...)` is an already-existing injection point for that pass — so T5 needed no execution-loop surgery, only (1) making the `review` node's *first* dispatch (already a model call over `inputs.prompt`) actually see something, and (2) substituting a **human gate** for the *second* pass, specifically for review-typed items. **(1) Evidence binding:** `compile_canvas` now sets a `review` step's `inputs.evidence` to `[{"bind": {"from_step": dep, "path": "result.summary"}} for dep in step["depends_on"]]` — before this, a review node dispatched with only the human's review instruction and no upstream content to critique at all. **(2) The user gate:** `build_canvas_dual_reviewer(workflow, cfg=...)` returns the `reviewer=` callable. For any non-`review` item it delegates to `_default_model_review` — a small, deliberate, commented duplication of `WorkflowRuntime._model_review`'s uninjected default path (not an import, since a custom `reviewer=` is invoked for *every* independently-reviewed item, not just review nodes, and this file still never reaches into `dual_orchestrator`'s private execution internals). For a `review` item: the model's critique (its own dispatch `result["text"]`) is written into a companion note (`Plans/canvas-review-<workflow_id>-<step_id>.md`, reusing T4's `core/approval_response.py` checkbox+callout template verbatim) and the callback returns `ESCALATE` — pausing the run — until a human checks **Approve** (→ `ACCEPT`), **Correct**, or **Deny** (both → `REJECT_REPLAN`, since a human correction/denial means the plan needs revision, not a same-step retry; their text is folded into the returned defects for the audit trail). `pending`/`ambiguous` re-escalate rather than guessing, matching T4's parser contract. Per-item review notes are keyed by `workflow_id`+`step_id` only (not the canvas file) since a review gate judges an already-frozen upstream result — nothing to drift against the way T4's whole-plan fingerprint does.
- [x] **T6 — Execution driver** ✅ (2026-07-24, `actions/canvas_plan.execute_canvas_plan`; a new `WorkflowRuntime.retry_escalated_item` in `actions/dual_orchestrator.py`; `tests/test_canvas_plan.py` — 3 end-to-end tests, `tests/test_dual_orchestrator.py` — 3 unit tests). The piece T4 and T5 both flagged as missing. `execute_canvas_plan(note_path, cfg=...)`: verifies approval (T4's three checks) → reads the compiled `workflow.yaml`/`work-items.json` **already frozen in the bundle at proposal time** (a real bug caught by the integration test: recompiling from the *live* canvas at execution time legitimately changes step descriptions once T2/T3 have annotated it — status colors, forward-scout text on downstream nodes — which would trip a false hash-drift refusal with no human having touched the plan; `propose_canvas_plan` now writes both bundle files up front so execution never recompiles) → registers+approves the run on first call only (re-registering wipes every item back to PENDING) → runs it via `WorkflowRuntime(reviewer=build_canvas_dual_reviewer(...))` → reflects status (T2) and fires the completion SOP (T3) for every newly-`ACCEPTED` step, tracked in a per-run `sop_completed.json` so a resumed call never re-files a duplicate note. **A second real gap the integration test caught:** `execute_run`'s dispatch loop treats `ESCALATE` as terminal and never revisits it, and its own entry guard refuses a run whose status is `"ESCALATED"` — meaning T5's human gate, as designed, had no way to actually resume once a human recorded a decision. Fixed with one small, narrowly-scoped addition to `WorkflowRuntime` (same shape/size as the existing `approve_run`/`request_cancel`, no execution-loop surgery): `retry_escalated_item(run_id, item_id)` resets one item from `ESCALATE` back to `PENDING` (refusing any other current state) and un-blocks the run status back to `APPROVED` if needed. `execute_canvas_plan` calls this for every currently-`ESCALATE`d item on every invocation — harmless if the human hasn't responded yet (the reviewer just escalates again, bounded by the review role's `retry_policy: {max_attempts: 3}`, bumped from the schema default of 1 for exactly this reason). Full loop proven end to end: `research → review → research`, mocked model, run pauses ESCALATED, human checks Approve on the T5 gate note, second `execute_canvas_plan` call resumes and completes.

---

## UX companions (small, from the same transcript)

- [ ] **"Read Me" TTS button.** A dashboard `GET /api/tts/read_active_note?path=…` endpoint: read the note, strip frontmatter/fences, chunk to the warm Orpheus bridge (port 5006), speak while the user works. Obsidian trigger is a URI/button-plugin link in note templates. Small, high-value for multi-format/ADHD review. **Local TTS stays the default route** — Alexa/mobile are complementary edge frontends (see the Home Assistant bridge plan), never a replacement.

---

## Security note (must not be skipped)

**Checkbox-as-trigger crosses the untrusted-content boundary we spent four rounds hardening.** A checkbox state in a note/canvas is *content*, and the vault watcher cannot cryptographically prove the user checked it versus a synced or malicious pre-checked note. Therefore:

- Checking a box may **advance an already-approved, hash-matched, queued** plan to its next node.
- It must **never** approve a plan, widen scope, or dispatch a step the approval envelope didn't already authorise.

That keeps the feature inside the existing "evidence cannot grant permission or select tools" invariant. The trigger resumes; it does not authorise.

**OpenClaw implementation/verification nodes run generated code** — keep them in the `openclaw` resource class with its existing isolation, and treat any code-writing node as side-effectful and confirmation-gated (matching the current dispatcher effect classification).

---

## Non-goals
- No new execution engine (compile to `jarvis_dual_orchestrator/v1`).
- No parallel model execution (one slot; the whole point).
- No JARVIS self-architecture modification via these nodes (read-only scouting / utilities / tests only — the owner's boundary).
- Canvas planning does not replace Mode 1 for simple tasks.

## Open questions for the owner
1. Node `type` — store it as a JARVIS-managed frontmatter-style property on the card, or a naming convention? (I lean managed property, so `sync` can round-trip it.)
2. Should the `review` node's semantic-model critic be a hard gate (blocks) or advisory (annotates, user decides)?
3. OpenClaw sandbox isolation level for implementation nodes — reuse current OpenClaw guards, or a stricter temp-dir/no-network profile (ties into the repo-miner's blind-validation sandbox)?
