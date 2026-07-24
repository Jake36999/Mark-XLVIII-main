from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Mapping, TypeVar


T = TypeVar("T")


class MappingModel:
    """Small mapping adapter for JSON payloads returned by JARVIS actions."""

    @classmethod
    def from_mapping(cls: type[T], value: Mapping[str, Any] | T) -> T:
        if isinstance(value, cls):
            return value
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: raw for key, raw in value.items() if key in allowed})


@dataclass(slots=True)
class NoteItem(MappingModel):
    id: str
    title: str
    path: str = ""
    summary: str = ""
    content: str = ""
    project_id: str = ""
    note_type: str = "note"
    updated: str = ""
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    obsidian_uri: str = ""
    revision: str = ""

    def updated_at(self) -> datetime | None:
        if not self.updated:
            return None
        try:
            return datetime.fromisoformat(self.updated.replace("Z", "+00:00"))
        except ValueError:
            return None


@dataclass(slots=True)
class CalendarItem(MappingModel):
    id: str
    title: str
    start: str
    end: str = ""
    kind: str = "task"
    source_id: str = ""
    project_id: str = ""
    status: str = "open"
    all_day: bool = True
    detail: str = ""


@dataclass(slots=True)
class GraphNode(MappingModel):
    id: str
    label: str
    kind: str = "note"
    project_id: str = ""
    path: str = ""
    score: float = 1.0
    updated: str = ""
    color: str = ""


@dataclass(slots=True)
class GraphEdge(MappingModel):
    source: str
    target: str
    kind: str = "link"
    weight: float = 1.0
    label: str = ""


@dataclass(slots=True)
class OperationItem(MappingModel):
    id: str
    title: str
    state: str = "queued"
    progress: int = 0
    kind: str = "workflow"
    updated: str = ""
    detail: str = ""
    requires_approval: bool = False


@dataclass(slots=True)
class HealthItem(MappingModel):
    id: str
    label: str
    state: str = "unknown"
    detail: str = ""


@dataclass(slots=True)
class CommandAction(MappingModel):
    id: str
    title: str
    subtitle: str = ""
    group: str = "Commands"
    keywords: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def searchable_text(self) -> str:
        return " ".join(
            [self.title, self.subtitle, self.group, *self.keywords]
        ).casefold()


def coerce_many(model: type[T], values: list[Mapping[str, Any] | T]) -> list[T]:
    return [model.from_mapping(value) for value in values]

