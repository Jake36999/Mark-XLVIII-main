from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Callable

import requests

from core.runtime_config import RUNTIME_CONFIG_PATH, load_runtime_config


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_PATH = RUNTIME_CONFIG_PATH

DEFAULT_NATIVE_URL = "http://localhost:1234/api/v1"
DEFAULT_OPENAI_COMPAT_URL = "http://localhost:1234/v1"
DEFAULT_BASELINE_MODELS = ["qwen/qwen3-4b-2507"]
DEFAULT_TASK_TTL_SECONDS = 300
DEFAULT_IDLE_CLEANUP_SECONDS = 300
DEFAULT_MAX_TASK_MODELS_LOADED = 1
DEFAULT_OPENCLAW_GUARD_SECONDS = 1800
DEFAULT_LOAD_TIMEOUT_SECONDS = 180
DEFAULT_GENERATION_WAIT_SECONDS = 900
DEFAULT_GENERATION_LEASE_SECONDS = 2400
DEFAULT_GENERATION_FIRST_TOKEN_SECONDS = 180
DEFAULT_GENERATION_IDLE_SECONDS = 180
DEFAULT_RESEARCH_GENERATION_MAX_SECONDS = 1800
DEFAULT_HEALTH_PROBE_TIMEOUT_SECONDS = 45
DEFAULT_HEALTH_PROBE_MAX_TOKENS = 64
# Reasoning models emit reasoning tokens before any content. `qwen/qwen3.5-9b`
# uses 110-190 completion tokens before its first content token, so a 64-token
# probe measures our own budget rather than the model.
DEFAULT_HEALTH_PROBE_REASONING_MAX_TOKENS = 512
# A probe is an optimisation. It waits only briefly for the generation lease and
# skips rather than blocking a busy machine.
DEFAULT_HEALTH_PROBE_WAIT_SECONDS = 5
DEFAULT_HEALTH_SAMPLE_TTL_SECONDS = 3600
DEFAULT_HEALTH_FAILURE_THRESHOLD = 2
DEFAULT_HEALTH_COOLDOWN_TIERS = [300, 900, 3600]
DEFAULT_HEALTH_SLOW_FIRST_TOKEN_SECONDS = 90

# Failures a model is answerable for. Everything else — a lease wait, an
# unreachable backend, memory pressure from a third-party process — records as
# `inconclusive` and must not count against the model, or working models get
# blacklisted for conditions they did not cause.
ATTRIBUTABLE_FAILURES = frozenset({"timeout", "empty_output", "malformed_output", "load_failed"})
HEALTH_OUTCOMES = frozenset({"ok", "inconclusive"}) | ATTRIBUTABLE_FAILURES
HEALTH_EWMA_ALPHA = 0.3
ACTIVE_LEASE_STATES = {"RESERVED", "LOADING", "GENERATING", "DRAINING"}
DEFAULT_MODEL_LOAD_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "context_length": 8192,
        "eval_batch_size": 256,
        "flash_attention": True,
        "offload_kv_cache_to_gpu": True,
    },
    "qwen/qwen3-4b-2507": {
        "context_length": 4096,
        "eval_batch_size": 256,
        "flash_attention": True,
        "offload_kv_cache_to_gpu": True,
    },
    "qwen2.5-14b-deepresearch-i1": {
        "context_length": 8192,
        "eval_batch_size": 256,
        "flash_attention": True,
        "offload_kv_cache_to_gpu": False,
    },
    "marco-deepresearch-8b": {
        "context_length": 8192,
        "eval_batch_size": 256,
        "flash_attention": True,
        "offload_kv_cache_to_gpu": True,
    },
    "deepseek-r1-0528-qwen3-8b": {
        "context_length": 8192,
        "eval_batch_size": 256,
        "flash_attention": True,
        "offload_kv_cache_to_gpu": True,
    },
}

_LOAD_PROFILE_FIELDS = {
    "context_length",
    "eval_batch_size",
    "flash_attention",
    "num_experts",
    "offload_kv_cache_to_gpu",
}

_active_lock = threading.RLock()
_load_lock = threading.RLock()
_lease_init_lock = threading.RLock()
_initialized_lease_dbs: set[str] = set()
_active_requests: dict[str, dict[str, Any]] = {}


def _load_file_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return load_runtime_config(path)


def _split_models(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = _normalize_model_id(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _clean_url(url: str | None, default: str) -> str:
    return (url or default).strip().rstrip("/")


def _derive_native_url(raw: dict[str, Any]) -> str:
    configured = str(raw.get("lmstudio_native_url") or "").strip()
    if configured:
        return _clean_url(configured, DEFAULT_NATIVE_URL)
    compat = _clean_url(str(raw.get("lmstudio_url") or raw.get("llm_url") or ""), DEFAULT_OPENAI_COMPAT_URL)
    if compat.endswith("/v1"):
        return f"{compat[:-3]}/api/v1"
    if compat.endswith("/api/v1"):
        return compat
    return DEFAULT_NATIVE_URL


def _coerce_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, number)


def _model_load_profiles(value: Any) -> dict[str, dict[str, Any]]:
    profiles = {key: dict(profile) for key, profile in DEFAULT_MODEL_LOAD_PROFILES.items()}
    if not isinstance(value, dict):
        return profiles
    for raw_key, raw_profile in value.items():
        if not isinstance(raw_profile, dict):
            continue
        key = _normalize_model_id(str(raw_key)) or "default"
        current = dict(profiles.get(key) or profiles.get("default") or {})
        current.update({field: raw_profile[field] for field in _LOAD_PROFILE_FIELDS if field in raw_profile})
        profiles[key] = current
    return profiles


def _cooldown_tiers(value: Any) -> list[int]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        candidates = [value]
    elif isinstance(value, str):
        candidates = [part for part in value.replace(",", " ").split() if part]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        candidates = []

    tiers: list[int] = []
    for candidate in candidates:
        try:
            seconds = int(float(candidate))
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            tiers.append(seconds)
    return tiers or list(DEFAULT_HEALTH_COOLDOWN_TIERS)


def _model_runtime_db_path(raw: dict[str, Any]) -> Path:
    configured = str(raw.get("model_runtime_db_path") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    notes_root = str(raw.get("jarvis_notes_root") or raw.get("notes_root") or "").strip()
    if notes_root:
        return (Path(notes_root).expanduser().resolve() / ".jarvis" / "model-runtime.sqlite")
    return BASE_DIR / ".aletheia_operator" / "model-runtime.sqlite"


def resolve_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _load_file_config()
    if overrides:
        raw.update({key: value for key, value in overrides.items() if value is not None})

    baseline = _split_models(raw.get("baseline_models")) or list(DEFAULT_BASELINE_MODELS)
    # The always-warm worker is baseline by definition; configs list it too, so
    # this is normally a no-op that just tolerates it being omitted.
    worker_model = str(raw.get("worker_model") or "").strip()
    if worker_model:
        baseline.append(worker_model)
    # Speech models are deliberately NOT promoted here. This used to append
    # `tts_model` and, for the Orpheus engine, `orpeus_text_to_speech` -- which
    # silently overrode `baseline_models` in runtime.json and contradicted a
    # recorded decision (2026-07-24, pinned by
    # tests/test_speech_runtime.py::test_runtime_config_gates_filler_on_user_idle):
    # three always-resident models held RAM at roughly 70% stationary, so speech
    # should load on demand and idle out through the normal task-model TTL.
    # Promoting it also made that TTL unreachable, since baseline models are
    # never unloaded. The TTS path protects the voice it is about to use through
    # `unload_non_baseline(keep=...)` instead, which is a narrower guarantee than
    # permanent residency.

    return {
        "native_url": _derive_native_url(raw),
        "api_key": "",
        "baseline_models": _dedupe(baseline),
        "task_model_ttl_seconds": _coerce_int(
            raw.get("task_model_ttl_seconds"),
            DEFAULT_TASK_TTL_SECONDS,
            minimum=1,
        ),
        "idle_cleanup_seconds": _coerce_int(
            raw.get("idle_cleanup_seconds"),
            DEFAULT_IDLE_CLEANUP_SECONDS,
            minimum=30,
        ),
        "max_task_models_loaded": _coerce_int(
            raw.get("max_task_models_loaded"),
            DEFAULT_MAX_TASK_MODELS_LOADED,
            minimum=1,
        ),
        "openclaw_cleanup_guard_seconds": _coerce_int(
            raw.get("openclaw_cleanup_guard_seconds"),
            DEFAULT_OPENCLAW_GUARD_SECONDS,
            minimum=60,
        ),
        "explicit_load_enabled": bool(raw.get("lmstudio_explicit_load_enabled", True)),
        "load_timeout_seconds": _coerce_int(
            raw.get("lmstudio_load_timeout_seconds"),
            DEFAULT_LOAD_TIMEOUT_SECONDS,
            minimum=30,
        ),
        "generation_wait_seconds": _coerce_int(
            raw.get("model_generation_wait_seconds"),
            DEFAULT_GENERATION_WAIT_SECONDS,
            minimum=1,
        ),
        "generation_lease_seconds": _coerce_int(
            raw.get("model_generation_lease_seconds"),
            DEFAULT_GENERATION_LEASE_SECONDS,
            minimum=60,
        ),
        "generation_first_token_seconds": _coerce_int(
            raw.get("model_first_token_timeout_seconds"),
            DEFAULT_GENERATION_FIRST_TOKEN_SECONDS,
            minimum=15,
        ),
        "generation_idle_seconds": _coerce_int(
            raw.get("model_inter_token_timeout_seconds"),
            DEFAULT_GENERATION_IDLE_SECONDS,
            minimum=15,
        ),
        "research_generation_max_seconds": _coerce_int(
            raw.get("research_generation_max_seconds"),
            DEFAULT_RESEARCH_GENERATION_MAX_SECONDS,
            minimum=120,
        ),
        "lease_db_path": str(_model_runtime_db_path(raw)),
        "inference_url": _clean_url(
            raw.get("lmstudio_url") or raw.get("llm_url"),
            DEFAULT_OPENAI_COMPAT_URL,
        ),
        "runtime_strategy": str(raw.get("lmstudio_runtime_strategy") or "nvidia_primary").strip().lower(),
        "model_load_profiles": _model_load_profiles(raw.get("lmstudio_model_load_profiles")),
        "health_enabled": bool(raw.get("model_health_enabled", False)),
        "health_probe_enabled": bool(raw.get("model_health_probe_enabled", False)),
        "health_probe_timeout_seconds": _coerce_int(
            raw.get("model_health_probe_timeout_seconds"),
            DEFAULT_HEALTH_PROBE_TIMEOUT_SECONDS,
            minimum=5,
        ),
        "health_probe_max_tokens": _coerce_int(
            raw.get("model_health_probe_max_tokens"),
            DEFAULT_HEALTH_PROBE_MAX_TOKENS,
            minimum=8,
        ),
        "health_probe_reasoning_max_tokens": _coerce_int(
            raw.get("model_health_probe_reasoning_max_tokens"),
            DEFAULT_HEALTH_PROBE_REASONING_MAX_TOKENS,
            minimum=64,
        ),
        "health_probe_wait_seconds": _coerce_int(
            raw.get("model_health_probe_wait_seconds"),
            DEFAULT_HEALTH_PROBE_WAIT_SECONDS,
            minimum=0,
        ),
        "health_sample_ttl_seconds": _coerce_int(
            raw.get("model_health_sample_ttl_seconds"),
            DEFAULT_HEALTH_SAMPLE_TTL_SECONDS,
            minimum=60,
        ),
        "health_failure_threshold": _coerce_int(
            raw.get("model_health_failure_threshold"),
            DEFAULT_HEALTH_FAILURE_THRESHOLD,
            minimum=1,
        ),
        "health_cooldown_seconds": _cooldown_tiers(raw.get("model_health_cooldown_seconds")),
        "health_slow_first_token_seconds": _coerce_int(
            raw.get("model_health_slow_first_token_seconds"),
            DEFAULT_HEALTH_SLOW_FIRST_TOKEN_SECONDS,
            minimum=5,
        ),
    }


def _resolved_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Accept runtime config keys or an already-normalized lifecycle config."""
    required = {
        "native_url",
        "baseline_models",
        "task_model_ttl_seconds",
        "idle_cleanup_seconds",
        "max_task_models_loaded",
        "explicit_load_enabled",
        "load_timeout_seconds",
        "runtime_strategy",
        "model_load_profiles",
    }
    if config is not None and required.issubset(config):
        defaults = resolve_config()
        defaults.update(config)
        return defaults
    return resolve_config(config)


def _headers(cfg: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    return headers


def _normalize_model_id(model: str | None) -> str:
    return (model or "").strip().lower().replace("\\", "/")


def _baseline_keys(cfg: dict[str, Any]) -> set[str]:
    keys = {_normalize_model_id(model) for model in cfg.get("baseline_models", [])}
    return {key for key in keys if key}


def load_profile_for(model: str, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    profiles = cfg.get("model_load_profiles") or {}
    candidate = _normalize_model_id(model)
    profile = dict(profiles.get("default") or {})
    exact = profiles.get(candidate)
    if isinstance(exact, dict):
        profile.update(exact)
    else:
        for key, value in profiles.items():
            normalized = _normalize_model_id(str(key))
            if normalized != "default" and normalized and (normalized in candidate or candidate in normalized):
                if isinstance(value, dict):
                    profile.update(value)
                break
    return {field: profile[field] for field in _LOAD_PROFILE_FIELDS if field in profile}


def build_load_payload(
    model: str,
    cfg: dict[str, Any] | None = None,
    *,
    model_type: str = "llm",
) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    profile = load_profile_for(model, cfg)
    if str(model_type).strip().lower() == "embedding":
        for field in ("eval_batch_size", "flash_attention", "num_experts", "offload_kv_cache_to_gpu"):
            profile.pop(field, None)
    return {
        "model": model,
        **profile,
        "echo_load_config": True,
    }


def _available_model_type(model: str, models: list[dict[str, Any]]) -> str:
    candidate = _normalize_model_id(model)
    for item in models:
        if not isinstance(item, dict):
            continue
        identities = {
            _normalize_model_id(str(item.get("key") or "")),
            _normalize_model_id(str(item.get("display_name") or "")),
            *{
                _normalize_model_id(str(variant))
                for variant in (item.get("variants") or [])
            },
        }
        if candidate in identities or any(candidate in value or value in candidate for value in identities if value):
            return str(item.get("type") or "llm").strip().lower()
    return "embedding" if "embed" in candidate else "llm"


def is_baseline_model(model: str | None, cfg: dict[str, Any] | None = None) -> bool:
    cfg = _resolved_config(cfg)
    candidate = _normalize_model_id(model)
    if not candidate:
        return False
    baseline = _baseline_keys(cfg)
    if candidate in baseline:
        return True
    if "orpheus" in baseline and ("orpheus" in candidate or "orpeus" in candidate):
        return True
    return False


def _summarize_loaded_instance(model: dict[str, Any], instance: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    config = instance.get("config") if isinstance(instance.get("config"), dict) else {}
    model_key = str(model.get("key") or "")
    instance_id = str(instance.get("id") or instance.get("instance_id") or model_key)
    display_name = str(model.get("display_name") or model_key)
    return {
        "model_key": model_key,
        "display_name": display_name,
        "type": model.get("type"),
        "instance_id": instance_id,
        "parallel": config.get("parallel"),
        "context_length": config.get("context_length"),
        "selected_variant": model.get("selected_variant"),
        "load_config": config,
        "baseline": is_baseline_model(model_key, cfg) or is_baseline_model(instance_id, cfg) or is_baseline_model(display_name, cfg),
    }


def list_models(
    cfg: dict[str, Any] | None = None,
    *,
    get: Callable = requests.get,
    timeout: int = 10,
) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    response = get(f"{cfg['native_url']}/models", headers=_headers(cfg), timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = data.get("models") if isinstance(data, dict) else []
    if not isinstance(models, list):
        models = []

    loaded: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        instances = model.get("loaded_instances") or []
        if not isinstance(instances, list):
            continue
        for instance in instances:
            if isinstance(instance, dict):
                loaded.append(_summarize_loaded_instance(model, instance, cfg))

    task_models = [item for item in loaded if not item.get("baseline")]
    return {
        "ok": True,
        "native_url": cfg["native_url"],
        "models": models,
        "loaded": loaded,
        "loaded_count": len(loaded),
        "task_loaded_count": len(task_models),
        "baseline_models": cfg["baseline_models"],
        "policy": {
            "task_model_ttl_seconds": cfg["task_model_ttl_seconds"],
            "idle_cleanup_seconds": cfg["idle_cleanup_seconds"],
            "max_task_models_loaded": cfg["max_task_models_loaded"],
            "parallel_is_instance_config": True,
            "max_active_task_generations": 1,
            "max_active_baseline_generations": 1,
            "generation_wait_seconds": cfg["generation_wait_seconds"],
            "generation_lease_seconds": cfg["generation_lease_seconds"],
            "research_generation_max_seconds": cfg["research_generation_max_seconds"],
            "lease_db_path": cfg["lease_db_path"],
            "explicit_load_enabled": cfg["explicit_load_enabled"],
            "runtime_strategy": cfg["runtime_strategy"],
        },
    }


def ensure_model_loaded(
    model: str,
    *,
    route: str = "main",
    exclusive_lease_id: str = "",
    cfg: dict[str, Any] | None = None,
    get: Callable = requests.get,
    post: Callable = requests.post,
    timeout: int | None = None,
) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    if not cfg.get("explicit_load_enabled", True):
        return {"ok": True, "skipped": True, "reason": "explicit_load_disabled", "model": model}
    timeout = int(timeout or cfg["load_timeout_seconds"])
    candidate = _normalize_model_id(model)
    if not candidate:
        return {"ok": False, "error": "A model identifier is required."}

    with _load_lock:
        listed = list_models(cfg, get=get, timeout=min(timeout, 20))
        for item in listed["loaded"]:
            loaded_keys = {
                _normalize_model_id(str(item.get("model_key") or "")),
                _normalize_model_id(str(item.get("instance_id") or "")),
                _normalize_model_id(str(item.get("display_name") or "")),
            }
            if candidate in loaded_keys or any(candidate in key or key in candidate for key in loaded_keys if key):
                return {
                    "ok": True,
                    "already_loaded": True,
                    "model": model,
                    "instance": item,
                    "profile": load_profile_for(model, cfg),
                }

        route_kind = classify_model_route(model, route, cfg)
        if route_kind == "task" and listed["task_loaded_count"] >= int(cfg["max_task_models_loaded"]):
            cleanup = unload_non_baseline(
                cfg,
                get=get,
                post=post,
                timeout=min(timeout, 30),
                force=bool(exclusive_lease_id),
            )
            if cleanup.get("skipped") or cleanup.get("failed"):
                return {
                    "ok": False,
                    "error": "Task model budget is occupied and cleanup could not make room.",
                    "cleanup": cleanup,
                }

        model_type = _available_model_type(model, listed.get("models") or [])
        payload = build_load_payload(model, cfg, model_type=model_type)
        response = post(
            f"{cfg['native_url']}/models/load",
            json=payload,
            headers=_headers(cfg),
            timeout=timeout,
        )
        try:
            response.raise_for_status()
        except Exception as exc:
            body = str(getattr(response, "text", "") or exc)
            raise RuntimeError(f"LM Studio native model load failed: {body[:500]}") from exc
        data = response.json()
        return {
            "ok": True,
            "already_loaded": False,
            "model": model,
            "model_type": model_type,
            "route": route_kind,
            "profile": {key: value for key, value in payload.items() if key not in {"model", "echo_load_config"}},
            "instance_id": data.get("instance_id"),
            "load_time_seconds": data.get("load_time_seconds"),
            "load_config": data.get("load_config") or {},
        }


def drain_model_instance(
    instance_id: str,
    *,
    model: str = "",
    route: str = "task",
    cfg: dict[str, Any] | None = None,
    get: Callable = requests.get,
    post: Callable = requests.post,
    timeout: int = 90,
) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    candidate = _normalize_model_id(instance_id or model)
    if not candidate:
        return {"ok": False, "confirmed": False, "error": "A model instance is required for drain."}
    if classify_model_route(model or instance_id, route, cfg) == "baseline":
        return {
            "ok": False,
            "confirmed": False,
            "baseline": True,
            "error": "Baseline generations cannot be force-unloaded; fallback is suppressed.",
        }
    unload_error = ""
    try:
        response = post(
            f"{cfg['native_url']}/models/unload",
            json={"instance_id": instance_id or model},
            headers=_headers(cfg),
            timeout=min(max(5, int(timeout)), 60),
        )
        response.raise_for_status()
    except Exception as exc:
        unload_error = str(exc)
    deadline = time.monotonic() + max(1, int(timeout))
    last_loaded: list[str] = []
    while time.monotonic() < deadline:
        try:
            listed = list_models(cfg, get=get, timeout=min(10, max(2, int(timeout))))
            last_loaded = [str(item.get("instance_id") or item.get("model_key") or "") for item in listed["loaded"]]
            normalized = [_normalize_model_id(item) for item in last_loaded]
            if not any(candidate == item or candidate in item or item in candidate for item in normalized if item):
                return {
                    "ok": True,
                    "confirmed": True,
                    "instance_id": instance_id or model,
                    "unload_error": unload_error,
                }
        except Exception as exc:
            unload_error = unload_error or str(exc)
        time.sleep(0.5)
    return {
        "ok": False,
        "confirmed": False,
        "instance_id": instance_id or model,
        "loaded_instances": last_loaded,
        "error": unload_error or "Timed out confirming model drain.",
    }


def _prune_expired_activity(now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    expired = [
        token
        for token, entry in _active_requests.items()
        if entry.get("expires_at") is not None and float(entry["expires_at"]) <= now
    ]
    for token in expired:
        _active_requests.pop(token, None)


def mark_request_start(model: str, *, kind: str = "model", ttl_seconds: int | None = None) -> str:
    token = uuid.uuid4().hex
    now = time.monotonic()
    with _active_lock:
        _prune_expired_activity(now)
        _active_requests[token] = {
            "model": model,
            "kind": kind,
            "started_at": now,
            "expires_at": now + ttl_seconds if ttl_seconds else None,
        }
    return token


def mark_request_done(token: str | None) -> None:
    if not token:
        return
    with _active_lock:
        _active_requests.pop(token, None)


def register_external_activity(label: str, *, ttl_seconds: int | None = None) -> str:
    cfg = resolve_config()
    return mark_request_start(
        label,
        kind="external",
        ttl_seconds=ttl_seconds or int(cfg["openclaw_cleanup_guard_seconds"]),
    )


def active_snapshot(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    with _active_lock:
        _prune_expired_activity()
        entries = list(_active_requests.values())
    persistent = persistent_generation_snapshot(cfg)
    persistent_entries = persistent.get("leases") or []
    return {
        "active_count": len(entries) + len(persistent_entries),
        "model_request_count": sum(1 for item in entries if item.get("kind") != "external") + len(persistent_entries),
        "external_activity_count": sum(1 for item in entries if item.get("kind") == "external"),
        "entries": [
            {
                "model": item.get("model"),
                "kind": item.get("kind"),
                "age_seconds": round(time.monotonic() - float(item.get("started_at", time.monotonic())), 3),
                "expires_in_seconds": (
                    round(float(item["expires_at"]) - time.monotonic(), 3)
                    if item.get("expires_at") is not None
                    else None
                ),
            }
            for item in entries
        ] + persistent_entries,
        "generation_leases": persistent_entries,
    }


def _lease_connect(cfg: dict[str, Any]) -> sqlite3.Connection:
    path = Path(str(cfg["lease_db_path"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        key = str(path).lower()
        with _lease_init_lock:
            if key not in _initialized_lease_dbs:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS model_generation_leases (
                        lease_id TEXT PRIMARY KEY,
                        resource_class TEXT NOT NULL,
                        model TEXT NOT NULL,
                        instance_id TEXT,
                        route TEXT NOT NULL,
                        state TEXT NOT NULL,
                        owner_pid INTEGER NOT NULL,
                        run_id TEXT,
                        step_id TEXT,
                        acquired_at REAL NOT NULL,
                        heartbeat_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        completed_at REAL,
                        outcome TEXT,
                        error TEXT
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS one_active_generation_per_class
                    ON model_generation_leases(resource_class)
                    WHERE state IN ('RESERVED','LOADING','GENERATING','DRAINING');
                    CREATE UNIQUE INDEX IF NOT EXISTS one_active_generation_global
                    ON model_generation_leases((1))
                    WHERE state IN ('RESERVED','LOADING','GENERATING','DRAINING');
                    CREATE TABLE IF NOT EXISTS model_generation_events (
                        event_id TEXT PRIMARY KEY,
                        lease_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS model_health (
                        model TEXT PRIMARY KEY,
                        last_outcome TEXT NOT NULL,
                        last_checked_at REAL NOT NULL,
                        last_source TEXT NOT NULL,
                        consecutive_failures INTEGER NOT NULL DEFAULT 0,
                        cooldown_until REAL,
                        ewma_first_token_seconds REAL,
                        ewma_tokens_per_second REAL,
                        sample_count INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT
                    );
                    """
                )
                connection.commit()
                _initialized_lease_dbs.add(key)
        return connection
    except Exception:
        connection.close()
        raise


def _lease_resource_class(model: str, route: str, cfg: dict[str, Any]) -> str:
    return "baseline_generation" if classify_model_route(model, route, cfg) == "baseline" else "task_generation"


def _lease_event(connection: sqlite3.Connection, lease_id: str, event_type: str, details: dict[str, Any] | None = None) -> None:
    connection.execute(
        "INSERT INTO model_generation_events VALUES (?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, lease_id, event_type, json.dumps(details or {}, sort_keys=True), time.time()),
    )


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            # Access denied means the process exists but cannot be queried.
            return int(kernel32.GetLastError()) == 5
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return int(exit_code.value) == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _expire_stale_leases(connection: sqlite3.Connection, now: float) -> None:
    stale = connection.execute(
        "SELECT lease_id,owner_pid,expires_at FROM model_generation_leases "
        "WHERE state IN ('RESERVED','LOADING','GENERATING','DRAINING')",
    ).fetchall()
    for row in stale:
        expired = float(row["expires_at"]) <= now
        orphaned = not _pid_is_alive(int(row["owner_pid"]))
        if not expired and not orphaned:
            continue
        outcome = "lease_expired" if expired else "owner_process_exit"
        connection.execute(
            "UPDATE model_generation_leases SET state='STALE', completed_at=?, outcome=? WHERE lease_id=?",
            (now, outcome, row["lease_id"]),
        )
        _lease_event(connection, row["lease_id"], outcome, {"owner_pid": int(row["owner_pid"])})


def acquire_generation_lease(
    model: str,
    *,
    route: str,
    cfg: dict[str, Any] | None = None,
    wait_seconds: float | None = None,
    run_id: str = "",
    step_id: str = "",
) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    wait_limit = float(cfg["generation_wait_seconds"] if wait_seconds is None else max(0.0, wait_seconds))
    lease_seconds = float(cfg["generation_lease_seconds"])
    resource_class = _lease_resource_class(model, route, cfg)
    started = time.monotonic()
    deadline = started + wait_limit
    while True:
        now = time.time()
        lease_id = uuid.uuid4().hex
        try:
            with closing(_lease_connect(cfg)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                _expire_stale_leases(connection, now)
                active = connection.execute(
                    "SELECT lease_id,model,state,owner_pid,heartbeat_at,expires_at FROM model_generation_leases "
                    "WHERE resource_class=? AND state IN ('RESERVED','LOADING','GENERATING','DRAINING') LIMIT 1",
                    (resource_class,),
                ).fetchone()
                if active is None:
                    connection.execute(
                        "INSERT INTO model_generation_leases "
                        "(lease_id,resource_class,model,instance_id,route,state,owner_pid,run_id,step_id,acquired_at,heartbeat_at,expires_at) "
                        "VALUES (?,?,?,?,?,'RESERVED',?,?,?,?,?,?)",
                        (
                            lease_id,
                            resource_class,
                            model,
                            "",
                            route,
                            os.getpid(),
                            run_id,
                            step_id,
                            now,
                            now,
                            now + lease_seconds,
                        ),
                    )
                    _lease_event(connection, lease_id, "lease_acquired", {"model": model, "route": route})
                    connection.commit()
                    return {
                        "ok": True,
                        "lease_id": lease_id,
                        "resource_class": resource_class,
                        "queue_wait_seconds": round(time.monotonic() - started, 3),
                        "lease_db_path": cfg["lease_db_path"],
                    }
                connection.commit()
                holder = dict(active)
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
            holder = {"state": "contended", "error": str(exc)}
        if time.monotonic() >= deadline:
            return {
                "ok": False,
                "error": "Timed out waiting for the local model generation lease.",
                "resource_class": resource_class,
                "queue_wait_seconds": round(time.monotonic() - started, 3),
                "holder": holder,
            }
        time.sleep(min(0.25, max(0.02, deadline - time.monotonic())))


def update_generation_lease(
    lease_id: str,
    *,
    state: str | None = None,
    instance_id: str | None = None,
    cfg: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    if not lease_id:
        return False
    cfg = _resolved_config(cfg)
    now = time.time()
    with closing(_lease_connect(cfg)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT lease_id FROM model_generation_leases WHERE lease_id=?", (lease_id,)).fetchone()
        if row is None:
            connection.commit()
            return False
        fields = ["heartbeat_at=?", "expires_at=?"]
        values: list[Any] = [now, now + float(cfg["generation_lease_seconds"])]
        if state:
            if state not in ACTIVE_LEASE_STATES:
                raise ValueError(f"Invalid active generation lease state: {state}")
            fields.append("state=?")
            values.append(state)
        if instance_id is not None:
            fields.append("instance_id=?")
            values.append(instance_id)
        values.append(lease_id)
        connection.execute(f"UPDATE model_generation_leases SET {', '.join(fields)} WHERE lease_id=?", values)
        _lease_event(connection, lease_id, f"lease_{(state or 'heartbeat').lower()}", details)
        connection.commit()
    return True


def release_generation_lease(
    lease_id: str | None,
    *,
    cfg: dict[str, Any] | None = None,
    outcome: str = "completed",
    error: str = "",
) -> None:
    if not lease_id:
        return
    cfg = _resolved_config(cfg)
    now = time.time()
    terminal = "COMPLETE" if outcome == "completed" else "FAILED"
    with closing(_lease_connect(cfg)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE model_generation_leases SET state=?,completed_at=?,heartbeat_at=?,outcome=?,error=? WHERE lease_id=?",
            (terminal, now, now, outcome, error[:1000], lease_id),
        )
        _lease_event(connection, lease_id, "lease_released", {"outcome": outcome, "error": error[:500]})
        connection.commit()


def persistent_generation_snapshot(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    now = time.time()
    try:
        with closing(_lease_connect(cfg)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _expire_stale_leases(connection, now)
            rows = connection.execute(
                "SELECT lease_id,resource_class,model,instance_id,route,state,owner_pid,run_id,step_id,acquired_at,heartbeat_at,expires_at "
                "FROM model_generation_leases WHERE state IN ('RESERVED','LOADING','GENERATING','DRAINING') ORDER BY acquired_at"
            ).fetchall()
            connection.commit()
    except Exception as exc:
        return {"ok": False, "leases": [], "error": str(exc), "lease_db_path": cfg["lease_db_path"]}
    leases = []
    for row in rows:
        item = dict(row)
        item["kind"] = "generation_lease"
        item["age_seconds"] = round(max(0.0, now - float(item.pop("acquired_at"))), 3)
        item["expires_in_seconds"] = round(float(item.pop("expires_at")) - now, 3)
        item.pop("heartbeat_at", None)
        leases.append(item)
    return {"ok": True, "leases": leases, "lease_db_path": cfg["lease_db_path"]}


def recently_used_models(cfg: dict[str, Any] | None = None, *, within_seconds: float | None = None) -> set[str]:
    """Models whose generation lease finished within `within_seconds`.

    `active_snapshot()` only knows about work happening *right now*, which is
    why idle cleanup could not tell "unused" from "used two seconds ago" -- by
    the time a reply is spoken the lease is already released, so a just-used
    specialist looked exactly like a cold one and got evicted before every
    single spoken reply. The lease table already records `completed_at`, so
    recency is read from there rather than adding new global state.
    """
    cfg = _resolved_config(cfg)
    ttl = float(cfg.get("task_model_ttl_seconds") or 0) if within_seconds is None else float(within_seconds)
    if ttl <= 0:
        return set()
    cutoff = time.time() - ttl
    try:
        with closing(_lease_connect(cfg)) as connection:
            rows = connection.execute(
                "SELECT DISTINCT model, instance_id FROM model_generation_leases "
                "WHERE completed_at IS NOT NULL AND completed_at >= ?",
                (cutoff,),
            ).fetchall()
    except Exception:
        # Fail open: no recency information means cleanup behaves exactly as
        # it did before. Never let this block a genuine eviction.
        return set()
    recent: set[str] = set()
    for row in rows:
        for value in (row["model"], row["instance_id"]):
            text = str(value or "").strip()
            if text:
                recent.add(text)
    return recent


def _ewma(previous: Any, sample: Any) -> float | None:
    if sample is None:
        return None if previous is None else float(previous)
    try:
        value = float(sample)
    except (TypeError, ValueError):
        return None if previous is None else float(previous)
    if previous is None:
        return value
    return HEALTH_EWMA_ALPHA * value + (1.0 - HEALTH_EWMA_ALPHA) * float(previous)


def record_model_outcome(
    model: str,
    *,
    outcome: str,
    source: str = "passive",
    metrics: dict[str, Any] | None = None,
    error: str = "",
    cfg: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Persist one observation of a model's behaviour.

    `outcome` must be one of `HEALTH_OUTCOMES`. Only `ATTRIBUTABLE_FAILURES`
    advance the consecutive-failure counter and can open a cooldown; `ok` clears
    it immediately and `inconclusive` leaves it untouched.
    """
    cfg = _resolved_config(cfg)
    if not cfg.get("health_enabled"):
        return {"ok": True, "skipped": True, "reason": "health_disabled"}

    candidate = _normalize_model_id(model)
    if not candidate:
        return {"ok": False, "error": "A model identifier is required."}

    normalized_outcome = str(outcome or "").strip().lower()
    if normalized_outcome not in HEALTH_OUTCOMES:
        raise ValueError(f"Unknown model health outcome: {outcome!r}")

    now = time.time() if now is None else float(now)
    metrics = metrics or {}
    threshold = int(cfg["health_failure_threshold"])
    tiers = list(cfg["health_cooldown_seconds"])

    with closing(_lease_connect(cfg)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT consecutive_failures,cooldown_until,ewma_first_token_seconds,"
            "ewma_tokens_per_second,sample_count FROM model_health WHERE model=?",
            (candidate,),
        ).fetchone()

        previous_failures = int(row["consecutive_failures"]) if row else 0
        previous_cooldown = row["cooldown_until"] if row else None
        previous_first_token = row["ewma_first_token_seconds"] if row else None
        previous_tps = row["ewma_tokens_per_second"] if row else None
        sample_count = (int(row["sample_count"]) if row else 0) + 1

        if normalized_outcome == "ok":
            failures = 0
            cooldown_until = None
        elif normalized_outcome == "inconclusive":
            failures = previous_failures
            cooldown_until = previous_cooldown
        else:
            failures = previous_failures + 1
            cooldown_until = None
            if failures >= threshold:
                tier_index = min(max(failures - threshold, 0), len(tiers) - 1)
                cooldown_until = now + float(tiers[tier_index])

        first_token = _ewma(previous_first_token, metrics.get("first_token_seconds"))
        tokens_per_second = _ewma(previous_tps, metrics.get("tokens_per_second"))

        connection.execute(
            "INSERT INTO model_health "
            "(model,last_outcome,last_checked_at,last_source,consecutive_failures,cooldown_until,"
            "ewma_first_token_seconds,ewma_tokens_per_second,sample_count,last_error) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(model) DO UPDATE SET "
            "last_outcome=excluded.last_outcome,last_checked_at=excluded.last_checked_at,"
            "last_source=excluded.last_source,consecutive_failures=excluded.consecutive_failures,"
            "cooldown_until=excluded.cooldown_until,"
            "ewma_first_token_seconds=excluded.ewma_first_token_seconds,"
            "ewma_tokens_per_second=excluded.ewma_tokens_per_second,"
            "sample_count=excluded.sample_count,last_error=excluded.last_error",
            (
                candidate,
                normalized_outcome,
                now,
                str(source or "passive").strip().lower(),
                failures,
                cooldown_until,
                first_token,
                tokens_per_second,
                sample_count,
                str(error or "")[:1000],
            ),
        )
        connection.commit()

    cooldown_opened = bool(cooldown_until) and cooldown_until != previous_cooldown
    if cooldown_opened:
        _emit_cooldown_event(candidate, normalized_outcome, failures, cooldown_until, error, source)

    return {
        "ok": True,
        "model": candidate,
        "outcome": normalized_outcome,
        "consecutive_failures": failures,
        "cooldown_until": cooldown_until,
        "cooldown_opened": cooldown_opened,
    }


def _emit_cooldown_event(
    model: str,
    outcome: str,
    failures: int,
    cooldown_until: float,
    error: str,
    source: str,
) -> None:
    """Make fail-over visible in the Router trace instead of silent.

    A model name and failure class are safe operational metadata; no prompt or
    response content is included. Emission is best-effort.
    """
    try:
        from core.process_events import emit_process_event

        emit_process_event(
            category="model",
            source="model_lifecycle",
            summary=f"{model} entered health cooldown after {failures} consecutive {outcome} outcomes",
            state="degraded",
            severity="warning",
            detail={
                "model": model,
                "outcome": outcome,
                "consecutive_failures": failures,
                "cooldown_seconds": max(0, int(cooldown_until - time.time())),
                "source": source,
                "error": str(error or "")[:200],
            },
        )
    except Exception:
        pass


def _health_state(record: dict[str, Any], cfg: dict[str, Any], now: float) -> str:
    if not record["sample_count"]:
        return "unknown"
    cooldown_until = record["cooldown_until"]
    if cooldown_until is not None and float(cooldown_until) > now:
        return "cooling_down"
    if now - float(record["last_checked_at"]) > float(cfg["health_sample_ttl_seconds"]):
        return "stale"
    if record["last_outcome"] != "ok":
        return "failing"
    first_token = record["ewma_first_token_seconds"]
    if first_token is not None and float(first_token) > float(cfg["health_slow_first_token_seconds"]):
        return "degraded"
    return "healthy"


def _health_record(row: Any, model: str, cfg: dict[str, Any], now: float) -> dict[str, Any]:
    record = {
        "model": model,
        "last_outcome": row["last_outcome"] if row else "",
        "last_checked_at": float(row["last_checked_at"]) if row else 0.0,
        "last_source": row["last_source"] if row else "",
        "consecutive_failures": int(row["consecutive_failures"]) if row else 0,
        "cooldown_until": row["cooldown_until"] if row else None,
        "ewma_first_token_seconds": row["ewma_first_token_seconds"] if row else None,
        "ewma_tokens_per_second": row["ewma_tokens_per_second"] if row else None,
        "sample_count": int(row["sample_count"]) if row else 0,
        "last_error": (row["last_error"] if row else "") or "",
    }
    record["state"] = _health_state(record, cfg, now)
    return record


def model_health(model: str, *, cfg: dict[str, Any] | None = None, now: float | None = None) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    candidate = _normalize_model_id(model)
    now = time.time() if now is None else float(now)
    with closing(_lease_connect(cfg)) as connection:
        row = connection.execute(
            "SELECT * FROM model_health WHERE model=?", (candidate,)
        ).fetchone()
    return _health_record(row, candidate, cfg, now)


def is_model_cooling_down(
    model: str,
    *,
    cfg: dict[str, Any] | None = None,
    now: float | None = None,
) -> tuple[bool, str]:
    """Return whether the model is inside an open cooldown, and why."""
    cfg = _resolved_config(cfg)
    if not cfg.get("health_enabled"):
        return False, ""
    now = time.time() if now is None else float(now)
    record = model_health(model, cfg=cfg, now=now)
    if record["state"] != "cooling_down":
        return False, ""
    remaining = max(0, int(float(record["cooldown_until"]) - now))
    reason = (
        f"{record['last_outcome']} x{record['consecutive_failures']}; "
        f"cooling down for {remaining}s"
    )
    if record["last_error"]:
        reason = f"{reason} ({record['last_error'][:120]})"
    return True, reason


def health_snapshot(cfg: dict[str, Any] | None = None, *, now: float | None = None) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    now = time.time() if now is None else float(now)
    with closing(_lease_connect(cfg)) as connection:
        rows = connection.execute("SELECT * FROM model_health ORDER BY model").fetchall()
    models = [_health_record(row, row["model"], cfg, now) for row in rows]
    return {
        "ok": True,
        "enabled": bool(cfg.get("health_enabled")),
        "models": models,
        "cooling_down_count": sum(1 for item in models if item["state"] == "cooling_down"),
        "sample_ttl_seconds": cfg["health_sample_ttl_seconds"],
        "failure_threshold": cfg["health_failure_threshold"],
        "cooldown_tiers": list(cfg["health_cooldown_seconds"]),
    }


PROBE_PROMPT = "Reply with the single word: ready"
PROBE_SENTINEL = "ready"


def _budget_exhausted(choice: dict[str, Any], data: dict[str, Any]) -> bool:
    """Empty content because the token budget ran out, not because the model failed.

    Either signal is sufficient: an explicit `length` finish reason, or completion
    tokens that were spent entirely on reasoning.
    """
    if str(choice.get("finish_reason") or "").strip().lower() == "length":
        return True
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    return int(details.get("reasoning_tokens") or 0) > 0


def model_reports_reasoning(model: str, models: list[dict[str, Any]]) -> bool:
    """Whether LM Studio reports this model as reasoning-enabled by default."""
    candidate = _normalize_model_id(model)
    for item in models:
        if not isinstance(item, dict):
            continue
        identities = {
            _normalize_model_id(str(item.get("key") or "")),
            _normalize_model_id(str(item.get("display_name") or "")),
        }
        if candidate not in identities:
            continue
        reasoning = (item.get("capabilities") or {}).get("reasoning")
        if not isinstance(reasoning, dict):
            return False
        return str(reasoning.get("default") or "").strip().lower() == "on"
    return False


def probe_budget_for(model: str, cfg: dict[str, Any], models: list[dict[str, Any]]) -> int:
    if model_reports_reasoning(model, models):
        return int(cfg["health_probe_reasoning_max_tokens"])
    return int(cfg["health_probe_max_tokens"])


def probe_model(
    model: str,
    *,
    route: str = "main",
    cfg: dict[str, Any] | None = None,
    get: Callable = requests.get,
    post: Callable = requests.post,
    wait_seconds: float | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Run one small bounded generation to establish whether a model works.

    Used only when no recent passive sample exists. Real traffic is the better
    signal — a model that answers a 20-token probe can still fail an 8,000-token
    synthesis — so this is a fallback for cold models, not the primary source.

    The probe acquires a generation lease like any other call: it must not
    bypass the one-generation-at-a-time guarantee.
    """
    cfg = _resolved_config(cfg)
    now = time.time() if now is None else float(now)

    if not cfg.get("health_enabled"):
        return {"ok": True, "skipped": True, "reason": "health_disabled", "model": model}
    if not cfg.get("health_probe_enabled"):
        return {"ok": True, "skipped": True, "reason": "probe_disabled", "model": model}

    existing = model_health(model, cfg=cfg, now=now)
    if existing["state"] not in {"unknown", "stale"}:
        return {
            "ok": True,
            "skipped": True,
            "reason": "recent_sample",
            "model": model,
            "health": existing,
        }

    timeout = int(cfg["health_probe_timeout_seconds"])
    if wait_seconds is None:
        wait_seconds = float(cfg["health_probe_wait_seconds"])
    lease = acquire_generation_lease(model, route=route, cfg=cfg, wait_seconds=wait_seconds)
    if not lease.get("ok"):
        record_model_outcome(
            model,
            outcome="inconclusive",
            source="probe",
            cfg=cfg,
            error=str(lease.get("error") or ""),
            now=now,
        )
        return {
            "ok": False,
            "skipped": True,
            "reason": "lease_unavailable",
            "model": model,
            "outcome": "inconclusive",
        }

    lease_id = str(lease["lease_id"])
    outcome = "inconclusive"
    error = ""
    text = ""
    skip_reason = ""
    metrics: dict[str, Any] = {}
    started = time.monotonic()
    try:
        update_generation_lease(lease_id, state="LOADING", cfg=cfg, details={"probe": True})
        ready = ensure_model_loaded(model, route=route, exclusive_lease_id=lease_id, cfg=cfg, get=get, post=post)
        if not ready.get("ok"):
            outcome = "load_failed"
            error = str(ready.get("error") or "Model load failed during probe.")
        else:
            request_model = str(ready.get("instance_id") or (ready.get("instance") or {}).get("instance_id") or model)
            update_generation_lease(lease_id, state="GENERATING", instance_id=request_model, cfg=cfg)
            try:
                inventory = list_models(cfg, get=get, timeout=min(timeout, 20)).get("models") or []
            except Exception:
                inventory = []
            response = post(
                f"{cfg['inference_url']}/chat/completions",
                json={
                    "model": request_model,
                    "messages": [{"role": "user", "content": PROBE_PROMPT}],
                    "stream": False,
                    "max_tokens": probe_budget_for(model, cfg, inventory),
                },
                headers=_headers(cfg),
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            first = choices[0] if choices else {}
            text = ((first.get("message") or {}).get("content") or "").strip() if choices else ""
            elapsed = max(0.001, time.monotonic() - started)
            metrics = {"first_token_seconds": round(elapsed, 3)}
            if text:
                outcome = "ok"
            elif _budget_exhausted(first, data):
                # We ran out of tokens, the model did not fail. Attributing this
                # would blacklist every reasoning model.
                outcome = "inconclusive"
                skip_reason = "probe_budget_exhausted"
                error = "Probe budget exhausted before the model produced content."
            else:
                outcome = "empty_output"
                error = "Probe returned no text."
    except Exception as exc:
        error = str(exc)
        if isinstance(exc, requests.exceptions.Timeout) or "timed out" in error.lower():
            outcome = "timeout"
        else:
            # Transport and backend faults are not this model's responsibility.
            outcome = "inconclusive"
    finally:
        release_generation_lease(
            lease_id,
            cfg=cfg,
            outcome="completed" if outcome == "ok" else "failed",
            error=error,
        )

    record_model_outcome(
        model,
        outcome=outcome,
        source="probe",
        metrics=metrics,
        error=error,
        cfg=cfg,
        now=now,
    )

    # A verbose but working model must not be blacklisted for adding preamble,
    # so a missing sentinel is reported, not punished.
    sentinel_matched = PROBE_SENTINEL in text.lower()
    return {
        "ok": outcome == "ok",
        "skipped": False,
        "reason": skip_reason,
        "model": model,
        "outcome": outcome,
        "sentinel_matched": sentinel_matched,
        "text": text[:200],
        "error": error[:500],
        "metrics": metrics,
    }


def classify_model_route(model: str, route: str, cfg: dict[str, Any] | None = None) -> str:
    cfg = _resolved_config(cfg)
    if is_baseline_model(model, cfg):
        return "baseline"
    if (route or "").strip().lower() in {"quick", "worker", "baseline"}:
        return "baseline" if is_baseline_model(model, cfg) else "task"
    return "task"


def prepare_lmstudio_payload(
    payload: dict[str, Any],
    *,
    model: str,
    route: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = _resolved_config(config)
    prepared = dict(payload)
    if classify_model_route(model, route, cfg) == "task":
        prepared.setdefault("ttl", int(cfg["task_model_ttl_seconds"]))
    return prepared


def unload_non_baseline(
    cfg: dict[str, Any] | None = None,
    *,
    get: Callable = requests.get,
    post: Callable = requests.post,
    timeout: int = 15,
    force: bool = False,
    keep: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Release non-baseline models.

    `keep` names models the caller is about to use and must not lose. The TTS
    path needs it: it runs this immediately before speaking, so without an
    explicit exclusion it could unload the very voice it is about to load again.
    `keep` is honoured even under `force=True` -- forcing a cleanup should not
    mean sabotaging the caller's own next call.
    """
    cfg = _resolved_config(cfg)
    active = active_snapshot(cfg)
    if active["active_count"] and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "active_requests",
            "active": active,
            "unloaded": [],
            "kept": [],
            "failed": [],
        }

    listed = list_models(cfg, get=get, timeout=timeout)
    unloaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []

    # `task_model_ttl_seconds` was configured but never actually enforced, so a
    # specialist used seconds ago was indistinguishable from an idle one and got
    # evicted before every spoken reply -- then cold-loaded again on the next
    # turn. Honour the TTL here. VRAM safety is unchanged: max_task_models_loaded
    # still evicts at the next load, and the idle sweep still fires once the TTL
    # elapses. This delays eviction; it does not remove it. `force=True` (an
    # explicit "unload models" request) bypasses it entirely.
    recent = set() if force else recently_used_models(cfg)
    protected = {_normalize_model_id(item) for item in (keep or []) if str(item).strip()}

    for item in listed["loaded"]:
        if item.get("baseline"):
            kept.append(item)
            continue
        instance_id = item.get("instance_id")
        if not instance_id:
            failed.append({"item": item, "error": "missing instance_id"})
            continue
        identifiers = {str(instance_id), str(item.get("model_key") or ""), str(item.get("display_name") or "")}
        if protected and {_normalize_model_id(value) for value in identifiers if value} & protected:
            kept.append(item)
            continue
        if recent and {str(instance_id), str(item.get("model_key") or "")} & recent:
            kept.append(item)
            continue
        try:
            response = post(
                f"{cfg['native_url']}/models/unload",
                json={"instance_id": instance_id},
                headers=_headers(cfg),
                timeout=timeout,
            )
            response.raise_for_status()
            unloaded.append({"instance_id": instance_id, "model_key": item.get("model_key")})
        except Exception as exc:
            failed.append({"instance_id": instance_id, "model_key": item.get("model_key"), "error": str(exc)})

    return {
        "ok": not failed,
        "skipped": False,
        "native_url": cfg["native_url"],
        "unloaded": unloaded,
        "kept": kept,
        "failed": failed,
        "policy": listed["policy"],
    }


def cleanup_idle(
    cfg: dict[str, Any] | None = None,
    *,
    get: Callable = requests.get,
    post: Callable = requests.post,
    timeout: int = 15,
) -> dict[str, Any]:
    return unload_non_baseline(cfg, get=get, post=post, timeout=timeout, force=False)


def status(
    cfg: dict[str, Any] | None = None,
    *,
    get: Callable = requests.get,
    timeout: int = 10,
) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    active = active_snapshot(cfg)
    try:
        health = health_snapshot(cfg)
    except Exception as exc:
        health = {"ok": False, "error": str(exc), "models": [], "cooling_down_count": 0}
    try:
        listed = list_models(cfg, get=get, timeout=timeout)
        return {
            "ok": True,
            "reachable": True,
            "native_url": cfg["native_url"],
            "baseline_models": cfg["baseline_models"],
            "loaded": listed["loaded"],
            "loaded_count": listed["loaded_count"],
            "task_loaded_count": listed["task_loaded_count"],
            "active": active,
            "health": health,
            "policy": listed["policy"],
        }
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "native_url": cfg["native_url"],
            "baseline_models": cfg["baseline_models"],
            "loaded": [],
            "loaded_count": 0,
            "task_loaded_count": 0,
            "active": active,
            "health": health,
            "policy": {
                "task_model_ttl_seconds": cfg["task_model_ttl_seconds"],
                "idle_cleanup_seconds": cfg["idle_cleanup_seconds"],
                "max_task_models_loaded": cfg["max_task_models_loaded"],
                "parallel_is_instance_config": True,
                "max_active_task_generations": 1,
                "max_active_baseline_generations": 1,
                "generation_wait_seconds": cfg["generation_wait_seconds"],
                "generation_lease_seconds": cfg["generation_lease_seconds"],
                "research_generation_max_seconds": cfg["research_generation_max_seconds"],
                "lease_db_path": cfg["lease_db_path"],
                "explicit_load_enabled": cfg["explicit_load_enabled"],
                "runtime_strategy": cfg["runtime_strategy"],
            },
            "error": str(exc),
        }


def baseline(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _resolved_config(cfg)
    return {
        "ok": True,
        "baseline_models": cfg["baseline_models"],
        "policy": {
            "task_model_ttl_seconds": cfg["task_model_ttl_seconds"],
            "idle_cleanup_seconds": cfg["idle_cleanup_seconds"],
            "max_task_models_loaded": cfg["max_task_models_loaded"],
            "max_active_task_generations": 1,
            "max_active_baseline_generations": 1,
            "generation_wait_seconds": cfg["generation_wait_seconds"],
            "generation_lease_seconds": cfg["generation_lease_seconds"],
            "research_generation_max_seconds": cfg["research_generation_max_seconds"],
            "lease_db_path": cfg["lease_db_path"],
            "native_url": cfg["native_url"],
            "explicit_load_enabled": cfg["explicit_load_enabled"],
            "runtime_strategy": cfg["runtime_strategy"],
            "model_load_profiles": cfg["model_load_profiles"],
        },
    }


def model_lifecycle(
    parameters: dict[str, Any] | None = None,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = dict(parameters or {})
    cfg = resolve_config(params.pop("_config", None))
    operation = str(params.get("operation") or "status").strip().lower()
    try:
        if operation in {"health", "status"}:
            result = status(cfg)
        elif operation == "baseline":
            result = baseline(cfg)
        elif operation == "cleanup_idle":
            result = cleanup_idle(cfg)
        elif operation == "unload_non_baseline":
            result = unload_non_baseline(cfg, force=bool(params.get("force", False)))
        elif operation in {"loaded_models", "list"}:
            result = list_models(cfg)
        elif operation in {"load_profile", "profile"}:
            model = str(params.get("model") or "")
            result = {"ok": bool(model), "model": model, "profile": load_profile_for(model, cfg)}
        elif operation in {"ensure_loaded", "load"}:
            result = ensure_model_loaded(
                str(params.get("model") or ""),
                route=str(params.get("route") or "main"),
                cfg=cfg,
            )
        elif operation == "probe":
            model = str(params.get("model") or "").strip()
            if not model:
                result = {"ok": False, "error": "A model is required for probe."}
            else:
                result = probe_model(model, route=str(params.get("route") or "main"), cfg=cfg)
        elif operation in {"model_health", "health_report"}:
            result = health_snapshot(cfg)
        else:
            result = {"ok": False, "error": f"Unknown model_lifecycle operation: {operation}"}
    except Exception as exc:
        result = {"ok": False, "operation": operation, "error": str(exc)}
    return json.dumps(result, ensure_ascii=False, indent=2)
