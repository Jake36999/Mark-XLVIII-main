"""Reusable PyQt6 components for the MARK XLVIII desktop dashboard.

Widget imports are lazy so pure data and layout helpers remain testable on
machines that do not have a GUI runtime installed.
"""

from importlib import import_module

from .models import (
    CalendarItem,
    CommandAction,
    GraphEdge,
    GraphNode,
    HealthItem,
    NoteItem,
    OperationItem,
)

__all__ = [
    "CalendarAgendaWidget",
    "CalendarItem",
    "CommandAction",
    "CommandPalette",
    "DashboardController",
    "DashboardDataProvider",
    "DashboardWorkspace",
    "GraphEdge",
    "GraphNode",
    "HealthItem",
    "KnowledgeGraphWidget",
    "KnowledgeWorkspace",
    "NoteItem",
    "NoteViewer",
    "OperationItem",
    "OperationsView",
    "RecentNotesWidget",
    "WorkspaceSwitcher",
]

__version__ = "0.1.0"


_LAZY_IMPORTS = {
    "CalendarAgendaWidget": (".calendar_panel", "CalendarAgendaWidget"),
    "CommandPalette": (".command_palette", "CommandPalette"),
    "DashboardController": (".provider", "DashboardController"),
    "DashboardDataProvider": (".provider", "DashboardDataProvider"),
    "DashboardWorkspace": (".workspace", "DashboardWorkspace"),
    "KnowledgeGraphWidget": (".knowledge_graph", "KnowledgeGraphWidget"),
    "KnowledgeWorkspace": (".workspace", "KnowledgeWorkspace"),
    "NoteViewer": (".note_viewer", "NoteViewer"),
    "OperationsView": (".operations_view", "OperationsView"),
    "RecentNotesWidget": (".recent_notes", "RecentNotesWidget"),
    "WorkspaceSwitcher": (".workspace_switcher", "WorkspaceSwitcher"),
}


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(name)
    module_name, attribute = _LAZY_IMPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
