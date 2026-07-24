---
id: "jarvis-20260724T160447Z-1f7a8f2d"
title: "Live Prompt Testing - 16 Prompts Across Topics and Workflows"
type: "report"
status: "active"
created: "2026-07-24T16:04:47Z"
updated: "2026-07-24T16:06:00Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "capability-test", "lmstudio-performance", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T16:04:47Z"
review_after: ""
source_version: 1
content_hash: "460bacea64c1b2de2e2d57428b7b4c24c1ee5d3470a9c9d9376f65beecb5c12e"
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
> A 16-prompt live-testing pass across distinct topics, goals, and workflows, run while you were away, per your request to log behaviour, accuracy, and LM Studio performance. Every prompt ran through the real `_handle_router_text_command` path (real `call_with_tools`/`call_text`, real tool execution, real LM Studio) — only `ui`/`speak` were mocked to capture output, the same "developer console" methodology used for this session's earlier canvas live tests. Full per-turn data (process-event timelines, exact replies, model provenance) is preserved in the harness script and results JSON referenced at the bottom.

## Why this ran sequentially, not delegated to parallel subagents

You asked me to delegate as much as I could without reducing accuracy. I considered fanning prompts out to parallel subagents, then didn't: this session already proved, concretely, that concurrent calls against this single LM Studio instance cause resource contention that corrupts results (three concurrent verification-node test runs starved each other into a false `BLOCKED`/timeout earlier today). Running 16 prompts in parallel against the same one-GPU-slot backend would very likely have done the same thing — and silently, since a contention-induced timeout looks identical to a real model failure unless you're watching for it. So every prompt ran one at a time, in the foreground, exactly as a single real user's session would experience it. That's the accuracy-preserving choice; parallelizing was the one on the table that would have cut time at the cost of trustworthy data.

## Headline finding: local-model timeout cascades, not model quality, dominate wall-clock time

Six of the sixteen turns (P3, P5, P6, P7, P11, P13) took between 160 and 1109 seconds. In every single one, the *actual* model that answered took seconds to tens of seconds — the rest of the wall-clock was spent retrying candidate models that timed out entirely, 2–4 times in a row each, before the fallback chain reached one that worked. Reconstructed from the process-event timeline (now populated with real detail thanks to WS2's receipts):

| Turn | Total time | What actually happened |
|---|---|---|
| P3 (system status) | **1109 s** | `qwen/qwen3.5-9b` timed out 3x → `deepseek-r1-0528-qwen3-8b` timed out 2x → `qwen/qwen3.5-9b` timed out **4 more times** → `google/gemma-4-e4b` finally answered in ~140s |
| P5 (memory save) | **780 s** | `deepseek-r1-0528-qwen3-8b` timed out 2x → `mistralai/mistral-7b-instruct-v0.3` timed out 2x → `google/gemma-4-e4b` answered in ~6s |
| P6 (memory recall) | 354 s | `deepseek-r1-0528-qwen3-8b` timed out 3x → `qwen/qwen3-4b-2507` answered in ~20s |
| P7 (project status) | 286 s | `mistralai/mistral-7b-instruct-v0.3` timed out 3x → `google/gemma-4-e4b` answered in ~9s |
| P11 (summarize note) | 285 s | `deepseek-r1-0528-qwen3-8b` timed out 4x → `google/gemma-4-e4b` answered in ~21s |
| P13 (research) | 312 s | `mistralai/mistral-7b-instruct-v0.3` timed out 4x → `google/gemma-4-e4b` answered in ~20s |

In the worst case (P3), roughly **90% of an 18-minute wait** was pure timeout-retry overhead for a question that a working model answered in under 2.5 minutes once it got the chance. The system's own safety net (health cooldown + fallback chain) *worked correctly* — nothing hung forever, nothing crashed, every turn eventually got a real answer — but the user-experienced latency on these turns is severe, and it's not a "the model is slow at reasoning" problem, it's a "several configured candidate models are frequently not responding at all" problem. This is the sharpest, most concretely-quantified version yet of the "local-model reliability is the recurring bottleneck" theme flagged qualitatively several times earlier this session — worth prioritizing over most of the accuracy findings below, since it's a pure tax on every slow turn regardless of what's actually being asked.

**Worth checking when you're back:** whether `deepseek-r1-0528-qwen3-8b`, `mistralai/mistral-7b-instruct-v0.3`, and `qwen/qwen3.5-9b` are consistently slow/unresponsive under whatever load LM Studio was under during this run, or whether this is specific to today's session. If it's persistent, the existing VRAM-admission and health-probe gaps already on record (from the earlier session assessment) are directly implicated.

## Other findings, roughly by severity

### 1. A malformed JSON blob leaked directly into a user-facing reply (P3)
After the 1109-second ordeal above, the actual final answer to "what's your CPU/memory/GPU usage" was:
> `{"tool_calls":[{"name":"system_status","arguments":{""}],"text":""}`

This is broken, unparseable JSON — the raw scaffolding some local models produce when asked to emit a tool call as text (`_parse_tool_json_response`'s prompting convention, used when a model doesn't support real structured tool-calling) leaked through unparsed and became the entire reply. Nothing downstream caught it or asked the model to retry. This is the single worst quality result in the whole run: a user would see literal garbage after an 18-minute wait. Worth a dedicated look — likely needs a guard that detects an unparsed/malformed tool-call-shaped string and either retries once or falls back to a plain apology rather than surfacing it verbatim.

### 2. Route misclassification via system-prompt contamination ("vision" mislabeling)
Every `worker`-role call in this run — weather, memory-save, memory-recall, project-status, canvas-check, summarize-roadmap, both research prompts — was tagged `route: "vision"` in its telemetry, despite none of them being remotely vision-related. Root cause, confirmed directly: `core/model_router._route_from_context` checks the *system prompt* text (not just the user's words) for routing keywords, and the standing system prompt (`core/prompt.txt`) contains a capability line — `"Vision (screen_process): ... wait for the image result."` — that always matches the vision-keyword check. Since that system prompt is included on effectively every call, "vision" wins the classification almost every time, before code/research/reasoning/main ever get a look-in.

This happens to be mostly harmless for the `worker` role specifically, because `resolve settings for that role always tries the configured `worker_model` first regardless of route — so the "wrong" classification doesn't currently pick the wrong model. But it does two real things: it corrupts the `route` field in every performance/health record this run produced (I had to reconstruct the real picture from the event timeline rather than trust the labelled route), and for the `planner` role, the candidate-list logic *does* branch on route (`if role == "planner" and route == "main"`), so a misclassified route there could plausibly skip the correctly-configured planner-model override. Cheap, well-scoped fix candidate: exclude the system prompt from the vision/code/research keyword scan, or gate it behind an explicit `[jarvis-route:...]` directive the way the "trusted route" override already works.

### 3. A keyword-substring collision misrouted a Mode 1 plan (confirmed, exact mechanism found)
P12 asked for "a plan to add unit tests for the **weather_report** tool." Mode 1's `_steps_from_prompt` returned the "delegate to OpenClaw for a registered *project*" template — the wrong one for what was actually a small, self-contained testing task. Traced it directly: `_steps_from_prompt`'s code/project keyword list includes `"repo"`, and its substring check is naive (`"repo" in lowered`) — **`"repo"` is a literal substring of `"weather_repo`**rt`"**. This is a small, funny, completely real bug: an unrelated tool name accidentally contains a routing keyword. It's exactly the kind of failure mode the roadmap's WS4 (reasoning-backed planning) is meant to replace; this is now a concrete, reproducible example to keep for that work, or fixable cheaply today with a word-boundary-aware match instead of bare substring containment.

Aside from the misrouted template, the plan document itself was solid: it genuinely pulled in 5 real local-vault context hits and 5 real cited web sources on Python unit testing (verified: the plan note and its sources are real, not fabricated) — so Mode 1 planning does more real research-grounding than "purely a keyword lookup with zero data" suggests; it's specifically the *step template* that's still fixed and keyword-driven.

### 4. Ad-hoc research replies dropped all citations
P13 and P14 (both routed through `web_search` → generic tool-summary synthesis, not the dedicated deep-research pipeline) each produced a well-organized, plausible answer — and neither included a single URL, despite `web_search` itself returning cited sources. For a research-flavored question asked directly in chat (as opposed to through a formal research-report workflow), the user currently has no way to verify or follow up on where any of it came from. Distinct from the already-known citation-gate looseness in the dedicated deep-research pipeline — this is the plain-chat path, which apparently drops citations from its evidence entirely rather than requiring or even permitting them in the final reply.

### 5. A retrieval false-negative under-answered a real question (safe failure mode, but incomplete)
P11 asked what the Planning Subsystem Roadmap note says about Workstream 4. It correctly found and named the note, then reported *"no specific information about Workstream 4 is available in the current note"* — which is false: Workstream 4 is fully described in that note (I wrote it earlier today). `jarvis_memory`'s retrieval surfaced only the note's top-level "Scope" callout, not the section actually asked about, and the model — correctly, per the anti-fabrication hardening — declined to invent an answer rather than guess. This is the *safe* failure mode (decline over fabricate), and a good sign the earlier hardening generalizes beyond the exact bug it was built for. But it's still a real accuracy gap: the information existed and wasn't found. Likely a retrieval-granularity issue (whole-note match without the ability to jump to a specific heading) rather than anything related to this session's other work.

### 6. A hallucinated tool name, handled gracefully
One greeting-prompt run had the model attempt to call a tool named `system_health`, which doesn't exist (`"Unknown tool: system_health"`). No crash — the error string was treated as an ordinary (failed) tool result and the model still produced a sensible reply around it — but it's a real instance of the model inventing a plausible-sounding capability that was never registered.

### 7. A capability question got narrated instead of answered
P2 ("what can you do?") produced: *"I can access that information through the capability_registry function... Let's get the list!"* — with **no tool actually called**. The model described its intended next step as if it were the answer, rather than the router actually dispatching `capability_registry` and returning the real manifest. The user asking a plain capability question would come away having learned nothing concrete.

### 8. A code-explanation request never reached for a file-reading tool
P8 asked what `_tool_receipt` in `main.py` does — a function that genuinely exists in this repo (added earlier today). No tool was called at all; the reply was "please paste the code or I can't help." Nothing routed this to `code_helper`'s explain action or a file-read, even though the function and file are real and locatable. Same shape of gap as the very first fabrication bug (the right capability existed, wasn't reached for) — worth noting since it's the second time in one session code-adjacent chat requests haven't found the tool that could actually answer them.

## Strengths — real wins worth keeping in mind

- **The anti-fabrication hardening held up on a live, unscripted repeat of the exact original bug.** P9 ("check if the canvas planning tests are currently passing") misrouted to `project_operator`/`quantule_mapper` again — the same pre-existing routing gap as before — but this time gave a fully honest, precisely-grounded answer: *"this does not confirm the passing of any canvas planning tests... to verify test status, a specific test-run operation must be initiated."* No fabrication, no confident wrong claim. That's the WS0 prompt-hardening from earlier today doing real work outside of a crafted test.
- **Memory save → recall round-tripped correctly and accurately.** P5 wrote a real note to `Jarvis_notes/Memories/preferences/testing-log-format.md` (verified on disk); P6 recalled it with the exact correct format, file path, and status. No fabrication, no drift.
- **Project-status and plan-creation answers were accurate and grounded.** P7's description of `mark_platform` matched the real registry entry verbatim. P12's plan file was real (verified on disk), with genuinely real cited sources.
- **Reasoning-only questions (no tool needed) were handled well.** P10 (cloud vs. local planner tradeoffs) and P16 (smart-home integration requirements, correctly citing this project's own confirmation-gate pattern) were coherent, accurate, well-structured answers with no hallucination.
- **Ambiguous prompts correctly triggered a clarifying question instead of a guess.** P4 (weather, no location given) and P15 (vague "improve error handling") both asked for specifics rather than assuming — good calibration.

## LM Studio performance summary

- Models observed handling turns: `qwen/qwen3-4b-2507` (worker default, fast and reliable — never itself timed out), `google/gemma-4-e4b` (the model that ultimately rescued every timeout-cascade turn), `deepseek-r1-0528-qwen3-8b` and `mistralai/mistral-7b-instruct-v0.3` (both frequently timed out as first-choice candidates), `qwen/qwen3.5-9b` (timed out repeatedly in the single worst case).
- No model ever failed to *eventually* answer — the fallback chain is working as designed, just slowly when it has to climb through multiple dead candidates.
- **CORRECTION (post-run, 2026-07-24 via `lms ps` / `lms status`): the timeouts ARE almost certainly cold-loading.** This bullet originally claimed "17 models stayed resident, so timeouts are not cold-loading" — that was wrong. The harness snapshotted the OpenAI-compat `/v1/models` endpoint, which lists *installed* models (always 17, stable), not *loaded* ones. `lms ps` shows only **2 models actually loaded** (`qwen/qwen3-4b-2507` + `orpeus_text_to_speech`, ~4.6 GB total), with the GTX 1080 65% empty (5.1 GB free). The large reasoning models were NOT resident — so every time the router reached for one, LM Studio had to cold-load an 8–9B GGUF on demand, and the cold-load time very likely exceeded the request timeout, which is exactly what produced the repeated-timeout cascade. The cross-vendor Vulkan runtime IS selected (`llama.cpp-win-x86_64-vulkan-avx2@2.27.0`), so pooling is available; whether each large model is actually *configured* to split across both cards is the open question the follow-up benchmark will answer.

## Full per-turn log

| # | Prompt (topic) | Tool(s) | Time | Verdict |
|---|---|---|---|---|
| P1 | Greeting | (hallucinated `system_health`) | 30s | OK reply, hallucinated tool name |
| P2 | "What can you do?" | none (narrated only) | 24s | Weak — described action, didn't take it |
| P3 | CPU/mem/GPU status | none | **1109s** | Timeout cascade + malformed JSON leaked to user |
| P4 | Weather, no location | `weather_report` | 102s | Correctly asked for location |
| P5 | Remember test-log format | `save_memory` | **780s** | Timeout cascade; result itself correct & verified |
| P6 | Recall test-log format | `jarvis_memory` | 354s | Timeout cascade; recall accurate & verified |
| P7 | mark_platform status | `project_operator` | 286s | Timeout cascade; answer accurate |
| P8 | Explain `_tool_receipt` | none | 66s | Should have reached for code_helper/file-read |
| P9 | Canvas tests passing? | `project_operator` (misrouted) | 161s | **Honest, well-grounded — hardening held** |
| P10 | Cloud vs local planner tradeoff | none | 106s | Strong, accurate reasoning |
| P11 | Summarize roadmap WS4 | `jarvis_memory` | 285s | Timeout cascade; false-negative retrieval, declined rather than fabricated |
| P12 | Plan: test weather_report | `plan_workflow` | 11s | Fast; real plan + sources; misrouted by a "repo"/"report" substring collision |
| P13 | Research: on-device inference | `web_search` | 312s | Timeout cascade; good content, no citations |
| P14 | Research: vector DBs | `web_search` | 180s | Good content, no citations |
| P15 | Vague: "improve error handling" | none | 52s | Good — asked for specifics |
| P16 | Vague: smart-home control | `capability_registry` | 78s | Good, accurate, cited real confirmation-gate design |

## Suggested priority if you want to act on any of this

1. **Investigate the timeout cascade** (deepseek-r1/mistral-7b/qwen3.5-9b repeatedly not responding) — biggest, most quantifiable latency cost by far.
2. **Guard against malformed tool-call JSON leaking into a reply** (P3) — worst single quality result.
3. **Fix the system-prompt vision-keyword contamination** in `_route_from_context` — cheap, contained, improves telemetry accuracy and planner-role routing correctness.
4. Everything else here is real but lower-severity — happy to go through any of it in more depth.

## Artifacts
- Harness script + raw JSON (all 16 full event timelines, replies, provenance): `Jarvis_notes/Validation/2026-07-24-live-prompt-testing-artifacts/` (copied here permanently, not left in session scratchpad).
- Verified-real artifacts from this run: `Jarvis_notes/Memories/preferences/testing-log-format.md`, `Jarvis_notes/Plans/2026-07-24-plan-add-unit-tests-for-the-weather-report-tool.md`.
