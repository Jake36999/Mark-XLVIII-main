"""How this system reports whether something actually happened.

Seven defects in the 2026-07 cycle were the same defect. None shared a
subsystem; all shared a mistake about *when* a return value is allowed to claim
success:

  * vision returned "the actual image arrives in the next message" -- it never did
  * `screen_process()` returned True the moment bytes were queued to a dead session
  * MCP `cancel()` returned True while the task kept running
  * `research_state` was the literal string "complete" on every plan, including
    ones built with no sources at all
  * the lifecycle resolver reported a baseline it had silently added to
  * a Canvas implementation node with no project target compiled "successfully"
    and then did nothing

Each returned a success signal at the moment work was **dispatched**, not when
it was **done**. On a hosted stack that gap is milliseconds and invisible. Here a
model load takes ninety seconds, a vault write crosses a filesystem watcher, and
a delegated task runs in another process -- the gap is where the truth lives.

The rule
--------
**A return value describes what the caller may rely on having happened.**

If a function returns before its effect is observable, its state is `REQUESTED`.
Not `COMPLETED`, and not a bare `True`. `REQUESTED` is not a failure -- it is the
honest name for "asked for, outcome not yet known", and it is the state this
codebase kept getting wrong.

Two corollaries worth stating, because both were violated in practice:

  * A bare `True`/`False` cannot express `REQUESTED`, so it is the wrong return
    type for anything asynchronous, delegated, or queued. Prefer a named state.
  * Reporting a *configured* value is not reporting an *effective* one. If a
    function transforms its input, it must report what it produced, not what it
    was given (see `scripts/config_audit.py`, which exists for this reason).

This module is descriptive, not aspirational: `SITE_VOCABULARIES` records the
words the repaired sites actually use and maps them onto the canonical states,
so `tests/test_effect_honesty.py` can check real call sites rather than a
convention nobody adopted.
"""
from __future__ import annotations

from typing import Any

# The effect happened, and this code observed that it happened.
COMPLETED = "completed"
# Some of the effect happened. The caller must look at the detail to know what.
PARTIAL = "partial"
# Dispatched, and *not* observed to complete. The state this system kept
# mislabelling as success.
REQUESTED = "requested"
# Deliberately not attempted -- disabled, offline, or nothing to do. Distinct
# from FAILED: nothing went wrong.
SKIPPED = "skipped"
# Attempted, and did not happen.
FAILED = "failed"
# Cannot be determined. Honest, and better than guessing in either direction.
UNKNOWN = "unknown"

EFFECT_STATES = frozenset({COMPLETED, PARTIAL, REQUESTED, SKIPPED, FAILED, UNKNOWN})

# The only states a caller may read as "the effect is done". Anything else means
# the caller must not build on the effect having taken place.
ASSERTS_COMPLETION = frozenset({COMPLETED})


class EffectStateError(ValueError):
    """Raised for a state outside the vocabulary, so typos fail loudly."""


def outcome(state: str, *, summary: str = "", **detail: Any) -> dict[str, Any]:
    """Build a report of how far an effect actually got.

    `ok` is derived rather than passed in, so it cannot disagree with `state` --
    the original defects were all a success flag that had drifted away from
    what really happened.
    """
    if state not in EFFECT_STATES:
        raise EffectStateError(f"{state!r} is not an effect state; expected one of {sorted(EFFECT_STATES)}")
    payload: dict[str, Any] = {"state": state, "ok": state in ASSERTS_COMPLETION}
    if summary:
        payload["summary"] = summary
    payload.update(detail)
    return payload


def asserts_completion(state: str) -> bool:
    """Whether this state entitles a caller to act as though the effect happened."""
    return state in ASSERTS_COMPLETION


# Each repaired site kept its own domain words -- "cancellation_requested" reads
# better than "requested" at an MCP boundary. Recorded here so the equivalence is
# checkable, and so a new state added to a site without thought shows up as an
# unmapped word rather than passing silently.
SITE_VOCABULARIES: dict[str, dict[str, str]] = {
    # core/mcp_server.py :: MCPTaskStore.cancel
    "mcp_task_cancel": {
        "cancelled": COMPLETED,
        "cancellation_requested": REQUESTED,
        "completed": SKIPPED,   # already finished; the cancel did nothing
        "failed": SKIPPED,      # already failed; likewise
        "unknown": UNKNOWN,
    },
    # actions/plan_workflow.py :: _research_state
    "plan_research": {
        "complete": COMPLETED,
        "partial": PARTIAL,
        "local_only": PARTIAL,
        "offline": SKIPPED,
        "failed": FAILED,
    },
    # actions/vision_pipeline.py :: describe_image (the `path` it actually took)
    "vision_answer": {
        "ocr_then_text": COMPLETED,
        "vision_scene": COMPLETED,
        "vision_scene_fallback": COMPLETED,
        "ocr_only": PARTIAL,
        "": FAILED,
    },
}


def canonical_state(site: str, word: str) -> str:
    """Map a site's own vocabulary onto the canonical states."""
    try:
        vocabulary = SITE_VOCABULARIES[site]
    except KeyError:
        raise EffectStateError(f"no recorded vocabulary for site {site!r}") from None
    try:
        return vocabulary[word]
    except KeyError:
        raise EffectStateError(
            f"{site!r} reported {word!r}, which is not in its recorded vocabulary. "
            "Add it to SITE_VOCABULARIES with the canonical state it means."
        ) from None
