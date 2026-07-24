---
id: "jarvis-20260724T132443Z-3fabd047"
title: "Planning Subsystem Roadmap"
type: "report"
status: "active"
created: "2026-07-24T13:24:43Z"
updated: "2026-07-24T13:25:04Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["mark-platform", "planning", "roadmap", "architecture", "canvas-plan", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T13:24:43Z"
review_after: ""
source_version: 1
content_hash: "b1e14a241abab385ecce8d8d9209cb8918bf6df86376bf54298057a77ef4e95a"
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
memory_tier: "short_term"
---

> [!info] Scope
> A design-locked roadmap for turning JARVIS's planning subsystem from a deterministic keyword/compile step into a reasoning-backed, structured, auditable pipeline. WS1–WS3 are built; WS4 is the reasoning-planner capstone. Grew directly out of [[2026-07-24-canvas-node-live-test-and-hardening]] and [[user led test round]].

> [!abstract] Track A prerequisite added 2026-07-24 (from live testing + benchmark)
> The 16-prompt live test ([[2026-07-24-live-prompt-testing-16-prompts]]) exposed severe local-model timeout cascades, and the follow-up characterization benchmark ([[2026-07-24-model-characterization-benchmark]]) diagnosed them: **it was never load time** (every model cold-loads in <30 s; the 14B in 15 s) — it was the JIT-load path colliding with a short generation-timeout and health-cooldown. **Track A** (model characterization → timeout/residency hardening) is the prerequisite WS4's "large local overseer" silently assumed, and it now has concrete data. Key results: cross-vendor Vulkan pooling is confirmed working (14B = 9 GB across both 8 GB cards); **mistral-7b-instruct is the recommended interactive overseer** (clean structured output + tool calls, no reasoning bloat); the reasoning models (deepseek-r1, qwen3.5-9b, marco) over-think bounded prompts and never emit a final answer, which is the model-level root cause of the live test's "narrated instead of answered" failures. See the benchmark note for the full A2 settings (preload the overseer, split load-vs-generation timeouts, bound context, VRAM-admit mistral+qwen3-4b resident together).

> [!success] Track A2 shipped (2026-07-24, same day)
> Applied the benchmark's findings directly: `model_routes` ("main"/"reasoning"/"code", both `core.model_router.DEFAULT_LMSTUDIO_ROUTES` and the live `config/runtime.json` override) now try `mistral-7b-instruct-v0.3` first, with `deepseek-r1-0528-qwen3-8b`/`qwen/qwen3.5-9b` demoted to last resort. Also fixed a real bug found while diagnosing the cascade: `_route_from_context` scanned the *system prompt* for routing keywords, and the standing system prompt documents the `screen_process` capability with the word "image" in it -- so nearly every call misclassified as `route: vision`. Keyword routing now scans the user's prompt only. Deliberately did NOT touch timeouts (the load/generation split already exists as separate config keys -- `lmstudio_load_timeout_seconds`, `model_first_token_timeout_seconds`, `model_inter_token_timeout_seconds` -- the bug was purely which model got tried first) or `max_task_models_loaded` (reserved for after VRAM admission, Part C, lands). See [[2026-07-24-runtime-delegation-fix-and-reverification]] for the before/after re-test.
>
> **Revised same day:** initially also added `mistral-7b-instruct` to `baseline_models` to warm-keep it -- reverted after the owner reported 3 always-resident models held system RAM at ~70% stationary. `baseline_models` is now just `qwen/qwen3-4b-2507`; `mistral-7b-instruct` and `orpeus_text_to_speech` both load on demand and idle out after 5 minutes via the *existing* task-model TTL (`task_model_ttl_seconds`, already 300s -- LM Studio's own native per-model `ttl`, backed by a periodic sweep) rather than new preload/warm-keep machinery. TTS already has a Windows-SAPI fallback and is the last step before speaking, so a cold-load delay there is low-stakes.

## The problem, in one line

Plan *creation* today invokes no reasoning model at all — `plan_workflow._steps_from_prompt` is a keyword table and `canvas_plan.compile_canvas` is pure Python — while plan *execution* is a capable, gated, hash-bound runtime. The intelligence is on the wrong side of the line: the system reasons carefully about *running* a plan it never reasoned about *making*.

## Three facts that make this cheaper than it looks

1. **Model tiering already exists at the router.** `core/model_router.resolve_settings("planner")` already routes the `planner` role to a cloud provider and **auto-falls back to LM Studio when no cloud key is valid**. The overseer plumbing is done — nothing currently *calls* it during planning.
2. **The hook/command mechanism is already the execution model.** `CommandRegistry`/`HookRegistry` consume a structured input contract (`inputs.args`, `inputs.workdir`, tool params) and `_resolve_bindings` already threads results between steps. The runtime is ready to run scoped tools; the compiler just never fills in the scope.
3. **The receipt surface already half-exists.** Every tool dispatch already emits a `process_event` with an unused structured `detail` field, and a process-trace already exists. The action feed is an *enrichment*, not new infrastructure.

## The unifying idea

The reasoning model's real job is **not** "pick a step count." It is to produce **structured, executable parameters once, at plan time**, which are frozen into the approved bundle (exactly as T6 already freezes `workflow.yaml`) and then replayed deterministically. Parameter-binding, anti-fabrication, and the receipt feed are all just different views of *the structured params the runtime actually executed*.

```
   PLAN TIME (overseer model)                     EXEC TIME (deterministic)          SURFACE
 goal / canvas -> reason: decompose -> STRUCTURED -> [human gate] -> replay -> RECEIPT -> vault trace
                  + critique (looped)   params        (Obsidian)     frozen     (real       + Obsidian
                                        (frozen,                     params      return)     review notes
                                        hash-bound)                  only
```

---

## Decision log — owner, 2026-07-24

These are locked design decisions, not open questions.

### D1 — Every planning-canvas node is dual-purpose
A node is simultaneously **(a)** a structural step in the compiled workflow and **(b)** a complete, self-contained prompt to whichever agent executes it. `role:` plus clear directive lines give the executing agent an unambiguous brief. This is the load-bearing principle the rest of the design hangs off: the node text is both the plan and the prompt.

### D2 — Targeting is a visible, editable *recommendation*, not a silent default
- **One dedicated canvas per overall plan** (so plan-level context — including the target project for developer work — lives at the canvas level, not repeated per node).
- Where a task could go to different engines, the planner assigns it a coarse class — **`semantic`** (reasoning / research / knowledge models) or **`developer`** (code / OpenClaw) — and renders it on the node as, e.g., `recommended model: developer (openclaw)`.
- **The user can edit or remove that line. Left unedited = accepted. Edited = re-assessed** (re-fingerprint → re-approval, which T4 already enforces). This *is* the authorization surface for side-effectful nodes: instead of silently defaulting a `project_id` and letting OpenClaw touch a live repo on approval, the user always sees "this runs via developer/OpenClaw" and tacitly consents by leaving it in place.

### D3 — Offline overseer = large local model; cloud is a first-class upgrade via the session key box
- No elaborate keyword-fallback ladder is needed. The overseer is the `planner` role: cloud model when a key is present, **large local model otherwise**. The deterministic keyword table is demoted to a last-resort safety net (total model unavailability), not the happy path.
- The existing session API-key box (left of screen, entered at session start or on demand) must be generalized to accept **both Anthropic and OpenAI keys**, which requires adding an **Anthropic provider** to `core/model_router.py` alongside the existing `openai`/`gemini`/`lmstudio`.

### D4 — Anti-fabrication is the hard version, surfaced through the existing vault trace
- Approved: the runtime post-checks the final summary against actual receipts and flags/redacts any completion/test/build claim it can't cite. (Structural replacement for the prompt-hardening band-aid already shipped.)
- Plus: a **listener that feeds every script/test/command result into the same trace already used to track vault edits**, so "last script/test: passed / failed" is visible where the user already looks — no separate panel needed to answer "did that actually run and pass?"

### D5 — Plan critique lives in Obsidian, and refinement is an automatic loop
- Critique is **linked Obsidian review notes**, connected to the plan by inline wikilinks — *not* a JARVIS-UI panel (which would clutter/compress). Obsidian's linking is the right substrate.
- A weighting step decides one of: **re-review** (loop back and rewrite the plan), **caution** (proceed but flag), or **reject** (discard the critique). **Caution or reject → notify / call in the user for review.**
- The goal is an **automatic plan-rewrite/refinement loop** inside the planning phase, not a one-shot pass.

---

## Workstream 1 — Dual-purpose nodes + structured directives *(first: no model, offline-safe, fixes confirmed bugs)* — ✅ DONE (2026-07-24)

> [!success] WS1 shipped and live-verified (2026-07-24)
> `actions/canvas_plan.py`: `_parse_node_directives`/`_node_directives` parse consecutive `role:`/`scope:`/`test:`/`project:`/`file:`/`recommended model:` lines (any order, any subset); `compile_canvas` wires `scope:` into `inputs.args`, `project:` into `inputs.project_id` (node-level overrides a `project:` declared on the canvas's `plan`-role root node -- "one canvas = one plan target"), and always forwards the stripped prose as `inputs.intent`. An unregistered `project:` now raises `CanvasCompileError` at compile time instead of silently no-opping at dispatch. `plan_fingerprint` now includes directives, so editing one (e.g. `recommended model:`) re-triggers approval per D2 -- confirmed with a dedicated test. The approval preview table gained a **Resolved target** column showing the real `scope:`/`project:` (or a `⚠` warning when neither resolves), replacing the old prose-only view that could describe an action the compiled step would never take.
>
> **24 new unit tests, 717/717 full suite green.** Live re-run of the exact scoped-verification case from [[2026-07-24-canvas-node-live-test-and-hardening]]: the original unscoped run took 600s+ and ended `BLOCKED`/`REJECT_REPLAN` from self-starvation; the same request with a `scope:` directive now completes in **2.15s total** (`17 passed in 0.35s`, `ACCEPTED`). The implementation-node chain was validated end-to-end with `delegate_openclaw` called directly (a mocked subprocess, so nothing was actually spawned): the canvas node's prose correctly arrives as the real OpenClaw task text and clears both policy checks (`agent_count`, `intent`).
>
> **New safety-relevant finding surfaced during that dry run, not yet acted on:** `config/project_registry.json` lists `delegate_openclaw` under `mark_platform`'s `safe_operations` -- meaning `project_operator`'s own policy layer requires **no separate confirmation_id** for OpenClaw delegation against this live codebase. The single canvas-level Approve checkbox is the *only* gate between an approved implementation node and OpenClaw actually writing to this repo. Worth a deliberate decision (leave as-is, since T4's approval is already a real human gate; or add a per-operation confirmation requirement) rather than silently discovering it live again.
>
> **Not done:** a real, non-dry-run OpenClaw spawn was deliberately not triggered as part of this validation -- letting an autonomous coding agent loose on the live repo is a bigger action than validating the parameter-wiring fix required, and the dry run already proves the chain works.


Implements **D1** and the deterministic half of **D2**.

**Node anatomy** (directive lines first, then the freeform agent prompt):
```
role: verification
scope: tests/test_vault_watch.py
recommended model: developer (openclaw)

Verify scan_once still passes after the wiring change — just this one file.
```

**Directive schema (deterministically parsed, zero model):**

| Directive | Applies to | Compiles into | Notes |
|---|---|---|---|
| `role:` | all | step role / `_ROLE_SPECS` | already parsed today; extend the same line-directive reader |
| `scope:` / `test:` | verification | `inputs.args` (e.g. `["tests/test_vault_watch.py"]`) | fixes full-suite-always + self-starvation |
| `project:` | implementation | `project_id` (else inherit canvas-level) | one canvas = one plan target |
| `file:` | reference / implementation | `inputs.file` / target path | |
| `recommended model:` | semantic\|developer nodes | model-class hint + authorization surface (**D2**) | editable; unedited = accepted |
| *(prose after directives)* | all | the agent's actual prompt / `intent` | the D1 dual-purpose payload |

**What this fixes immediately** (all confirmed in [[2026-07-24-canvas-node-live-test-and-hardening]]): verification nodes that ignored their scope and ran the whole suite; three same-layer test nodes starving each other into false timeouts; implementation nodes that silently no-op'd with no `project_id`; and the approval preview showing prose that wouldn't actually run.

**Validation:**
- *Unit:* `scope: X` → `inputs.args == ["X"]`; `project: Y` → real `project_id`; missing directive + no model → node flagged, not silently empty.
- *Live:* re-run the exact V1/V2/V3 + I1/I2/I3 from the hardening report; expect V2 to finish in seconds without starving, and I-nodes to reach their declared target (or, if gated, to arrive at OpenClaw with the right project + intent).
- *Regression:* params now enter the plan fingerprint (correct — a changed scope *should* re-gate approval); re-verify T4 binding and T5 review still behave.

---

## Workstream 2 — Execution receipts into the vault trace + hard anti-fabrication *(highest trust value)* — ✅ DONE (2026-07-24)

> [!success] WS2 shipped and live-verified (2026-07-24)
> Turned out the "trace listener" didn't need building: vault-edit events and tool-dispatch events already emit into the same `core.process_events.PROCESS_EVENTS` hub the `ProcessTraceWidget` renders (confirmed by matching the widget's `_show_detail()` JSON shape against the exact blob the owner pasted from their own test). The gap was purely that tool-dispatch events carried an empty `detail`. Fixed: `main._tool_receipt(name, arguments, raw_result)` builds a deterministic receipt (tool, operation, parsed `ok`/`returncode`/`error`, a bounded result snippet) and it's now attached to every tool-call event in `_handle_router_text_command`. `actions/canvas_plan._canvas_execution_receipt(result)` does the equivalent for canvas runs, reading each item's already-written result file for a real pass/fail/output-tail summary, attached to the `canvas_plan()` dispatcher's `execute` completion event.
>
> **Hard anti-fabrication post-check**, `main._unverified_completion_notice(reply, receipts)`: scans the final reply for completion-style claims (test/build passed, confirmation gate satisfied, proceeding with closure) and appends a deterministic caveat -- not a silent rewrite -- whenever none of the turn's receipts contain real supporting evidence (a pytest-style `N passed`/`N failed` summary). Applied only to the generic model-narrated reply path (tool-routed, no-tool, and the planner-failure fallback), deliberately not to the specialized hard-routed workflow handlers (plan/learn_project/etc.), which weren't audited for this and use their own result construction.
>
> **Live re-run of the original fabrication scenario** (real `project_operator` call against `quantule_mapper`, real LM Studio model, real `_build_tool_summary_prompt`): the model's reply was *already* honest this time -- "tests... were not run... cannot be confirmed as passing" -- a direct benefit of the WS0 prompt-hardening from earlier the same day. That surfaced a real bug in the new check itself: the negation-blind regex flagged this correct, honest reply as if it were the false-positive claim (matched "tests... passing" without noticing "cannot be confirmed as"). Fixed with sentence-scoped negation checking (`_CLAIM_NEGATION_RE`, `_sentence_start`) before this shipped, with a regression test pinned to the exact reply text that exposed it. Re-verified live after the fix: the honest reply gets no caveat, and the original verbatim fabricated reply ("proceeding with feature closure") still does.
>
> **Not built (deferred, not needed yet):** the "(Later) UI action feed" panel -- the existing `ProcessTraceWidget` already renders receipts distinctly once selected (its detail pane shows the JSON), so a dedicated feed is only worth building if that's not enough in practice.
>
> 12 new tests, 729/729 full suite green.


Implements **D4**.

- **Receipt data (cheap):** populate the already-present `detail` field on tool/command dispatch events with a factual receipt — tool + operation + arguments sent + real return (exit code / `ok` / short output snippet / result path). Runtime-produced, so unfabricatable.
- **Trace listener:** a subscriber that mirrors every script/test/command receipt into the existing vault-edit trace, so "last script/test: passed/failed" shows up where the user already watches vault activity.
- **Hard summary post-check:** the deterministic summary step cross-checks completion/test/build claims against receipts and flags or redacts any that can't cite one.
- **(Later) UI action feed:** a panel rendering receipts visually distinct from conversational replies — optional once the trace listener already answers the core question.

**Validation:**
- *Unit:* a tool dispatch emits a receipt with payload + return; a conversational reply emits none; the post-check strips an unsupported "tests passed" claim.
- *Live:* re-run the original fabrication prompt from [[user led test round]]; confirm the trace shows a `project_operator` receipt with a project-list result and **no test receipt**, so the false "tests passed" claim has nothing to cite and is redacted.

---

## Workstream 3 — Cloud key adaptability (Anthropic + OpenAI) *(small, unblocks the cloud overseer)* — ✅ DONE (2026-07-24)

> [!success] WS3 shipped (2026-07-24)
> `core/model_router.py`: added `anthropic` as a first-class provider alongside `openai`/`gemini`/`lmstudio` -- `_call_anthropic_responses`/`_call_anthropic_with_tools` target the real Messages API (`POST /v1/messages`, mandatory `max_tokens`, `system` as a top-level field, tool results as `input_schema` not `parameters`, tool calls as `tool_use` content blocks not a `tool_calls` array). Wired into both `call_text`/`call_with_tools` with the exact same shape as the OpenAI branch: invalid/missing key or any request failure falls back to lmstudio, never a hard failure. `claude`/`anthropic` both normalise to the same provider string.
>
> **Real bug found and fixed while wiring this in, not introduced by it:** `resolve_settings` baked `cfg.get("openai_model") or DEFAULT_OPENAI_MODEL` into `selected_model` *before* branching on which provider was actually selected -- so `planner_provider: gemini` (or now `anthropic`) with no explicit model configured silently got `gpt-5.5` handed to the wrong API. Fixed by moving each provider's default resolution into its own branch; added a regression test pinning the previously-silent gemini case too. The lmstudio-fallback model-id strip (`gpt-`/`o1`/`o3`/`o4` prefixes, so a cloud model id never gets sent to LM Studio on fallback) now also strips `claude` prefixes.
>
> **Session key box** (`ui.py`) generalized: header now reads "API KEY (OPENAI / ANTHROPIC)", `core.session_credentials.detect_key_provider(key)` routes by shape (`sk-ant-...` -> Anthropic, everything else -> OpenAI, preserving existing behavior for current users), and the status label shows which provider is linked. The credential broker (`_broker_main`, the separate OS process that holds the raw key) got provider-aware headers (`x-api-key`+`anthropic-version` for Anthropic vs `Authorization: Bearer` for OpenAI) and a provider-aware link-validation probe. Deliberately skipped the `/models` list-check for Anthropic specifically (kept OpenAI's unchanged) since that endpoint's exact response shape was never verified against a live key, and a wrong assumption there would have rejected a valid key before the real validation (the message probe) ever ran.
>
> **Not live-tested against a real Anthropic key** -- none was available and the owner was stepping away, so this shipped on mocked-broker unit tests (mirroring the existing OpenAI test pattern) rather than a live round-trip. Worth a real key test when convenient.
>
> 17 new tests, 746/746 full suite green.


Implements **D3**'s key half.

- Add an **Anthropic provider** to `core/model_router.py` (Messages API), parallel to `_call_openai_responses` / `_call_openai_with_tools`.
- Generalize the session key box (currently "OPENAI API KEY") to detect provider by key shape (`sk-ant-…` → Anthropic, else OpenAI) or a small selector, and route the `planner`/`reviewer` roles accordingly.
- Preserve the existing fallback: invalid/absent key → large local model, never a hard failure.

**Validation:** unit — an `sk-ant-` key resolves `planner` to the Anthropic provider; an absent key falls back to lmstudio. Live — enter each key type in the box mid-session and confirm the next planning turn routes to the intended provider (visible via the new receipts).

---

## Workstream 4 — Reasoning plan + Obsidian-native critique loop *(the capstone; needs WS1's contract)*

Implements the model half of **D2** and all of **D5**.

- **Decomposition pass:** `call_text(role="planner")` takes the goal (Mode 1) or the drawn canvas (Mode 2) and emits a *structured* plan — ordered steps, each with WS1 directives + a `recommended model` class + rationale. Router tiers cloud → large-local automatically.
- **Critique pass:** a second planner-role call assesses the draft for missing steps / prerequisite to-dos, written out as **linked Obsidian review notes** (extends T5's per-node review up to plan level).
- **Weighted refine loop (D5):** the weighting step chooses re-review / caution / reject; re-review rewrites the plan and loops; caution or reject **notifies the user for review**. The loop is automatic within the planning phase; the human is pulled in only on caution/reject, not every pass.
- **Non-authoritative throughout:** the model proposes; the human gate (T4/T5) still binds; execution stays deterministic replay of the frozen bundle.

**Validation:** unit — mock `call_text(role="planner")` returning a known structured plan → assert parse/render + directives populate; return garbage → assert last-resort safety net. Live — run a genuinely complex goal (e.g. the VRAM-admission work) and compare decomposition against today's keyword template; force a deliberately under-scoped plan and confirm the critique catches the missing prerequisite and loops.

---

## North star (EOL expectation) — backward decomposition + semi-automated research

The long-term target the above is shaped to reach: the user states a single **goal**; even if it spans five subsystems each with their own components, the planner **works backwards** from the goal to the simplest atomic actions, and along the way **identifies missing knowledge** and spawns **semi-automated research nodes** to fill those gaps before the dependent build steps run. This requires the structured plan artifact to be **recursive/nestable** (a step can expand into its own sub-plan) and the critique loop to be able to emit *research* nodes, not just corrections. WS1–WS4 are the substrate; this is the capability they compound into.

---

## Suggested sequence

| # | Workstream | Why here | Cost | Blocks |
|---|---|---|---|---|
| 1 | WS1 dual-purpose nodes + directives | fixes confirmed bugs, offline-safe, no model | Low | — |
| 2 | WS2 receipts → vault trace + post-check | kills the fabrication class at the data layer | Low–Med | — |
| 3 | WS3 Anthropic + OpenAI key adaptability | unblocks the cloud overseer | Low | enables WS4 quality |
| 4 | WS4 reasoning plan + Obsidian critique loop | the capstone | High | WS1 |
| 5 | North-star recursion + research-gap nodes | compounds WS1–WS4 | High | WS1–WS4 |

## Related
- [[2026-07-24-canvas-node-live-test-and-hardening]] — the live findings this responds to
- [[user led test round]] · [[Claud led testing]] — the owner's manual test + observations
- [[Project Brief]] · [[Project Memory]] — Mark Platform project space
- `docs/superpowers/plans/2026-07-23-mark-canvas-planning-engine.md` (repo) — the T1–T7 canvas engine this builds on
- `docs/superpowers/dag-training-opportunities.md` (repo) — the tool-selector + retry-classifier candidates this touches
