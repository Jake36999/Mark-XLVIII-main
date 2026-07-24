"""A predictable, parseable checkbox+callout approval schema for plan review.

Both planning modes (Mode 1's long-form Markdown plan in `plan_workflow.py` and
Mode 2's Canvas graph in `canvas_plan.py`) eventually put a compiled plan in
front of the user for a yes/no/correction decision. A plain approve/deny button
in a UI cannot carry a correction or a reason, and free-form chat replies are
not reliably parseable. This gives both modes the same fixed, three-option
template with bounded input boxes (Obsidian callouts) for the free-text case,
so the response can be read back deterministically regardless of which
planning mode produced it.

The three options are mutually exclusive by construction: this module never
guesses when more than one box is checked (`"ambiguous"`) or when none is
(`"pending"`) — the caller must refuse to act in both cases. This module only
renders and parses; it has no opinion on what "approve" should cause the caller
to do.
"""

from __future__ import annotations

import re
from typing import Any

APPROVAL_SECTION = "Approval Decision"

_LABELS = ("Approve", "Correct", "Deny")
_DECISION_BY_LABEL = {"approve": "approve", "correct": "correct", "deny": "deny"}
_CHECKBOX_RE = re.compile(r"^-\s+\[([ xX])\]\s+\*\*(Approve|Correct|Deny)\*\*", re.IGNORECASE)


def render_approval_template() -> str:
    """The fixed Markdown block a caller appends to a note awaiting a decision.

    Exactly one checkbox should end up checked; the matching callout below it is
    where the free-text correction or denial reason belongs.
    """
    return "\n".join(
        [
            f"## {APPROVAL_SECTION}",
            "",
            "Mark exactly one box below, then save this note.",
            "",
            "- [ ] **Approve** — execute the plan exactly as compiled.",
            "- [ ] **Correct** — the plan needs changes before it can run.",
            "- [ ] **Deny** — do not execute this plan.",
            "",
            "> [!note] Correction details (only read if **Correct** is checked)",
            "> Describe what should change.",
            "",
            "> [!note] Reason for denial (only read if **Deny** is checked)",
            "> Explain why this plan should not run.",
        ]
    )


def _extract_section(body: str, section_name: str) -> str:
    lines = (body or "").splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(section_name)}\s*$", line.strip(), flags=re.I):
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"^##\s+\S", lines[index].strip()):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def _extract_callout(section_text: str, title_prefix: str) -> str:
    lines = section_text.splitlines()
    pattern = rf"^>\s*\[!note\][+-]?\s*{re.escape(title_prefix)}"
    start = None
    for index, line in enumerate(lines):
        if re.match(pattern, line.strip(), flags=re.I):
            start = index + 1
            break
    if start is None:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped.startswith(">"):
            break
        collected.append(stripped[1:].strip())
    return "\n".join(collected).strip()


def parse_approval_response(body: str) -> dict[str, Any]:
    """Read a decision back out of a note carrying `render_approval_template()`.

    Returns `{"decision": "pending"|"approve"|"correct"|"deny"|"ambiguous",
    "correction": str, "denial_reason": str}`. `"pending"` (nothing checked) and
    `"ambiguous"` (more than one box checked) are both non-decisions — a caller
    must refuse to act on either rather than guess which the user meant.
    """
    section = _extract_section(body, APPROVAL_SECTION)
    checked = [
        match.group(2)
        for match in (_CHECKBOX_RE.match(line.strip()) for line in section.splitlines())
        if match and match.group(1).lower() == "x"
    ]
    if not checked:
        decision = "pending"
    elif len(checked) > 1:
        decision = "ambiguous"
    else:
        decision = _DECISION_BY_LABEL[checked[0].lower()]
    return {
        "decision": decision,
        "checked_options": sorted(checked),
        "correction": _extract_callout(section, "Correction details"),
        "denial_reason": _extract_callout(section, "Reason for denial"),
    }
