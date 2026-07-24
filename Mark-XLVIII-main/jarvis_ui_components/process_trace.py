"""Bounded process trace widget backed by the typed runtime event hub."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from core.process_events import PROCESS_EVENTS, ProcessEvent


class ProcessTraceWidget(QWidget):
    _event_signal = pyqtSignal(object)
    activity = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paused = False
        self._autoscroll = True
        self._subscription_id = ""
        self.setObjectName("ProcessTrace")
        self.setStyleSheet(
            "QWidget#ProcessTrace{background:#00090f;border:1px solid #07394a;}"
            "QLabel{color:#79cdd8;font-family:'Courier New';font-size:8pt;}"
            "QPushButton,QComboBox{background:#00131d;color:#89dce7;border:1px solid #07546a;padding:3px 6px;}"
            "QTreeWidget,QTextEdit{background:#00060a;color:#b6edf3;border:1px solid #063444;font-family:'Courier New';font-size:8pt;}"
            "QTreeWidget::item:selected{background:#073448;color:#00e5ff;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(4)
        toolbar = QHBoxLayout()
        self._title = QLabel("TRACE  0")
        toolbar.addWidget(self._title)
        toolbar.addStretch()
        self._filter = QComboBox()
        self._filter.addItem("ALL")
        self._filter.setFixedWidth(66)
        self._filter.currentTextChanged.connect(self.refresh)
        toolbar.addWidget(self._filter)
        self._pause = QPushButton("PAUSE")
        self._pause.setCheckable(True)
        self._compact_button(self._pause, QStyle.StandardPixmap.SP_MediaPause, "Pause process trace updates")
        self._pause.toggled.connect(self._set_paused)
        toolbar.addWidget(self._pause)
        self._scroll = QPushButton("FOLLOW")
        self._scroll.setCheckable(True)
        self._scroll.setChecked(True)
        self._compact_button(self._scroll, QStyle.StandardPixmap.SP_ArrowDown, "Follow the newest event")
        self._scroll.toggled.connect(lambda checked: setattr(self, "_autoscroll", checked))
        toolbar.addWidget(self._scroll)
        clear = QPushButton("CLEAR")
        self._compact_button(clear, QStyle.StandardPixmap.SP_DialogDiscardButton, "Clear session trace")
        clear.clicked.connect(self._clear)
        toolbar.addWidget(clear)
        copy = QPushButton("COPY")
        self._compact_button(copy, QStyle.StandardPixmap.SP_FileDialogContentsView, "Copy selected event")
        copy.clicked.connect(self._copy)
        toolbar.addWidget(copy)
        export = QPushButton("EXPORT")
        self._compact_button(export, QStyle.StandardPixmap.SP_DialogSaveButton, "Export redacted trace")
        export.clicked.connect(self._export)
        toolbar.addWidget(export)
        layout.addLayout(toolbar)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["TIME", "CATEGORY", "STATE", "SUMMARY"])
        self._tree.setRootIsDecorated(False)
        self._tree.setColumnWidth(0, 78)
        self._tree.setColumnWidth(1, 66)
        self._tree.setColumnWidth(2, 62)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree.itemSelectionChanged.connect(self._show_detail)
        layout.addWidget(self._tree, 1)
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(72)
        self._detail.setPlaceholderText("Select an event for safe operational details.")
        self._detail.hide()
        layout.addWidget(self._detail)

        self._event_signal.connect(self._append_event)
        self._subscription_id = PROCESS_EVENTS.subscribe(self._event_signal.emit)
        self.refresh()

    def _compact_button(self, button: QPushButton, icon: QStyle.StandardPixmap, tooltip: str) -> None:
        button.setText("")
        button.setIcon(self.style().standardIcon(icon))
        button.setFixedSize(25, 22)
        button.setToolTip(tooltip)

    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._pause.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_MediaPlay if paused else QStyle.StandardPixmap.SP_MediaPause
            )
        )
        self._pause.setToolTip("Resume process trace updates" if paused else "Pause process trace updates")
        if not paused:
            self.refresh()

    def _append_event(self, event: ProcessEvent) -> None:
        self.activity.emit(event.to_dict())
        category = event.category.upper()
        if self._filter.findText(category) < 0:
            self._filter.addItem(category)
        if not self._paused and self._filter.currentText() in {"ALL", category}:
            self._add_row(event.to_dict())
            self._trim_rows()
        self._title.setText(f"TRACE  {PROCESS_EVENTS.status()['event_count']}")

    def _add_row(self, event: dict) -> None:
        stamp = str(event.get("timestamp") or "")
        stamp = stamp[11:19] if len(stamp) >= 19 else stamp
        item = QTreeWidgetItem([stamp, str(event.get("category") or "").upper(), str(event.get("state") or "").upper(), str(event.get("summary") or "")])
        item.setData(0, Qt.ItemDataRole.UserRole, event)
        self._tree.addTopLevelItem(item)
        if self._autoscroll:
            self._tree.scrollToItem(item)

    def _trim_rows(self) -> None:
        while self._tree.topLevelItemCount() > PROCESS_EVENTS.max_events:
            self._tree.takeTopLevelItem(0)

    def refresh(self) -> None:
        if not hasattr(self, "_tree"):
            return
        category = self._filter.currentText().casefold() if hasattr(self, "_filter") else "all"
        categories = [] if category == "all" else [category]
        self._tree.clear()
        for event in PROCESS_EVENTS.snapshot(categories=categories):
            self._add_row(event)
        self._title.setText(f"TRACE  {PROCESS_EVENTS.status()['event_count']}")

    def _show_detail(self) -> None:
        item = self._tree.currentItem()
        event = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not event:
            self._detail.clear()
            self._detail.hide()
            return
        safe = {
            "source": event.get("source"),
            "progress": event.get("progress"),
            "detail": event.get("detail"),
            "evidence_refs": event.get("evidence_refs"),
        }
        self._detail.setPlainText(json.dumps(safe, ensure_ascii=False, indent=2))
        self._detail.show()

    def _clear(self) -> None:
        PROCESS_EVENTS.clear()
        self.refresh()

    def _copy(self) -> None:
        item = self._tree.currentItem()
        if item:
            QGuiApplication.clipboard().setText(" | ".join(item.text(column) for column in range(4)))

    def _export(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, "Export redacted process trace", "jarvis-process-trace.md", "Markdown (*.md)")
        if selected:
            PROCESS_EVENTS.export_markdown(Path(selected))

    def closeEvent(self, event) -> None:
        if self._subscription_id:
            PROCESS_EVENTS.unsubscribe(self._subscription_id)
            self._subscription_id = ""
        super().closeEvent(event)
