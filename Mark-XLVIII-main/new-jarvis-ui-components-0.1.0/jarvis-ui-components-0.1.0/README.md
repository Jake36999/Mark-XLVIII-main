# JARVIS UI Components

Reusable PyQt6 components for adding knowledge, calendar, recent-note, and
operations workspaces to the MARK XLVIII desktop interface.

This package is additive. It does not replace or modify the supplied `ui.py`.
Its data access is callback-driven so the UI stays independent of
`jarvis_memory`, reminders, model lifecycle, and workflow implementation
details.

## Included Components

- `DashboardWorkspace`: LIVE / KNOWLEDGE / OPERATIONS mode shell.
- `KnowledgeGraphWidget`: interactive native graph with search, zoom, pan,
  explicit-link edges, and optional semantic edges.
- `RecentNotesWidget`: Edited / Viewed / Cited note lists.
- `CalendarAgendaWidget`: month calendar plus task, reminder, and workflow
  agenda.
- `NoteViewer`: Markdown preview with Open, Ask, Edit, and Pin signals.
- `OperationsView`: health chips, workflow state, progress, approvals,
  reviews, and cancellation signals.
- `CommandPalette`: searchable keyboard command launcher (`Ctrl+K`).
- `DashboardController`: runs synchronous provider calls through Qt's thread
  pool and safely updates widgets on the GUI thread.
- Typed data contracts for notes, graph nodes and edges, calendar entries,
  operations, health, and commands.
- A runnable demo and focused pure-Python tests.

## Requirements

- Python 3.10+
- PyQt6 6.6+

The graph is implemented with native Qt graphics and does not require
PyQt-WebEngine, Node.js, a CDN, or a second web server. It intentionally limits
the full graph to 420 high-value nodes and the compact graph to 180 nodes.
Large-vault rendering can later be swapped for a WebGL implementation without
changing the provider contract.

## Install

From the extracted folder:

```powershell
python -m pip install -e .
```

Or install the prebuilt pure-Python package:

```powershell
python -m pip install .\dist\jarvis_ui_components-0.1.0-py3-none-any.whl
```

Or place the `jarvis_ui_components` directory beside the current `ui.py`.

## Run The Demo

```powershell
python -m jarvis_ui_components.demo
```

The demo uses synthetic local data. It does not access the JARVIS vault,
models, microphone, network, or project files.

## Minimal Integration

In `ui.py`, import the new workspace:

```python
from jarvis_ui_components import DashboardWorkspace
```

Replace the line that adds `self._center_split` directly to the body:

```python
body.addWidget(self._center_split, stretch=5)
```

with:

```python
self._dashboard_workspace = DashboardWorkspace()
self._dashboard_workspace.set_live_widget(self._center_split)
body.addWidget(self._dashboard_workspace, stretch=5)
```

The existing HUD, camera stack, and briefing splitter remain the LIVE
workspace. The package adds the two new workspaces around them.

Then attach a provider after the JARVIS actions are initialized:

```python
from jarvis_ui_components import DashboardController

self._dashboard_controller = DashboardController(
    self._dashboard_workspace,
    provider,
    self,
)
self._dashboard_controller.error.connect(self._log.append_log)
self._dashboard_controller.action_requested.connect(handle_dashboard_action)
```

See [INTEGRATION.md](INTEGRATION.md) and
[`examples/callback_provider.py`](examples/callback_provider.py) for the full
contract.

## Provider Contract

Provider methods are synchronous. `DashboardController` calls them in Qt's
global thread pool, so they may safely wrap SQLite, vault scans, or local HTTP
requests without freezing the interface.

```python
class DashboardDataProvider:
    def get_graph(self, scope="all", scope_id=""): ...
    def get_recent_notes(self, mode="edited", limit=20): ...
    def get_calendar(self, start, end): ...
    def get_note(self, note_id): ...
    def get_operations(self): ...
    def get_health(self): ...
```

Methods may return Python dictionaries/lists or JSON strings.

### Graph

```json
{
  "nodes": [
    {"id": "note-1", "label": "Vault Memory", "kind": "note", "project_id": "mark_platform", "score": 2.4}
  ],
  "edges": [
    {"source": "note-1", "target": "tag-rag", "kind": "tag", "weight": 1.0}
  ]
}
```

Suggested edge kinds are `link`, `tag`, `project`, `citation`, and `semantic`.
Semantic edges are hidden by default so embedding similarity is never confused
with an explicit Obsidian link.

### Recent Notes

```json
{
  "notes": [
    {
      "id": "note-1",
      "title": "Vault Memory",
      "path": "Systems/Vault Memory.md",
      "summary": "Local-first RAG design",
      "project_id": "mark_platform",
      "note_type": "report",
      "updated": "2026-07-22T13:20:00",
      "tags": ["rag", "obsidian"]
    }
  ]
}
```

### Calendar

```json
{
  "items": [
    {
      "id": "task-1",
      "title": "Review dashboard plan",
      "start": "2026-07-24T15:00:00",
      "kind": "task",
      "status": "open",
      "source_id": "note-1"
    }
  ]
}
```

### Operations And Health

```json
{
  "operations": [
    {"id": "run-1", "title": "Reindex vault", "state": "running", "progress": 62}
  ]
}
```

```json
{
  "health": [
    {"id": "rag", "label": "RAG", "state": "healthy", "detail": "37 notes indexed"}
  ]
}
```

## Action Boundary

The package does not directly write vault files or execute plans. User actions
are emitted through `DashboardController.action_requested`:

- `note.open`
- `note.ask`
- `note.edit`
- `note.pin`
- `calendar.open`
- `calendar.create`
- `operation.cancel`
- `operation.approve`
- `operation.review`

The host application remains responsible for path validation, confirmation
gates, atomic Markdown writes, revision checks, and audit logging.

## Validation

```powershell
python -m compileall jarvis_ui_components
python -m unittest discover -s tests -v
```

The standard-library test suite covers mapping compatibility and deterministic graph layout.
Run the demo on the JARVIS machine for the visual smoke test because it already
has the PyQt6 desktop runtime.
