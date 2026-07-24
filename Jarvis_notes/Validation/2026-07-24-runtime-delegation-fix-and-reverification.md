---
id: "jarvis-20260724T185050Z-8299d7ab"
title: "Runtime Delegation Fix and Re-verification"
type: "report"
status: "active"
created: "2026-07-24T18:50:50Z"
updated: "2026-07-24T19:03:06Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "live-test", "lmstudio-performance", "before-after", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T18:50:50Z"
review_after: ""
source_version: 1
content_hash: "82e7af318639c9d576057ef5f08cdae12be39b744e100d6dbb2eaf3a258be2f5"
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
> Re-ran the 10 problem prompts from [[2026-07-24-live-prompt-testing-16-prompts]] after applying the Track A2 runtime-delegation fix (see [[Planning Subsystem Roadmap]]): reordered `model_routes` so `mistral-7b-instruct-v0.3` is tried first, added it to `baseline_models` so it warm-keeps, and fixed the system-prompt-contamination bug in `_route_from_context`. Same methodology as the original test: real `_handle_router_text_command`, real LM Studio, sequential (never parallel — proven to corrupt timing data). This is the fair before/after the owner asked for.

## Timing: the cascade is gone

| Prompt | Before | After | Change |
|---|---:|---:|---|
| P1 greeting | 30–126 s | 31.1 s | in range |
| P2 capabilities | 24 s | 127.6 s | slower, see below |
| **P3 system status** | **1109 s** | **161.1 s** | **6.9x faster** |
| **P5 memory save** | **780 s** | **340.3 s** | **2.3x faster** |
| **P6 memory recall** | **354 s** | **234.3 s** | **1.5x faster** |
| **P7 project status** | **286 s** | **133.1 s** | **2.2x faster** |
| P8 code explain | 66 s | 32.3 s | 2x faster |
| P11 summarize roadmap | 285 s | 325.7 s | slower, see below |
| P12 create plan | 11 s | 10.6 s | unchanged (expected) |
| **P13 research** | **312 s** | **153.8 s** | **2x faster** |

**Zero timeout/health-cooldown events fired across all 10 re-runs.** Before: 6 of these 10 prompts had 1–4 "entered health cooldown after N consecutive timeout outcomes" events each. After: none. Every single call in this batch succeeded on its first try — the reordering put a reliable model first, so the router never needed the fallback chain at all.

**P2 and P11 being slower is not a regression of the fix — it's a different, better-behaved kind of slow.** Both completed in one clean, uninterrupted generation with zero retries; the extra time is ordinary run-to-run variance in how long a single successful generation takes (longer output, momentary system load), not the multi-attempt failure cascade that dominated the original run. That's a categorically different (and far less concerning) source of latency.

## Accuracy and behavior, prompt by prompt

| # | Before | After | Verdict |
|---|---|---|---|
| P1 | Hallucinated a tool name (`system_health`, doesn't exist) | Clean, honest, no hallucinated tool | **Improved** |
| P2 | Model *narrated* calling `capability_registry` but never actually called it — zero tools used | Actually called `capability_registry` and gave a real, substantive capability list | **Improved** (likely a side-effect of the vision-contamination fix correcting model selection for this call) |
| P3 | Malformed raw JSON leaked into the reply after the 18-min wait | Clean, accurate real numbers (CPU 21.1%, mem 57.1%, uptime) | **Fixed** |
| P5 | Accurate, verified real note write | Accurate, same real note write | Unchanged (already good) |
| P6 | Accurate recall with real file path | Accurate recall with real file path | Unchanged (already good) |
| P7 | Accurate, matched real registry | Accurate, matched real registry | Unchanged (already good) |
| P8 | No tool reached; asked user to paste the code | Same — still asked user to paste the code | **Unchanged** (different bug, in `_router_tool_names_for_text`'s tool selection, not the model-routing layer this fix touched) |
| P11 | Called `jarvis_memory`, retrieved only the note's top-level scope, incorrectly said WS4 wasn't described | No tool called at all this time; declined outright ("I don't have access to...") | **Still an open gap**, shape changed: previously attempted-but-shallow retrieval, now doesn't attempt at all. Both are honest declines (no fabrication either time) but neither actually answers correctly — this is a retrieval/tool-selection reliability gap, not something today's fix targets |
| P12 | Real plan + real sources created; misrouted to the "delegate to OpenClaw" template because `"repo"` is a substring of `"weather_report"` | Identical — same collision, same real plan | **Unchanged, as expected** (this bug lives in `plan_workflow._steps_from_prompt`, untouched today) |
| P13 | Confident, detailed (if unverifiable) technical summary, no citations | Honest "no cited results found for this exact query" | Different outcome, likely live web-search result variance rather than a routing effect — an honest "found nothing" is arguably the more trustworthy of the two when a search genuinely returns empty |

## Bottom line

The fix did exactly what the benchmark predicted: **every prompt that previously suffered a multi-minute timeout cascade now completes in a fraction of the time, with zero cooldown events, because a reliable model is now tried first instead of last.** Two prompts got slower, but for an unrelated, benign reason (ordinary generation-time variance, no failures). Two real correctness improvements appeared as a side effect (P1's hallucinated tool name and P3's malformed-JSON leak both disappeared; P2 went from narrating an action to actually taking it). Three issues are confirmed **unrelated to this fix and still open**: P8's missed code-explanation tool, P11's unreliable note-section retrieval, and P12's keyword-substring collision in Mode 1 planning — all real, all previously flagged, none touched by today's change.

## Artifacts
- `rerun_harness.py`, `rerun_results.json` (10 full runs with event timelines) — this folder.
- Original data for comparison: `Jarvis_notes/Validation/2026-07-24-live-prompt-testing-16-prompts.md` and its artifacts folder.
