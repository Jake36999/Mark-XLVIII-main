---
title: "Canvas Node Live Test + Mode 1 Hardening"
type: "report"
status: "active"
created: "2026-07-24"
updated: "2026-07-24T12:55:47Z"
tags: ["validation", "canvas-plan", "capability-test", "hardening"]
index_state: "indexed_local"
content_hash: "ee3cf168379319767f8273033833635b9c178ed401ce4835ec3cae710ee2beb4"
---

> [!info] Scope
> Two things in one pass: (1) root-causing the issue found in [[user led test round]] (your manual run of prompt V1 through the real JARVIS UI), and (2) the 6 previously-proposed live tests of `implementation`/`verification` canvas nodes. Your live observations while I ran those are in [[Claud led testing]] and are addressed inline below.

## Headline finding: JARVIS can claim a test passed when it never ran

Your manual test asked JARVIS (via chat/voice) to run `tests/test_tts_read_trigger.py` and confirm it passes. It replied:

> "The vault-watcher's TTS read-trigger test suite has been checked for status. Result: ✅ Operation status confirmed as successful (`ok: true`)... This confirms the feature is ready for completion per the defined confirmation gate. Proceeding with feature closure."

**No test ever ran.** Tracing it: your prompt contains the word "test" four times, which matches a keyword-routing rule in `main.py` (`_router_tool_names_for_text`) that offers the model three tools: `code_helper`, `dev_agent`, `project_operator`. The model picked `project_operator`, called it with `project_id="quantule_mapper"` — an unrelated registered project (a physics side-project of yours, nothing to do with this codebase) — and got back a generic `{"ok": true, "projects": [...]}` status blob. The final-response step then fabricated "test suite currently active and operational," "confirmation gate," and "proceeding with feature closure" — none of which exist anywhere in that JSON. This happened *despite* an existing grounding instruction telling the model to only mention confirmation gates "when actually present in the tool results."

The correct tool was sitting right there in the same candidate set: `code_helper` with `action=run` executes a file directly (`python tests/test_tts_read_trigger.py`), which — since that file ends in `unittest.main()` — would have actually run the tests and returned real pass/fail output. The model just chose the wrong one of three options, then talked past the gap with total confidence.

**Fixed (cheap, same-turn):**
- [main.py](../../Mark-XLVIII-main/main.py)'s `project_operator` tool description now states outright that it does not run or verify tests, and steers away from using it as a substitute.
- `code_helper`'s description now explicitly says `action=run` is the way to execute a specific test file and get real pass/fail output.
- `_build_tool_summary_prompt` (the step that writes JARVIS's final reply after a tool call) now explicitly lists which tools were actually called, and explicitly forbids claiming a test/build passed or a confirmation gate was satisfied unless the tool result contains that specific outcome.
- 10 new regression tests covering all of the above (`tests/test_router_mode.py`).

**Not fixed, flagged for later:** there is still no capability reachable from chat that can run an arbitrary named test file end-to-end with a guarantee of being chosen correctly — the fix above reduces the odds of the wrong tool being picked and stops the model from over-claiming afterward, but a small/unreliable local model can still misroute. A dedicated, unambiguous "run this test" capability (or tightening `_router_tool_names_for_text`'s routing itself) would be the durable fix; out of scope for a cheap pass.

## Your other observations from the manual test

| # | Finding | What I did |
|---|---|---|
| 1 | Mic-not-plugged-in spammed the activity log forever (two lines every retry cycle) | **Fixed.** Removed the duplicate inner log line, and once backoff settles at its 15s ceiling with an unchanged error, it now logs every 20th cycle instead of every cycle. 2 new tests, [main.py](../../Mark-XLVIII-main/main.py). |
| 4 | Sys-monitor tab appears to freeze while replying | **Partially hardened, not fully diagnosed.** Found that `_SysMetrics._update()` computed CPU/MEM/NET/GPU/temp all together and only published them as one batch at the end — so a slow/stalled GPU or temperature sensor call (pynvml/wmi, plausible under heavy GPU load from local inference) would freeze *all five* bars, not just GPU/TMP. Reordered so CPU/MEM/NET publish immediately, independent of the GPU/temp probes. 2 new tests. This is a genuine improvement regardless of root cause, but I did not fully prove the sensor-hang theory — worth re-checking if the freeze still happens after this fix. |
| 2, 3, 7 | Multiple models loaded simultaneously + perf hit; no LM Studio progress visibility; high RAM | **Not fixed — larger scope.** Your own real-time observation in [[Claud led testing]] corroborates this: LM Studio showed 3 models resident at once (qwen3-4b, Orpheus TTS, nomic-embed), each configured for 4 parallel slots. This lines up with the VRAM-aware admission gap already on record from the earlier session assessment — worth prioritizing given it's now been observed twice. |
| 5, 6 | Trace doesn't show which models ran; should record response time | Noted, not built — both are real observability gaps worth a future pass, not cheap same-turn fixes. |

## Answering your question from [[Claud led testing]]

> "is claud using the embedding to work through the prompts instead of using the system to task the local models?"

No — during the propose/approve phase you watched with no model activity, that's correct and expected: `propose_canvas_plan` and `evaluate_canvas_approval` are 100% deterministic Python (compiling the canvas, hashing it, writing the approval note, checking a checkbox) — zero model calls either way. I was calling those functions directly as a developer would in a REPL, not going through JARVIS's own chat/voice loop — the running JARVIS app's NLU/routing was **not involved at all** in the 6 canvas-node tests below; I was testing the canvas engine's own compiler/dispatch machinery directly, the same way the T5/T6 canvas work was tested earlier this session. The `deepseek-r1-0528-qwen3-8b` load you saw came later, during the implementation-node test's independent review step (a real model call) — see below.

Your last note — "no reasoning model used... a reasoning model should be used to both plan and assess the given plan" — is a good point I want to flag rather than build: today, nothing model-based ever looks at a *compiled* canvas plan before it's shown to you for approval. Given what the implementation-node test found below (the approval preview shows misleading information), a model-based pre-approval sanity pass could plausibly have flagged "this implementation step has no project target, it won't do what the node says" *before* you ever had to approve it. Worth adding to the path-forward list rather than something I built today.

## The 6 canvas-node tests

Method used for all 6: hand-built a `.canvas` file, `propose_canvas_plan` → checked the Approve box → `evaluate_canvas_approval` → `execute_canvas_plan`, calling `actions/canvas_plan.py` directly (not through chat). Verification and implementation were each grouped into one 3-node canvas so the compiled `inputs` could be compared directly instead of guessed at.

### Verification — V1/V2/V3

**Prompt given:** V1 asked to run one specific test file; V2 explicitly asked for *only* one file, not the whole suite; V3 explicitly asked for the whole suite (the control case).
**Method of input:** Compiled all three into one canvas via `compile_canvas` first (no execution) to compare their dispatched `inputs`, then approved and executed the whole canvas for real.
**Result:** All three compiled to an *identical* dispatched step — `{"canvas_role": "verification", "canvas_node_id": ...}`, nothing else. None of the wording ("just that one file," "the whole suite") reached the actual command. All three then really ran `pytest -q` with no args (the entire ~680-test suite) concurrently (same-layer canvas nodes dispatch in true parallel, not sequentially, which I hadn't expected). Running three full suites at once starved each other for CPU: all three hit the fixed 300s command timeout, got one automatic repair retry, timed out again, and the whole run ended `BLOCKED`/`REJECT_REPLAN` — a real test-suite failure of my own making (three-at-once), not a defect in a single verification node.
**Thoughts:** Confirms the hypothesis completely and adds a new one: a canvas with more than one or two verification/test nodes at the same layer can starve itself into false failures purely from concurrency, since the timeout is fixed and non-scoped.
**Strengths:** T2 status write-back correctly colored and annotated all three nodes even under a hard block; the human's authored text was untouched; the system correctly reported BLOCKED rather than a false pass.
**Weaknesses:** A verification node's instruction text is cosmetic — it has no way to scope what actually runs. Combined with a fixed timeout and true parallel dispatch, this is a real correctness gap for anyone drawing more than one test node in a canvas.

### Implementation — I1/I2/I3

**Prompt given:** three trivial, reversible file-creation/append requests under a throwaway `scratch/` folder.
**Method of input:** Same pattern — compiled all three first to compare `inputs`, then approved and executed for real.
**Result:** All three compiled to `{"canvas_role": "implementation", "canvas_node_id": ..., "operation": "delegate_openclaw"}` — no `project_id`, no `intent`/`task` from the node's text, regardless of wording. At execution, `project_operator()` treated the missing `project_id` as `operation=list` and returned the plain registered-project list (`ok: true`) — **OpenClaw was never invoked**. No file was written; `scratch/` was never created (confirmed on disk). All three then hit `reviewer_unavailable: RuntimeError` on the independent-review call and ended `ESCALATED` rather than falsely `ACCEPTED` — the same transient reviewer `RuntimeError` flagged during the earlier canvas review live test, now recurring in a different role, which raises my confidence it's a real, recurring reliability gap worth investigating rather than a one-off.
**Thoughts:** This is the more serious of the two findings — an implementation node can silently no-op and still reach a human-reviewable state (`ESCALATE`, not falsely `ACCEPTED`, so the safety gate did its job), but the approval preview a human reads *before* approving shows the full authored instruction next to "Resource: openclaw, Confirm: yes" as if it will be carried out verbatim. What you'd approve and what actually runs are not the same thing.
**Strengths:** No destructive or wrong-target action occurred — the failure mode is a safe no-op, not a wrong write. T2 write-back and the review gate both worked correctly on top of that no-op.
**Weaknesses:** An implementation node cannot function today regardless of what's drawn on the canvas. Fixing this needs a real design decision (how does a canvas author specify which registered project an implementation node targets?) — I did not default this to any project myself, since silently assuming a target (e.g. this very codebase) would change the blast radius from "safe no-op" to "OpenClaw can write to a live repo on approval," which needs its own explicit sign-off, not a quick patch. Documented the gap directly in [`actions/canvas_plan.py`](../../Mark-XLVIII-main/actions/canvas_plan.py)'s `_ROLE_SPECS["implementation"]` so this doesn't need rediscovering.

## Test suite

693 passed (was 686 before this session's changes), zero regressions, across two full runs.

## Artifacts

Test canvases and their approval/run records are left in place under `Canvases/live-tests/` and `Plans/canvas-approval-live_test_*` as a record, same as the earlier capability-test round.
