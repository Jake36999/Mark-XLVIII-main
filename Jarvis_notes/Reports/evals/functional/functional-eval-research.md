---
id: "functional-eval-research-2026-07-21"
title: "Functional Evaluation - Deep Research"
type: "evaluation_report"
status: "complete_with_gaps"
created: "2026-07-21T18:12:38+01:00"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis-functional-eval"
source: "codex-functional-evaluator"
tags: ["evaluation", "research", "lmstudio", "jarvis", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "internal"
confidence: 1.0
valid_from: "2026-07-21"
review_after: "2026-08-21"
source_version: 1
content_hash: "0b275851382b33e8a8b7518e3603462701797dd18644a5b604f933de32e22cca"
supersedes: []
contradicts: []
related: ["[[functional-eval-plan]]", "[[functional-eval-final]]"]
deleted: false
deleted_at: ""
lifecycle: "short_term"
---

# Functional Evaluation - Deep Research

> [!failure] Result
> **Failed quality threshold.** Baseline: **2.07/4**. Rerun: **2.07/4**. No critical gate failed, but the report remained materially incomplete.

## Comparison

| Dimension | Baseline | Rerun |
| --- | ---: | ---: |
| Report created | 4 | 4 |
| Cited sources | 4 | 4 |
| Scope coverage | 1.5 | 1.5 |
| Primary-source quality | 2 | 2 |
| Uncertainty and inference | 1 | 1 |
| Host-specific recommendations | 1 | 1 |
| Consolidation and contrast | 1 | 1 |

The rerun took `728.254s`. Every preferred local synthesis route failed or timed out, so JARVIS saved a visibly degraded deterministic extract instead of presenting unsupported synthesis. The artifact records `quality_state: degraded_unsynthesized` and `synthesis_state: deterministic_extract`.

## Systemic Changes

- Added shorter vendor-specific searches and primary-domain hints for LM Studio, llama.cpp, NVIDIA, Vulkan, Dagster, and OpenAI.
- Added grouped deterministic fallback sections for memory, concurrency, loading, telemetry, recovery, uncertainty, and host actions.
- Added explicit fallback provenance and preferred-model-unavailable state.
- Fixed LM Studio lifecycle routing after the scored rerun so inference addresses the native loaded instance ID instead of a catalog alias.

> [!warning] Remaining weakness
> Search retrieval is usable, but specialist-model loading and long local synthesis are not yet reliable enough for high-quality deep research. Deterministic fallback is honest and cited, but still too shallow to pass the rubric.

## Evidence

- [Baseline run](<../../../.jarvis/evals/functional/mixed-vendor-dual-gpu-research/baseline/run.json>)
- [Baseline report](<../../../.jarvis/evals/functional/mixed-vendor-dual-gpu-research/baseline/vault/Reports/2026-07-21-mixed-vendor-dual-gpu-local-model-orchestration.md>)
- [Rerun](<../../../.jarvis/evals/functional/mixed-vendor-dual-gpu-research/rerun/run.json>)
- [Rerun report](<../../../.jarvis/evals/functional/mixed-vendor-dual-gpu-research/rerun/vault/Reports/2026-07-21-mixed-vendor-dual-gpu-local-model-orchestration.md>)
- [Rerun telemetry](<../../../.jarvis/evals/functional/mixed-vendor-dual-gpu-research/rerun/evidence/events.jsonl>)
