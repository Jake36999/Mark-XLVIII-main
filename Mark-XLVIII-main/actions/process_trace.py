"""Read-only view of what JARVIS actually did.

The counterpart to the one-way phase hand-off: replies stop narrating
background operations, so there has to be somewhere the user can go when they
genuinely want that detail. Before this existed, "what did you just do" fell
through to `capability_registry`, which answers with the tool manifest --
a description of what JARVIS *can* do, not what it *did*.

Everything here reads the existing session event hub. Nothing is recomputed and
no new state is kept.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.process_events import PHASE_NAMES, PROCESS_EVENTS

_MAX_EVENTS = 40


def _format_event(event: dict[str, Any]) -> str:
    detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
    phase = detail.get("phase_name") or PHASE_NAMES.get(detail.get("phase"), "")
    marker = f" [{phase}]" if phase else ""
    return (
        f"- `{event.get('timestamp', '')}` **{event.get('category', '')}**"
        f"/{event.get('state', '')}{marker} — {event.get('summary', '')}"
    )


def _recent(limit: int, turn_id: str = "") -> str:
    """Prose, not JSON.

    This tool exists to answer a user asking what just happened, so its result
    is already the answer -- returning it as text lets the turn skip the
    summarising model entirely instead of paying a second generation to
    paraphrase a list back into a list.
    """
    events = PROCESS_EVENTS.snapshot(limit=limit, turn_id=turn_id)
    if not events:
        scope = f" for turn {turn_id}" if turn_id else ""
        return f"No operations have been recorded{scope} in this session."
    scope = f" for turn {turn_id}" if turn_id else ""
    header = f"Here is what I did{scope} ({len(events)} recorded operations, most recent last):"
    return header + "\n" + "\n".join(_format_event(event) for event in events)


def process_trace(parameters: dict[str, Any] | None = None, player=None, speak=None, **_: Any) -> str:
    params = parameters or {}
    operation = str(params.get("operation") or params.get("action") or "recent").strip().lower()
    try:
        limit = max(1, min(int(params.get("limit") or _MAX_EVENTS), 250))
    except (TypeError, ValueError):
        limit = _MAX_EVENTS

    if operation in {"recent", "list", ""}:
        return _recent(limit)

    if operation == "turn":
        turn_id = str(params.get("turn_id") or "").strip()
        if not turn_id:
            return "A turn_id is required to report on a specific turn."
        return _recent(limit, turn_id=turn_id)

    if operation == "export":
        target = str(params.get("path") or "").strip()
        if not target:
            return json.dumps({"ok": False, "error": "path is required for operation=export."})
        try:
            return json.dumps(PROCESS_EVENTS.export_markdown(Path(target)), ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return f"Unknown operation {operation!r}. Use recent, turn, or export."
