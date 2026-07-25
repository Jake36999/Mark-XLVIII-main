---
id: "jarvis-20260725T193924Z-d4724b69"
title: "Chat Tool Confirmation Gate - Implementation and Live Validation"
type: "report"
status: "active"
created: "2026-07-25T19:39:24Z"
updated: "2026-07-25T19:39:34Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "security", "confirmation-gate", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T19:39:24Z"
review_after: ""
source_version: 1
content_hash: "078408d0583d5653a72f9916e14eae5fd1105fc9b285e79fcae56bc2dfc9c8ed"
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
> Implementation and verification of the fix for the headline finding in [[Validation/2026-07-25-expanded-live-validation|the expanded validation pass]]: `main.py`'s plain-chat tool dispatch executed `requires_approval` tools (like `dev_agent`) with zero confirmation gate. Full plan at `C:\Users\jakem\.claude\plans\prancy-petting-honey.md`. This note documents what was built, two real bugs caught during implementation (not shipped), and live evidence the fix actually holds against the real running system -- not just mocked tests.

## What was built

- **`core/chat_confirmation.py`** (new): `is_affirmative_reply()` (explicit phrase-list matcher, `fullmatch` not `search` so a qualified reply like "yes but also X" does not count as authorization) and `describe_pending_action()` (deterministic, no extra LLM call, sourced from `capability_registry.CAPABILITY_POLICY`'s existing per-tool `permission_boundary` text).
- **Tier 1 (`main.py`, the `routed.tool_calls` loop)**: before executing any model-selected tool call, `classify_effect(name, args)` is consulted. A `requires_approval` call is no longer executed -- it's stored as `self._pending_tool_confirmation` (frozen tool name, frozen arguments, a 120s expiry) and the turn replies with a description instead. The next turn's `_handle_pending_tool_confirmation` (wired as the very first check in `_handle_router_text_command`) resolves it: a real affirmative reply executes using the *exact* arguments captured at ask-time (never a freshly model-regenerated call); anything else discards the pending action and routes normally. One-shot -- the pending record is always cleared, whether it matched or not, so a stale confirmation can never be replayed by a later, unrelated message. `interrupt()` also clears it, matching the existing "user changed their mind" handling for plan runs.
- **Tier 2 (`dev_agent` redirect)**: `dev_agent` never reaches the confirm-then-execute path at all -- every real call is a genuine multi-step coding task, not a single action, so it's redirected to `decompose_goal_to_canvas` + `propose_canvas_plan` (the same pipeline already live-verified end to end in the expanded validation pass) instead of a one-word yes/no.
- **Tier 3 (defensive backstop)**: `_execute_tool` gained a `pre_approved` parameter; a fail-closed `classify_effect` check runs unless `pre_approved=True`. `_execute_router_tool_call` (the shared helper used by the gated loop, the confirmed-resume path, and ~11 deterministic phrase-triggered workflow bootstraps) always passes `pre_approved=True`, since every one of its callers is already authorized by construction. The one caller that does *not* go through that helper -- `_receive_audio`'s direct `_execute_tool` call on the Gemini Live path -- defaults to `pre_approved=False` and now fails closed. That path is currently dead code (`_gemini_live_enabled()` is hardcoded `and False`), so this is pure insurance against a future revert silently reopening the exact gap this session found.

## Two real bugs caught during implementation, before either shipped

1. **Design-review catch**: my first draft threaded `pre_approved` through `_execute_router_tool_call`'s own signature, defaulting `False`. That would have made the Tier 3 backstop incorrectly block the ~11 deterministic bootstrap calls (`_handle_todo_template_workflow`'s `create_todo_template`, `_handle_start_plan_workflow`'s `start_plan`, etc.) that call this helper directly -- exactly the failure mode the plan's own design review had already warned against for Tier 1, just one layer deeper. Caught by re-reading my own diff against the plan before writing tests; fixed by hardcoding `pre_approved=True` inside the shared helper instead, since every real caller of it is already authorized.
2. **Test-suite catch**: the full suite (880 tests) surfaced 3 pre-existing failures after the first implementation pass, all `AttributeError: 'JarvisLive' object has no attribute '_pending_tool_confirmation'`. Root cause: `_handle_pending_tool_confirmation` read `self._pending_tool_confirmation` directly instead of defensively, unlike every other piece of turn state in this exact class (`_router_turn_mutex`, `_is_stale_router_turn` both use `getattr(self, ..., default)`). Pre-existing tests construct `JarvisLive` via `__new__` without full `__init__`, so they never had this attribute. Fixed in my code (`getattr(self, "_pending_tool_confirmation", None)`), not by patching the pre-existing tests -- they were right to not know about a feature that didn't exist when they were written.

## One pre-existing test legitimately updated, not just patched around

`tests/test_router_mode.py::RouterModeAntiFabricationIntegrationTests::test_a_real_pytest_pass_receipt_does_not_get_flagged` asserted that `code_helper`'s `run` operation executes in a single turn. That premise is now wrong on purpose -- `code_helper` is one of the 11 tools this whole fix targets (`risk_level: high`, `requires_confirmation: True`, and `run` isn't a read-only operation). Rewrote the test to simulate the real two-turn flow (ask, pauses; "yes", executes with frozen args) while preserving its actual original intent: a real, evidenced tool result still doesn't get flagged by the anti-fabrication check. Both assertions the test cares about still hold.

## Test suite

- New: `tests/test_chat_confirmation.py` (7 tests -- matcher accepts clean affirmatives, rejects qualified/negative/empty replies, case-insensitive; describer includes tool name and permission boundary).
- New: `tests/test_chat_tool_gate.py` (7 tests -- a `requires_approval` call pauses and doesn't execute; an affirmative reply executes with the exact frozen arguments; a non-affirmative reply discards the pending action and routes normally; an expired pending confirmation isn't honored; `dev_agent` never reaches direct execution, only the canvas-decompose path; two of the deterministic bootstrap calls (`jarvis_memory.create_todo_template`, `plan_workflow.start_plan`) still execute directly, unaffected -- this is the regression check that would have caught bug #1 above if the design-review hadn't already).
- Updated: `tests/test_router_mode.py` (1 test rewritten as above).
- Full suite: **880 passed**, 0 failed, after both fixes.

## Live evidence against the real running system

Same methodology as the rest of this session's live testing -- real `_handle_router_text_command`, real LM Studio, real tool dispatch, only `ui`/`speak` mocked.

| # | Scenario | Result |
|---|---|---|
| 1 | Exact original C1 prompt, retry 1 ("plan out how you'd approach adding a caching layer... including tests") | 845s. Model answered narratively with no tool call at all this time (routing is genuinely non-deterministic across runs, consistent with this session's other findings) -- no execution happened, safe by default either way. |
| 2 | Same prompt, retry 2 | 377s. Model selected `code_helper` (not `dev_agent`) with an `explain` action that included `output_path: "docs/caching_plan.md"`. `classify_effect` correctly flagged it `requires_approval: True` (code_helper has no read-only operations carved out yet, an intentional scope decision -- see the plan). **Paused correctly**, captured the exact arguments including the file it would have written, executed nothing. |
| 3 | Delete a real scratch file -- turn 1 (ask) | 275s. `file_controller`/`delete` correctly classified destructive, paused. File verified still present on disk after this turn. |
| 4 | Same, turn 2 ("yes") | 63s. Resumed with the *exact* frozen path from turn 1, called `file_controller` for real (confirmed via `[JARVIS] TOOL file_controller {...}` log). A separate, pre-existing safety layer inside `file_controller` itself (a write/delete root restriction) blocked the actual deletion ("Access denied") -- the system reported this honestly ("Confirmed. Attempt... was blocked... No further action taken.") rather than claiming success. File verified still present afterward, for the correct reason. |

The specific `dev_agent`-to-Canvas redirect branch wasn't exercised live in either retry, since the model didn't happen to select `dev_agent` either time -- this mirrors this session's broader, already-documented finding that local-model tool selection is not fully deterministic across identical prompts. That branch is proven deterministically instead by the mocked `test_dev_agent_never_executes_directly_from_chat` test, which is not subject to model-routing luck: it asserts on the actual Python branch (`if call.name == "dev_agent":`), which fires unconditionally in code whenever the model does select it. Across both live attempts and the file_controller round-trip, the one property that matters most -- **no unconfirmed write happened** -- held every time.

## What this does and doesn't prove

Proven, live and by direct code reading: the confirm-then-resume mechanism works correctly end to end for at least two different gapped tools (`code_helper`, `file_controller`), frozen arguments are honored exactly, and the specific incident that started this (`dev_agent` writing real files from a single "plan this out" turn) cannot recur through this code path -- `dev_agent` is now unreachable from chat except through the canvas-redirect branch, which never calls it directly either. Not separately live-tested: Tier 3's Gemini Live backstop, since that path is current dead code with no way to trigger it live -- covered by direct code review and its default-closed design instead.

## Related
[[Validation/2026-07-25-expanded-live-validation|Expanded Live Validation (source of the headline finding)]]
