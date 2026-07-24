from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .calendar_panel import CalendarAgendaWidget
from .command_palette import CommandPalette
from .knowledge_graph import KnowledgeGraphWidget
from .models import CommandAction
from .note_viewer import NoteViewer
from .operations_view import OperationsView
from .recent_notes import RecentNotesWidget
from .theme import Theme, panel_stylesheet
from .workspace_switcher import WorkspaceSwitcher


class KnowledgeWorkspace(QWidget):
    note_requested = pyqtSignal(str)
    note_open_requested = pyqtSignal(str)
    note_ask_requested = pyqtSignal(str)
    note_edit_requested = pyqtSignal(str)
    note_pin_requested = pyqtSignal(str)
    calendar_item_requested = pyqtSignal(str)
    create_for_date_requested = pyqtSignal(str)
    graph_refresh_requested = pyqtSignal()
    recent_mode_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(panel_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.graph = KnowledgeGraphWidget()
        split.addWidget(self.graph)

        self.tabs = QTabWidget()
        self.note_viewer = NoteViewer()
        self.recent_notes = RecentNotesWidget()
        self.calendar = CalendarAgendaWidget()
        self.tabs.addTab(self.note_viewer, "NOTE")
        self.tabs.addTab(self.recent_notes, "RECENT")
        self.tabs.addTab(self.calendar, "CALENDAR")
        self.tabs.setMinimumWidth(300)
        split.addWidget(self.tabs)
        split.setSizes([650, 350])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        layout.addWidget(split)

        self.graph.node_selected.connect(self._request_note)
        self.graph.node_activated.connect(self.note_open_requested.emit)
        self.graph.refresh_requested.connect(self.graph_refresh_requested.emit)
        self.recent_notes.note_selected.connect(self._request_note)
        self.recent_notes.note_activated.connect(self.note_open_requested.emit)
        self.recent_notes.open_requested.connect(self.note_open_requested.emit)
        self.recent_notes.ask_requested.connect(self.note_ask_requested.emit)
        self.recent_notes.pin_requested.connect(self.note_pin_requested.emit)
        self.recent_notes.mode_changed.connect(self.recent_mode_changed.emit)
        self.calendar.item_activated.connect(self.calendar_item_requested.emit)
        self.calendar.create_requested.connect(self.create_for_date_requested.emit)
        self.note_viewer.open_requested.connect(self.note_open_requested.emit)
        self.note_viewer.ask_requested.connect(self.note_ask_requested.emit)
        self.note_viewer.edit_requested.connect(self.note_edit_requested.emit)
        self.note_viewer.pin_requested.connect(self.note_pin_requested.emit)

    def _request_note(self, note_id: str) -> None:
        self.tabs.setCurrentWidget(self.note_viewer)
        self.note_requested.emit(note_id)


class DashboardWorkspace(QWidget):
    mode_changed = pyqtSignal(str)
    refresh_requested = pyqtSignal(str)
    command_action_triggered = pyqtSignal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(panel_stylesheet())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav = QWidget()
        nav.setStyleSheet(
            f"background: {Theme.PANEL}; border-bottom: 1px solid {Theme.BORDER};"
        )
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(8, 5, 8, 5)
        nav_layout.setSpacing(6)
        self.switcher = WorkspaceSwitcher()
        self.switcher.mode_changed.connect(self.set_mode)
        nav_layout.addWidget(self.switcher)
        nav_layout.addStretch()
        palette_button = QPushButton("COMMANDS  [CTRL+K]")
        palette_button.clicked.connect(lambda: self.palette.open_palette())
        nav_layout.addWidget(palette_button)
        refresh = QPushButton("REFRESH")
        refresh.clicked.connect(lambda: self.refresh_requested.emit(self.mode()))
        nav_layout.addWidget(refresh)
        layout.addWidget(nav)

        self.stack = QStackedWidget()
        self._live_placeholder = QLabel("Attach the existing JARVIS live view here.")
        self._live_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._live_placeholder.setStyleSheet(f"color: {Theme.TEXT_DIM};")
        self.stack.addWidget(self._live_placeholder)
        self.knowledge = KnowledgeWorkspace()
        self.operations = OperationsView()
        self.stack.addWidget(self.knowledge)
        self.stack.addWidget(self.operations)
        layout.addWidget(self.stack, stretch=1)

        self.palette = CommandPalette(self)
        self.palette.set_actions(self._default_actions())
        self.palette.action_triggered.connect(self._on_palette_action)

        self._shortcuts: list[QShortcut] = []
        for index, mode in enumerate(WorkspaceSwitcher.MODES, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda selected=mode: self.set_mode(selected))
            self._shortcuts.append(shortcut)
        palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        palette_shortcut.activated.connect(lambda: self.palette.open_palette())
        self._shortcuts.append(palette_shortcut)

    def set_live_widget(self, widget: QWidget) -> None:
        current = self.stack.widget(0)
        self.stack.removeWidget(current)
        if current is self._live_placeholder:
            current.deleteLater()
        self.stack.insertWidget(0, widget)

    def set_mode(self, mode: str) -> None:
        normalized = mode.casefold()
        if normalized not in WorkspaceSwitcher.MODES:
            raise ValueError(f"Unknown dashboard mode: {mode}")
        index = WorkspaceSwitcher.MODES.index(normalized)
        changed = self.stack.currentIndex() != index
        self.stack.setCurrentIndex(index)
        self.switcher.set_mode(normalized, emit=False)
        if changed:
            self.mode_changed.emit(normalized)

    def mode(self) -> str:
        return WorkspaceSwitcher.MODES[self.stack.currentIndex()]

    def set_command_actions(self, actions: list[CommandAction | dict]) -> None:
        merged = self._default_actions() + [CommandAction.from_mapping(value) for value in actions]
        self.palette.set_actions(merged)

    def _on_palette_action(self, action_id: str, payload: object) -> None:
        if action_id.startswith("workspace."):
            self.set_mode(action_id.split(".", 1)[1])
            return
        if action_id == "dashboard.refresh":
            self.refresh_requested.emit(self.mode())
            return
        self.command_action_triggered.emit(action_id, payload)

    @staticmethod
    def _default_actions() -> list[CommandAction]:
        return [
            CommandAction("workspace.live", "Open Live workspace", group="Navigation"),
            CommandAction("workspace.knowledge", "Open Knowledge workspace", group="Navigation"),
            CommandAction("workspace.operations", "Open Operations workspace", group="Navigation"),
            CommandAction("dashboard.refresh", "Refresh current workspace", group="Dashboard"),
        ]
