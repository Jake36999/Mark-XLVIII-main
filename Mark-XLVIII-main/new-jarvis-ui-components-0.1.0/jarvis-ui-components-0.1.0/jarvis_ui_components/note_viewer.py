from __future__ import annotations

from urllib.parse import quote

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .models import NoteItem
from .theme import Theme, panel_stylesheet


class NoteViewer(QWidget):
    open_requested = pyqtSignal(str)
    ask_requested = pyqtSignal(str)
    edit_requested = pyqtSignal(str)
    pin_requested = pyqtSignal(str)
    link_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._note: NoteItem | None = None
        self.setStyleSheet(panel_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self._title = QLabel("NO NOTE SELECTED")
        self._title.setObjectName("SectionTitle")
        self._title.setWordWrap(True)
        header.addWidget(self._title, stretch=1)

        self._open = QPushButton("OPEN")
        self._ask = QPushButton("ASK")
        self._edit = QPushButton("EDIT")
        self._pin = QPushButton("PIN")
        for button in (self._open, self._ask, self._edit, self._pin):
            button.setEnabled(False)
            header.addWidget(button)
        self._open.clicked.connect(lambda: self._emit(self.open_requested))
        self._ask.clicked.connect(lambda: self._emit(self.ask_requested))
        self._edit.clicked.connect(lambda: self._emit(self.edit_requested))
        self._pin.clicked.connect(lambda: self._emit(self.pin_requested))
        layout.addLayout(header)

        self._meta = QLabel("Select a node or recent note to inspect it.")
        self._meta.setWordWrap(True)
        self._meta.setStyleSheet(f"color: {Theme.TEXT_DIM}; font-family: {Theme.MONO}; font-size: 8pt;")
        layout.addWidget(self._meta)

        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)
        self._browser.setOpenExternalLinks(False)
        self._browser.anchorClicked.connect(self._on_link)
        self._browser.setPlaceholderText("Note content will appear here.")
        layout.addWidget(self._browser, stretch=1)

    def note(self) -> NoteItem | None:
        return self._note

    def show_note(self, note: NoteItem | dict) -> None:
        self._note = NoteItem.from_mapping(note)
        value = self._note
        self._title.setText(value.title.upper())
        bits = [value.note_type.upper()]
        if value.project_id:
            bits.append(value.project_id)
        if value.updated:
            bits.append(f"UPDATED {value.updated}")
        if value.tags:
            bits.append(" ".join(f"#{tag}" for tag in value.tags))
        self._meta.setText("  |  ".join(bits))
        markdown = value.content or value.summary or "_This note has no preview content._"
        self._browser.setMarkdown(markdown)
        for button in (self._open, self._ask, self._edit, self._pin):
            button.setEnabled(True)
        self._pin.setText("UNPIN" if value.pinned else "PIN")

    def clear(self) -> None:
        self._note = None
        self._title.setText("NO NOTE SELECTED")
        self._meta.setText("Select a node or recent note to inspect it.")
        self._browser.clear()
        for button in (self._open, self._ask, self._edit, self._pin):
            button.setEnabled(False)

    def obsidian_uri(self) -> str:
        if not self._note:
            return ""
        if self._note.obsidian_uri:
            return self._note.obsidian_uri
        if self._note.path:
            return f"obsidian://open?path={quote(self._note.path, safe='')}"
        return ""

    def open_in_obsidian(self) -> bool:
        uri = self.obsidian_uri()
        return bool(uri) and QDesktopServices.openUrl(QUrl(uri))

    def _emit(self, signal) -> None:
        if self._note:
            signal.emit(self._note.id)

    def _on_link(self, url: QUrl) -> None:
        self.link_requested.emit(url.toString())

