"""Thread-safe, redacted operational event stream for the desktop UI."""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|secret)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)((?:system|developer)[_ -]?prompt\s*[:=]\s*).+$"),
    re.compile(r"(?i)((?:chain[_ -]?of[_ -]?thought|raw[_ -]?reasoning)\s*[:=]\s*).+$"),
)
_FORBIDDEN_DETAIL_KEYS = {
    "prompt", "system_prompt", "developer_prompt", "messages", "chain_of_thought",
    "reasoning", "raw_reasoning", "authorization", "api_key", "token", "secret",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_text(value: Any, *, limit: int = 1200) -> str:
    text = str(value or "").replace("\x00", "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", text)
    return text[: max(40, min(int(limit), 4000))]


def safe_detail(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:40]:
            key_text = str(key)
            if key_text.casefold() in _FORBIDDEN_DETAIL_KEYS:
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = safe_detail(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [safe_detail(item, depth=depth + 1) for item in list(value)[:40]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(value)


@dataclass(frozen=True)
class ProcessEvent:
    event_id: str
    timestamp: str
    category: str
    source: str
    summary: str
    state: str = "info"
    severity: str = "info"
    progress: float | None = None
    turn_id: str = ""
    correlation_id: str = ""
    detail: Any = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProcessEventHub:
    def __init__(self, *, max_events: int = 250, max_bytes: int = 1024 * 1024):
        self.max_events = max(10, int(max_events))
        self.max_bytes = max(16_384, int(max_bytes))
        self._events: deque[tuple[ProcessEvent, int]] = deque()
        self._bytes = 0
        self._lock = threading.RLock()
        self._subscribers: dict[str, Callable[[ProcessEvent], None]] = {}

    def emit(
        self,
        *,
        category: str,
        source: str,
        summary: str,
        state: str = "info",
        severity: str = "info",
        progress: float | None = None,
        turn_id: str | int = "",
        correlation_id: str = "",
        detail: Any = None,
        evidence_refs: Iterable[str] = (),
    ) -> ProcessEvent:
        bounded_progress = None if progress is None else max(0.0, min(float(progress), 1.0))
        event = ProcessEvent(
            event_id=uuid.uuid4().hex,
            timestamp=_now(),
            category=redact_text(category, limit=80),
            source=redact_text(source, limit=100),
            summary=redact_text(summary, limit=500),
            state=redact_text(state, limit=60),
            severity=redact_text(severity, limit=40),
            progress=bounded_progress,
            turn_id=redact_text(turn_id, limit=100),
            correlation_id=redact_text(correlation_id, limit=120),
            detail=safe_detail(detail or {}),
            evidence_refs=tuple(redact_text(item, limit=500) for item in list(evidence_refs)[:20]),
        )
        encoded_size = len(json.dumps(event.to_dict(), ensure_ascii=False, default=str).encode("utf-8"))
        with self._lock:
            self._events.append((event, encoded_size))
            self._bytes += encoded_size
            while len(self._events) > self.max_events or self._bytes > self.max_bytes:
                _, size = self._events.popleft()
                self._bytes -= size
            subscribers = list(self._subscribers.values())
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                continue
        return event

    def subscribe(self, callback: Callable[[ProcessEvent], None]) -> str:
        subscription_id = uuid.uuid4().hex
        with self._lock:
            self._subscribers[subscription_id] = callback
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        with self._lock:
            self._subscribers.pop(str(subscription_id), None)

    def snapshot(self, *, categories: Iterable[str] = (), limit: int = 250) -> list[dict[str, Any]]:
        selected = {str(value).casefold() for value in categories if value}
        with self._lock:
            events = [event for event, _ in self._events]
        if selected:
            events = [event for event in events if event.category.casefold() in selected]
        return [event.to_dict() for event in events[-max(1, min(int(limit), self.max_events)) :]]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._bytes = 0

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "event_count": len(self._events),
                "memory_bytes": self._bytes,
                "max_events": self.max_events,
                "max_bytes": self.max_bytes,
                "subscriber_count": len(self._subscribers),
                "session_only": True,
            }

    def export_markdown(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        lines = [
            "---",
            "type: process-trace",
            "status: session-export",
            "rag_index: false",
            "sensitivity: internal",
            f"exported_at: {_now()}",
            "---",
            "",
            "# JARVIS Process Trace",
            "",
            "> [!warning] Session-only operational summary",
            "> This export is redacted and excluded from RAG. It does not contain hidden reasoning or prompts.",
            "",
        ]
        for event in self.snapshot():
            lines.append(f"- `{event['timestamp']}` **{event['category']}** [{event['state']}] {event['summary']}")
        from actions.jarvis_memory import atomic_write

        atomic_write(target, "\n".join(lines).rstrip() + "\n", origin="jarvis")
        return {"ok": True, "path": str(target), "event_count": len(self.snapshot())}


PROCESS_EVENTS = ProcessEventHub()


def emit_process_event(**kwargs: Any) -> ProcessEvent:
    return PROCESS_EVENTS.emit(**kwargs)
