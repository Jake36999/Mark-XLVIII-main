from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable, Protocol

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from .workspace import DashboardWorkspace


class DashboardDataProvider(Protocol):
    """Synchronous provider contract. DashboardController runs calls off-thread."""

    def get_graph(self, scope: str = "all", scope_id: str = "") -> Any: ...

    def get_recent_notes(self, mode: str = "edited", limit: int = 20) -> Any: ...

    def get_calendar(self, start: str, end: str) -> Any: ...

    def get_note(self, note_id: str) -> Any: ...

    def get_operations(self) -> Any: ...

    def get_health(self) -> Any: ...


def _decode(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class _WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)


class _CallWorker(QRunnable):
    def __init__(self, fn: Callable[[], Any], on_result: Callable[[Any], None]) -> None:
        super().__init__()
        self.fn = fn
        self.on_result = on_result
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit((self.on_result, _decode(self.fn())))
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")


class DashboardController(QObject):
    """Connect a provider to DashboardWorkspace without blocking the GUI thread."""

    error = pyqtSignal(str)
    action_requested = pyqtSignal(str, object)

    def __init__(
        self,
        workspace: DashboardWorkspace,
        provider: DashboardDataProvider,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.provider = provider
        self.pool = QThreadPool.globalInstance()

        knowledge = workspace.knowledge
        knowledge.note_requested.connect(self.load_note)
        knowledge.graph_refresh_requested.connect(self.refresh_graph)
        knowledge.recent_mode_changed.connect(self.refresh_recent)
        for name, signal in {
            "note.open": knowledge.note_open_requested,
            "note.ask": knowledge.note_ask_requested,
            "note.edit": knowledge.note_edit_requested,
            "note.pin": knowledge.note_pin_requested,
            "calendar.open": knowledge.calendar_item_requested,
            "calendar.create": knowledge.create_for_date_requested,
            "operation.cancel": workspace.operations.cancel_requested,
            "operation.approve": workspace.operations.approve_requested,
            "operation.review": workspace.operations.review_requested,
        }.items():
            signal.connect(lambda value, action=name: self.action_requested.emit(action, value))
        workspace.command_action_triggered.connect(self.action_requested.emit)
        workspace.refresh_requested.connect(self.refresh_mode)
        workspace.operations.refresh_requested.connect(self.refresh_operations)

    def refresh_mode(self, mode: str) -> None:
        if mode == "knowledge":
            self.refresh_knowledge()
        elif mode == "operations":
            self.refresh_operations()

    def refresh_knowledge(self) -> None:
        self.refresh_graph()
        self.refresh_recent(self.workspace.knowledge.recent_notes.mode())
        self.refresh_calendar()

    def refresh_graph(self, scope: str = "all", scope_id: str = "") -> None:
        self._run(
            lambda: self.provider.get_graph(scope, scope_id),
            self._apply_graph,
        )

    def refresh_recent(self, mode: str = "edited") -> None:
        self._run(
            lambda: self.provider.get_recent_notes(mode, 20),
            lambda data: self.workspace.knowledge.recent_notes.set_notes(
                self._list_payload(data, "notes", "results")
            ),
        )

    def refresh_calendar(self, start: str = "", end: str = "") -> None:
        year = date.today().year
        start = start or f"{year}-01-01"
        end = end or f"{year + 1}-01-01"
        self._run(
            lambda: self.provider.get_calendar(start, end),
            lambda data: self.workspace.knowledge.calendar.set_items(
                self._list_payload(data, "items", "events")
            ),
        )

    def load_note(self, note_id: str) -> None:
        self._run(
            lambda: self.provider.get_note(note_id),
            lambda data: self.workspace.knowledge.note_viewer.show_note(
                data.get("note", data) if isinstance(data, dict) else data
            ),
        )

    def refresh_operations(self) -> None:
        self._run(
            self.provider.get_operations,
            lambda data: self.workspace.operations.set_operations(
                self._list_payload(data, "operations", "items")
            ),
        )
        self._run(
            self.provider.get_health,
            lambda data: self.workspace.operations.set_health(
                self._list_payload(data, "health", "items")
            ),
        )

    def _apply_graph(self, data: Any) -> None:
        if not isinstance(data, dict):
            raise TypeError("Graph provider must return a mapping with nodes and edges")
        self.workspace.knowledge.graph.set_graph(
            list(data.get("nodes") or []),
            list(data.get("edges") or []),
        )

    def _run(self, fn: Callable[[], Any], on_result: Callable[[Any], None]) -> None:
        worker = _CallWorker(fn, on_result)
        worker.signals.result.connect(self._deliver_result)
        worker.signals.error.connect(self._deliver_error)
        self.pool.start(worker)

    def _deliver_result(self, delivery: object) -> None:
        """Qt queues this slot onto the controller's GUI thread."""
        callback, value = delivery
        try:
            callback(value)
        except Exception as exc:
            self.error.emit(f"Dashboard update failed: {type(exc).__name__}: {exc}")

    def _deliver_error(self, message: str) -> None:
        self.error.emit(message)

    @staticmethod
    def _list_payload(data: Any, *keys: str) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []
