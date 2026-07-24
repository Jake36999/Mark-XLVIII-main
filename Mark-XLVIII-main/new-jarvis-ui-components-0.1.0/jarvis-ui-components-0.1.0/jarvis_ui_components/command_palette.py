from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import CommandAction, coerce_many
from .theme import Theme, panel_stylesheet


class CommandPalette(QDialog):
    action_triggered = pyqtSignal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._actions: list[CommandAction] = []
        self._visible_actions: list[CommandAction] = []
        self.setModal(True)
        self.setWindowTitle("JARVIS Command Palette")
        self.setMinimumSize(560, 390)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(panel_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        label = QLabel("COMMAND PALETTE")
        label.setObjectName("SectionTitle")
        layout.addWidget(label)

        self._query = QLineEdit()
        self._query.setPlaceholderText("Search notes, projects, workflows, and commands...")
        self._query.textChanged.connect(self._filter)
        self._query.returnPressed.connect(self._trigger_current)
        layout.addWidget(self._query)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _item: self._trigger_current())
        layout.addWidget(self._list, stretch=1)

        hint = QLabel("ENTER run  |  ESC close  |  UP/DOWN navigate")
        hint.setStyleSheet(
            f"color: {Theme.TEXT_DIM}; font-family: {Theme.MONO}; font-size: 8pt;"
        )
        layout.addWidget(hint)

    def set_actions(self, actions: list[CommandAction | dict]) -> None:
        self._actions = coerce_many(CommandAction, actions)
        self._filter(self._query.text())

    def open_palette(self, initial_query: str = "") -> None:
        if self.parentWidget():
            parent_rect = self.parentWidget().geometry()
            self.resize(min(720, max(560, parent_rect.width() - 140)), 440)
        self._query.setText(initial_query)
        self._query.selectAll()
        self.show()
        self.raise_()
        self.activateWindow()
        self._query.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in {Qt.Key.Key_Down, Qt.Key.Key_Up}:
            current = self._list.currentRow()
            delta = 1 if event.key() == Qt.Key.Key_Down else -1
            if self._list.count():
                self._list.setCurrentRow((current + delta) % self._list.count())
            return
        super().keyPressEvent(event)

    def _filter(self, query: str) -> None:
        tokens = [token for token in query.casefold().split() if token]
        ranked: list[tuple[int, CommandAction]] = []
        for action in self._actions:
            haystack = action.searchable_text()
            if not all(token in haystack for token in tokens):
                continue
            title = action.title.casefold()
            score = sum(5 if title.startswith(token) else 1 for token in tokens)
            ranked.append((score, action))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].group, pair[1].title))
        self._visible_actions = [action for _score, action in ranked]
        self._list.clear()
        previous_group = ""
        for action in self._visible_actions:
            prefix = f"[{action.group}]  " if action.group != previous_group else "          "
            item = QListWidgetItem(f"{prefix}{action.title}\n          {action.subtitle}")
            item.setToolTip(action.subtitle or action.title)
            self._list.addItem(item)
            previous_group = action.group
        if self._list.count():
            self._list.setCurrentRow(0)

    def _trigger_current(self) -> None:
        index = self._list.currentRow()
        if not 0 <= index < len(self._visible_actions):
            return
        action = self._visible_actions[index]
        self.action_triggered.emit(action.id, dict(action.payload))
        self.accept()

