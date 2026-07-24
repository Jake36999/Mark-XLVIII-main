---
id: "functional-eval-final-2026-07-21"
title: "JARVIS Functional Evaluation - Final"
type: "evaluation_report"
status: "complete_with_gaps"
created: "2026-07-21T18:12:38+01:00"
updated: "2026-07-23T02:52:44Z"
project_id: "jarvis-functional-eval"
source: "codex-functional-evaluator"
tags: ["evaluation", "functional-quality", "jarvis", "final", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "internal"
confidence: 1.0
valid_from: "2026-07-21"
review_after: "2026-08-21"
source_version: 1
content_hash: "995ec006cd034416933e52b35bc4067e20483905c58dc87e542906ed1e218c8d"
supersedes: []
contradicts: []
related: ["[[functional-eval-plan]]", "[[functional-eval-research]]", "[[functional-eval-coding]]", "[[functional-eval-documentation]]", "[[functional-eval-learning]]", "[[functional-eval-productivity]]"]
deleted: false
deleted_at: ""
memory_tier: "short_term"
---

# JARVIS Functional Evaluation - Final

> [!abstract] Overall finding
> JARVIS is now reliable for structured vault documentation, linked learning sets, compact RAG takeaways, and approval-aware productivity workflows. Deep local research synthesis and complete coding-run dispatch remain the two material weaknesses.

## Results

| Workflow | Baseline | Rerun | Critical result |
| --- | ---: | ---: | --- |
| [[functional-eval-research|Deep research]] | 2.07 | 2.07 | Failed quality threshold; no critical gate |
| [[functional-eval-coding|Planned coding]] | 0.67 | 3.5 | Failed approved-run execution |
| [[functional-eval-documentation|Documentation]] | 1.6 | 4.0 | Passed |
| [[functional-eval-learning|Learn Dagster]] | 1.33 | 4.0 | Passed |
| [[functional-eval-productivity|Productivity]] | 2.4 | 4.0 | Passed |

Three of five scenarios passed their rerun. Coding produced a fully valid demo but failed one queue gate. Research remained cited and transparent but not deep enough to pass.

## Cross-Cutting Results

| Contract | Result | Evidence |
| --- | --- | --- |
| Concise RAG with backlinks | Passed | Dagster rerun scored `4/4` for compact RAG and backlinks |
| Pause, edit, resume | Passed | Regression test proves hash drift pauses the stale run, preserves the user edit, and creates a new versioned run |
| Cloud unavailable fallback | Passed deterministically; live timeout observed | Provenance records `lmstudio`, preferred-model unavailability, and fallback reason; an isolated live probe exceeded `90s` and was stopped |
| Links and YAML | Passed | Documentation rerun scored `4/4` for frontmatter, links, and typed relationships |
| Execution telemetry | Passed at artifact level | Coding demo and productivity queue include IDs, timestamps, status, durations, errors/retries, health, checkpoints, and review verdicts |
| Regression | Passed | `206 passed`, one Python `audioop` deprecation warning |

## Final Runtime State

- Mark restarted from the current source as one top-level process: PID `4040`.
- Both self-signed HTTPS endpoints returned `200` on ports `8000` and `8001`.
- LM Studio returned healthy lifecycle status with only `qwen/qwen3-4b-2507` and `orpeus_text_to_speech` loaded.
- A late DeepSeek load from the timed-out fallback probe was detected and unloaded; final task-model count is zero.

## Systemic Refactors

- Added deterministic artifact hooks for coding, documentation, and productivity outputs.
- Added complete learning-set generation and compact-only RAG indexing.
- Strengthened approval projection hashing so nested scope headings are protected.
- Prevented non-canonical plan prose from becoming hidden work items.
- Added visible model fallback provenance and preferred-model failure state.
- Fixed LM Studio lifecycle parsing, task budgeting, cleanup, and native instance-ID routing.
- Improved official-source discovery and honest degraded research fallback.

## Model Comparison

The strongest successful content workflow was the Dagster learning rerun using LM Studio with `qwen/qwen3-4b-2507` after a preferred-model failure. It was slow (`474.999s`) but complete. The deep-research specialist routes failed to synthesize within their budgets, producing a `728.254s` degraded research run. Deterministic hooks were fast and dependable for documentation (`0.475s`) and productivity (`0.445s`).

> [!warning] Do not conflate model presence with model reliability
> LM Studio can list and load the larger research models, but this evaluation did not prove stable, bounded completion from them. Model health must include a small generation probe, native instance ID, latency, and structured-output reliability before assignment.

## Prioritized Refactors

1. Add bounded load/generation health probes and cooldown state for each specialist model; fail over before a workflow spends several minutes waiting.
2. Split research synthesis into evidence normalization, section-level bounded synthesis, and final consolidation so one long request cannot sink the whole report.
3. Promote hook configuration validation to plan compilation so missing required config blocks before approval, not during dispatch.
4. Add a post-approval integration smoke for each registered hook using the exact compiled payload.
5. Keep report-quality floors explicit: degraded deterministic extracts may be saved for inspection but must not be presented as completed deep research.

## Evidence Index

- [[functional-eval-plan|Evaluation plan and rubric]]
- [[functional-eval-research|Research scenario report]]
- [[functional-eval-coding|Coding scenario report]]
- [[functional-eval-documentation|Documentation scenario report]]
- [[functional-eval-learning|Learning scenario report]]
- [[functional-eval-productivity|Productivity scenario report]]
- [Research baseline](<../../../.jarvis/evals/functional/mixed-vendor-dual-gpu-research/baseline/run.json>) and [rerun](<../../../.jarvis/evals/functional/mixed-vendor-dual-gpu-research/rerun/run.json>)
- [Coding baseline](<../../../.jarvis/evals/functional/modular-job-runner/baseline/run.json>) and [rerun](<../../../.jarvis/evals/functional/modular-job-runner/rerun/run.json>)
- [Documentation baseline](<../../../.jarvis/evals/functional/vault-documentation/baseline/run.json>), [invalid evaluator](<../../../.jarvis/evals/functional/vault-documentation/rerun-invalid-evaluator/run.json>), and [valid rerun](<../../../.jarvis/evals/functional/vault-documentation/rerun/run.json>)
- [Learning baseline](<../../../.jarvis/evals/functional/learn-dagster/baseline/run.json>) and [rerun](<../../../.jarvis/evals/functional/learn-dagster/rerun/run.json>)
- [Productivity baseline](<../../../.jarvis/evals/functional/task-ownership-and-approval/baseline/run.json>) and [rerun](<../../../.jarvis/evals/functional/task-ownership-and-approval/rerun/run.json>)

## External References

- [LM Studio REST API](https://lmstudio.ai/docs/developer/rest)
- [LM Studio model loading](https://lmstudio.ai/docs/developer/rest/load)
- [LM Studio idle TTL and auto-evict](https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict)
- [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Dagster documentation](https://docs.dagster.io/)
