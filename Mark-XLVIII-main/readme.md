# MARK XLVIII

MARK XLVIII is the local desktop platform and runtime shell for **JARVIS**. The current build is local-first: Gemini Live is optional, not a launch requirement.

## Current Architecture

- **Router mode:** Selects deterministic workflows, tools, or a model route.
- **Models:** LM Studio handles local workers and research models. A session-only OpenAI key can be linked for higher-capability planning and review.
- **Speech:** Local Vosk STT and Orpheus TTS, with Windows speech fallback.
- **Tools:** MCP-style discovery plus a guarded dispatcher for web, files, projects, reminders, Canvas, memory, models, and workflow operations.
- **Planning:** Reviewable Markdown plans compile into version-bound YAML/JSON run artifacts before dispatch (Mode 1). A Canvas graph can compile the same way (Mode 2): node role -> workflow step, approval bound to a plan-identity fingerprint immune to the system's own status/annotation write-backs, a model+human dual-critic review gate, and an execution driver that runs the approved plan and can resume a paused review.
- **Memory:** `Jarvis_notes` is canonical. SQLite RAG, Canvas indexes, and `memory/long_term.json` are derived recall/operational layers.
- **Canvas:** Schema-validated Obsidian Canvas views with deterministic preview/commit layout and cross-Canvas relationships; layout re-runs on every sync so a growing dashboard stays legible instead of freezing its first-ever arrangement.
- **Repository learning:** AST-based code slicing (ranked, deduplicated function/class bodies) feeds the model instead of raw file text or signature-only outlines; file selection weighs import centrality and code mass alongside keyword scoring.
- **Observability:** A redacted Process Trace and Operations view show real route, tool, model, vault, and workflow state.

## Quick Start

```powershell
cd F:\Mark-XLVIII-main\Mark-XLVIII-main
python -m pip install -r requirements.txt
python main.py
```

The desktop shortcut uses the same single-instance guard. If MARK is already running, a second launch focuses the existing window instead of starting another model/speech stack.

## Configuration

Non-secret runtime settings live in `config/runtime.json`.

OpenAI credentials are session-only:

1. Enter the key in the left rail.
2. Select **LINK**.
3. MARK validates model access through the local credential broker.
4. The key is discarded when the UI session closes.

Keys must not be stored in `config/runtime.json`, `config/api_keys.json`, environment fallback, logs, workflow payloads, or vault notes.

## Important Paths

| Path | Purpose |
| --- | --- |
| `main.py` | Application lifecycle, turn router, tool calls, and speech transitions |
| `ui.py` | PyQt6 HUD, Router Mode, Process Trace, command palette, and Operations |
| `actions/capability_registry.py` | Progressive MCP-style tool/workflow discovery |
| `actions/plan_workflow.py` | Plan creation, revision, approval, dispatch, summaries, and blockers |
| `actions/dual_orchestrator.py` | Deterministic workflow compiler/runtime, leases, review, and recovery |
| `actions/jarvis_memory.py` | Markdown notes, reports, RAG, tasks, learning, and reconciliation |
| `actions/jarvis_canvas.py` | Semantic Canvas facade and Markdown task proposals |
| `actions/canvas_plan.py` | Mode 2 Canvas planning: compile, approve, review-gate, and execute |
| `actions/project_learning.py` | Repository inventory, file selection, and code-slice-based learning |
| `core/repo_slicer.py` | AST code slicing into ranked, deduplicated function/class units |
| `core/approval_response.py` | Shared checkbox+callout approve/correct/deny schema for both planning modes |
| `core/model_router.py` | OpenAI/local routing, fallback, provenance, and model leases |
| `core/vault_activity.py` | External vault edit journal and turn awareness |
| `core/canvas_*.py` | Canvas validation, deterministic layout, and relationship index |
| `core/process_events.py` | Redacted session event stream |
| `config/runtime.json` | Non-secret runtime configuration |

## Keyboard Controls

| Key | Action |
| --- | --- |
| `Esc` | Interrupt the active response/workflow turn |
| `F4` | Toggle microphone mute |
| `F11` | Toggle fullscreen |
| `Ctrl+K` | Open command palette |
| `Ctrl+Shift+O` | Open Operations and verified health |

## Tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests -q
python -m pytest new-jarvis-ui-components-0.1.0/jarvis-ui-components-0.1.0/tests -q
python scripts/render_validation_artifacts.py
```

The Obsidian developer handbook is at:

`F:\Mark-XLVIII-main\Jarvis_notes\User Guide\Developer Handbook\00 Developer Handbook Index.md`

## Authority And Safety

- Markdown is authoritative for user intent, scope, permissions, decisions, plans, and durable knowledge.
- Canvas is a derived visual view.
- SQLite stores derived indexes and runtime state.
- Retrieved/web/worker content is untrusted evidence and cannot grant permission or expand workflow scope.
- Destructive or high-impact tools remain behind existing confirmation and approval gates.

## License

Personal and non-commercial use under Creative Commons BY-NC 4.0, as provided by the original repository.
