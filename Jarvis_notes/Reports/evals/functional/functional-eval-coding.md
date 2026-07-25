---
id: "functional-eval-coding-2026-07-21"
title: "Functional Evaluation - Planned Coding"
type: "evaluation_report"
status: "complete_with_blocker"
created: "2026-07-21T18:12:38+01:00"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis-functional-eval"
source: "codex-functional-evaluator"
tags: ["evaluation", "coding", "workflow", "telemetry", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "internal"
confidence: 1.0
valid_from: "2026-07-21"
review_after: "2026-08-21"
source_version: 1
content_hash: "54d0e71e02ef709861ef3d4d865bf202c0e5cf738b74c2ec829014bb931c477f"
supersedes: []
contradicts: []
related: ["[[functional-eval-plan]]", "[[functional-eval-final]]"]
deleted: false
deleted_at: ""
lifecycle: "short_term"
---

# Functional Evaluation - Planned Coding

> [!failure] Result
> **Failed one critical gate.** Baseline: **0.67/4**. Rerun: **3.5/4**. The demo itself passed every artifact and reproducibility check, but the approved workflow run ended blocked.

## Comparison

| Dimension | Baseline | Rerun |
| --- | ---: | ---: |
| Approved run executed | 4 | 1 |
| Project created | 0 | 4 |
| Modular files | 0 | 4 |
| Tests created | 0 | 4 |
| Telemetry contract | 0 | 4 |
| Fresh-process reproduction | 0 | 4 |

The rerun produced a replaceable task module, telemetry adapter, job runner, README, success/failure tests, and reproducible fresh-process result. The queue nevertheless blocked when the artifact hook received incomplete memory configuration and lacked `remember_project_id`.

## Systemic Changes

- Added deterministic registered artifact hooks for bounded coding workflows.
- Mapped specialized plan steps into strict YAML and immutable JSON work items.
- Prevented milestone and `Next Actions` prose from becoming hidden executable work.
- Added complete vault/Remember configuration to hook dispatch after the scored rerun.
- Added tests for hook configuration, visible work-item parity, modular artifacts, failure telemetry, and fresh-process execution.

> [!note] Scoring integrity
> The post-rerun configuration fix is covered by regression tests, but the scored rerun remains failed. No third scored run was used to erase the blocker.

## Evidence

- [Baseline run](<../../../.jarvis/evals/functional/modular-job-runner/baseline/run.json>)
- [Rerun](<../../../.jarvis/evals/functional/modular-job-runner/rerun/run.json>)
- [Blocked run record](<../../../.jarvis/evals/functional/modular-job-runner/rerun/vault/.jarvis/runs/plan-plan-plan-and-build-an-isolated-modular-python-job-runner-demo-unde/v1/run.json>)
- [Blocker note](<../../../.jarvis/evals/functional/modular-job-runner/rerun/vault/Blockers/2026-07-21-blocked-plan-plan-plan-and-build-an-isolated-modular-python-job-runner-demo-unde.md>)
- [Demo README](<../../../.jarvis/evals/functional/modular-job-runner/rerun/artifacts/job_runner_demo/README.md>)
- [Job runner](<../../../.jarvis/evals/functional/modular-job-runner/rerun/artifacts/job_runner_demo/job_runner.py>)
- [Task module](<../../../.jarvis/evals/functional/modular-job-runner/rerun/artifacts/job_runner_demo/tasks.py>)
- [Telemetry adapter](<../../../.jarvis/evals/functional/modular-job-runner/rerun/artifacts/job_runner_demo/telemetry.py>)
- [Tests](<../../../.jarvis/evals/functional/modular-job-runner/rerun/artifacts/job_runner_demo/tests/test_job_runner.py>)
- [Run telemetry](<../../../.jarvis/evals/functional/modular-job-runner/rerun/evidence/events.jsonl>)
