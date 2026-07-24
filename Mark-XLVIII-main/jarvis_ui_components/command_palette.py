"""Searchable command palette adapted to MARK's existing command boundary."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from .models import CommandAction, coerce_many


class CommandPalette(QDialog):
    action_triggered = pyqtSignal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._actions: list[CommandAction] = []
        self._visible_actions: list[CommandAction] = []
        self.setModal(True)
        self.setWindowTitle("JARVIS Command Palette")
        self.setMinimumSize(520, 360)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(
            "QDialog{background:#001018;border:1px solid #00a8c8;}"
            "QLabel{color:#7addeb;font-family:'Courier New';}"
            "QLineEdit,QListWidget{background:#00070c;color:#b6edf3;border:1px solid #07546a;padding:7px;}"
            "QListWidget::item:selected{background:#073448;color:#00e5ff;}"
        )
        layout = QVBoxLayout(self)
        title = QLabel("COMMAND PALETTE")
        layout.addWidget(title)
        self._query = QLineEdit()
        self._query.setPlaceholderText("Search tools, workflows, vault, and operations...")
        self._query.textChanged.connect(self._filter)
        self._query.returnPressed.connect(self._trigger_current)
        layout.addWidget(self._query)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _item: self._trigger_current())
        layout.addWidget(self._list, 1)
        layout.addWidget(QLabel("ENTER run  |  ESC close  |  UP/DOWN navigate"))

    def set_actions(self, actions: list[CommandAction | dict]) -> None:
        self._actions = coerce_many(CommandAction, actions)
        self._filter(self._query.text())

    def open_palette(self, initial_query: str = "") -> None:
        self._query.setText(initial_query)
        self._query.selectAll()
        self.show()
        self.raise_()
        self.activateWindow()
        self._query.setFocus()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in {Qt.Key.Key_Down, Qt.Key.Key_Up} and self._list.count():
            delta = 1 if event.key() == Qt.Key.Key_Down else -1
            self._list.setCurrentRow((self._list.currentRow() + delta) % self._list.count())
            return
        super().keyPressEvent(event)

    def _filter(self, query: str) -> None:
        tokens = [token for token in query.casefold().split() if token]
        ranked = []
        for action in self._actions:
            haystack = action.searchable_text()
            if all(token in haystack for token in tokens):
                score = sum(5 if action.title.casefold().startswith(token) else 1 for token in tokens)
                ranked.append((score, action))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].group, pair[1].title))
        self._visible_actions = [action for _, action in ranked]
        self._list.clear()
        for action in self._visible_actions:
            item = QListWidgetItem(f"[{action.group}]  {action.title}\n{action.subtitle}")
            item.setToolTip(action.subtitle or action.title)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _trigger_current(self) -> None:
        index = self._list.currentRow()
        if 0 <= index < len(self._visible_actions):
            action = self._visible_actions[index]
            self.action_triggered.emit(action.id, dict(action.payload))
            self.accept()
