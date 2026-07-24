from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCharFormat
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import CalendarItem, coerce_many
from .theme import Theme, panel_stylesheet, state_color


def _item_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


class CalendarAgendaWidget(QWidget):
    item_activated = pyqtSignal(str)
    date_selected = pyqtSignal(str)
    create_requested = pyqtSignal(str)
    filter_changed = pyqtSignal(str)

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[CalendarItem] = []
        self._by_date: dict[date, list[CalendarItem]] = defaultdict(list)
        self._formatted_dates: list[QDate] = []
        self.setStyleSheet(panel_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("CALENDAR")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        self._filter = QComboBox()
        self._filter.addItem("All", "all")
        self._filter.addItem("Tasks", "task")
        self._filter.addItem("Reminders", "reminder")
        self._filter.addItem("Workflows", "workflow")
        self._filter.currentIndexChanged.connect(self._on_filter)
        header.addWidget(self._filter)
        layout.addLayout(header)

        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(True)
        self._calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self._calendar.selectionChanged.connect(self._on_date_changed)
        layout.addWidget(self._calendar)

        agenda_header = QHBoxLayout()
        self._agenda_title = QLabel("AGENDA")
        self._agenda_title.setObjectName("SectionTitle")
        agenda_header.addWidget(self._agenda_title)
        agenda_header.addStretch()
        add = QPushButton("+ ADD")
        add.setToolTip("Create a task or note on the selected date")
        add.clicked.connect(
            lambda: self.create_requested.emit(
                self._calendar.selectedDate().toString(Qt.DateFormat.ISODate)
            )
        )
        agenda_header.addWidget(add)
        layout.addLayout(agenda_header)

        self._agenda = QTreeWidget()
        self._agenda.setHeaderLabels(["TIME", "ITEM", "SOURCE"])
        self._agenda.setRootIsDecorated(False)
        self._agenda.setColumnWidth(0, 54)
        self._agenda.setColumnWidth(2, 80)
        self._agenda.itemDoubleClicked.connect(self._activate_item)
        layout.addWidget(self._agenda, stretch=1)

        if compact:
            self._agenda.setMaximumHeight(120)

        self._on_date_changed()

    def set_items(self, items: list[CalendarItem | dict]) -> None:
        self._items = coerce_many(CalendarItem, items)
        self._rebuild()

    def selected_date(self) -> str:
        return self._calendar.selectedDate().toString(Qt.DateFormat.ISODate)

    def _on_filter(self) -> None:
        self._rebuild()
        self.filter_changed.emit(str(self._filter.currentData()))

    def _rebuild(self) -> None:
        for qdate in self._formatted_dates:
            self._calendar.setDateTextFormat(qdate, QTextCharFormat())
        self._formatted_dates.clear()
        self._by_date = defaultdict(list)
        wanted = str(self._filter.currentData())
        for item in self._items:
            if wanted != "all" and item.kind != wanted:
                continue
            when = _item_date(item.start)
            if when:
                self._by_date[when].append(item)

        for when, day_items in self._by_date.items():
            qdate = QDate(when.year, when.month, when.day)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(Theme.PRIMARY_GHOST))
            color = Theme.RED if any(i.status in {"overdue", "blocked"} for i in day_items) else Theme.PRIMARY
            fmt.setForeground(QColor(color))
            fmt.setFontWeight(700)
            self._calendar.setDateTextFormat(qdate, fmt)
            self._formatted_dates.append(qdate)
        self._on_date_changed()

    def _on_date_changed(self) -> None:
        selected = self._calendar.selectedDate()
        selected_date = date(selected.year(), selected.month(), selected.day())
        self._agenda_title.setText(f"AGENDA  {selected.toString('dd MMM')}")
        self._agenda.clear()
        for item in sorted(self._by_date.get(selected_date, []), key=lambda value: value.start):
            time_text = "ALL DAY"
            if "T" in item.start:
                try:
                    time_text = datetime.fromisoformat(item.start.replace("Z", "+00:00")).strftime("%H:%M")
                except ValueError:
                    pass
            row = QTreeWidgetItem([time_text, item.title, item.kind.upper()])
            row.setData(0, Qt.ItemDataRole.UserRole, item.id)
            row.setToolTip(1, item.detail or item.title)
            row.setForeground(1, QColor(state_color(item.status)))
            self._agenda.addTopLevelItem(row)
        self.date_selected.emit(selected.toString(Qt.DateFormat.ISODate))

    def _activate_item(self, item: QTreeWidgetItem, _column: int) -> None:
        item_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if item_id:
            self.item_activated.emit(item_id)

