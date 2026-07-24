"""Progressively disclosed health and workflow operations dialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QToolBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import HealthItem, OperationItem, coerce_many


STATE_COLORS = {
    "ready": "#3dff9b",
    "configured": "#3dff9b",
    "running": "#00e5ff",
    "completed": "#3dff9b",
    "degraded": "#ffbd45",
    "stopped": "#ffbd45",
    "optional-offline": "#7fa7af",
    "offline": "#ff5577",
    "failed": "#ff5577",
    "unknown": "#7fa7af",
}


class OperationsDialog(QDialog):
    refresh_requested = pyqtSignal()
    action_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._operations: dict[str, OperationItem] = {}
        self.setWindowTitle("JARVIS Operations")
        self.resize(760, 620)
        self.setStyleSheet(
            "QDialog{background:#000b12;color:#b6edf3;}"
            "QLabel,QTreeWidget,QTextEdit,QToolBox,QPushButton{font-family:'Courier New';font-size:8pt;}"
            "QTreeWidget,QTextEdit{background:#00060a;color:#b6edf3;border:1px solid #074456;}"
            "QPushButton{background:#00131d;color:#8fe3ed;border:1px solid #076079;padding:5px 8px;}"
        )
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("OPERATIONS AND HEALTH"))
        header.addStretch()
        refresh = QPushButton("REFRESH")
        refresh.clicked.connect(self.refresh_requested)
        header.addWidget(refresh)
        layout.addLayout(header)
        self._health = QToolBox()
        self._health.setMaximumHeight(210)
        layout.addWidget(self._health)
        self._table = QTreeWidget()
        self._table.setHeaderLabels(["RUN", "STATE", "PROGRESS", "UPDATED"])
        self._table.currentItemChanged.connect(self._selected)
        layout.addWidget(self._table, 1)
        actions = QHBoxLayout()
        for label, action in (("PAUSE", "pause"), ("RESUME", "resume"), ("REVIEW", "review"), ("CANCEL", "cancel"), ("RECOVER", "recover")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=action: self._request(value))
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(120)
        layout.addWidget(self._detail)

    def set_state(self, payload: dict) -> None:
        while self._health.count():
            self._health.removeItem(0)
        groups = {
            "Speech pipeline": {"speech"},
            "Model lifecycle": {"models"},
            "Vault and RAG": {"vault"},
            "Services and connectivity": {"mcp", "aletheia"},
        }
        health = coerce_many(HealthItem, payload.get("health") or [])
        for title, ids in groups.items():
            page = QWidget()
            page_layout = QVBoxLayout(page)
            matching = [item for item in health if item.id in ids]
            for item in matching:
                color = STATE_COLORS.get(item.state, STATE_COLORS["unknown"])
                label = QLabel(f"{item.label.upper()}: {item.state.upper()}\n{item.detail}")
                label.setWordWrap(True)
                label.setStyleSheet(f"color:{color};padding:5px;border:1px solid {color};")
                page_layout.addWidget(label)
            if not matching:
                page_layout.addWidget(QLabel("No verified telemetry available."))
            self._health.addItem(page, title)
        operations = coerce_many(OperationItem, payload.get("operations") or [])
        self._operations = {item.id: item for item in operations}
        self._table.clear()
        for item in operations:
            row = QTreeWidgetItem([item.title, item.state.upper(), f"{item.progress}%", item.updated])
            row.setData(0, Qt.ItemDataRole.UserRole, item.id)
            self._table.addTopLevelItem(row)
        if not operations:
            self._table.addTopLevelItem(QTreeWidgetItem(["No recorded workflow runs", "IDLE", "0%", ""]))

    def _selected(self, current, _previous) -> None:
        operation = self._operations.get(str(current.data(0, Qt.ItemDataRole.UserRole) or "")) if current else None
        self._detail.setPlainText(operation.detail if operation else "")

    def _request(self, action: str) -> None:
        item = self._table.currentItem()
        run_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "") if item else ""
        if run_id:
            self.action_requested.emit(action, run_id)
