---
id: "functional-eval-documentation-2026-07-21"
title: "Functional Evaluation - Planned Documentation"
type: "evaluation_report"
status: "passed"
created: "2026-07-21T18:12:38+01:00"
updated: "2026-07-23T02:52:44Z"
project_id: "jarvis-functional-eval"
source: "codex-functional-evaluator"
tags: ["evaluation", "documentation", "obsidian", "workflow", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "internal"
confidence: 1.0
valid_from: "2026-07-21"
review_after: "2026-08-21"
source_version: 1
content_hash: "4e903bd4b7a5ed22cae13ef66e9eebbbe38cdd041bf92c81b642fff67ea64373"
supersedes: []
contradicts: []
related: ["[[functional-eval-plan]]", "[[functional-eval-final]]"]
deleted: false
deleted_at: ""
memory_tier: "short_term"
---

# Functional Evaluation - Planned Documentation

> [!success] Result
> **Passed.** Baseline: **1.6/4** with critical artifact and link failures. Valid rerun: **4/4**.

## Comparison

| Dimension | Baseline | Rerun |
| --- | ---: | ---: |
| Three required artifacts | 0 | 4 |
| Frontmatter valid | 4 | 4 |
| Obsidian links resolve | 0 | 4 |
| Callouts used | 4 | 4 |
| Typed relationships | 0 | 4 |

The workflow now creates an evaluation MOC, architecture report, and evidence-backed knowledge-gap report as separate linked artifacts. YAML parses, links resolve, and typed relationships point to real notes.

## Systemic Changes

- Added a deterministic documentation artifact hook using canonical vault writes.
- Added typed relationships, source references, and scoped link generation.
- Corrected the evaluator to match frontmatter titles independently of hyphenated filenames.
- Restricted link validation to generated artifacts so unrelated fixture text such as `[[SCHEMA]]` cannot create a false failure.

> [!info] Invalid evaluator run preserved
> The first rerun was rejected because the checker was wrong, not because the generated documents were wrong. Its evidence remains under `rerun-invalid-evaluator`; the valid rerun was then performed with the corrected deterministic contract.

## Evidence

- [Baseline run](<../../../.jarvis/evals/functional/vault-documentation/baseline/run.json>)
- [Invalid-evaluator rerun](<../../../.jarvis/evals/functional/vault-documentation/rerun-invalid-evaluator/run.json>)
- [Valid rerun](<../../../.jarvis/evals/functional/vault-documentation/rerun/run.json>)
- [Evaluation MOC](<../../../.jarvis/evals/functional/vault-documentation/rerun/vault/Reports/2026-07-21-evaluation-moc.md>)
- [Workflow architecture report](<../../../.jarvis/evals/functional/vault-documentation/rerun/vault/Reports/2026-07-21-workflow-architecture-report.md>)
- [Knowledge gaps and next actions](<../../../.jarvis/evals/functional/vault-documentation/rerun/vault/Reports/2026-07-21-knowledge-gaps-and-next-actions-report.md>)
- [Compiled workflow YAML](<../../../.jarvis/evals/functional/vault-documentation/rerun/vault/.jarvis/runs/plan-plan-review-the-markdown-vault-and-create-three-linked-obsidian-art/v1/workflow.yaml>)
- [Run telemetry](<../../../.jarvis/evals/functional/vault-documentation/rerun/evidence/events.jsonl>)
