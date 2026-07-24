from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from actions import model_lifecycle
from core.runtime_config import load_runtime_config
from core.session_credentials import get_session_broker


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


MODEL_PROFILES: dict[str, dict[str, Any]] = {
    "qwen/qwen3-4b-2507": {
        "roles": ["quick", "worker", "extraction"],
        "structured_output": "medium",
        "tool_use": True,
        "context_window": 32768,
        "vram_gb": 4,
        "parallel_capacity": 2,
        "known_failures": ["Not preferred for long synthesis or high-stakes review."],
    },
    "qwen/qwen3.5-9b": {
        "roles": ["planner", "reasoning", "code", "review"],
        "structured_output": "high",
        "tool_use": True,
        "context_window": 32768,
        "vram_gb": 8,
        "parallel_capacity": 1,
        "known_failures": ["May require task-model eviction on constrained GPUs."],
    },
    "deepseek-r1-0528-qwen3-8b": {
        "roles": ["planner", "reasoning", "review", "code"],
        "structured_output": "medium",
        "tool_use": False,
        "context_window": 32768,
        "vram_gb": 8,
        "parallel_capacity": 1,
        "known_failures": ["Reasoning traces can reduce concise structured-output reliability."],
    },
    "mistralai/mistral-7b-instruct-v0.3": {
        "roles": ["quick", "worker", "code"],
        "structured_output": "low",
        "tool_use": False,
        "context_window": 32768,
        "vram_gb": 6,
        "parallel_capacity": 1,
        "known_failures": ["No native tool-use contract; validate structured output before use."],
    },
    "google/gemma-4-e4b": {
        "roles": ["quick", "worker", "vision"],
        "structured_output": "medium",
        "tool_use": True,
        "context_window": 32768,
        "vram_gb": 8,
        "parallel_capacity": 1,
        "known_failures": ["Reasoning mode can add prose around requested structured output."],
    },
    "qwen/qwen3-vl-4b": {
        "roles": ["quick", "worker", "vision", "extraction"],
        "structured_output": "medium",
        "tool_use": True,
        "context_window": 32768,
        "vram_gb": 5,
        "parallel_capacity": 1,
        "known_failures": ["Visual claims require image evidence; text-only fallback must be explicit."],
    },
    "qwen3-vl-30b-a3b-instruct": {
        "roles": ["vision", "reasoning", "planner"],
        "structured_output": "high",
        "tool_use": True,
        "context_window": 32768,
        "vram_gb": 16,
        "parallel_capacity": 1,
        "known_failures": ["May be unavailable on the current host; never silently substitute below the workflow floor."],
    },
    "qwen2.5-14b-deepresearch-i1": {
        "roles": ["research", "planner", "synthesis"],
        "structured_output": "high",
        "tool_use": False,
        "context_window": 32768,
        "vram_gb": 12,
        "parallel_capacity": 1,
        "known_failures": ["Large VRAM footprint; require lifecycle TTL."],
    },
    "marco-deepresearch-8b": {
        "roles": ["research", "planner", "synthesis"],
        "structured_output": "medium",
        "tool_use": False,
        "context_window": 32768,
        "vram_gb": 8,
        "parallel_capacity": 1,
        "known_failures": ["Verify citations independently of model prose."],
    },
    "openai": {
        "roles": ["planner", "research", "reasoning", "review", "synthesis", "code"],
        "structured_output": "high",
        "tool_use": True,
        "context_window": 100000,
        "vram_gb": 0,
        "parallel_capacity": 4,
        "known_failures": ["Session credential, quota, model access, or network may be unavailable."],
    },
}


QUALITY_FLOORS = {
    "quick": {"structured_output": "low", "tool_use": False, "min_context": 4096},
    "worker": {"structured_output": "medium", "tool_use": False, "min_context": 8192},
    "planner": {"structured_output": "high", "tool_use": True, "min_context": 16000},
    "research": {"structured_output": "medium", "tool_use": False, "min_context": 16000},
    "review": {"structured_output": "medium", "tool_use": False, "min_context": 16000},
}

_LEVEL = {"low": 1, "medium": 2, "high": 3}


# Explicit spellings that should resolve onto a calibrated profile. Substring
# matching is deliberately not used: `qwen3-8b` is a distinct installed model whose
# key is a strict substring of `deepseek-r1-0528-qwen3-8b`, and fuzzy matching gave
# it DeepSeek's capabilities.
MODEL_ALIASES: dict[str, str] = {}


def normalize_model_id(value: str) -> str:
    return (value or "").strip().lower().replace("\\", "/")


def _strip_variant(value: str) -> str:
    """Drop an LM Studio variant qualifier such as `@q4_k_m`."""
    return value.split("@", 1)[0].strip()


def _profile_index() -> dict[str, str]:
    return {normalize_model_id(key): key for key in MODEL_PROFILES if key != "openai"}


def _profile_for(model_id: str) -> dict[str, Any]:
    normalized = normalize_model_id(model_id)
    index = _profile_index()

    key = index.get(normalized)
    if key is None:
        alias = MODEL_ALIASES.get(normalized)
        if alias:
            key = index.get(normalize_model_id(alias))
    if key is None:
        base = normalize_model_id(_strip_variant(normalized))
        if base and base != normalized:
            key = index.get(base)
    if key is not None:
        return {"profile_id": key, **MODEL_PROFILES[key]}

    return {
        "profile_id": normalized,
        "roles": ["worker"],
        "structured_output": "low",
        "tool_use": False,
        "context_window": 8192,
        "vram_gb": None,
        "parallel_capacity": 1,
        "known_failures": ["Capability profile has not been calibrated."],
    }


def meets_floor(profile: dict[str, Any], role: str) -> tuple[bool, list[str]]:
    floor = QUALITY_FLOORS.get(role, QUALITY_FLOORS["worker"])
    reasons: list[str] = []
    if _LEVEL.get(str(profile.get("structured_output")), 0) < _LEVEL[floor["structured_output"]]:
        reasons.append("structured_output_below_floor")
    if floor["tool_use"] and not profile.get("tool_use"):
        reasons.append("tool_use_below_floor")
    if int(profile.get("context_window") or 0) < int(floor["min_context"]):
        reasons.append("context_window_below_floor")
    return not reasons, reasons


def _reported_capabilities(item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Facts LM Studio reports directly.

    These outrank the hand-declared table: `MODEL_PROFILES` understated context
    windows across the board and contradicted LM Studio on tool support for the
    research models. `structured_output` has no reported equivalent and stays
    declared.
    """
    reported: dict[str, Any] = {}
    fields: list[str] = []

    max_context = item.get("max_context_length")
    if isinstance(max_context, int) and max_context > 0:
        reported["context_window"] = max_context
        fields.append("context_window")

    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict):
        if "trained_for_tool_use" in capabilities:
            reported["tool_use"] = bool(capabilities.get("trained_for_tool_use"))
            fields.append("tool_use")
        if "vision" in capabilities:
            reported["vision"] = bool(capabilities.get("vision"))
            fields.append("vision")

    return reported, fields


def registry_status(config: dict[str, Any] | None = None, *, timeout: int = 3) -> dict[str, Any]:
    cfg = load_runtime_config()
    if config:
        cfg.update(config)
    try:
        cloud = get_session_broker().status("openai")
    except Exception as exc:
        cloud = {"state": "unlinked", "reason": f"broker_unavailable: {exc}"}
    lifecycle_cfg = model_lifecycle.resolve_config(cfg)
    try:
        lifecycle = model_lifecycle.list_models(lifecycle_cfg, timeout=timeout)
        lmstudio_health = "healthy"
        models = lifecycle.get("models") or []
    except Exception as exc:
        lifecycle = {"ok": False, "error": str(exc), "loaded": []}
        lmstudio_health = "unavailable"
        models = []

    health_enabled = bool(lifecycle_cfg.get("health_enabled"))
    health_by_model: dict[str, dict[str, Any]] = {}
    if health_enabled:
        try:
            snapshot = model_lifecycle.health_snapshot(lifecycle_cfg)
            health_by_model = {
                normalize_model_id(item["model"]): item for item in snapshot.get("models") or []
            }
        except Exception:
            health_by_model = {}
    local: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("key") or item.get("model_key") or item.get("id") or item.get("display_name") or "")
        if not model_id:
            continue
        profile = _profile_for(model_id)
        reported, reported_fields = _reported_capabilities(item)
        quantization = item.get("quantization") if isinstance(item.get("quantization"), dict) else {}
        health = health_by_model.get(normalize_model_id(model_id), {})
        cooling_down = health.get("state") == "cooling_down"
        local.append(
            {
                "provider": "lmstudio",
                "model": model_id,
                **profile,
                **reported,
                "vision": reported.get("vision", "vision" in (profile.get("roles") or [])),
                "size_bytes": item.get("size_bytes"),
                "params_string": item.get("params_string"),
                "quantization": quantization.get("name"),
                "architecture": item.get("architecture"),
                # `installed` is inventory; `available` is measured selectability.
                "installed": True,
                "available": not cooling_down,
                "health": health.get("state", "unknown"),
                "cooldown_until": health.get("cooldown_until"),
                "consecutive_failures": health.get("consecutive_failures", 0),
                "last_error": health.get("last_error", ""),
                "loaded_instances": len(item.get("loaded_instances") or []),
                "reported_fields": reported_fields,
                "declared_fields": sorted(set(profile) - set(reported) - {"profile_id"}),
                "last_health_check": _now(),
            }
        )
    openai_profile = {"profile_id": "openai", **MODEL_PROFILES["openai"]}
    cloud_model = str(cfg.get("planner_model") or cfg.get("openai_model") or "gpt-5.5")
    cloud_record = {
        "provider": "openai",
        "model": cloud_model,
        **openai_profile,
        "vision": "vision" in openai_profile.get("roles", []),
        "installed": cloud.get("state") == "linked",
        "available": cloud.get("state") == "linked",
        "cooldown_until": None,
        "consecutive_failures": 0,
        "last_error": "",
        "health": cloud.get("state", "unlinked"),
        "health_reason": cloud.get("reason", ""),
        "reported_fields": [],
        "declared_fields": sorted(set(openai_profile) - {"profile_id"}),
        "last_health_check": _now(),
    }
    result = {
        "ok": True,
        "last_health_check": _now(),
        "lmstudio_health": lmstudio_health,
        "models": [cloud_record, *local],
        "lifecycle": lifecycle,
        "quality_floors": QUALITY_FLOORS,
    }
    result["routes"] = route_inventory_diagnostics(config, status_payload=result)
    return result


def route_inventory_diagnostics(
    config: dict[str, Any] | None = None,
    *,
    status_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Report configured route entries that LM Studio does not actually have.

    A route that names an absent model advertises a fallback which can never be
    selected, so capability health reports a depth of coverage that does not
    exist. Silent when LM Studio is unreachable — an unavailable backend is not
    evidence that every model is missing.
    """
    cfg = load_runtime_config()
    if config:
        cfg.update(config)
    status = status_payload or registry_status(config)

    if str(status.get("lmstudio_health") or "") == "unavailable":
        return {"ok": True, "missing": [], "checked": 0, "reason": "lmstudio_unavailable"}

    installed = {
        normalize_model_id(str(record.get("model") or ""))
        for record in status.get("models") or []
        if record.get("provider") == "lmstudio"
    }
    installed.discard("")

    missing: list[dict[str, str]] = []
    checked = 0
    for route, models in (cfg.get("model_routes") or {}).items():
        for model in models or []:
            checked += 1
            if normalize_model_id(str(model)) not in installed:
                missing.append({"route": str(route), "model": str(model)})

    return {"ok": not missing, "missing": missing, "checked": checked, "reason": ""}


# A cold-selection probe is a safeguard, not a search. Never walk the whole
# inventory looking for a model that answers.
MAX_COLD_PROBES = 2

# States backed by a usable recent measurement. `degraded` is slow but working.
# `failing` is deliberately excluded: a single probe failure sits below the
# cooldown threshold, so without this the model that just failed would be handed
# straight back on the next call.
MEASURED_GOOD_STATES = frozenset({"healthy", "degraded"})

# Preference order when quality is otherwise equal.
_HEALTH_RANK = {"healthy": 0, "degraded": 1, "unknown": 2, "stale": 3, "failing": 4, "cooling_down": 5}


def _probe_cold_candidates(
    eligible: list[dict[str, Any]],
    config: dict[str, Any] | None,
    *,
    probe_fn: Any,
    probe_failures: list[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return the first candidate that is either already measured or probes clean.

    Only models with no usable measurement are probed. A skipped probe (busy
    lease, disabled) is not a failure — selection proceeds unprobed rather than
    blocking on an optimisation.
    """
    probed: list[str] = []
    for candidate in eligible:
        if candidate.get("provider") != "lmstudio":
            return candidate, probed
        if candidate.get("health") in MEASURED_GOOD_STATES:
            return candidate, probed
        if len(probed) >= MAX_COLD_PROBES:
            return candidate, probed

        model = str(candidate.get("model") or "")
        probed.append(model)
        try:
            result = probe_fn(model, cfg=config)
        except Exception:
            # The probe subsystem is not a precondition for answering.
            return candidate, probed
        if result.get("skipped") or result.get("ok"):
            return candidate, probed
        probe_failures.append(model)

    return None, probed


def select_for_role(
    role: str,
    config: dict[str, Any] | None = None,
    *,
    status_payload: dict[str, Any] | None = None,
    probe: bool = False,
    probe_fn: Any = None,
) -> dict[str, Any]:
    status = status_payload or registry_status(config)
    normalized_role = str(role or "worker").strip().lower()
    candidates: list[dict[str, Any]] = []
    cooling_down: list[str] = []
    for record in status.get("models") or []:
        if record.get("health") == "cooling_down":
            cooling_down.append(str(record.get("model") or ""))
        if not record.get("available"):
            continue
        passed, reasons = meets_floor(record, normalized_role)
        if normalized_role not in record.get("roles", []) and normalized_role not in {"quick", "worker"}:
            passed = False
            reasons = [*reasons, "role_not_profiled"]
        candidates.append({**record, "meets_floor": passed, "floor_failures": reasons})
    eligible = [item for item in candidates if item["meets_floor"]]
    provider_preference = {"openai": 0, "lmstudio": 1}
    eligible.sort(
        key=lambda item: (
            provider_preference.get(item["provider"], 9),
            # A measured-good model outranks an equally-specified one that has
            # failed recently.
            _HEALTH_RANK.get(str(item.get("health") or "unknown"), 2),
            -_LEVEL.get(item.get("structured_output"), 0),
            -int(item.get("context_window") or 0),
        )
    )
    probe_failures: list[str] = []
    probed: list[str] = []
    probe_allowed = bool(probe)
    if probe_allowed:
        lifecycle_cfg = model_lifecycle.resolve_config(config)
        probe_allowed = bool(
            lifecycle_cfg.get("health_enabled") and lifecycle_cfg.get("health_probe_enabled")
        )

    if eligible and probe_allowed:
        selected, probed = _probe_cold_candidates(
            eligible,
            config,
            probe_fn=probe_fn or model_lifecycle.probe_model,
            probe_failures=probe_failures,
        )
    else:
        selected = eligible[0] if eligible else None

    error = ""
    if not selected:
        if probe_failures:
            error = (
                "No healthy model meets the workflow quality floor; "
                f"{len(probe_failures)} candidate(s) failed a live probe: "
                f"{', '.join(probe_failures)}."
            )
        elif cooling_down:
            # Pause on an explicit reason rather than silently dropping below the
            # role's quality floor.
            error = (
                "No healthy model meets the workflow quality floor; "
                f"{len(cooling_down)} candidate(s) are cooling down after repeated failures: "
                f"{', '.join(sorted(item for item in cooling_down if item))}."
            )
        else:
            error = "No healthy model meets the workflow quality floor."

    return {
        "ok": bool(selected),
        "role": normalized_role,
        "selected": selected,
        "candidates": candidates,
        "cooling_down": sorted(item for item in cooling_down if item),
        "probed": probed,
        "probe_failures": probe_failures,
        "error": error,
    }


def model_registry(parameters: dict[str, Any] | None = None, response=None, player=None, session_memory=None, speak=None) -> str:
    params = dict(parameters or {})
    operation = str(params.get("operation") or "status").strip().lower()
    try:
        if operation in {"status", "health", "list"}:
            result = registry_status(params.get("_config"))
        elif operation in {"select", "route"}:
            result = select_for_role(str(params.get("role") or "worker"), params.get("_config"))
        elif operation == "floor":
            result = {"ok": True, "floors": QUALITY_FLOORS}
        elif operation in {"routes", "inventory"}:
            result = route_inventory_diagnostics(params.get("_config"))
        else:
            result = {"ok": False, "error": f"Unknown model_registry operation: {operation}"}
    except Exception as exc:
        result = {"ok": False, "operation": operation, "error": str(exc)}
    return json.dumps(result, ensure_ascii=True, indent=2)
