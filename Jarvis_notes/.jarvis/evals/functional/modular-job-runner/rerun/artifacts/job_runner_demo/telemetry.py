from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Event:
    run_id: str
    task_id: str
    timestamp: str
    status: str
    duration_ms: float = 0.0
    error: str = ""
    retry: int = 0
    health: str = "healthy"


class TelemetryAdapter(Protocol):
    def emit(self, event: Event) -> None: ...


class JsonlTelemetry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(event), sort_keys=True) + "\n")
