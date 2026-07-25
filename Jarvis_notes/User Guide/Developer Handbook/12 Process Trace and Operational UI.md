---
id: "developer-process-trace-operational-ui"
title: "Process Trace and Operational UI"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-25T14:33:58Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "ui", "telemetry", "process-trace", "privacy", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.98
content_hash: "c8b6b791c60ba07a160114072d00abb5514f04eb466c0e6b789e889290a4f6a7"
lifecycle: "short_term"
schema_version: "jarvis_developer_handbook/v1"
---

# Process Trace And Operational UI

> [!abstract]
> Router Mode now separates a safe operational trace from the final answer. The trace communicates phase, route, tool, model, vault, approval, retry, blocker, and completion events without exposing hidden reasoning.

## Event Contract

`core/process_events.py` defines the session event boundary:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC event time |
| `category` | Router, capability, tool, model, vault, Canvas, workflow, speech, approval, or service |
| `source` | Emitting component or selected capability |
| `summary` | Short factual operational statement |
| `state` / `severity` | Running, completed, degraded, blocked, failed, and importance |
| `progress` | Optional normalized progress from 0 to 1 |
| `turn_id` / `correlation_id` | Bounded linkage to a turn or run |
| `detail` | Schema-redacted safe metadata only |
| `evidence_refs` | Paths or IDs, never raw evidence bodies |

The global event hub is thread-safe and capped at 250 events or 1 MiB. Subscribers receive immutable `ProcessEvent` records through queued Qt signals.

## Redaction Boundary

The hub rejects or redacts prompt bodies, system/developer prompts, message arrays, hidden reasoning fields, API keys, bearer headers, tokens, and secrets. It also applies secret-pattern redaction to summaries and nested details.

> [!danger] Not chain-of-thought
> A process event reports what subsystem ran and its observable state. It does not reconstruct or expose private model reasoning.

Trace export is explicit, redacted, session-scoped Markdown with:

```yaml
type: process-trace
rag_index: false
sensitivity: internal
```

## Desktop Layout

The existing HUD and camera stack remain unchanged. The Router Mode panel uses a nested vertical splitter:

1. Bounded Process Trace
2. Final answer/content

Controls include category filter, pause/resume display, follow newest, clear, copy selected, safe export, and expandable safe detail. Background housekeeping remains in history but does not force Router Mode open; a real router/tool/workflow/approval event does.

Splitter state is saved with `QSettings`. Secrets are never persisted.

## Command Palette

Press `Ctrl+K` to search common actions. Palette actions either open a read-only view or submit a normal JARVIS request. They do not call effectful tools directly.

Current entries include capabilities, create plan, local RAG search, recent vault changes, Canvas status, model lifecycle status, and Operations.

## Operations Dialog

Press `Ctrl+Shift+O` to open Operations. `core/operations_state.py` gathers telemetry on a worker thread:

- LM Studio reachability, loaded models, and active request count;
- vault watcher, pending external changes, and last index time;
- configured STT/TTS engines, with live transitions in Process Trace;
- MCP HTTP and optional Aletheia bridge reachability;
- recent workflow runs and item-state progress.

Pause, resume, review, cancel, and recover controls submit ordinary JARVIS commands. Existing dispatcher schemas and approval gates remain authoritative.

The left rail no longer claims `AI CORE ACTIVE` or `SEC CLEARED`. It displays verified `MODELS`, `VAULT`, and `SPEECH` states with detail tooltips. Offline, optional-offline, degraded, stopped, and unknown are represented honestly.

## Supplied Package Integration

The stable typed models, deterministic optional graph layout, and command-palette/controller patterns from `new-jarvis-ui-components-0.1.0` were promoted into the importable `jarvis_ui_components` package. The full wide workspace shell was not adopted because it conflicts with MARK's minimum window and existing HUD.

The point-force graph remains available for a future knowledge graph. Canvas uses the separate rectangle-aware deterministic service.

## Tests And Screenshots

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_process_events.py tests/test_process_trace_ui.py -q
python scripts/render_validation_artifacts.py
```

Desktop screenshots are generated at `820x580`, `980x700`, and `1920x1080` under:

`Mark-XLVIII-main/test_artifacts/vault-canvas-ui/desktop/`

## Related Notes

- [[10 Vault Change Awareness]]
- [[11 Safe Canvas Service and Relationships]]
- [[02 Capability Registry MCP and Safety]]
- [[07 Models Credentials Speech and Resource Lifecycle]]
