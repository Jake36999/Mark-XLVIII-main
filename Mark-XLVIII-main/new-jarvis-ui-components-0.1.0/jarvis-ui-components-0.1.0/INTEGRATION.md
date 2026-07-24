# Integration Guide

## 1. Keep `ui.py` As The Facade

The current `JarvisUI` class is the public interface used by `main.py`. Keep
that class and move only new visual responsibilities into this package.

Do not import `jarvis_memory` or workflow actions directly inside individual
widgets. Build one provider in the application layer and give it to
`DashboardController`.

## 2. Wrap The Existing Centre View

The current centre view is `self._center_split`, containing the HUD/camera
stack and briefing panel. It becomes the LIVE page unchanged:

```python
self._dashboard_workspace = DashboardWorkspace()
self._dashboard_workspace.set_live_widget(self._center_split)
body.addWidget(self._dashboard_workspace, stretch=5)
```

Remove the original direct `body.addWidget(self._center_split, stretch=5)`
call. The fixed left and right rails can remain while the first integration is
tested.

## 3. Expose Provider Attachment

Add a small method to `JarvisUI` after the controller is available:

```python
def attach_dashboard_provider(self, provider, action_handler=None):
    controller = DashboardController(
        self._win._dashboard_workspace,
        provider,
        self._win,
    )
    controller.error.connect(
        lambda message: self._win._log_sig.emit(f"DASHBOARD: {message}")
    )
    if action_handler:
        controller.action_requested.connect(action_handler)
    self._win._dashboard_controller = controller
    controller.refresh_knowledge()
    controller.refresh_operations()
```

Keeping the controller as a window attribute prevents it from being garbage
collected while background work is active.

## 4. Map Existing JARVIS Capabilities

Recommended data sources:

| Provider method | Existing source |
| --- | --- |
| `get_graph` | `jarvis_memory` graph operation |
| `get_recent_notes` | SQLite note index plus dashboard open/citation history |
| `get_calendar` | Markdown task dates, reminders, workflow deadlines |
| `get_note` | Vault service by stable note ID |
| `get_operations` | Plan/workflow scheduler status |
| `get_health` | Speech, model lifecycle, RAG watcher, Aletheia, dashboard |

Normalize action-specific payloads in the provider. Do not make the widgets
understand every historical backend response shape.

## 5. Handle User Actions Centrally

Suggested dispatcher:

```python
def handle_dashboard_action(action: str, value):
    if action == "note.open":
        open_note_in_obsidian(value)
    elif action == "note.ask":
        submit_text_command(f"Use note {value} as context")
    elif action == "operation.cancel":
        cancel_operation(value)
    else:
        route_guarded_dashboard_action(action, value)
```

Actions that mutate Markdown, reschedule work, cancel processes, or approve a
plan must pass through the same confirmation and audit policy used by normal
JARVIS tool calls.

## 6. Optional Compact Widgets

After the workspace is stable, move the OpenAI session-key controls to the
existing setup/settings overlay. The recovered left-rail space can host:

```python
self._mini_graph = KnowledgeGraphWidget(compact=True)
self._mini_graph.setMinimumHeight(170)
lay.addWidget(self._mini_graph, stretch=1)
```

A compact `RecentNotesWidget(compact=True)` can sit above it. On the right,
place `CalendarAgendaWidget(compact=True)` in an Activity / Calendar / Files
tab control rather than stacking every panel vertically.

## 7. Responsive Follow-Up

The current `148px` and `340px` rails are fixed. A later pass should replace
the body `QHBoxLayout` with a horizontal `QSplitter`, set sensible minimums,
and persist sizes with `QSettings`. At narrow widths, collapse one rail rather
than shrinking graph or note content below a usable size.

## 8. Threading And Lifetime

- Provider methods run in `QThreadPool`; they must not manipulate widgets.
- Widget updates happen through queued Qt signals.
- Store `DashboardController` on the window.
- Keep SQLite transactions short and do not hold a write lock during embedding
  model calls.
- Debounce vault-watcher refresh events before calling `refresh_knowledge()`.

