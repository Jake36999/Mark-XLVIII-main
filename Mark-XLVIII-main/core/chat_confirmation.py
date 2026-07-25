"""Plain-chat tool confirmation helpers.

Pure and stateless: the pending-confirmation state itself lives on the
`JarvisLive` instance (main.py), not here. Kept separate from
`core/tool_dispatcher.py` because that module's `_verify_workflow_authorization`
gate requires a pre-approved, hash-frozen `dual_orchestrator` workflow bundle
-- there is no such bundle for a spontaneous chat request, so plain chat needs
its own lightweight ask-then-resume mechanism instead of reusing that gate
directly. `classify_effect()` (the read/write/destructive classifier) is
still reused as-is from `core.tool_dispatcher`.
"""
from __future__ import annotations

import re
from typing import Any

# Deliberately `fullmatch`, not `search`: "yes but also do X" must NOT match,
# so any reply beyond a clean affirmative falls through to normal routing
# rather than being (mis)treated as authorization for a stale pending action.
_AFFIRMATIVE_RE = re.compile(
    r"^(?:sir[, ]*)?(?:yes|yeah|yep|yup|confirm(?:ed)?|affirmative|correct|"
    r"that'?s right|do it|go ahead|proceed|please (?:do|proceed)|sure|"
    r"ok(?:ay)?)(?:[, ]*sir)?[.!]?$",
    re.IGNORECASE,
)


def is_affirmative_reply(text: str) -> bool:
    return bool(_AFFIRMATIVE_RE.fullmatch((text or "").strip()))


def describe_pending_action(tool_name: str, arguments: dict[str, Any], classification: dict[str, Any]) -> str:
    from actions.capability_registry import CAPABILITY_POLICY

    policy = CAPABILITY_POLICY.get(tool_name) or {}
    boundary = str(policy.get("permission_boundary") or "").strip()
    operation = str(classification.get("operation") or "").strip()
    effect = str(classification.get("effect") or "write").strip()

    action_desc = f"call `{tool_name}`"
    if operation:
        action_desc += f" (operation: `{operation}`)"
    args_preview = ", ".join(f"{key}={value!r}" for key, value in list(arguments.items())[:5])
    if args_preview:
        action_desc += f" with {args_preview}"

    lines = [f"This would {action_desc} -- a {effect} action that requires confirmation."]
    if boundary:
        lines.append(boundary)
    lines.append("Reply with a clear yes to proceed, or say anything else to cancel.")
    return " ".join(lines)
