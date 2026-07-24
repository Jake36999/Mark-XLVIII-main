---
id: "project-brief-mark-platform"
title: "Project Brief - Mark Platform"
type: "report"
status: "complete"
created: "2026-07-22T00:08:36Z"
updated: "2026-07-23T09:25:32Z"
project_id: "jarvis_notes"
source: "F:\\Mark-XLVIII-main"
tags: ["project-learning", "repository", "read-only", "mark-platform", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.8
valid_from: "2026-07-22T01:24:58Z"
review_after: ""
source_version: 9
content_hash: "9838875ba62a95210837561cd84bc248f7fe559c20657ea991adf770378f9719"
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
files_read_count: 16
inventory_file_count: 355
memory_tier: "short_term"
project_key: "mark_platform"
project_root: "F:\\Mark-XLVIII-main"
read_only: true
snapshot_hash: "a90bcc490f1e510695496e511e86ccc36bb23b74274df791b1a7012005934c58"
workflow_id: "project_repository_learning/v1"
---

# Obsidian Project Brief: MARK XLVIII

## Executive Summary  
MARK XLVIII is a cross-platform personal AI assistant enabling real-time voice interaction, system control, and autonomous task execution via Gemini Live API. It integrates agent orchestration, workflow planning, and local document analysis in a distributed, file-based architecture. [Mark-XLVIII-main/readme.md](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/readme.md)

## Repository Profile  
Root: `F:\\Mark-XLVIII-main`, 355 files, 13.8MB. Primary components include `actions/`, `core/`, and `config/` directories. Git branch: `main` (commit: `794368f`). Sensitive files skipped. [Mark-XLVIII-main/readme.md](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/readme.md)

## Architecture And Components  
Core modules: `actions/` (file, browser, screen control), `core/` (model routing, memory), and `capability_registry` for tool/workflow routing. Functional layers: voice (STT/TTS), planning, model routing, and system control. [Mark-XLVIII-main/main.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/main.py)

## Entry Points And Workflows  
- `main.py`: Initializes runtime and assistant mode.  
- `clawteam` CLI (via ClawTeam-OpenClaw) for agent orchestration.  
- `document_workflow.py`: Resumable, chunked extraction of local files via OCR.  
- `project_operator.py`: Planned; will enforce policy-gated operations. [Mark-XLVIII-main/actions/document_workflow.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/actions/document_workflow.py)

## Dependencies And Tests  
Relies on Gemini Live API; Python 3.10+, with `pytesseract`, `playwright`, `opencv-python`. Tests: 76 total; includes `test_capability_registry`, `test_lifecycle`. Configuration via `runtime.json`, `project_registry.json`. [Mark-XLVIII-main/tests/test_capability_registry.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/tests/test_capability_registry.py)

## Operational Guidance  
Operate in operator mode via `project_registry.json`. Use `clawteam` CLI for agent control; validate workflows via `live-validate-workflow.py`. Avoid direct access to `project_operator.py`—it is planned.  

## Risks, Gaps, And Questions  
- `project_operator.py` exists only in documentation; no code.  
- Stale documentation: `project_operator.md` references non-existent file.  
- `dual_orchestrator` workflow not fully implemented.  
- `clawteam` CLI modifications in git show active development.  

## Files Read  

- [ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/CLAUDE.md](file:///F:/Mark-XLVIII-main/ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/CLAUDE.md)
- [ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/clawteam/board/server.py](file:///F:/Mark-XLVIII-main/ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/clawteam/board/server.py)
- [ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/docs/skills/clawteam/references/workflows.md](file:///F:/Mark-XLVIII-main/ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/docs/skills/clawteam/references/workflows.md)
- [ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/pyproject.toml](file:///F:/Mark-XLVIII-main/ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/pyproject.toml)
- [ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/tests/test_lifecycle.py](file:///F:/Mark-XLVIII-main/ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/tests/test_lifecycle.py)
- [ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/website/src/App.jsx](file:///F:/Mark-XLVIII-main/ClawTeam-OpenClaw-main/ClawTeam-OpenClaw-main/website/src/App.jsx)
- [Mark-XLVIII-main/actions/capability_registry.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/actions/capability_registry.py)
- [Mark-XLVIII-main/actions/document_workflow.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/actions/document_workflow.py)
- [Mark-XLVIII-main/config/project_registry.json](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/config/project_registry.json)
- [Mark-XLVIII-main/config/runtime.json](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/config/runtime.json)
- [Mark-XLVIII-main/docs/superpowers/plans/2026-07-06-mark-project-operator.md](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/docs/superpowers/plans/2026-07-06-mark-project-operator.md)
- [Mark-XLVIII-main/main.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/main.py)
- [Mark-XLVIII-main/memory/memory_manager.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/memory/memory_manager.py)
- [Mark-XLVIII-main/readme.md](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/readme.md)
- [Mark-XLVIII-main/requirements.txt](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/requirements.txt)
- [Mark-XLVIII-main/tests/test_capability_registry.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/tests/test_capability_registry.py)

## RAG Takeaways  
- `project_operator.py` is planned but not implemented.  
- `dual_orchestrator` workflow exists in schema but not in code.  
- `clawteam` CLI is actively developed with live file edits.  
- `capability_registry` uses stateless selectors for efficiency.  
- `document_workflow.py` supports resumable, chunked file analysis.
