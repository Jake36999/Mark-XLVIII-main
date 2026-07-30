---
id: "jarvis-20260730T173753Z-a67d11b5"
title: "System Assessment: Where MARK XLVIII Is Strong, and Where It Is Not"
type: "report"
status: "active"
created: "2026-07-30T17:37:53Z"
updated: "2026-07-30T17:37:53Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["assessment", "architecture", "test-coverage", "technical-debt", "tier-long-term", "tier/long-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.85
valid_from: "2026-07-30T17:37:53Z"
review_after: ""
source_version: 1
content_hash: "71fe583c0ce039f9522b4f88dc95d0f29a03b62c279f517a0d1c22305dd87741"
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
lifecycle: "long_term"
sync_error: ""
---

# System Assessment: Where MARK XLVIII Is Strong, and Where It Is Not

> [!abstract] The finding in one line
> The defects found this cycle are not seven unrelated bugs. They are one failure mode -- **the system reports success it has never verified** -- and only the instances have been fixed, not the cause.

## 1. The dominant failure mode

Seven separate defects this cycle, all the same shape:

| Where | What it claimed | What was true |
| --- | --- | --- |
| Vision injection (`main.py`) | "the actual image arrives in the next message" | It never arrived. The reply was generated from no visual input. |
| `screen_process()` (`screen_processor.py`) | Returned `True` | Bytes were queued to a dead session; nothing was processed |
| MCP `cancel()` | Returned `True` | `Future.cancel()` fails on a running task; it kept going |
| `research_state` | Hardcoded `"complete"` | Search may have failed entirely |
| Orpheus baseline | Configuration honoured | `_resolved_config` silently appended two models |
| Canvas implementation node | Plan compiled successfully | Silent no-op -- no project target |
| `_resolved_config` | Reported the declared baseline | Promoted models the configuration never named |

These share no subsystem. They share **epistemics**: each returns a success signal when work is *dispatched* rather than when it is *done*.

On a cloud stack that gap is milliseconds and invisible. On a host where a model load takes ninety seconds, that gap is where the truth lives. This is the architectural consequence of going local-first that was never accounted for.

> [!danger] The cause is still open
> Every instance above was repaired individually. There is still **no convention** that a return value must describe a completed effect rather than an accepted request. Until there is, this will keep recurring, and it will keep being invisible -- none of these were caught by tests, by review, or by the type system. Two were caught by a user noticing the answer was wrong.

## 2. Strengths

### Adversarial posture is genuinely strong

`evidence_block` nonce fencing, `_TOOL_AUTHORIZATION_BASES` with a *required* keyword so a new call site cannot silently inherit a bypass, hash-frozen approval envelopes, trusted-channel-only route pinning, and 18 dedicated injection-corpus tests.

The proof is behavioural: when the vision pipeline was written, the screen transcript was fenced before any model reasoned over it -- not because it was remembered, but because the pattern was already the obvious thing to reach for. That is architecture doing its job.

### The decision layer is well tested

| Module | Lines | Tests | Lines per test |
| --- | --- | --- | --- |
| `actions/canvas_plan.py` | 2,464 | 160 | 15 |
| `core/model_router.py` | 2,125 | 70 | 30 |
| `actions/project_learning.py` | 1,508 | 40 | 38 |
| `actions/jarvis_memory.py` | 4,518 | 86 | 53 |

The planning, routing and approval spine is the most exercised code in the repository, and it is where a mistake propagates furthest.

### The instrumentation built this cycle is the real asset

`process_trace`, `scripts/config_audit.py`, provenance recording, and `char_budget_for()` all convert *invisible* failures into *visible* ones -- precisely the class this system is worst at. The configuration audit alone would have caught two of the seven defects in section 1.

### Failure reporting is becoming honest

MCP cancellation now returns `cancellation_requested` rather than a bare `True`. `research_state` returns `partial`, `offline`, or `failed`. Vision says "no local vision model could read it" instead of describing an image it never saw. This is a measurable behavioural shift and it should continue.

## 3. Weaknesses

### 3.1 Verification asymmetry -- the sharpest structural problem

**7 of 12 high-risk tools have no test importing their module**: `browser_control`, `computer_control`, `computer_settings`, `desktop_control`, `file_controller`, `screen_process`, `shutdown_jarvis`.

The *gates* around them are tested. `test_chat_tool_gate` mocks `main.file_controller` and proves the confirmation pause works and that frozen arguments are used on resume. So:

- Well defended against a dangerous tool being called **wrongly**.
- Undefended against a dangerous tool **behaving wrongly once approved**.

Deletion and desktop control are in that set. This asymmetry should be closed deliberately rather than left as an accident of what was interesting to test.

> [!success] Closed on 2026-07-30 — `tests/test_high_risk_tool_contracts.py`
> 28 contract tests, asking three things per tool: does it do what it says, does it refuse what it should refuse, and when it fails does it say so.
>
> The guards that turned out to exist and are now pinned: `_SAFE_ROOTS` confines file operations to the home directory and resolves before comparing, so `..` cannot escape; `delete_file` refuses the seven protected user directories; deletion is **send2trash only** and refuses outright rather than falling back to a permanent unlink; `_safe_screenshot_path` silently redirects an out-of-bounds capture instead of writing where it was told.
>
> Verified by mutation, not assumed: each guard was removed in turn and the test naming it was required to fail. All ten caught, including a mutation that replaced trash with a real `unlink()`.
>
> Two tests now guard the *category* rather than individual tools — a newly registered high-risk tool with no contract test, or one that stops requiring confirmation, fails the suite.

> [!danger] `shutdown_jarvis` is tested at its gate only, deliberately
> Its handler calls `os._exit(0)`. A test that executed it would terminate the runner mid-suite, so the contract tests assert its classification, its permission boundary, and that a deterministic shortcut cannot reach it — never the effect itself. Any future work here must keep that boundary.

### 3.2 Test density is inverted against risk

`actions/dual_orchestrator.py` is the engine that executes approved work against real state: **1,762 lines, 19 tests, one per 93 lines**. `actions/canvas_plan.py`, which produces *proposals a human then reviews*, has 160.

The artefact that gets human review is six times better tested than the executor that does not.

> [!success] Addressed on 2026-07-30 — `tests/test_dual_orchestrator_guards.py`
> 35 new tests, density now **one per 33 lines**. Aimed at the paths that stop a run executing something the human did not approve, or executing it twice — none of which had any coverage:
>
> | Area | What is now pinned |
> | --- | --- |
> | Envelope integrity | Every signed field; a forged, empty, or missing signature; an envelope signed by another vault; adding an action that was never approved |
> | On-disk drift | Editing `workflow.yaml` or `work-items.json` after approval halts the run before any work |
> | Crash recovery | A live lease means another worker owns it; an expired lease on retry-safe work is reclaimed; **non-retry-safe work is never silently retried**; an item missing from the manifest pauses the run |
> | Cancellation | Pending work never starts, items are marked, the reason is recorded |
> | Compensation | Runs on reject/escalate with real side effects; receives the original inputs and defects; a failing undo is recorded, not swallowed; does *not* run for `side_effects: none` or an accepted step |
> | Bindings | A missing source resolves to `None` rather than a stray value |
> | Resource classes | Model and OpenClaw slots; slot acquisition aborts on cancel |
>
> Verified by mutation: 21 checks, each removing a guard and requiring the naming test to fail. All caught.

> [!note] Two corrections the work produced
> The compensation tests were wrong on first write — I assumed a dispatch exception triggers compensation. It does not: compensation is gated on a **review verdict** of `REJECT_REPLAN`/`ESCALATE` *and* declared `side_effects` other than `none`. A step that merely raised has not necessarily changed anything. The tests now encode that gate rather than the assumption.
>
> Separately, `with sqlite3.connect(...)` commits but does **not** close. The open handle made temp-directory cleanup fail on Windows with a misleading `NotADirectoryError` on the `.sqlite` file. Test helpers now use `contextlib.closing`.

### 3.3 Dead scaffolding no tool can detect

Roughly **20 live references to `self.session`** remain in `main.py`, all permanently unreachable because `_gemini_live_enabled()` ends in `return bool(wants_gemini and False)`.

This already cost one entire capability for the whole local-first era. Nothing flags it -- not the compiler, not the type checker, not 1,041 tests. Every remaining reference is a place where a future feature can be built, appear wired, and silently do nothing.

### 3.4 Keyword routing remains fragile

**57 literal keywords** perform model-class selection. The documented history is poor: `"cited report"` inside anti-fabrication boilerplate routed *every tool summary in the system* into a 14B research chain; `"repo"` matched `weather_report`; `"ram"` matched `program` and `diagram`; `"read"` matched `already` and `thread`.

Route pinning fixed the worst path. The mechanism is unchanged, and its failures are silent and expensive.

### 3.5 Concentration

`actions/jarvis_memory.py` is 4,518 lines; `main.py` is 4,271. The top five modules are **32%** of non-test source. `main.py` holds the turn lifecycle, tool dispatch, deterministic workflow bootstraps, and dead Gemini remnants in one file -- which is a large part of why the vision defect could hide in it.

### 3.6 Local model quality is the actual ceiling

Measured, not asserted:

- An identical prompt produced **three different answers across three runs**.
- `unlimited-ocr` produced 4,766 usable characters on one screen and **164** on another.
- A screen question costs **76-145 seconds**.

No amount of plumbing improves this. It bounds what the product can be, and roadmap decisions should treat it as a constraint rather than something to engineer around.

## 4. Ranked next actions

1. ~~**Delete the Gemini scaffolding.**~~ **Done** (`dc0dd4e`) — 758 lines. Removal surfaced two costs beyond the vision loss: every dashboard command polled 8 seconds for a session that could never appear, and every tool call depended on `google-genai` because `_execute_tool` returned a vendor type while the import set `types = None` on failure.
2. ~~**Establish that return values describe completed effects.**~~ **Done** (`da93ab8`) — `core/effect_outcome.py` plus 25 mutation-verified regression tests.
3. ~~**Contract tests for the seven untested high-risk tools.**~~ **Done** — 28 tests, ten mutations verified. See section 3.1.
4. ~~**Raise `dual_orchestrator` test density.**~~ **Done** — 19 tests to 54, one per 93 lines to one per 33, 21 mutations verified. See section 3.2.

New work this cycle surfaced, not yet done:

5. **Audit the Gemini *generative* surface.** Eight action modules (`code_helper`, `computer_control`, `computer_settings`, `desktop`, `file_processor`, `flight_finder`, `web_search`, `youtube_video`) each define their own `_get_api_key()` and construct a `genai.Client`. That is separate from Live and was deliberately not touched. Whether any of those paths are reachable is unknown — and "looks wired, is not" is exactly the defect this cycle kept finding.
6. **Rewire or retire `SystemMonitor` and `ProactiveEngine`.** Both were started only as Live background tasks and have been inert since. Each produces a prompt string, so wiring either to router mode is small.

## 5. Caveat on the numbers

"Never imported by a test" is a **coverage proxy, not line coverage**. A module can be imported and barely exercised. The 18% figure (8,314 of 46,878 first-party lines, 30 of 79 modules) is a *floor* on the gap, not a measurement of it. A real coverage run would be a cheap and worthwhile follow-up.

## Related Notes

- [[2026-07-30-local-vision-wiring-and-model-measurements]]
- [[09 Implementation Log and Known Boundaries]]
- [[01 Runtime Architecture and Turn Lifecycle]]
- [[02 Capability Registry MCP and Safety]]
