---
id: "functional-eval-plan-2026-07-21"
title: "JARVIS Functional Evaluation Plan"
type: "evaluation_plan"
status: "complete"
created: "2026-07-21T16:45:00Z"
updated: "2026-07-23T02:52:44Z"
project_id: "jarvis-functional-eval"
source: "codex-functional-evaluator"
tags: ["evaluation", "functional-quality", "jarvis", "baseline-rerun", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "internal"
confidence: 1.0
valid_from: "2026-07-21"
review_after: "2026-08-21"
source_version: 1
content_hash: "35d86427ba9509f7116867924a94296d0102a999342ceca797cefdeb503fbb24"
supersedes: []
contradicts: []
related: []
deleted: false
deleted_at: ""
memory_tier: "short_term"
---

# JARVIS Functional Evaluation Plan

> [!abstract] Purpose
> Assess whether real JARVIS workflow outputs are correct, useful, coherent, observable, and properly integrated with Obsidian and local RAG. This is a functional-quality evaluation. STT, TTS, and adversarial security testing are excluded.

## Preflight

| Check | Required evidence | Initial state |
| --- | --- | --- |
| Latest Mark code | Running process start time is later than the source files under evaluation | Mark PID `15388` started `2026-07-21 15:57:33`; latest relevant source edit before startup was `15:30:37 UTC` |
| Dashboard | HTTP status from both Mark ports | `8000=200`, `8001=200` |
| LM Studio | Native model endpoint, runtime survey, loaded-model inventory | REST `200`; Vulkan llama.cpp `2.25.2`; GTX 1080 and RX 5500 XT visible |
| Model hygiene | Only intended idle baselines loaded | `orpeus_text_to_speech`; zero task models |
| No duplicate listener | One Mark PID owns both dashboard ports | PID `15388`; no second Mark process will be started |

## Isolation

> [!important] Evaluation containment
> Raw prompts, fixtures, source captures, telemetry, generated test vaults, and model output are stored under `Jarvis_notes/.jarvis/evals/functional`. That directory is excluded from the production RAG crawler. Human evaluation reports are stored here under `Reports/evals/functional` and have `rag_index: false`.

Each run receives:

- immutable `run.json` metadata;
- append-only `events.jsonl` telemetry;
- a copied prompt and source manifest;
- provider, model, route, tools, duration, artifacts, and fallback reason;
- deterministic validator output;
- preserved baseline and rerun directories.

## Score Scale

| Score | Observable meaning |
| ---: | --- |
| 0 | Missing, unusable, fabricated, or contradicts the requested behavior |
| 1 | Materially incomplete; manual reconstruction is required |
| 2 | Partially useful but important gaps, ambiguity, or weak integration remain |
| 3 | Correct and useful with bounded, clearly disclosed weaknesses |
| 4 | Complete, coherent, reproducible, well-instrumented, and directly usable |

Scores come from artifact inspection and deterministic checks, never model self-ratings.

## Critical Gates

> [!danger] No averaging away critical failures
> A scenario cannot pass if any applicable critical gate fails, even when its numeric average is high.

- Required artifacts are absent, unreadable, or outside the isolated root.
- A current factual claim relies on a fabricated, broken, or uncited source.
- Planned coding cannot be reproduced in a fresh process, has no failure telemetry, or silently skips required tests.
- Required YAML/frontmatter is invalid, or required Obsidian links do not resolve.
- Learning RAG stores raw reports/logs instead of compact verified takeaways with backlinks.
- Productivity automation changes user ownership or begins agent work before approval.
- Canonical-note resume overwrites a user edit or fails to disclose a conflict.
- Cloud failure silently downgrades quality, omits provenance, or claims unsupported capability.
- Run telemetry omits run ID, task ID where applicable, timestamp, status, duration, error/retry fields, artifacts, provider/model/route, tools, or fallback reason.

## Scenario Rubrics

### 1. Deep Research

Score each dimension `0-4`:

1. Covers memory, concurrency, loading, telemetry, and failure recovery.
2. Uses relevant working sources, favouring primary documentation.
3. Keeps claims consistent with sources and labels uncertainty/inference.
4. Produces actionable recommendations suitable for this dual-GPU host.
5. Consolidates overlapping workstreams while keeping genuinely contrasting findings separate.
6. Produces readable cited Markdown and complete run telemetry.

### 2. Planned Coding

1. Plan is specific, sequenced, approval-gated, and maps to visible work items.
2. Demo setup is clean and confined to its fixture root.
3. Job runner has a replaceable task module and telemetry adapter.
4. Events contain run/task IDs, timestamps, status, duration, errors, retries, and health.
5. Success and failure tests pass, including failure telemetry.
6. Documentation and a fresh-process command reproduce the result.

### 3. Planned Documentation

1. Evaluation MOC is navigable and all links resolve.
2. Architecture report accurately summarizes the inspected vault/workflows.
3. Knowledge-gap report identifies evidence-backed gaps and useful next actions.
4. Frontmatter/YAML parses and typed relationships point to real notes.
5. Obsidian callouts and structure improve scanning rather than decorate it.
6. Citations identify actual source notes/files; no invented relationships appear.

### 4. Learn Dagster

1. Uses current primary Dagster documentation with working citations.
2. Correctly distinguishes assets, ops/jobs, resources, partitions, schedules/sensors, and I/O/metadata concepts.
3. Covers ML, optimisation, and data-processing applications with concrete examples.
4. Includes a learning plan, definitions, source notes, exercises, gaps, and review.
5. Cross-links resolve and form a useful topic map rather than decorative backlinks.
6. RAG contains only compact verified takeaways with confidence and report/source backlinks.

### 5. Productivity

1. Parses a populated project/task note accurately.
2. Preserves user, agent, shared, advisory, and confirmation-required ownership.
3. Offers bounded help before requesting explicit approval.
4. Executes no agent-owned action before approval and stops revoked work.
5. Tracks status, dependencies, next action, and review evidence coherently.
6. Produces completion evidence linked to the canonical task IDs.

## Cross-Cutting Checks

| Check | Pass condition |
| --- | --- |
| RAG recall | Concise conclusions are returned with note backlinks; raw reports and telemetry are absent |
| Reconciliation | A paused run preserves a user edit on resume or produces a visible conflict record |
| Cloud fallback | Local fallback is explicit and records provider, model, route, reason, and quality-floor status |
| Link validation | Every required wiki link and Markdown file link resolves |
| YAML validation | Every generated YAML/frontmatter artifact parses and required fields exist |
| Regression | Full non-speech test suite passes after refactors |

## Execution Order

1. Freeze rubric, fixture manifest, and preflight state.
2. Run one baseline for each scenario without changing workflow code.
3. Inspect primary artifacts and telemetry; record root causes.
4. Implement only reusable fixes supported by failures across scenarios.
5. Run each scenario once more using the same acceptance contract.
6. Run cross-cutting and regression checks.
7. Write one scenario report each and `functional-eval-final.md`, linking every artifact.

## Completion

> [!done] Evaluation closed
> All five scenarios have preserved baseline and rerun evidence, cross-cutting contracts have explicit results, and the full regression suite passed. See [[functional-eval-final]].

- Final Mark runtime: one top-level process, PID `4040`.
- Dashboard verification: HTTPS `8000=200`, `8001=200`.
- LM Studio baseline: `qwen/qwen3-4b-2507` and `orpeus_text_to_speech`; zero task models.
- Regression: `206 passed`, with one `audioop` deprecation warning.
