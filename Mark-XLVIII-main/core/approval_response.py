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

# One-click alternative to editing a checkbox by hand, for vaults with the
# Buttons community plugin installed. A button cannot tick an existing checkbox
# -- in Buttons 0.9.x `replace` means the button replacing *itself*, and text
# actions only prepend/append/insert -- so a click appends this line instead and
# the parser treats it as equivalent evidence.
#
# The line is deliberately plain enough for a human to type by hand, so nothing
# here depends on the plugin being present. Vaults without Buttons see the
# buttons render as inert code blocks and keep using the checkboxes.
_DECISION_LINE_RE = re.compile(r"^Decision:\s+(Approve|Correct|Deny)\s*$", re.IGNORECASE)


def _decision_buttons() -> list[str]:
    """Buttons plugin blocks that append a decision line when clicked.

    `type append text` writes `action` immediately after the button block, which
    keeps the recorded line inside this section where the parser looks for it.
    """
    blocks: list[str] = []
    for label in _LABELS:
        blocks += [
            "```button",
            f"name {label}",
            "type append text",
            f"action Decision: {label}",
            "```",
            "",
        ]
    return blocks


def render_approval_template() -> str:
    """The fixed Markdown block a caller appends to a note awaiting a decision.

    Exactly one decision should end up recorded -- either by ticking one
    checkbox or by clicking one button. The matching callout below is where the
    free-text correction or denial reason belongs.
    """
    return "\n".join(
        [
            f"## {APPROVAL_SECTION}",
            "",
            "Click one button below, or tick exactly one box by hand, then save this note.",
            "",
            *_decision_buttons(),
            "- [ ] **Approve** — execute the plan exactly as compiled.",
            "- [ ] **Correct** — the plan needs changes before it can run.",
            "- [ ] **Deny** — do not execute this plan.",
            "",
            # Wording held stable deliberately. Callers and tests substitute
            # correction/denial text by matching these lines verbatim, so a
            # cosmetic edit here silently turns those replacements into no-ops
            # and the placeholder text survives into a real decision.
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
    # Button clicks append `Decision: <label>` lines. Repeating the same choice
    # is harmless (a double-click is still one decision), so only the distinct
    # set matters.
    clicked = [
        match.group(1)
        for match in (_DECISION_LINE_RE.match(line.strip()) for line in section.splitlines())
        if match
    ]

    distinct = {label.capitalize() for label in checked} | {label.capitalize() for label in clicked}
    if not distinct:
        decision = "pending"
    elif len(distinct) > 1:
        # Covers a ticked box disagreeing with a clicked button just as much as
        # two ticked boxes. Both are non-decisions; the caller must refuse
        # rather than pick one.
        decision = "ambiguous"
    else:
        decision = _DECISION_BY_LABEL[next(iter(distinct)).lower()]
    return {
        "decision": decision,
        "checked_options": sorted(checked),
        "clicked_options": sorted({label.capitalize() for label in clicked}),
        "correction": _extract_callout(section, "Correction details"),
        "denial_reason": _extract_callout(section, "Reason for denial"),
    }
