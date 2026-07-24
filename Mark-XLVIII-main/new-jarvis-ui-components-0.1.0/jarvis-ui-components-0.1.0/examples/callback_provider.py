"""Example adapter for connecting the components to existing JARVIS actions.

Replace the callback bodies with the current action calls from main.py. The
DashboardController accepts dictionaries, lists, or JSON strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class CallbackProvider:
    graph: Callable[[str, str], Any]
    recent: Callable[[str, int], Any]
    calendar: Callable[[str, str], Any]
    note: Callable[[str], Any]
    operations: Callable[[], Any]
    health: Callable[[], Any]

    def get_graph(self, scope: str = "all", scope_id: str = "") -> Any:
        return self.graph(scope, scope_id)

    def get_recent_notes(self, mode: str = "edited", limit: int = 20) -> Any:
        return self.recent(mode, limit)

    def get_calendar(self, start: str, end: str) -> Any:
        return self.calendar(start, end)

    def get_note(self, note_id: str) -> Any:
        return self.note(note_id)

    def get_operations(self) -> Any:
        return self.operations()

    def get_health(self) -> Any:
        return self.health()

