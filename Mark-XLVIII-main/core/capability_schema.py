"""The centralised capability schema.

One stable, abstract data source that the scattered registries this session
found -- `actions.capability_registry.CAPABILITY_HELP`/`CAPABILITY_POLICY`,
`core.tool_catalogue.DISPATCHABLE_TOOL_IDS`, `actions.canvas_plan`'s
`_ROLE_SPECS[...]["allowed_tools"]` and `_KNOWN_MODEL_ROUTER_ROLES` -- become
consumers of, rather than each independently re-deriving its own partial view
of "what capabilities exist." This is the Clean Architecture "abstract
component" pattern (Component Coupling, Ch.14): a component containing
nothing but a stable data shape, which every volatile, concrete
implementation depends on, never the reverse. See
`D:\\Resource-Library\\branch offerings\\Mark-XLVIII\\Application - A
Centralised Capability Router for Canvas Mode 2.md` for the full design this
implements.

Deliberately not a new registry of its own data: `_tool_capabilities()` reads
`capability_registry.py`'s existing `_tool_help()` merge (CAPABILITY_HELP +
CAPABILITY_POLICY) rather than duplicating keywords/risk/confirmation a
second time. The one genuinely new piece of information this module owns is
`_WORKFLOW_DISPATCHABLE_TOOL_IDS` -- which of CAPABILITY_HELP's ~20 live-chat
capabilities `dual_orchestrator.WorkflowRuntime._dispatch_tool` actually
implements a branch for. That fact can't be derived from CAPABILITY_HELP
itself (it covers every live-chat capability, most unreachable from a
workflow tool step); it has to be declared once, and this is that one place,
replacing the fifth hand-maintained copy `tool_catalogue.py` held before this
migration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CapabilityKind = Literal["tool", "model_role", "lens"]

# Written by scripts/derive_capability_keywords.py's offline, two-step blind
# LLM pipeline -- see that script and "Deriving the `keywords` Axis" in the
# design doc. Loaded here read-only, best-effort: the file may not exist yet
# (nothing has derived anything), and this must never be the reason
# capability lookups fail. Deliberately never merged into `keywords` --
# derived and hand-authored keywords stay comparable, not blended, until a
# human has actually looked at both.
_DERIVED_KEYWORDS_PATH = Path(__file__).resolve().parent.parent / "config" / "derived_capability_keywords.json"

_RISK_LEVEL_TO_TIER = {"low": "T1", "medium": "T2", "high": "T3", "critical": "T4"}

# Mirrors dual_orchestrator.WorkflowRuntime._dispatch_tool's actual target
# branches by hand -- there is no single source of truth for "which tools a
# workflow step can reach" in the orchestrator itself, so it has to be
# declared here and kept in sync manually when a branch is added or removed.
_WORKFLOW_DISPATCHABLE_TOOL_IDS = frozenset({"web_search", "jarvis_memory", "project_operator", "capability_registry"})

# model_router.py roles that carry real, explicit provider/model config in
# runtime.json (planner_provider, worker_provider, research_provider,
# reviewer_provider). Moved here from canvas_plan._KNOWN_MODEL_ROUTER_ROLES
# (2026-09-24) as part of the same migration -- a `recommended model:`
# directive naming anything outside this set would silently fall through
# resolve_settings's generic `cfg.get(f"{role}_provider")` branch to its
# lmstudio default, the exact bug class found live the same day with the
# "reviewer" role.
_MODEL_ROLE_IDS = ("planner", "worker", "research", "reviewer")


# Which canvas roles a tool capability may be offered to at all -- the same
# fact canvas_plan._ROLE_SPECS["research"]["allowed_tools"] declared by hand
# before this migration. Not every dispatchable tool needs an entry here:
# "implementation" reaches project_operator through a fixed, compile-time-
# frozen target assignment (see _ROLE_SPECS["implementation"]), never through
# the role's own allowed_tools + tool_catalogue.rank_tools mechanism this
# governs, so project_operator legitimately has no role ceiling here.
_TOOL_ALLOWED_ROLES: dict[str, tuple[str, ...]] = {
    "web_search": ("research",),
    "jarvis_memory": ("research",),
    "capability_registry": ("research",),
}


@dataclass(frozen=True)
class Capability:
    id: str
    kind: CapabilityKind
    keywords: tuple[str, ...] = ()
    derived_keywords: tuple[str, ...] = ()
    risk_tier: str = "T1"
    requires_confirmation: bool = False
    provider: str = ""
    health_eligible: bool = False
    allowed_roles: tuple[str, ...] = ()
    summary: str = ""
    details: str = ""


def _load_derived_keywords() -> dict[str, tuple[str, ...]]:
    try:
        raw = json.loads(_DERIVED_KEYWORDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(capability_id): tuple(str(k) for k in (entry.get("keywords") or []))
        for capability_id, entry in raw.items()
        if isinstance(entry, dict)
    }


def _tool_capabilities() -> tuple[Capability, ...]:
    from actions.capability_registry import _tool_help

    derived = _load_derived_keywords()
    capabilities = []
    for tool_id in sorted(_WORKFLOW_DISPATCHABLE_TOOL_IDS):
        help_data = _tool_help(tool_id)
        risk_level = str(help_data.get("risk_level") or "high").lower()
        capabilities.append(
            Capability(
                id=tool_id,
                kind="tool",
                keywords=tuple(help_data.get("keywords") or []),
                derived_keywords=derived.get(tool_id, ()),
                risk_tier=_RISK_LEVEL_TO_TIER.get(risk_level, "T3"),
                requires_confirmation=bool(help_data.get("requires_confirmation", True)),
                allowed_roles=_TOOL_ALLOWED_ROLES.get(tool_id, ()),
                summary=str(help_data.get("summary") or ""),
                details=str(help_data.get("details") or ""),
            )
        )
    return tuple(capabilities)


def _model_role_capabilities() -> tuple[Capability, ...]:
    return tuple(
        Capability(id=role_id, kind="model_role", health_eligible=True) for role_id in _MODEL_ROLE_IDS
    )


def all_capabilities() -> tuple[Capability, ...]:
    """Every known capability, tool and model role alike. No `lens` entries
    yet -- that directive doesn't exist in the canvas compiler; when it's
    built, its capabilities join here as `kind="lens"`, not a sixth parallel
    registry."""
    return _tool_capabilities() + _model_role_capabilities()


def by_kind(kind: CapabilityKind) -> tuple[Capability, ...]:
    return tuple(c for c in all_capabilities() if c.kind == kind)


def ids_by_kind(kind: CapabilityKind) -> frozenset[str]:
    return frozenset(c.id for c in by_kind(kind))


def get(capability_id: str) -> Capability | None:
    for capability in all_capabilities():
        if capability.id == capability_id:
            return capability
    return None


def tool_ids_for_role(role: str) -> tuple[str, ...]:
    """The hard tool ceiling for a canvas role -- what it may ever be
    offered, regardless of how a specific node's instruction scores.
    `_ROLE_SPECS[role]["allowed_tools"]` reads this directly rather than
    declaring its own list a second time."""
    return tuple(c.id for c in by_kind("tool") if role in c.allowed_roles)
