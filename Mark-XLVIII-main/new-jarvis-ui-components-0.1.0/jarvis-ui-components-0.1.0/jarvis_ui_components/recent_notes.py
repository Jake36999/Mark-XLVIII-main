from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .models import NoteItem, coerce_many
from .theme import Theme, panel_stylesheet


def _relative_time(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    now = datetime.now(value.tzinfo) if value.tzinfo else datetime.now()
    seconds = max(0, int((now - value).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


class RecentNotesWidget(QWidget):
    note_selected = pyqtSignal(str)
    note_activated = pyqtSignal(str)
    open_requested = pyqtSignal(str)
    ask_requested = pyqtSignal(str)
    pin_requested = pyqtSignal(str)
    mode_changed = pyqtSignal(str)

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._notes: dict[str, NoteItem] = {}
        self.setStyleSheet(panel_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("RECENT NOTES")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        self._mode = QComboBox()
        self._mode.addItem("Edited", "edited")
        self._mode.addItem("Viewed", "viewed")
        self._mode.addItem("Cited", "cited")
        self._mode.currentIndexChanged.connect(
            lambda: self.mode_changed.emit(self._mode.currentData())
        )
        header.addWidget(self._mode)
        layout.addLayout(header)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setWordWrap(True)
        self._list.currentItemChanged.connect(self._on_selected)
        self._list.itemDoubleClicked.connect(self._on_activated)
        layout.addWidget(self._list, stretch=1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        self._open = QPushButton("OPEN")
        self._ask = QPushButton("ASK")
        self._pin = QPushButton("PIN")
        self._open.setToolTip("Open the selected note")
        self._ask.setToolTip("Ask JARVIS about the selected note")
        self._pin.setToolTip("Pin or unpin the selected note")
        self._open.clicked.connect(lambda: self._emit_selected(self.open_requested))
        self._ask.clicked.connect(lambda: self._emit_selected(self.ask_requested))
        self._pin.clicked.connect(lambda: self._emit_selected(self.pin_requested))
        for button in (self._open, self._ask, self._pin):
            button.setEnabled(False)
            actions.addWidget(button)
        layout.addLayout(actions)

        if compact:
            self._ask.hide()
            self._mode.setMaximumWidth(78)

    def mode(self) -> str:
        return str(self._mode.currentData())

    def set_notes(self, notes: list[NoteItem | dict]) -> None:
        values = coerce_many(NoteItem, notes)
        self._notes = {note.id: note for note in values}
        self._list.clear()
        for note in values:
            item = QListWidgetItem()
            pin = "[PIN] " if note.pinned else ""
            project = note.project_id or "vault"
            updated = _relative_time(note.updated_at())
            item.setText(f"{pin}{note.title}\n{project}  |  {note.note_type}  |  {updated}")
            item.setData(Qt.ItemDataRole.UserRole, note.id)
            item.setToolTip(note.summary or note.path or note.title)
            item.setFont(QFont(Theme.UI, 9))
            item.setForeground(QBrush(QColor(Theme.TEXT)))
            self._list.addItem(item)
        self._update_actions()

    def selected_note_id(self) -> str:
        item = self._list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def _on_selected(self, current: QListWidgetItem | None, _previous) -> None:
        self._update_actions()
        if current:
            self.note_selected.emit(str(current.data(Qt.ItemDataRole.UserRole)))

    def _on_activated(self, item: QListWidgetItem) -> None:
        self.note_activated.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _emit_selected(self, signal) -> None:
        note_id = self.selected_note_id()
        if note_id:
            signal.emit(note_id)

    def _update_actions(self) -> None:
        enabled = bool(self.selected_note_id())
        for button in (self._open, self._ask, self._pin):
            button.setEnabled(enabled)
