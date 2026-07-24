"""A note-level checkbox trigger that reads the note aloud via local TTS.

Insert the `Read Me Aloud` Obsidian template into any note, check its box,
and MARK speaks the note the next time the vault watcher notices the change
(within its normal debounce window -- a couple of seconds). No new server,
port, or authentication surface: this hooks into `actions.vault_watch`'s
already-running watcher, which every MARK session starts unconditionally.

Security posture: checking this box can only ever trigger a read-only,
local speech action. It writes nothing except resetting its own trigger
line back to unchecked, cannot approve a plan, run code, or touch any file
other than the note it lives in -- it is not the kind of checkbox-as-trigger
this project's canvas/plan work has to guard scope around.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

# Matches `- [x] ... [tts:read]` (any case, any text between the checkbox and
# the marker), mirroring the existing `[task:id]`/`[tool:name]` bracket-marker
# convention already used for checkbox tasks in `jarvis_memory._extract_tasks`.
_TRIGGER = re.compile(r"^(\s*[-*]\s+\[)[xX](\]\s+.*\[tts:read\].*)$", re.IGNORECASE | re.MULTILINE)
_UNCHECKED_TRIGGER = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+.*\[tts:read\].*$", re.IGNORECASE | re.MULTILINE)

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_CHECKBOX_LINE = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+", re.MULTILINE)
_TRIGGER_MARKER_TEXT = re.compile(r"\[tts:read\]", re.IGNORECASE)
_WIKILINK = re.compile(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]")
_HEADING_HASHES = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_CALLOUT_MARKER = re.compile(r"^>\s*\[![a-zA-Z]+\][+-]?\s*", re.MULTILINE)
_BLOCKQUOTE_MARKER = re.compile(r"^>\s?", re.MULTILINE)

_lock = threading.Lock()
_reader: Any = None


def has_trigger(text: str) -> bool:
    """Whether the note's raw text contains the `[tts:read]` marker at all."""
    return bool(_UNCHECKED_TRIGGER.search(text))


def is_triggered(text: str) -> bool:
    """Whether the marker's checkbox is specifically checked."""
    return bool(_TRIGGER.search(text))


def reset_trigger(text: str) -> str:
    """Return `text` with the trigger checkbox reset to unchecked."""
    return _TRIGGER.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)


def text_for_speech(raw_text: str) -> str:
    """Strip frontmatter, checkbox/markup syntax, and code before speaking."""
    from actions.jarvis_memory import parse_frontmatter

    _metadata, body = parse_frontmatter(raw_text)
    body = _CODE_FENCE.sub(" Code block omitted. ", body)
    body = _INLINE_CODE.sub(r"\1", body)
    body = _TRIGGER_MARKER_TEXT.sub("", body)
    body = _CHECKBOX_LINE.sub("", body)
    body = _WIKILINK.sub(lambda m: (m.group(2)[1:] if m.group(2) else m.group(1)), body)
    body = _HEADING_HASHES.sub("", body)
    body = _CALLOUT_MARKER.sub("", body)
    body = _BLOCKQUOTE_MARKER.sub("", body)
    return body.strip()


def _get_reader(cfg: dict[str, Any]):
    global _reader
    with _lock:
        if _reader is None:
            from core.tts import create_tts_player

            _reader = create_tts_player(cfg)
        return _reader


def check_tts_read_triggers(changed_paths: list[str]) -> list[str]:
    """Check changed vault notes for a checked `[tts:read]` trigger.

    For each match: reset the checkbox first (so a slow read can't be
    re-triggered by the very next debounced scan, and so the box can be
    checked again later for a re-read), then speak the note in a background
    thread. Returns the paths that were triggered this call. Every failure
    mode (config disabled, revision conflict, empty resulting text) is a
    silent no-op for that path rather than a raised exception -- this must
    never be able to break the vault watcher's own reindexing.
    """
    from actions.jarvis_memory import atomic_write
    from core.runtime_config import load_runtime_config

    config = load_runtime_config()
    if not bool(config.get("tts_read_trigger_enabled", True)):
        return []

    triggered: list[str] = []
    for path_str in changed_paths:
        path = Path(path_str)
        if path.suffix.lower() != ".md":
            continue
        try:
            if not path.is_file():
                continue
            raw_bytes = path.read_bytes()
            raw = raw_bytes.decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        if not is_triggered(raw):
            continue
        reset_text = reset_trigger(raw)
        import hashlib

        revision = hashlib.sha256(raw_bytes).hexdigest()
        try:
            atomic_write(path, reset_text, expected_revision=revision)
        except (RuntimeError, OSError):
            # Someone else wrote to the note between our read and reset, or
            # the write failed outright -- skip this cycle rather than risk
            # reading stale content or fighting a concurrent edit. The next
            # scan will pick the still-checked box back up.
            continue
        speech_text = text_for_speech(raw)
        if not speech_text:
            continue
        triggered.append(str(path))
        reader = _get_reader(config)
        threading.Thread(target=reader.speak, args=(speech_text,), daemon=True, name="jarvis-read-note-aloud").start()
    return triggered
