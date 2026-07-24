from __future__ import annotations


class Theme:
    BG = "#00060a"
    PANEL = "#010d14"
    PANEL_ALT = "#01131d"
    BORDER = "#0d3347"
    BORDER_BRIGHT = "#1a5c7a"
    PRIMARY = "#00d4ff"
    PRIMARY_DIM = "#007a99"
    PRIMARY_GHOST = "#001f2e"
    TEXT = "#b9edf5"
    TEXT_DIM = "#5e9aaa"
    WHITE = "#e9fbff"
    GREEN = "#00d982"
    AMBER = "#ffbd3d"
    ORANGE = "#ff7a2f"
    RED = "#ff4f70"
    PURPLE = "#b78cff"
    MONO = "Courier New"
    UI = "Segoe UI"


NODE_COLORS = {
    "note": Theme.PRIMARY,
    "project": Theme.GREEN,
    "tag": Theme.AMBER,
    "task": Theme.RED,
    "citation": Theme.PURPLE,
    "daily": Theme.ORANGE,
}


STATE_COLORS = {
    "healthy": Theme.GREEN,
    "active": Theme.GREEN,
    "complete": Theme.GREEN,
    "completed": Theme.GREEN,
    "running": Theme.PRIMARY,
    "speaking": Theme.PRIMARY,
    "queued": Theme.TEXT_DIM,
    "waiting": Theme.AMBER,
    "approval": Theme.AMBER,
    "degraded": Theme.AMBER,
    "blocked": Theme.RED,
    "failed": Theme.RED,
    "error": Theme.RED,
    "offline": Theme.RED,
    "unknown": Theme.TEXT_DIM,
}


def state_color(state: str) -> str:
    return STATE_COLORS.get((state or "unknown").casefold(), Theme.TEXT_DIM)


def panel_stylesheet() -> str:
    return f"""
        QWidget {{
            background: {Theme.BG};
            color: {Theme.TEXT};
            font-family: {Theme.UI};
            font-size: 10pt;
        }}
        QLabel#SectionTitle {{
            color: {Theme.PRIMARY};
            font-family: {Theme.MONO};
            font-size: 8pt;
            font-weight: 700;
        }}
        QLineEdit, QComboBox, QTextBrowser, QListWidget, QTreeWidget {{
            background: {Theme.PANEL};
            color: {Theme.TEXT};
            border: 1px solid {Theme.BORDER};
            border-radius: 4px;
            padding: 5px;
            selection-background-color: {Theme.PRIMARY_GHOST};
        }}
        QLineEdit:focus, QComboBox:focus, QTextBrowser:focus,
        QListWidget:focus, QTreeWidget:focus {{
            border-color: {Theme.PRIMARY_DIM};
        }}
        QPushButton {{
            background: {Theme.PANEL};
            color: {Theme.TEXT};
            border: 1px solid {Theme.BORDER};
            border-radius: 4px;
            padding: 5px 9px;
        }}
        QPushButton:hover {{
            color: {Theme.WHITE};
            border-color: {Theme.PRIMARY_DIM};
            background: {Theme.PRIMARY_GHOST};
        }}
        QPushButton:disabled {{
            color: {Theme.TEXT_DIM};
            border-color: {Theme.BORDER};
        }}
        QHeaderView::section {{
            background: {Theme.PANEL_ALT};
            color: {Theme.TEXT_DIM};
            border: none;
            border-bottom: 1px solid {Theme.BORDER};
            padding: 5px;
            font-family: {Theme.MONO};
            font-size: 8pt;
        }}
        QScrollBar:vertical {{
            background: {Theme.BG};
            width: 7px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {Theme.BORDER_BRIGHT};
            min-height: 18px;
            border-radius: 3px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QSplitter::handle {{
            background: {Theme.BORDER};
            width: 4px;
            height: 4px;
        }}
        QSplitter::handle:hover {{
            background: {Theme.PRIMARY_DIM};
        }}
    """

