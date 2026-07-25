---
id: "project-brief-network-management"
title: "Project Brief - network_management"
type: "report"
status: "reviewed"
created: "2026-07-22T02:42:11Z"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis_notes"
source: "F:\\network_management"
tags: ["project-learning", "repository", "read-only", "verified", "network-management", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.92
valid_from: "2026-07-22T03:46:34Z"
review_after: ""
source_version: 7
content_hash: "0f3712cda089661bcfe0167916ab36c58194b8f64c4ad833babffab47c70e957"
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
inventory_file_count: 711
lifecycle: "short_term"
project_root: "F:\\network_management"
read_only: true
snapshot_hash: "47dd7c39c3b69c4a81d97d4b27896b2af86248d5726701a035d13ec7f8aa16e4"
workflow_id: "project_repository_learning/v1"
---

## Executive Summary

`network_management` is a hybrid cyber-physical monitoring repository that combines Intel 5300 Wi-Fi CSI sensing, packet/network telemetry, security-event normalization, and forensic timeline correlation. The repository-level design is broader than its local two-class CSI training experiment. [README.md](file:///F:/network_management/README.md)

## Repository Profile

The verified snapshot contains 711 files (67.8 MB). JARVIS read 36 selected files spanning the root architecture, deployment scripts, Intel 5300 translation, Rust training crates, the Python physics service, SIEM configuration, research notes, and tests.

## Architecture And Components

- The RF plane captures Intel 5300 CSI and feeds sensing/inference components; the network plane contributes packet and reconnaissance telemetry. [README.md](file:///F:/network_management/README.md)
- Wazuh normalizes RF and network events, while Timesketch is the intended correlation and investigation sink. [README.md](file:///F:/network_management/README.md)
- `wifi-densepose-core` defines Rust CSI frame, pose, processor, and inference contracts used by the model-training workspace. [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/src/types.rs](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/src/types.rs) [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/src/traits.rs](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/src/traits.rs)
- `physics_reference/app.py` is a separate FastAPI service with orchestration, persistence, diagnostics, and visualization support. [physics_reference/app.py](file:///F:/network_management/physics_reference/app.py)

## Entry Points And Workflows

- `Deploy-RfBackend.ps1` is the current idempotent backend bring-up and verification path. It explicitly distinguishes the locked `csi-control` route from the legacy `start_csi_pipeline.bat` recovery route. [Deploy-RfBackend.ps1](file:///F:/network_management/Deploy-RfBackend.ps1)
- The Intel 5300 fixture documentation describes the real-capture parser gate used by Rust tests. [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-train/tests/fixtures/README.md](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-train/tests/fixtures/README.md)
- The two-class static-scene training workflow is a scoped subproject, not the purpose of the entire repository. [docs/model_training_workflow_overview.md](file:///F:/network_management/docs/model_training_workflow_overview.md)

## Dependencies And Tests

The inventory contains ten dependency manifests and 97 test-like files. This is structural evidence only; this read-only learning pass did not execute tests and makes no pass/fail claim.

## Operational Guidance

Use `Deploy-RfBackend.ps1` and its `Verify-RfBackend.ps1` gate for the locked RF backend. Treat the batch launcher as a legacy recovery path unless the deployment contract is deliberately changed. [Deploy-RfBackend.ps1](file:///F:/network_management/Deploy-RfBackend.ps1)

For model training, preserve the documented claim boundary: the current target is local two-class static-scene classification, and promotion remains blocked until at least three independent recordings per class exist. [docs/model_training_workflow_overview.md](file:///F:/network_management/docs/model_training_workflow_overview.md)

## Risks, Gaps, And Questions

- The training workflow explicitly does not establish object, material, pose, biometric, or cross-geometry generalization claims. [docs/model_training_workflow_overview.md](file:///F:/network_management/docs/model_training_workflow_overview.md)
- Dual-link RF outputs remain provisional unless geometry, physics prediction, and measurement evidence agree; current collection windows are sequential rather than guaranteed same-instant measurements. [docs/runbooks/dual-ap-physics-mirror-workflow.md](file:///F:/network_management/docs/runbooks/dual-ap-physics-mirror-workflow.md)
- Runtime health and test outcomes must be validated separately before deployment; repository presence is not proof that Wazuh, Timesketch, routers, receivers, or workers are currently online.

## RAG Takeaways

- The repository combines RF sensing, network telemetry, Wazuh normalization, and forensic correlation. [README.md](file:///F:/network_management/README.md)
- `Deploy-RfBackend.ps1` is the canonical locked deployment path; `start_csi_pipeline.bat` is legacy recovery. [Deploy-RfBackend.ps1](file:///F:/network_management/Deploy-RfBackend.ps1)
- The Intel 5300 classifier is deliberately limited to a local two-class static-scene claim and is data-blocked pending contrastive captures. [docs/model_training_workflow_overview.md](file:///F:/network_management/docs/model_training_workflow_overview.md)
- Project details should be verified against the cited source and snapshot before operational use.

## Files Read

- [.gitignore](file:///F:/network_management/.gitignore)
- [Deploy-RfBackend.ps1](file:///F:/network_management/Deploy-RfBackend.ps1)
- [Forensic Logging & Monitoring/.gitignore](file:///F:/network_management/Forensic%20Logging%20%26%20Monitoring/.gitignore)
- [Forensic Logging & Monitoring/docker-compose.yml](file:///F:/network_management/Forensic%20Logging%20%26%20Monitoring/docker-compose.yml)
- [Forensic Logging & Monitoring/intel5300_translation/README.md](file:///F:/network_management/Forensic%20Logging%20%26%20Monitoring/intel5300_translation/README.md)
- [Forensic Logging & Monitoring/test_csi_recovery_static.ps1](file:///F:/network_management/Forensic%20Logging%20%26%20Monitoring/test_csi_recovery_static.ps1)
- [GITHUB_REPO_PREP.md](file:///F:/network_management/GITHUB_REPO_PREP.md)
- [README.md](file:///F:/network_management/README.md)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/Cargo.toml](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/Cargo.toml)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/Cargo.toml](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/Cargo.toml)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/src/error.rs](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/src/error.rs)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/src/lib.rs](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/src/lib.rs)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/src/traits.rs](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/src/traits.rs)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/src/types.rs](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/src/types.rs)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-core/src/utils.rs](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-core/src/utils.rs)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/crates/wifi-densepose-train/tests/fixtures/README.md](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/crates/wifi-densepose-train/tests/fixtures/README.md)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/docs/external_research_enrichment/canonical_external_feature_schema_v1.md](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/docs/external_research_enrichment/canonical_external_feature_schema_v1.md)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/docs/metadata_finetuning_strategy.md](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/docs/metadata_finetuning_strategy.md)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/docs/model_training_pipeline.md](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/docs/model_training_pipeline.md)
- [Wi-Fi Sensing & CSI Data Extraction/Model_training/scripts/test_collect_static_scenes.py](file:///F:/network_management/Wi-Fi%20Sensing%20%26%20CSI%20Data%20Extraction/Model_training/scripts/test_collect_static_scenes.py)
- [cleanup_c_space.ps1](file:///F:/network_management/cleanup_c_space.ps1)
- [docs/deep-research-report.md](file:///F:/network_management/docs/deep-research-report.md)
- [docs/model_training/README.md](file:///F:/network_management/docs/model_training/README.md)
- [docs/model_training/metadata_finetuning_strategy.md](file:///F:/network_management/docs/model_training/metadata_finetuning_strategy.md)
- [docs/model_training_workflow_overview.md](file:///F:/network_management/docs/model_training_workflow_overview.md)
- [docs/rf_sensing_physics_agent_context.md](file:///F:/network_management/docs/rf_sensing_physics_agent_context.md)
- [docs/runbooks/dual-ap-physics-mirror-workflow.md](file:///F:/network_management/docs/runbooks/dual-ap-physics-mirror-workflow.md)
- [physics_reference/app.py](file:///F:/network_management/physics_reference/app.py)
- [physics_reference/backlog_orchestrator.py](file:///F:/network_management/physics_reference/backlog_orchestrator.py)
- [physics_reference/orchestrator/diagnostics/lifecycle_report.py](file:///F:/network_management/physics_reference/orchestrator/diagnostics/lifecycle_report.py)
- [physics_reference/tests/test_orchestrator_refinement_dispatch.py](file:///F:/network_management/physics_reference/tests/test_orchestrator_refinement_dispatch.py)
- [physics_reference/tests/test_phase_d_orchestrator.py](file:///F:/network_management/physics_reference/tests/test_phase_d_orchestrator.py)
- [research/immediate_security_control_sprint/csi_rf_pipeline_evidence.md](file:///F:/network_management/research/immediate_security_control_sprint/csi_rf_pipeline_evidence.md)
- [research/immediate_security_control_sprint/implementation_phase_1_2/01_unifi_router_switch_evidence_checklist.md](file:///F:/network_management/research/immediate_security_control_sprint/implementation_phase_1_2/01_unifi_router_switch_evidence_checklist.md)
- [research/immediate_security_control_sprint/implementation_phase_3/dashboard/README.md](file:///F:/network_management/research/immediate_security_control_sprint/implementation_phase_3/dashboard/README.md)
- [research/immediate_security_control_sprint/implementation_phase_3/scripts/test_dashboard_contract_lint.py](file:///F:/network_management/research/immediate_security_control_sprint/implementation_phase_3/scripts/test_dashboard_contract_lint.py)
