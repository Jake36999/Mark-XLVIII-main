from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

DEFAULT_NATIVE_URL = "http://localhost:1234/api/v1"
DEFAULT_OPENAI_COMPAT_URL = "http://localhost:1234/v1"
DEFAULT_BASELINE_MODELS = ["qwen/qwen3-4b-2507", "orpeus_text_to_speech"]
DEFAULT_TASK_TTL_SECONDS = 300
DEFAULT_IDLE_CLEANUP_SECONDS = 300
DEFAULT_MAX_TASK_MODELS_LOADED = 1
DEFAULT_OPENCLAW_GUARD_SECONDS = 1800

_active_lock = threading.RLock()
_active_requests: dict[str, dict[str, Any]] = {}


def _load_file_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


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


def resolve_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _load_file_config()
    if overrides:
        raw.update({key: value for key, value in overrides.items() if value is not None})

    baseline = _split_models(raw.get("baseline_models")) or list(DEFAULT_BASELINE_MODELS)
    for key in ("worker_model", "tts_model"):
        value = str(raw.get(key) or "").strip()
        if value:
            baseline.append(value)
    if str(raw.get("tts_engine") or "").strip().lower() == "orpheus":
        baseline.append("orpeus_text_to_speech")

    return {
        "native_url": _derive_native_url(raw),
        "api_key": os.environ.get("LMSTUDIO_API_KEY") or str(raw.get("lmstudio_api_key") or ""),
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
    }


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


def is_baseline_model(model: str | None, cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or resolve_config()
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
        "baseline": is_baseline_model(model_key, cfg) or is_baseline_model(instance_id, cfg) or is_baseline_model(display_name, cfg),
    }


def list_models(
    cfg: dict[str, Any] | None = None,
    *,
    get: Callable = requests.get,
    timeout: int = 10,
) -> dict[str, Any]:
    cfg = cfg or resolve_config()
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
        },
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


def active_snapshot() -> dict[str, Any]:
    with _active_lock:
        _prune_expired_activity()
        entries = list(_active_requests.values())
    return {
        "active_count": len(entries),
        "model_request_count": sum(1 for item in entries if item.get("kind") != "external"),
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
        ],
    }


def classify_model_route(model: str, route: str, cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or resolve_config()
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
    cfg = resolve_config(config)
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
) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    active = active_snapshot()
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

    for item in listed["loaded"]:
        if item.get("baseline"):
            kept.append(item)
            continue
        instance_id = item.get("instance_id")
        if not instance_id:
            failed.append({"item": item, "error": "missing instance_id"})
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
    cfg = cfg or resolve_config()
    active = active_snapshot()
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
            "policy": {
                "task_model_ttl_seconds": cfg["task_model_ttl_seconds"],
                "idle_cleanup_seconds": cfg["idle_cleanup_seconds"],
                "max_task_models_loaded": cfg["max_task_models_loaded"],
                "parallel_is_instance_config": True,
            },
            "error": str(exc),
        }


def baseline(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    return {
        "ok": True,
        "baseline_models": cfg["baseline_models"],
        "policy": {
            "task_model_ttl_seconds": cfg["task_model_ttl_seconds"],
            "idle_cleanup_seconds": cfg["idle_cleanup_seconds"],
            "max_task_models_loaded": cfg["max_task_models_loaded"],
            "native_url": cfg["native_url"],
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
        else:
            result = {"ok": False, "error": f"Unknown model_lifecycle operation: {operation}"}
    except Exception as exc:
        result = {"ok": False, "operation": operation, "error": str(exc)}
    return json.dumps(result, ensure_ascii=False, indent=2)
