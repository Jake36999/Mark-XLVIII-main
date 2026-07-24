from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from .models import CommandAction
from .provider import DashboardController
from .theme import Theme
from .workspace import DashboardWorkspace


class DemoProvider:
    def __init__(self) -> None:
        now = datetime.now().replace(microsecond=0)
        self.notes = {
            "jarvis": {
                "id": "jarvis",
                "title": "JARVIS Architecture",
                "path": "Projects/JARVIS/Architecture.md",
                "project_id": "mark_platform",
                "note_type": "project",
                "updated": now.isoformat(),
                "tags": ["jarvis", "architecture"],
                "content": "# JARVIS Architecture\n\nThe local platform coordinates memory, tools, speech, and workflows.",
            },
            "memory": {
                "id": "memory",
                "title": "Vault Memory",
                "path": "Systems/Vault Memory.md",
                "project_id": "mark_platform",
                "note_type": "note",
                "updated": (now - timedelta(hours=3)).isoformat(),
                "tags": ["rag", "obsidian"],
                "content": "# Vault Memory\n\nMarkdown is canonical. SQLite provides hybrid retrieval.",
            },
            "network": {
                "id": "network",
                "title": "Network Management",
                "path": "Projects/network-management/Project Brief.md",
                "project_id": "network_management",
                "note_type": "project",
                "updated": (now - timedelta(days=1)).isoformat(),
                "tags": ["csi", "project"],
                "content": "# Network Management\n\nA CSI processing and RF operations project.",
            },
            "task": {
                "id": "task",
                "title": "Dashboard knowledge workspace",
                "path": "Tasks/Dashboard knowledge workspace.md",
                "project_id": "mark_platform",
                "note_type": "task",
                "updated": (now - timedelta(minutes=18)).isoformat(),
                "tags": ["ui", "task"],
                "content": "# Dashboard knowledge workspace\n\n- [ ] Integrate graph\n- [ ] Connect calendar\n- [ ] Add recent notes",
                "pinned": True,
            },
        }

    def get_graph(self, scope: str = "all", scope_id: str = "") -> dict:
        nodes = [
            {"id": "jarvis", "label": "JARVIS", "kind": "project", "project_id": "mark_platform", "score": 3},
            {"id": "memory", "label": "Vault Memory", "kind": "note", "project_id": "mark_platform", "score": 2},
            {"id": "network", "label": "Network Management", "kind": "project", "project_id": "network_management", "score": 2},
            {"id": "task", "label": "Knowledge Workspace", "kind": "task", "project_id": "mark_platform", "score": 2},
            {"id": "rag", "label": "rag", "kind": "tag", "project_id": "mark_platform"},
            {"id": "obsidian", "label": "obsidian", "kind": "tag", "project_id": "mark_platform"},
            {"id": "csi", "label": "csi", "kind": "tag", "project_id": "network_management"},
        ]
        edges = [
            {"source": "jarvis", "target": "memory", "kind": "link"},
            {"source": "jarvis", "target": "task", "kind": "link"},
            {"source": "memory", "target": "rag", "kind": "tag"},
            {"source": "memory", "target": "obsidian", "kind": "tag"},
            {"source": "network", "target": "csi", "kind": "tag"},
            {"source": "memory", "target": "network", "kind": "semantic", "weight": 0.55},
        ]
        return {"nodes": nodes, "edges": edges}

    def get_recent_notes(self, mode: str = "edited", limit: int = 20) -> dict:
        return {"notes": list(self.notes.values())[:limit]}

    def get_calendar(self, start: str, end: str) -> dict:
        today = date.today()
        return {
            "items": [
                {"id": "cal-1", "title": "Review UI package", "start": today.isoformat(), "kind": "task"},
                {"id": "cal-2", "title": "Vault reindex", "start": (today + timedelta(days=1)).isoformat(), "kind": "workflow", "status": "running"},
                {"id": "cal-3", "title": "Project check-in", "start": (today + timedelta(days=3)).isoformat(), "kind": "reminder"},
            ]
        }

    def get_note(self, note_id: str) -> dict:
        return {"note": self.notes[note_id]}

    def get_operations(self) -> dict:
        return {
            "operations": [
                {"id": "op-1", "title": "Index changed vault notes", "kind": "rag", "state": "running", "progress": 62, "detail": "Embedding changed notes and updating the local index."},
                {"id": "op-2", "title": "Review dashboard plan", "kind": "review", "state": "approval", "progress": 100, "requires_approval": True, "detail": "The implementation plan is ready for operator approval."},
                {"id": "op-3", "title": "Repository scout", "kind": "project", "state": "completed", "progress": 100, "detail": "Read-only project orientation completed."},
            ]
        }

    def get_health(self) -> dict:
        return {
            "health": [
                {"id": "mic", "label": "Microphone", "state": "active"},
                {"id": "tts", "label": "TTS", "state": "healthy"},
                {"id": "rag", "label": "RAG", "state": "running", "detail": "37 notes indexed"},
                {"id": "watcher", "label": "Vault Watcher", "state": "healthy"},
                {"id": "model", "label": "Local Model", "state": "active"},
                {"id": "bridge", "label": "Aletheia", "state": "degraded"},
            ]
        }


def _live_placeholder() -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    title = QLabel("J.A.R.V.I.S")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet(
        f"color: {Theme.PRIMARY}; font: 700 24pt {Theme.MONO};"
    )
    status = QLabel("LIVE WORKSPACE PLACEHOLDER\n\nYour existing HUD and content splitter attach here.")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status.setStyleSheet(
        f"color: {Theme.TEXT_DIM}; font: 10pt {Theme.MONO};"
    )
    layout.addStretch()
    layout.addWidget(title)
    layout.addWidget(status)
    layout.addStretch()
    return widget


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    window = QMainWindow()
    window.setWindowTitle("JARVIS UI Components Demo")
    window.resize(1180, 760)

    workspace = DashboardWorkspace()
    workspace.set_live_widget(_live_placeholder())
    workspace.set_command_actions(
        [
            CommandAction("note.capture", "Quick capture note", "Create a vault note", "Knowledge"),
            CommandAction("plan.latest", "Open latest plan", "Inspect the current plan", "Operations"),
        ]
    )
    window.setCentralWidget(workspace)

    controller = DashboardController(workspace, DemoProvider(), window)
    controller.error.connect(lambda message: print(f"Dashboard error: {message}"))
    controller.action_requested.connect(
        lambda action, payload: print(f"Action: {action} -> {payload}")
    )
    workspace.mode_changed.connect(
        lambda mode: controller.refresh_mode(mode)
    )
    controller.refresh_knowledge()
    controller.refresh_operations()
    workspace.set_mode("knowledge")

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

