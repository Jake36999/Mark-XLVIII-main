---
id: "project-brief-quantule-mapper"
title: "Project Brief - quantule_mapper"
type: "report"
status: "reviewed"
created: "2026-07-22T02:57:00Z"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis_notes"
source: "F:\\quantule_mapper"
tags: ["project-learning", "repository", "read-only", "verified", "quantule-mapper", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.92
valid_from: "2026-07-22T03:46:34Z"
review_after: ""
source_version: 4
content_hash: "e8f5bbbc1e2cd9396ea5f0a678800cbdcc4a0a5eebcc388ed9755b0a005980f5"
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
inventory_file_count: 1438
lifecycle: "short_term"
project_root: "F:\\quantule_mapper"
read_only: true
snapshot_hash: "cc195e58fb39b0751a53d5decb5ed03a5f0ba2ba0a46e685d62921ae4786b6e5"
workflow_id: "project_repository_learning/v1"
---

## Executive Summary

`quantule_mapper` is the ASTE/Quantule Mapper physics exploration bench: a FastAPI control surface coordinates orchestrated simulation hunts, workers execute bounded physics/evaluation jobs, and artifacts plus provenance are exposed through UI, CLI, and MCP-facing interfaces. [README.md](file:///F:/quantule_mapper/README.md) [app.py](file:///F:/quantule_mapper/app.py)

## Repository Profile

The verified snapshot contains 1,438 files (45.7 MB). JARVIS read 36 selected files across the API, orchestrator, UI, visualization CLI, MCP server, configuration, evidence, Colab capsules, and tests. One sensitive file was excluded from reading.

## Architecture And Components

- `app.py` supplies FastAPI control APIs, WebSocket telemetry, static UI serving, run/session state, and visual-analysis routes. [app.py](file:///F:/quantule_mapper/app.py)
- The documented runtime separates the API, orchestrator, and manually started worker processes; workers claim queued simulation/evaluation work. [README.md](file:///F:/quantule_mapper/README.md)
- `orchestrator/orchestrator_engine.py` and the surrounding diagnostics/tests represent the deterministic orchestration and provenance layer. [orchestrator/orchestrator_engine.py](file:///F:/quantule_mapper/orchestrator/orchestrator_engine.py) [orchestrator/diagnostics/lifecycle_report.py](file:///F:/quantule_mapper/orchestrator/diagnostics/lifecycle_report.py)
- The React UI and visualization CLI are separate presentation/analysis surfaces. [UI/components/package.json](file:///F:/quantule_mapper/UI/components/package.json) [quantule_viz/cli.py](file:///F:/quantule_mapper/quantule_viz/cli.py)

## Entry Points And Workflows

- The primary local API command is `python -m uvicorn app:app --host 127.0.0.1 --port 8000`; the documented operator flow then starts the orchestrator and one or more workers. [README.md](file:///F:/quantule_mapper/README.md)
- `python -m mcp_server.server` starts the FastMCP surface. Its module includes read-only ledger/artifact queries and explicitly labeled write operations for bounded smoke simulation and validation, so permissions must be assessed per tool rather than from the module banner alone. [mcp_server/server.py](file:///F:/quantule_mapper/mcp_server/server.py)
- `quantule_viz/cli.py` is the visualization/analysis CLI entry point. [quantule_viz/cli.py](file:///F:/quantule_mapper/quantule_viz/cli.py)

## Dependencies And Tests

`pyproject.toml` requires Python 3.11 and defines NumPy/SciPy/HDF5, FastAPI, data-science, topology, file-locking, and watchdog dependencies, with optional GPU, UI, and development groups. [pyproject.toml](file:///F:/quantule_mapper/pyproject.toml)

The inventory contains 109 test-like files. This read-only learning pass did not execute them and makes no pass/fail claim.

## Operational Guidance

Follow the root `README.md` launch sequence and keep a single orchestrator owner per queue set. Start workers only after a run has been staged so active-run pointers and leases exist. [README.md](file:///F:/quantule_mapper/README.md)

Treat `readme.json` as stale where it names `G:/quantule_mapper`; the verified repository root is `F:/quantule_mapper`. [readme.json](file:///F:/quantule_mapper/readme.json)

## Risks, Gaps, And Questions

- The API defaults to port 8000, which conflicts with MARK when both are launched unchanged; choose a non-conflicting port before concurrent deployment. [README.md](file:///F:/quantule_mapper/README.md)
- MCP capability descriptions and actual side effects are mixed in one server module; registry metadata should preserve each tool's read/write risk classification. [mcp_server/server.py](file:///F:/quantule_mapper/mcp_server/server.py)
- Scientific interpretation remains outside automated project-learning authority; JARVIS may inventory and summarize evidence but should not promote physical conclusions without user or Claude review.

## RAG Takeaways

- ASTE separates API/UI, orchestrator, and worker responsibilities and uses queued, lease-aware execution. [README.md](file:///F:/quantule_mapper/README.md)
- `app.py` is the main FastAPI control and telemetry surface. [app.py](file:///F:/quantule_mapper/app.py)
- The MCP server contains both read-only queries and explicitly labeled bounded write tools, requiring per-tool permission metadata. [mcp_server/server.py](file:///F:/quantule_mapper/mcp_server/server.py)
- `readme.json` contains a stale `G:` root; the current verified root is `F:/quantule_mapper`. [readme.json](file:///F:/quantule_mapper/readme.json)

## Files Read

- [.gitignore](file:///F:/quantule_mapper/.gitignore)
- [README.md](file:///F:/quantule_mapper/README.md)
- [UI/components/package.json](file:///F:/quantule_mapper/UI/components/package.json)
- [UI/components/src/Dashboard.tsx](file:///F:/quantule_mapper/UI/components/src/Dashboard.tsx)
- [UI/components/src/api_client.ts](file:///F:/quantule_mapper/UI/components/src/api_client.ts)
- [UI/components/src/index.css](file:///F:/quantule_mapper/UI/components/src/index.css)
- [UI/components/src/index.tsx](file:///F:/quantule_mapper/UI/components/src/index.tsx)
- [UI/components/src/react-three-fiber.d.ts](file:///F:/quantule_mapper/UI/components/src/react-three-fiber.d.ts)
- [UI/components/tsconfig.json](file:///F:/quantule_mapper/UI/components/tsconfig.json)
- [app.py](file:///F:/quantule_mapper/app.py)
- [aste_hunter.py](file:///F:/quantule_mapper/aste_hunter.py)
- [backlog_orchestrator.py](file:///F:/quantule_mapper/backlog_orchestrator.py)
- [burn_in_config.json](file:///F:/quantule_mapper/burn_in_config.json)
- [colab_jobs/COLAB_CAPSULE_WORKFLOW.json](file:///F:/quantule_mapper/colab_jobs/COLAB_CAPSULE_WORKFLOW.json)
- [colab_jobs/Colab_runs/cl_tg_b2_definitive_force_20260716_113033/cl_tg_b2_definitive_force_20260716_113033/cl_tg_b2_definitive_force/results/cl_tg_b2_definitive/config.json](file:///F:/quantule_mapper/colab_jobs/Colab_runs/cl_tg_b2_definitive_force_20260716_113033/cl_tg_b2_definitive_force_20260716_113033/cl_tg_b2_definitive_force/results/cl_tg_b2_definitive/config.json)
- [colab_jobs/Colab_runs/cl_tg_r_robustness_capsule_20260717_112558/cl_tg_r_robustness_capsule/docs/gravity_maturity/TG_PROTECTED_REGISTRY.json](file:///F:/quantule_mapper/colab_jobs/Colab_runs/cl_tg_r_robustness_capsule_20260717_112558/cl_tg_r_robustness_capsule/docs/gravity_maturity/TG_PROTECTED_REGISTRY.json)
- [colab_jobs/README.md](file:///F:/quantule_mapper/colab_jobs/README.md)
- [colab_jobs/results/cl_tg_r_robustness_capsule_v2/docs/gravity_maturity/TG_PROTECTED_REGISTRY.json](file:///F:/quantule_mapper/colab_jobs/results/cl_tg_r_robustness_capsule_v2/docs/gravity_maturity/TG_PROTECTED_REGISTRY.json)
- [colab_jobs/tests/tg_b1s_d_reproduce_and_compare.py](file:///F:/quantule_mapper/colab_jobs/tests/tg_b1s_d_reproduce_and_compare.py)
- [colab_jobs/tests/tg_b1s_d_reproduction_compare.py](file:///F:/quantule_mapper/colab_jobs/tests/tg_b1s_d_reproduction_compare.py)
- [compiled_knowledge_base/Quantule_Mapper_CoPilot_Bundle/workflows.yaml](file:///F:/quantule_mapper/compiled_knowledge_base/Quantule_Mapper_CoPilot_Bundle/workflows.yaml)
- [docs/claud_memory_files/MEMORY.md](file:///F:/quantule_mapper/docs/claud_memory_files/MEMORY.md)
- [docs/codex_conservative_c2_campaign_archive/GPU_CAPABILITY_TEST_20260709.md](file:///F:/quantule_mapper/docs/codex_conservative_c2_campaign_archive/GPU_CAPABILITY_TEST_20260709.md)
- [docs/evidence_package/README.md](file:///F:/quantule_mapper/docs/evidence_package/README.md)
- [docs/theory_synthesis/irer_archive/conversations/2025-05/D20250516_030512_irer-simulation-pipeline-summary.md](file:///F:/quantule_mapper/docs/theory_synthesis/irer_archive/conversations/2025-05/D20250516_030512_irer-simulation-pipeline-summary.md)
- [jax_scout/equivalence/README.md](file:///F:/quantule_mapper/jax_scout/equivalence/README.md)
- [mcp_server/server.py](file:///F:/quantule_mapper/mcp_server/server.py)
- [orchestrator/diagnostics/lifecycle_report.py](file:///F:/quantule_mapper/orchestrator/diagnostics/lifecycle_report.py)
- [orchestrator/orchestrator_engine.py](file:///F:/quantule_mapper/orchestrator/orchestrator_engine.py)
- [pyproject.toml](file:///F:/quantule_mapper/pyproject.toml)
- [quantule_viz/cli.py](file:///F:/quantule_mapper/quantule_viz/cli.py)
- [readme.json](file:///F:/quantule_mapper/readme.json)
- [requirements.txt](file:///F:/quantule_mapper/requirements.txt)
- [tests/test_orchestrator_refinement_dispatch.py](file:///F:/quantule_mapper/tests/test_orchestrator_refinement_dispatch.py)
- [tests/test_phase_d_orchestrator.py](file:///F:/quantule_mapper/tests/test_phase_d_orchestrator.py)
- [tests/test_refinement_lifecycle_e2e.py](file:///F:/quantule_mapper/tests/test_refinement_lifecycle_e2e.py)
