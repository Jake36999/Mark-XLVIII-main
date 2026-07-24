from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from .theme import Theme


class WorkspaceSwitcher(QWidget):
    """Compact segmented control for LIVE, KNOWLEDGE, and OPERATIONS modes."""

    mode_changed = pyqtSignal(str)

    MODES = ("live", "knowledge", "operations")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        for index, mode in enumerate(self.MODES):
            button = QPushButton(mode.upper())
            button.setCheckable(True)
            button.setProperty("mode", mode)
            button.setToolTip(f"Switch to {mode.title()} workspace (Ctrl+{index + 1})")
            button.setStyleSheet(self._button_style())
            button.clicked.connect(
                lambda checked=False, selected=mode: self.set_mode(selected)
            )
            self._group.addButton(button)
            self._buttons[mode] = button
            layout.addWidget(button)

        self.set_mode("live", emit=False)

    @staticmethod
    def _button_style() -> str:
        return f"""
            QPushButton {{
                background: {Theme.PANEL}; color: {Theme.TEXT_DIM};
                border: 1px solid {Theme.BORDER}; border-radius: 3px;
                padding: 5px 12px; font-family: {Theme.MONO};
                font-size: 8pt; font-weight: 700;
            }}
            QPushButton:hover {{
                color: {Theme.TEXT}; border-color: {Theme.PRIMARY_DIM};
            }}
            QPushButton:checked {{
                color: {Theme.PRIMARY}; background: {Theme.PRIMARY_GHOST};
                border-color: {Theme.PRIMARY};
            }}
        """

    def mode(self) -> str:
        for mode, button in self._buttons.items():
            if button.isChecked():
                return mode
        return "live"

    def set_mode(self, mode: str, emit: bool = True) -> None:
        normalized = mode.casefold()
        if normalized not in self._buttons:
            raise ValueError(f"Unknown workspace mode: {mode}")
        changed = self.mode() != normalized
        self._buttons[normalized].setChecked(True)
        if emit and changed:
            self.mode_changed.emit(normalized)

    def set_badge(self, mode: str, count: int | None) -> None:
        normalized = mode.casefold()
        button = self._buttons[normalized]
        suffix = f"  {count}" if count else ""
        button.setText(f"{normalized.upper()}{suffix}")

