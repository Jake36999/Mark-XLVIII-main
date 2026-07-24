from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import HealthItem, OperationItem, coerce_many
from .theme import Theme, panel_stylesheet, state_color


class _HealthChip(QLabel):
    def __init__(self, health: HealthItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.update_health(health)

    def update_health(self, health: HealthItem) -> None:
        color = state_color(health.state)
        self.setText(f"{health.label.upper()}  {health.state.upper()}")
        self.setToolTip(health.detail or health.state)
        self.setStyleSheet(
            f"background: {Theme.PANEL_ALT}; color: {color};"
            f"border: 1px solid {color}; border-radius: 4px;"
            f"padding: 5px 8px; font-family: {Theme.MONO}; font-size: 8pt;"
        )


class OperationsView(QWidget):
    operation_selected = pyqtSignal(str)
    operation_activated = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)
    approve_requested = pyqtSignal(str)
    review_requested = pyqtSignal(str)
    refresh_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._operations: dict[str, OperationItem] = {}
        self._chips: list[_HealthChip] = []
        self.setStyleSheet(panel_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("OPERATIONS")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        refresh = QPushButton("REFRESH")
        refresh.clicked.connect(self.refresh_requested)
        header.addWidget(refresh)
        layout.addLayout(header)

        self._health_grid = QGridLayout()
        self._health_grid.setContentsMargins(0, 0, 0, 0)
        self._health_grid.setSpacing(5)
        layout.addLayout(self._health_grid)

        self._table = QTreeWidget()
        self._table.setHeaderLabels(["TASK", "TYPE", "STATE", "PROGRESS", "UPDATED"])
        self._table.setRootIsDecorated(False)
        self._table.setAlternatingRowColors(False)
        self._table.setColumnWidth(0, 270)
        self._table.setColumnWidth(1, 100)
        self._table.setColumnWidth(2, 100)
        self._table.setColumnWidth(3, 130)
        self._table.currentItemChanged.connect(self._on_selected)
        self._table.itemDoubleClicked.connect(self._on_activated)
        layout.addWidget(self._table, stretch=3)

        actions = QHBoxLayout()
        self._approve = QPushButton("APPROVE")
        self._review = QPushButton("REVIEW")
        self._cancel = QPushButton("CANCEL")
        self._approve.clicked.connect(lambda: self._emit_selected(self.approve_requested))
        self._review.clicked.connect(lambda: self._emit_selected(self.review_requested))
        self._cancel.clicked.connect(lambda: self._emit_selected(self.cancel_requested))
        self._approve.setStyleSheet(
            f"color: {Theme.GREEN}; border: 1px solid {Theme.GREEN};"
        )
        self._cancel.setStyleSheet(
            f"color: {Theme.RED}; border: 1px solid {Theme.RED};"
        )
        for button in (self._approve, self._review, self._cancel):
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self._detail = QTextBrowser()
        self._detail.setOpenExternalLinks(False)
        self._detail.setPlaceholderText("Select an operation to inspect its evidence and status.")
        self._detail.setMaximumHeight(170)
        layout.addWidget(self._detail, stretch=1)

    def set_health(self, items: list[HealthItem | dict]) -> None:
        while self._health_grid.count():
            child = self._health_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._chips = []
        for index, health in enumerate(coerce_many(HealthItem, items)):
            chip = _HealthChip(health)
            self._chips.append(chip)
            self._health_grid.addWidget(chip, index // 4, index % 4)

    def set_operations(self, items: list[OperationItem | dict]) -> None:
        operations = coerce_many(OperationItem, items)
        self._operations = {operation.id: operation for operation in operations}
        self._table.clear()
        for operation in operations:
            row = QTreeWidgetItem(
                [
                    operation.title,
                    operation.kind.upper(),
                    operation.state.upper(),
                    "",
                    operation.updated,
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, operation.id)
            row.setForeground(2, QBrush(QColor(state_color(operation.state))))
            if operation.requires_approval:
                row.setForeground(0, QBrush(QColor(Theme.AMBER)))
                row.setToolTip(0, "This operation is waiting for approval")
            self._table.addTopLevelItem(row)
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(max(0, min(100, int(operation.progress))))
            progress.setTextVisible(True)
            progress.setFixedHeight(17)
            progress.setStyleSheet(
                f"QProgressBar {{ background: {Theme.PANEL}; color: {Theme.TEXT};"
                f"border: 1px solid {Theme.BORDER}; border-radius: 3px; text-align: center; }}"
                f"QProgressBar::chunk {{ background: {state_color(operation.state)}; }}"
            )
            self._table.setItemWidget(row, 3, progress)
        self._update_actions()

    def selected_operation_id(self) -> str:
        item = self._table.currentItem()
        return str(item.data(0, Qt.ItemDataRole.UserRole)) if item else ""

    def _on_selected(self, current: QTreeWidgetItem | None, _previous) -> None:
        operation_id = self.selected_operation_id()
        operation = self._operations.get(operation_id)
        self._detail.setMarkdown(operation.detail if operation else "")
        self._update_actions()
        if current and operation_id:
            self.operation_selected.emit(operation_id)

    def _on_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        operation_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if operation_id:
            self.operation_activated.emit(operation_id)

    def _emit_selected(self, signal) -> None:
        operation_id = self.selected_operation_id()
        if operation_id:
            signal.emit(operation_id)

    def _update_actions(self) -> None:
        operation = self._operations.get(self.selected_operation_id())
        self._review.setEnabled(operation is not None)
        self._cancel.setEnabled(
            bool(operation and operation.state in {"queued", "running", "waiting", "approval"})
        )
        self._approve.setEnabled(bool(operation and operation.requires_approval))
