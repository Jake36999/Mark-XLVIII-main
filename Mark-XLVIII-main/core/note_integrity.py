"""Detectors for the frontmatter corruption patterns seen on the live vault.

Every check here corresponds to a real defect that reached the vault during the
2026-07-23 tier migration, so JARVIS (and any bulk vault operation) can flag them
instead of shipping them silently:

* doubled frontmatter — CRLF notes whose whole frontmatter got treated as body,
  then a second block written on top (see the parse_frontmatter CRLF fix).
* exploded tags — an unquoted YAML flow list parsed as a string, then `list()`-ed
  into single characters ("developer-handbook" -> ["d","e","v",...]).
* unparsable frontmatter — a `---` fence that yields no readable key/value lines.
* CRLF in the fence — will parse now, but is the shape that caused the doubling.
* bare `[file:...]` citation — a repo citation that renders as unclickable text.

The functions are pure (text in, findings out) and self-contained (no imports
from `actions`), so they are cheap to call from a write path, a script, or a tool.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

SEVERITIES = ("error", "warning", "info")

_FENCE_HEAD = re.compile(r"\A---\n(id|title|type|created|status)\s*:", re.IGNORECASE)
_FILE_CITATION = re.compile(r"\[file:[^\]\n]+\](?!\()")
_TAGS_LINE = re.compile(r"^tags\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _finding(kind: str, severity: str, detail: str) -> dict[str, str]:
    return {"kind": kind, "severity": severity, "detail": detail}


def _split_fence(normalised: str) -> tuple[str, str] | None:
    """Return (frontmatter_body, note_body) if a fence is present, else None."""
    if not normalised.startswith("---\n"):
        return None
    end = normalised.find("\n---", 4)
    if end < 0:
        return None
    return normalised[4:end], normalised[end + 4 :].lstrip("\n")


def _looks_exploded(items: list[Any]) -> bool:
    if not isinstance(items, list) or not items:
        return False
    junk = any(isinstance(x, str) and x in {"[", "]", ","} for x in items)
    singles = sum(1 for x in items if isinstance(x, str) and len(x.strip()) <= 1)
    return junk or singles >= 3


def inspect_note(text: str) -> list[dict[str, str]]:
    """Return every integrity finding in one note's raw text, worst-severity first."""
    findings: list[dict[str, str]] = []
    raw = text.lstrip("﻿")
    normalised = raw.replace("\r\n", "\n").replace("\r", "\n")

    has_fence = normalised.startswith("---\n")
    fence = _split_fence(normalised)

    if has_fence and fence is None:
        findings.append(_finding("unparsable_frontmatter", "error",
                                 "opens with '---' but no closing fence was found"))
    elif fence is not None:
        fm_body, note_body = fence
        # CRLF anywhere in the note is the shape that caused the doubling bug; flag
        # it as a heads-up (it will be normalised to LF on the next JARVIS write).
        if "\r" in raw:
            findings.append(_finding("crlf_frontmatter", "warning",
                                     "note uses CRLF line endings (normalise on next write)"))

        # Doubled frontmatter: the body itself starts another metadata block.
        if _FENCE_HEAD.match(note_body):
            findings.append(_finding("doubled_frontmatter", "error",
                                     "note body begins a second '---' frontmatter block"))

        # No readable key/value lines at all.
        kv_lines = [ln for ln in fm_body.splitlines() if ":" in ln and ln.split(":", 1)[0].strip()]
        if not kv_lines:
            findings.append(_finding("unparsable_frontmatter", "error",
                                     "frontmatter fence contains no readable 'key: value' lines"))

        # Exploded tags.
        match = _TAGS_LINE.search(fm_body)
        if match:
            value = match.group(1).strip()
            parsed: Any = None
            try:
                parsed = json.loads(value)
            except Exception:
                if value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1].strip()
                    parsed = [p.strip() for p in inner.split(",") if p.strip()] if inner else []
            if _looks_exploded(parsed if isinstance(parsed, list) else []):
                findings.append(_finding("exploded_tags", "error",
                                         "tags look character-exploded (e.g. ['d','e','v',...])"))

    # Bare, unclickable repo citations.
    bare = len(_FILE_CITATION.findall(normalised))
    if bare:
        findings.append(_finding("bare_file_citation", "info",
                                 f"{bare} unclickable [file:...] citation(s) — render as file links"))

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: order.get(f["severity"], 9))
    return findings


def inspect_file(path: str | Path) -> list[dict[str, str]]:
    try:
        return inspect_note(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return [_finding("unreadable", "error", str(exc))]


def scan_vault(
    root: str | Path,
    *,
    skip_dirs: Iterable[str] = (".obsidian", ".jarvis", "backups"),
    max_findings: int = 500,
) -> dict[str, Any]:
    """Scan every Markdown note under root and aggregate integrity findings."""
    root = Path(root)
    skip = set(skip_dirs)
    issues: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    scanned = 0
    for note in sorted(root.rglob("*.md")):
        if any(part in skip for part in note.parts):
            continue
        scanned += 1
        for finding in inspect_file(note):
            counts[finding["kind"]] = counts.get(finding["kind"], 0) + 1
            if len(issues) < max_findings:
                issues.append({"path": str(note), **finding})
    errors = sum(counts.get(k, 0) for k, v in _kinds_by_severity().items() if v == "error")
    return {
        "ok": errors == 0,
        "scanned": scanned,
        "error_count": errors,
        "counts": counts,
        "issues": issues,
    }


def _kinds_by_severity() -> dict[str, str]:
    return {
        "doubled_frontmatter": "error",
        "unparsable_frontmatter": "error",
        "exploded_tags": "error",
        "unreadable": "error",
        "crlf_frontmatter": "warning",
        "bare_file_citation": "info",
    }
