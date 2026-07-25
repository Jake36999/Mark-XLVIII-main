---
id: "project-brief-knowledge-compiler-engine"
title: "Project Brief - Knowledge Compiler Engine"
type: "report"
status: "reviewed"
created: "2026-07-22T11:42:34Z"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis_notes"
source: "F:\\knowledge_compiler_engine (DAG Engine)"
tags: ["project-learning", "repository", "read-only", "verified", "knowledge-compiler-engine", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.94
valid_from: "2026-07-22T12:18:48Z"
review_after: ""
source_version: 2
content_hash: "af66ca6986e3499f1bf6c660cc467534d1b915b599cea35e68bbda90c162420d"
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
audit_status: "verified_read_only"
files_read_count: 36
inventory_file_count: 123
lifecycle: "short_term"
project_key: "knowledge_compiler_engine"
project_root: "F:\\knowledge_compiler_engine (DAG Engine)"
quality_state: "audited"
read_only: true
snapshot_hash: "57b3b67feb775d5b1684e683f4484d92f8373330ba8459705b7ae6cb0fa64bac"
workflow_id: "project_repository_learning/v1"
---

# Project Brief - Knowledge Compiler Engine

> [!abstract] Verified read-only repository orientation
> This brief was checked against the current snapshot `57b3b67feb775d5b1684e683f4484d92f8373330ba8459705b7ae6cb0fa64bac`. No project source files were changed.

## Executive Summary

The Knowledge Compiler Engine is an Aletheia data-curation and model-training pipeline. Its distributed path clones a repository, extracts an AST-derived knowledge representation, processes and scores nodes by cognitive mode, and emits structured artifacts suitable for QLoRA/SFT workflows. [README.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/README.md) [src/tasks/pipeline_workflow.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/tasks/pipeline_workflow.py) [config/axolotl_2x8gb.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_2x8gb.yml)

## Repository Profile

- Root: `F:\knowledge_compiler_engine (DAG Engine)`
- Snapshot: `57b3b67feb775d5b1684e683f4484d92f8373330ba8459705b7ae6cb0fa64bac`
- Inventoried files: 123
- Files examined in the bounded scout: 36
- Primary implementation language: Python, with YAML configuration and a small TypeScript/React frontend.
- The root README is only a short description; detailed behavior is documented in code and release/architecture notes. [README.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/README.md) [V2_RELEASE_NOTES.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/V2_RELEASE_NOTES.md)

## Architecture And Components

- `src/api.py` exposes ingestion, direct scoring, status, and health endpoints. [src/api.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/api.py)
- `src/tasks/pipeline_workflow.py` defines the Celery pipeline: clone and slice a repository, cognitively process it, partition nodes across `theorist`, `coding_assistant`, `advocate`, and `veteran` workers, then collect scored artifacts. [src/tasks/pipeline_workflow.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/tasks/pipeline_workflow.py)
- `src/pipeline/Agent_Forge_orchestrator.py` is a separate interactive/CLI control path with contract checks, quality gates, resumable runs, manifests, and optional training handoff. [src/pipeline/Agent_Forge_orchestrator.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/pipeline/Agent_Forge_orchestrator.py)
- `src/pipeline/sie_projection.py` normalizes node metrics into a deterministic field surface used by invariants and validation. [src/pipeline/sie_projection.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/pipeline/sie_projection.py)
- `src/validation/pipeline_firewall.py` enforces epistemic fields, canonical code formatting, token limits, placeholder rejection, and semantic-drift checks. [src/validation/pipeline_firewall.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/validation/pipeline_firewall.py)

## Entry Points And Workflows

The containerized route uses FastAPI, Redis, Celery mode workers, a pipeline worker, and Flower. `POST /ingest` launches the full repository pipeline; `POST /score` handles supplied payloads; status and health endpoints expose queue state. [src/api.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/api.py) [docker-compose.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docker-compose.yml)

The local operator route is `src/pipeline/Agent_Forge_orchestrator.py`, which scans mode-specific landing pads and sequences subprocess-backed curation/training stages. [src/pipeline/Agent_Forge_orchestrator.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/pipeline/Agent_Forge_orchestrator.py) [config/engine_config.yaml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/engine_config.yaml)

## Dependencies And Tests

The runtime combines Pydantic, NetworkX, semantic/NLP tooling, Celery/Redis, FastAPI, Tree-sitter, formatting/validation libraries, and optional monitoring. [requirements.txt](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/requirements.txt)

The V2 release note records a historical regression result of 427 passed and 1 skipped for that release. This audit did not rerun the Knowledge Compiler test suite, so that statement is documentation evidence rather than current runtime proof. [V2_RELEASE_NOTES.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/V2_RELEASE_NOTES.md)

The supplied Axolotl configuration targets Llama 3 8B QLoRA on two 8 GB GPUs with 4-bit loading, micro-batch size 1, gradient accumulation, and checkpointing. [config/axolotl_2x8gb.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_2x8gb.yml)

## Operational Guidance

Treat ingestion and training as expensive, explicit workflows. The Celery ingestion task permits multi-hour slicing/processing timeouts, while the Axolotl stage is separately configured for the dual-GPU host. [src/tasks/pipeline_workflow.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/tasks/pipeline_workflow.py) [config/axolotl_2x8gb.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_2x8gb.yml)

MARK already owns dashboard port 8000, while this project's Docker API also maps port 8000. Change the external project port before launching both stacks together. [docker-compose.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docker-compose.yml)

## Risks, Gaps, And Questions

- `bypass_math.py` is not a mathematical inference service. It is a run-specific recovery script that reads archived YAML, force-sets recovered nodes to `ACCEPTED`, and writes JSONL. It must not be treated as a normal validated path or launched automatically. [bypass_math.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/bypass_math.py)
- The V2.1 distributed-concurrency document proposes ledger shards, Redis claims, and deterministic merge behavior, but its own open notes say key pieces still need implementation and tests. [docs/V2_1_DISTRIBUTED_CONCURRENCY_ARCHITECTURE.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docs/V2_1_DISTRIBUTED_CONCURRENCY_ARCHITECTURE.md)
- Mode-balance downsampling is an export-boundary distribution control and deliberately does not modify the source failure matrix or semantic validation layers. [docs/MODE_BALANCE_DOWNSAMPLING.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docs/MODE_BALANCE_DOWNSAMPLING.md)
- The project worktree currently contains generated `__pycache__` changes; this audit did not alter or clean them.

## RAG Takeaways

- The Knowledge Compiler Engine turns repository evidence into curated, scored training artifacts through ingestion, mode-specific DAG processing, validation, and export stages. [src/tasks/pipeline_workflow.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/tasks/pipeline_workflow.py)
- It supports a distributed FastAPI/Celery/Redis route and a separate interactive Agent Forge orchestration route. [src/api.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/api.py) [src/pipeline/Agent_Forge_orchestrator.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/pipeline/Agent_Forge_orchestrator.py)
- QLoRA training is intentionally compute-heavy and has a configuration tailored to two 8 GB GPUs. [config/axolotl_2x8gb.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_2x8gb.yml)
- `bypass_math.py` force-accepts recovered nodes and is a risky recovery utility, not a trusted inference capability. [bypass_math.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/bypass_math.py)
- The documented V2.1 ledger-sharding design remains partly prospective and should not be described as fully deployed. [docs/V2_1_DISTRIBUTED_CONCURRENCY_ARCHITECTURE.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docs/V2_1_DISTRIBUTED_CONCURRENCY_ARCHITECTURE.md)

## Files Read

- `[README.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/README.md)`
- `[.gitignore](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/.gitignore)`
- `[config/axolotl_2x8gb.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_2x8gb.yml)`
- `[test_dossier.yaml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/test_dossier.yaml)`
- `[src/pipeline/Agent_Forge_orchestrator.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/pipeline/Agent_Forge_orchestrator.py)`
- `[src/pipeline/sie_projection.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/pipeline/sie_projection.py)`
- `[docs/MODE_BALANCE_DOWNSAMPLING.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docs/MODE_BALANCE_DOWNSAMPLING.md)`
- `[bypass_math.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/bypass_math.py)`
- `[docker-compose.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docker-compose.yml)`
- `[scripts/config/environment.json](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/scripts/config/environment.json)`
- `[tests/Autonomous_Ingestor.ps1](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/tests/Autonomous_Ingestor.ps1)`
- `[src/tasks/pipeline_workflow.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/tasks/pipeline_workflow.py)`
- `[frontend/App.tsx](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/frontend/App.tsx)`
- `[docs/V2_1_DISTRIBUTED_CONCURRENCY_ARCHITECTURE.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/docs/V2_1_DISTRIBUTED_CONCURRENCY_ARCHITECTURE.md)`
- `[mypy.ini](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/mypy.ini)`
- `[Dockerfile](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/Dockerfile)`
- `[config/axolotl_coder.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_coder.yml)`
- `[tests/dataset_formatter_test.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/tests/dataset_formatter_test.py)`
- `[src/validation/pipeline_firewall.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/validation/pipeline_firewall.py)`
- `[src/api.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/api.py)`
- `[requirements-lock.txt](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/requirements-lock.txt)`
- `[LICENSE](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/LICENSE)`
- `[config/axolotl_theorist.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_theorist.yml)`
- `[tests/ingestor_integration_test.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/tests/ingestor_integration_test.py)`
- `[frontend/components/FileDropzone.tsx](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/frontend/components/FileDropzone.tsx)`
- `[requirements_semantic.txt](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/requirements_semantic.txt)`
- `[requirements.txt](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/requirements.txt)`
- `[config/axolotl_veteran.yml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/axolotl_veteran.yml)`
- `[tests/smoke_test_remediation.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/tests/smoke_test_remediation.py)`
- `[src/celery_app.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/src/celery_app.py)`
- `[requirements_training.txt](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/requirements_training.txt)`
- `[config/engine_config.yaml](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/engine_config.yaml)`
- `[tests/test_adversarial_lens.py](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/tests/test_adversarial_lens.py)`
- `[frontend/components/LogPanel.tsx](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/frontend/components/LogPanel.tsx)`
- `[V2_RELEASE_NOTES.md](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/V2_RELEASE_NOTES.md)`
- `[config/environment.json](file:///F:/knowledge_compiler_engine%20%28DAG%20Engine%29/config/environment.json)`
