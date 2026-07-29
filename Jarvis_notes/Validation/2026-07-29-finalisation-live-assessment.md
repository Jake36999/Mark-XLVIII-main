---
id: "jarvis-20260729T204852Z-925c65a0"
title: "Finalisation Workflow: Live Demonstration and Assessment"
type: "report"
status: "active"
created: "2026-07-29T20:48:52Z"
updated: "2026-07-29T20:49:01Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "assessment", "model-economics", "file-pipeline", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-29T20:48:52Z"
review_after: ""
source_version: 1
content_hash: "aa16bc1fe8d2713f592b90e9036b4170c70171224a774769690a3fa2b6f5e23b"
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
> Live demonstration and assessment round for the autonomous finalisation workflow, run against the real system after Phases 1-3. Eleven turns through the real `_handle_router_text_command` with real LM Studio and real tool execution; only `ui`/`speak` mocked. Sequential by design. Every claim below is checked against real disk state or real tool output, never the model's own report.
>
> The metric added for this round is the one the owner actually complained about: **how many distinct models a single turn touches**.

## Headline result: model swapping is gone

Across **all eleven live turns**, exactly **one** model was ever loaded or used: `qwen/qwen3-4b-2507`, the always-warm baseline. **Zero evictions. Zero cold loads after the first.** No turn touched more than one model.

| | 2026-07-25 baseline | this round |
| --- | --- | --- |
| Distinct models in the reported capability question | 2 (qwen-4b + deepseek-r1-8b) | **0** |
| Max distinct models in any single turn | 5+ across the fallback chain | **1** |
| Model evictions observed | eviction before every spoken reply | **0** |
| Worst single turn | 1109 s (~90% timeout-retry overhead) | 197.8 s |
| Mean turn | several minutes, heavily skewed by cascades | 97.6 s |

The timeout cascades that dominated the previous round did not occur once. That is the expected consequence of three Phase 1 changes acting together: the route pin stopped every tool summary reaching for an 8-14B research model, the chain cap stopped long walks through cold candidates, and the TTL guard stopped TTS evicting a model seconds after it was used.

## The two reported symptoms, re-tested live

**"What tools or workflows do you have available"** — the exact prompt that burned a qwen-4b and a deepseek-8b. It now completes in **0.0 s with zero model calls**, answering from the deterministic manifest: 35 tools and 20 workflows, correctly named. Not "fewer models" -- no model at all.

**"Can you extract the methods from this pdf"** — previously answered with JARVIS's own backend orchestration methods. Tested end to end against a real PDF containing a genuine Methods section. The upload was remembered across the turn boundary, `file_processor` was the only tool offered, the path the model omitted was backfilled, and the reply contained **the actual paper's methods**: CSI collected from three Intel 5300 NICs at 5 GHz over 14 days, subjects walking a fixed 6-metre path, a Butterworth low-pass filter and PCA before classification. The wrong-source failure did not recur.

**"What did you just do"** — previously reached `capability_registry` (which answers what JARVIS *can* do, and is the same manifest that produced the PDF failure). It now reports real, phase-labelled operations through the new `process_trace` tool.

## Full results

| # | Scenario | Time | Models | Tools | Verdict |
| --- | --- | --- | --- | --- | --- |
| H1 | Capability question (reported symptom) | 0.0 s | **0** | capability_registry | **Correct**, zero model calls |
| H2 | PDF upload announcement | 129.8 s | 1 | — | Correct |
| H3 | "Extract the methods from this pdf" (reported symptom) | 136.1 s | 1 | file_processor | **Correct**, real paper content |
| H4 | "What did you just do" | 62.5 s | 1 | process_trace | Correct, phase-labelled |
| R1 | Memory recall | 176.5 s | 1 | jarvis_memory | Correct, with a minor embellishment (below) |
| R2 | Project status | 197.8 s | 1 | project_operator | Correct, matches the registry verbatim |
| R3 | Reasoning tradeoff (no tool needed) | 46.8 s | 1 | graphify_query | **Failed** — see below |
| R3b | Same, after fix | 40.6 s | 1 | — | Correct, real comparative analysis |
| R4 | "What calls `_apply_graphify_centrality`" | 90.4 s | 1 | project_operator | **Failed** — carried-forward issue |
| R5 | Weather | 16.6 s | 1 | weather_report | Correct, fastest turn |
| R6 | System status | 119.7 s | 1 | system_status | Correct, real telemetry |

## A regression this round introduced, found and fixed

**R3 is the important finding, because it was mine.** A pure reasoning question ("walk me through the tradeoffs of blending graphify's degree centrality...") was misrouted to `graphify_query`, which returned `"No node matching '...' found."` — a *technically successful* call with a null result and a clean receipt. Phase 3's new direct-answer path saw a whitelisted tool, a clean receipt and short plain text, and handed that dead end to the user as the entire reply.

The baseline answered this same question well, with no tool at all. So the direct-answer optimisation turned a recoverable misroute into a visibly worse answer.

Fixed: a near-empty or explicitly negative result no longer short-circuits the model. The guard inspects content only to decide whether to *add* a model step, never to decide how content is presented — the whitelist itself stays keyed on tool name, so tool output still cannot steer its own presentation. Getting the guard wrong costs one extra generation; the other direction costs the user a dead end.

Honest attribution: on the live re-run the model happened not to call `graphify_query` at all (tool selection is non-deterministic across identical prompts, already on record), so the improved live answer is not by itself proof the fix worked. The deterministic unit tests are — they assert the dead-end path is closed for the exact returned string and its family.

A second, smaller self-correction: the first version of that guard used a 40-character minimum, which would have blocked a genuinely terse answer like "Sunny in Glasgow, 18C." Lowered to 16 so it only rejects near-empty output, leaving semantic negatives to explicit markers.

## Carried forward, not fixed this round

**R4: `graphify_query` still is not reliably selected for the questions it exists for.** "What functions call `_apply_graphify_centrality` in project_learning.py" went to `project_operator` with an invented `project_id` of "project_learning", was correctly blocked by policy, and JARVIS reported plainly that it could not answer. This is the same finding as the 2026-07-25 round — a tool-selection reliability problem, not a regression.

Worth noting the inversion: this round `graphify_query` was called for a question that needed no tool (R3) and *not* called for a textbook structural question (R4). That is a model-selection reliability issue rather than a routing-table one, and it is the strongest remaining candidate for Phase 5.

**R1 embellishment.** The reply listed the testing-log columns as "date, prompt, method, result, thoughts, strengths, and weaknesses". The real note (verified on disk) says "prompt, method, result, thoughts, strengths, weaknesses" — "date" was added. Small, but it is exactly the ungrounded-detail class worth watching.

## What this round did not test

Speech/TTS end to end, memory consolidation apply, canvas decompose/critique/propose (covered clean in the previous round and untouched by Phases 1-3), and the Gemini Live path (dead code by configuration). The injection-resilience battery was not repeated: the trap artifacts were deliberately removed after the previous round, and rebuilding them was out of scope here.

## Instrumentation caveat

The harness flags "narration markers" in replies as a signal for the one-way barrier. H1 tripped one — but on inspection it was the literal tool name *"Secure Dual Orchestrator"* inside the tool list, not narration. A false positive of the detector, not a finding. Every marker hit in this round was read by hand rather than scored automatically.

## Related
[[Validation/2026-07-25-expanded-live-validation]]
[[Validation/2026-07-25-session-closing-summary]]
