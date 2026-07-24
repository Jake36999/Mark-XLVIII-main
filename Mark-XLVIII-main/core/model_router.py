from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import requests

from actions import model_lifecycle as model_lifecycle_service
from core.process_events import emit_process_event
from core.runtime_config import RUNTIME_CONFIG_PATH, load_runtime_config
from core.session_credentials import get_session_broker


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_PATH = RUNTIME_CONFIG_PATH

DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_WORKER_MODEL = "qwen/qwen3-4b"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1"
DEFAULT_LMSTUDIO_URL = "http://localhost:1234/v1"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
OPENAI_KEY_CHECK_TTL_SECONDS = 600
_OPENAI_KEY_CHECK_CACHE: dict[tuple[str, str], tuple[bool, float]] = {}
_PROVENANCE = threading.local()
DEFAULT_LMSTUDIO_ROUTES = {
    "quick": [
        "mistralai/mistral-7b-instruct-v0.3",
        "google/gemma-4-e4b",
        "qwen/qwen3-vl-4b",
    ],
    "main": [
        "qwen/qwen3.5-9b",
        "mistralai/mistral-7b-instruct-v0.3",
        "deepseek-r1-0528-qwen3-8b",
        "google/gemma-4-e4b",
    ],
    "reasoning": [
        "deepseek-r1-0528-qwen3-8b",
        "qwen/qwen3.5-9b",
        "mistralai/mistral-7b-instruct-v0.3",
    ],
    "code": [
        "deepseek-r1-0528-qwen3-8b",
        "qwen/qwen3.5-9b",
        "mistralai/mistral-7b-instruct-v0.3",
    ],
    "vision": [
        "qwen/qwen3-vl-4b",
        "qwen3-vl-30b-a3b-instruct",
    ],
    "worker": [
        "google/gemma-4-e4b",
        "mistralai/mistral-7b-instruct-v0.3",
        "qwen/qwen3-vl-4b",
    ],
}


@dataclass(frozen=True)
class ProviderSettings:
    role: str
    provider: str
    model: str
    base_url: str
    api_key: str | None = None


@dataclass(frozen=True)
class TextResponse:
    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolModelResponse:
    text: str
    tool_calls: list[ToolCall]


def _record_provenance(
    *,
    provider: str,
    model: str,
    role: str,
    fallback_reason: str = "",
    preferred_unavailable: bool = False,
    metrics: dict | None = None,
) -> None:
    _PROVENANCE.value = {
        "provider": provider,
        "model": model,
        "role": role,
        "fallback_reason": fallback_reason,
        "preferred_model_unavailable": preferred_unavailable,
        "metrics": dict(metrics or {}),
        "recorded_at": time.time(),
    }
    route = str((metrics or {}).get("route") or role)
    state = "degraded" if fallback_reason or preferred_unavailable else "completed"
    emit_process_event(
        category="model",
        source=provider,
        summary=f"{provider}/{model} completed the {role} route" + (" using fallback." if state == "degraded" else "."),
        state=state,
        severity="warning" if state == "degraded" else "info",
        detail={
            "provider": provider,
            "model": model,
            "role": role,
            "route": route,
            "fallback_reason": fallback_reason,
            "duration_seconds": (metrics or {}).get("duration_seconds"),
            "tokens_per_second": (metrics or {}).get("tokens_per_second"),
        },
    )


def last_model_provenance() -> dict:
    return dict(getattr(_PROVENANCE, "value", {}) or {})


def load_config(path: Path = CONFIG_PATH) -> dict:
    return load_runtime_config(path)


def _clean_provider(value: str | None, default: str) -> str:
    provider = (value or default).strip().lower().replace("-", "_")
    if provider in {"lm_studio", "lmstudio", "localai", "jan", "llamacpp", "openai_compatible"}:
        return "lmstudio"
    if provider in {"openai", "gemini", "ollama"}:
        return provider
    return default


def _clean_base_url(url: str | None, default: str) -> str:
    return (url or default).strip().rstrip("/")


def _split_models(value) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _route_from_context(prompt: str, role: str, system: str | None = None) -> str:
    # Internal workflows may pin routing before appending untrusted evidence.
    # Only the trusted system channel is inspected for this directive so file,
    # web, and worker content cannot select its own model class.
    trusted_route = re.search(
        r"\[jarvis-route:(quick|main|reasoning|code|vision|research|worker)\]",
        system or "",
        flags=re.I,
    )
    if trusted_route:
        return trusted_route.group(1).lower()
    text = f"{system or ''}\n{prompt or ''}".lower()
    stripped = (prompt or "").strip().lower()
    if stripped in {"hi", "hello", "hey", "hello jarvis", "hey jarvis", "hi jarvis"}:
        return "quick"
    if any(token in text for token in ("screenshot", "image", "vision", "visual", "ocr", "photo", "camera", "diagram")):
        return "vision"
    if any(token in text for token in ("deep research", "research report", "literature review", "source gathering", "cited report", "research sources")) or role == "research":
        return "research"
    if any(token in text for token in ("traceback", "exception", "debug", "bug", "implement", "refactor", "code", "test failure")):
        return "code"
    if any(token in text for token in ("reason", "prove", "derive", "math", "physics", "analysis", "tradeoff", "diagnose")):
        return "reasoning"
    if any(token in text for token in ("plan", "orchestrate", "architecture", "design", "roadmap", "strategy")):
        return "main"
    if role == "worker":
        return "worker"
    return "quick" if len(stripped) < 160 else "main"


def _lmstudio_routes(config: dict) -> dict[str, list[str]]:
    routes = {key: list(value) for key, value in DEFAULT_LMSTUDIO_ROUTES.items()}
    configured = config.get("model_routes") or config.get("lmstudio_model_routes") or {}
    if isinstance(configured, dict):
        for key, value in configured.items():
            models = _split_models(value)
            if models:
                routes[str(key).strip().lower()] = models
    return routes


def select_lmstudio_models(
    prompt: str,
    *,
    role: str = "worker",
    model: str | None = None,
    system: str | None = None,
    config: dict | None = None,
) -> list[str]:
    cfg = load_config() if config is None else config
    normalized_role = (role or "worker").strip().lower()
    if model:
        return [model]

    route = _route_from_context(prompt, normalized_role, system)
    routes = _lmstudio_routes(cfg)

    candidates: list[str] = []
    if normalized_role == "planner" and route == "main":
        candidates += _split_models(cfg.get("planner_models")) or [str(cfg.get("planner_model") or "")]
    if normalized_role == "worker":
        candidates += _split_models(cfg.get("worker_models")) or [str(cfg.get("worker_model") or "")]
    candidates += routes.get(route, [])
    if normalized_role == "planner":
        candidates += routes.get("main", [])
    candidates += routes.get("quick", [])
    return _drop_cooling_down(_dedupe([candidate for candidate in candidates if candidate]), cfg)


def _drop_cooling_down(candidates: list[str], config: dict) -> list[str]:
    """Remove models inside an open health cooldown from a fallback chain.

    Never returns an empty list: a conversational turn still needs an answer, so
    when every candidate is cooling down the original order is preserved and the
    call proceeds. Approved workflows take the stricter path and pause — see
    `actions.model_registry.select_for_role`.
    """
    if not candidates:
        return candidates
    try:
        lifecycle_cfg = model_lifecycle_service.resolve_config(config)
        if not lifecycle_cfg.get("health_enabled"):
            return candidates
        snapshot = model_lifecycle_service.health_snapshot(lifecycle_cfg)
    except Exception:
        # Health is an optimisation, never a precondition for answering.
        return candidates

    cooling = {
        str(item.get("model") or "").strip().lower()
        for item in snapshot.get("models") or []
        if item.get("state") == "cooling_down"
    }
    if not cooling:
        return candidates
    healthy = [item for item in candidates if item.strip().lower() not in cooling]
    return healthy or candidates


def _env_get(environ: Mapping[str, str], key: str) -> str | None:
    value = environ.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve_settings(
    role: str,
    *,
    config: dict | None = None,
    environ: Mapping[str, str] | None = None,
    model: str | None = None,
) -> ProviderSettings:
    cfg = load_config() if config is None else config
    normalized_role = (role or "worker").strip().lower()

    if normalized_role == "planner":
        provider = _clean_provider(cfg.get("planner_provider"), "openai")
        selected_model = model or cfg.get("planner_model") or cfg.get("openai_model") or DEFAULT_OPENAI_MODEL
    elif normalized_role == "worker":
        provider = _clean_provider(cfg.get("worker_provider"), "lmstudio")
        selected_model = model or cfg.get("worker_model") or cfg.get("llm_model") or DEFAULT_WORKER_MODEL
    else:
        provider = _clean_provider(cfg.get(f"{normalized_role}_provider"), "lmstudio")
        selected_model = model or cfg.get(f"{normalized_role}_model") or cfg.get("worker_model") or DEFAULT_WORKER_MODEL

    if provider == "openai":
        return ProviderSettings(
            role=normalized_role,
            provider=provider,
            model=str(selected_model),
            base_url=_clean_base_url(cfg.get("openai_url"), DEFAULT_OPENAI_URL),
            api_key=None,
        )

    if provider == "gemini":
        return ProviderSettings(
            role=normalized_role,
            provider=provider,
            model=str(selected_model or cfg.get("gemini_model") or DEFAULT_GEMINI_MODEL),
            base_url="",
            api_key=None,
        )

    return ProviderSettings(
        role=normalized_role,
        provider="lmstudio",
        model=str(selected_model),
        base_url=_clean_base_url(cfg.get("lmstudio_url") or cfg.get("llm_url"), DEFAULT_LMSTUDIO_URL),
        api_key=None,
    )


def _raise_http(prefix: str, response) -> None:
    try:
        response.raise_for_status()
    except Exception as exc:
        body = getattr(response, "text", "") or str(exc)
        raise RuntimeError(f"{prefix} failed: {body[:500]}") from exc


def _parse_openai_responses(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()

    parts: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _parse_chat_tool_calls(message: dict) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    for item in message.get("tool_calls") or []:
        function = item.get("function") or {}
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        raw_args = function.get("arguments") or {}
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw_arguments": raw_args}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        tool_calls.append(
            ToolCall(
                id=str(item.get("id") or f"call_{len(tool_calls) + 1}"),
                name=name,
                arguments=args,
            )
        )
    return tool_calls


def _parse_tool_request_markers(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for match in re.finditer(r"\[TOOL_REQUEST\](.*?)\[END_TOOL_REQUEST\]", text or "", flags=re.S | re.I):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else [payload]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            arguments = item.get("arguments")
            calls.append(
                ToolCall(
                    id=str(item.get("id") or f"call_{len(calls) + 1}"),
                    name=name,
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
    return calls


def _parse_chat_response(data: dict) -> ToolModelResponse:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Chat request returned no choices.")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    tool_calls = _parse_chat_tool_calls(message)
    if not tool_calls:
        tool_calls = _parse_tool_request_markers(content)
    if not tool_calls:
        tool_calls = _parse_tool_request_markers(str(message.get("reasoning_content") or ""))
    return ToolModelResponse(
        text=content,
        tool_calls=tool_calls,
    )


def _extract_json_object(text: str) -> dict | None:
    candidate = (text or "").strip()
    if not candidate:
        return None
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if "\n" in candidate:
            candidate = candidate.split("\n", 1)[1]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None


def _parse_tool_json_response(text: str) -> ToolModelResponse:
    payload = _extract_json_object(text)
    if not isinstance(payload, dict):
        return ToolModelResponse(text=(text or "").strip(), tool_calls=[])

    calls: list[ToolCall] = []
    for item in payload.get("tool_calls") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        arguments = item.get("arguments")
        calls.append(
            ToolCall(
                id=str(item.get("id") or f"call_{len(calls) + 1}"),
                name=name,
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return ToolModelResponse(text=str(payload.get("text") or "").strip(), tool_calls=calls)


def _tool_json_prompt(prompt: str, tools: list[dict]) -> str:
    compact_tools = []
    for tool in tools:
        function = tool.get("function") or {}
        compact_tools.append(
            {
                "name": function.get("name"),
                "description": function.get("description", ""),
                "parameters": function.get("parameters", {}),
            }
        )
    return (
        "You can call tools by returning JSON only.\n"
        "If a tool is needed, return exactly:\n"
        '{"tool_calls":[{"name":"tool_name","arguments":{}}],"text":""}\n'
        "If no tool is needed, return exactly:\n"
        '{"tool_calls":[],"text":"your concise answer"}\n\n'
        f"Available tools:\n{json.dumps(compact_tools, indent=2)}\n\n"
        f"User request:\n{prompt}"
    )


def _openai_key_is_valid(
    settings: ProviderSettings,
    *,
    timeout: int,
    get: Callable | None = None,
    credential_broker=None,
) -> bool:
    try:
        broker = credential_broker or get_session_broker()
        status = broker.status("openai")
        return status.get("state") in {"linked", "degraded"}
    except Exception:
        return False


def _call_openai_responses(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    timeout: int,
    max_tokens: int | None = None,
    post: Callable | None = None,
    credential_broker=None,
) -> str:
    payload: dict = {
        "model": settings.model,
        "input": prompt,
    }
    if system:
        payload["instructions"] = system
    if max_tokens is not None:
        payload["max_output_tokens"] = max(1, int(max_tokens))

    broker = credential_broker or get_session_broker()
    result = broker.request(
        provider="openai",
        base_url=settings.base_url,
        path="responses",
        payload=payload,
        timeout=timeout,
    )
    if not result.get("ok"):
        raise RuntimeError(f"OpenAI broker request failed: {result.get('reason') or result.get('error')}")
    text = _parse_openai_responses(result.get("data") or {})
    if not text:
        raise RuntimeError("OpenAI Responses request returned no text.")
    _record_provenance(provider="openai", model=settings.model, role=settings.role)
    return text


def _call_openai_with_tools(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    tools: list[dict],
    timeout: int,
    credential_broker=None,
    max_tokens: int = 900,
) -> ToolModelResponse:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": settings.model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "tools": tools,
        "tool_choice": "auto",
    }
    broker = credential_broker or get_session_broker()
    result = broker.request(
        provider="openai",
        base_url=settings.base_url,
        path="chat/completions",
        payload=payload,
        timeout=timeout,
    )
    if not result.get("ok"):
        raise RuntimeError(f"OpenAI broker tools request failed: {result.get('reason') or result.get('error')}")
    parsed = _parse_chat_response(result.get("data") or {})
    if not parsed.text and not parsed.tool_calls:
        raise RuntimeError("OpenAI broker tools request returned no text or tool calls.")
    _record_provenance(provider="openai", model=settings.model, role=settings.role)
    return parsed


def _lmstudio_response_text(
    response,
    *,
    streaming: bool,
    lease_id: str,
    lifecycle_cfg: dict,
    started_at: float,
    max_seconds: int,
) -> tuple[str, dict]:
    if not streaming or not callable(getattr(response, "iter_lines", None)):
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LM Studio chat request returned no choices.")
        text = ((choices[0].get("message") or {}).get("content") or "").strip()
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        elapsed = max(0.001, time.monotonic() - started_at)
        completion_tokens = int(usage.get("completion_tokens") or max(1, round(len(text.split()) * 1.3)))
        details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
        return text, {
            "streaming": False,
            "duration_seconds": round(elapsed, 3),
            "completion_tokens": completion_tokens,
            "tokens_per_second": round(completion_tokens / elapsed, 3),
            "first_token_seconds": None,
            "finish_reason": str(choices[0].get("finish_reason") or ""),
            "reasoning_tokens": int(details.get("reasoning_tokens") or 0),
        }

    parts: list[str] = []
    reasoning_parts: list[str] = []
    completion_tokens = 0
    first_token_at: float | None = None
    last_heartbeat = started_at
    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            now = time.monotonic()
            if now - started_at > max_seconds:
                raise requests.exceptions.Timeout("LM Studio streamed generation exceeded its safety ceiling.")
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            if usage.get("completion_tokens") is not None:
                completion_tokens = int(usage["completion_tokens"])
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
            if content:
                if first_token_at is None:
                    first_token_at = now
                parts.append(str(content))
            elif reasoning:
                if first_token_at is None:
                    first_token_at = now
                reasoning_parts.append(str(reasoning))
            if now - last_heartbeat >= 5:
                model_lifecycle_service.update_generation_lease(
                    lease_id,
                    cfg=lifecycle_cfg,
                    details={"phase": "streaming", "characters": sum(len(item) for item in parts)},
                )
                last_heartbeat = now
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    text = "".join(parts).strip()
    elapsed = max(0.001, time.monotonic() - started_at)
    if completion_tokens <= 0:
        completion_tokens = max(1, round(len(text.split()) * 1.3))
    return text, {
        "streaming": True,
        "duration_seconds": round(elapsed, 3),
        "completion_tokens": completion_tokens,
        "tokens_per_second": round(completion_tokens / elapsed, 3),
        "first_token_seconds": round((first_token_at or time.monotonic()) - started_at, 3),
        "reasoning_characters": sum(len(item) for item in reasoning_parts),
    }


# Some local chat templates accept only user/assistant turns. Measured on this
# host: `mistralai/mistral-7b-instruct-v0.3` returns HTTP 400 "Only user and
# assistant roles are supported!", while `qwen/qwen3-4b-2507` handles a system
# message correctly. Rather than maintain a list by hand, learn it at runtime.
_SYSTEM_ROLE_UNSUPPORTED: set[str] = set()
_SYSTEM_ROLE_ERROR_PATTERN = re.compile(
    r"only user and assistant roles|roles are supported|system role .*not|unsupported role",
    re.IGNORECASE,
)


def _use_system_role(config: dict | None) -> bool:
    """Whether to send policy as its own message rather than merging it.

    Merging made the boundary purely lexical: the model received one user message
    holding policy, the user's words, and any untrusted evidence appended to the
    turn. A real system message lets the transport carry the boundary.
    """
    cfg = load_config() if config is None else config
    return bool(cfg.get("lmstudio_use_system_role", True))


def system_role_supported(model: str, config: dict | None = None) -> bool:
    if not _use_system_role(config):
        return False
    return str(model or "").strip().lower() not in _SYSTEM_ROLE_UNSUPPORTED


def _mark_no_system_role(model: str) -> None:
    candidate = str(model or "").strip().lower()
    if candidate:
        _SYSTEM_ROLE_UNSUPPORTED.add(candidate)


def _is_system_role_error(response: Any) -> bool:
    try:
        status = int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return False
    if status != 400:
        return False
    return bool(_SYSTEM_ROLE_ERROR_PATTERN.search(str(getattr(response, "text", "") or "")))


def _build_messages(
    prompt: str,
    system: str | None,
    config: dict | None,
    *,
    model: str = "",
    force_merge: bool = False,
) -> list[dict]:
    messages: list[dict] = []
    if system and not force_merge and system_role_supported(model, config):
        messages.append({"role": "system", "content": system.strip()})
    elif system:
        prompt = f"{system.strip()}\n\nUser request:\n{prompt}"
    messages.append({"role": "user", "content": prompt})
    return messages


def _budget_exhausted(metrics: dict | None) -> bool:
    """Whether empty output is explained by the token budget rather than the model."""
    metrics = metrics or {}
    if str(metrics.get("finish_reason") or "").strip().lower() == "length":
        return True
    return int(metrics.get("reasoning_tokens") or 0) > 0


def _record_model_health(
    model: str,
    *,
    outcome: str,
    cfg: dict,
    metrics: dict | None = None,
    error: str = "",
    source: str = "passive",
) -> None:
    """Persist one health observation.

    Recording is strictly best-effort: a failure here must never turn a working
    generation into an error, so every exception is swallowed.
    """
    try:
        model_lifecycle_service.record_model_outcome(
            model,
            outcome=outcome,
            source=source,
            metrics=metrics or {},
            error=error,
            cfg=cfg,
        )
    except Exception:
        pass


def _call_lmstudio_chat(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    timeout: int,
    post: Callable,
    max_tokens: int = 1200,
    config: dict | None = None,
) -> str:
    route = _route_from_context(prompt, settings.role, system)
    lifecycle_cfg = model_lifecycle_service.resolve_config(config)
    messages = _build_messages(prompt, system, config, model=settings.model)

    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    payload = {
        "model": settings.model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }
    payload = model_lifecycle_service.prepare_lmstudio_payload(
        payload,
        model=settings.model,
        route=route,
        config=config,
    )
    lease = model_lifecycle_service.acquire_generation_lease(
        settings.model,
        route=route,
        cfg=lifecycle_cfg,
    )
    if not lease.get("ok"):
        # Queue contention is a machine condition, not a defect in this model.
        _record_model_health(
            settings.model,
            outcome="inconclusive",
            cfg=lifecycle_cfg,
            error=str(lease.get("error") or ""),
        )
        raise RuntimeError(f"LM Studio generation queue failed: {lease.get('error') or lease}")
    lease_id = str(lease["lease_id"])
    request_model = settings.model
    ready: dict = {}
    outcome = "failed"
    failure = ""
    health_outcome = "inconclusive"
    health_metrics: dict = {}
    request_started = 0.0
    try:
        model_lifecycle_service.update_generation_lease(
            lease_id,
            state="LOADING",
            cfg=lifecycle_cfg,
            details={"catalog_model": settings.model},
        )
        if post is requests.post:
            ready = model_lifecycle_service.ensure_model_loaded(
                settings.model,
                route=route,
                exclusive_lease_id=lease_id,
                cfg=lifecycle_cfg,
            )
            if not ready.get("ok"):
                health_outcome = "load_failed"
                raise RuntimeError(f"LM Studio model preparation failed: {ready.get('error') or ready}")
            request_model = str(
                ready.get("instance_id")
                or (ready.get("instance") or {}).get("instance_id")
                or settings.model
            )
            payload["model"] = request_model
        model_lifecycle_service.update_generation_lease(
            lease_id,
            state="GENERATING",
            instance_id=request_model,
            cfg=lifecycle_cfg,
            details={"request_model": request_model},
        )
        streaming = post is requests.post and route == "research"
        payload["stream"] = streaming
        request_started = time.monotonic()
        request_timeout = (
            (10, int(lifecycle_cfg["generation_first_token_seconds"]))
            if streaming
            else timeout
        )
        response = post(
            f"{settings.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=request_timeout,
            **({"stream": True} if streaming else {}),
        )
        if _is_system_role_error(response):
            # This model's chat template rejects a system turn. Remember it and
            # retry merged, so policy still reaches the model.
            _mark_no_system_role(settings.model)
            payload["messages"] = _build_messages(prompt, system, config, force_merge=True)
            response = post(
                f"{settings.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=request_timeout,
                **({"stream": True} if streaming else {}),
            )
        _raise_http("LM Studio chat request", response)
        text, stream_metrics = _lmstudio_response_text(
            response,
            streaming=streaming,
            lease_id=lease_id,
            lifecycle_cfg=lifecycle_cfg,
            started_at=request_started,
            max_seconds=(
                max(int(timeout), int(lifecycle_cfg["research_generation_max_seconds"]))
                if route == "research"
                else int(timeout)
            ),
        )
        if not text:
            # A reasoning model that spent its whole allowance thinking has not
            # failed; our budget was too small. Attributing that would blacklist
            # every reasoning model after two tight-budget calls.
            if _budget_exhausted(stream_metrics):
                health_outcome = "inconclusive"
                raise RuntimeError(
                    f"LM Studio returned no text for {settings.model}: the token budget "
                    f"({max_tokens}) was exhausted before content was produced."
                )
            health_outcome = "empty_output"
            raise RuntimeError("LM Studio chat request returned no text.")
        metrics = {
            "lease_id": lease_id,
            "instance_id": request_model,
            "route": route,
            "queue_wait_seconds": lease.get("queue_wait_seconds", 0.0),
            "load_time_seconds": ready.get("load_time_seconds"),
            **stream_metrics,
        }
        _record_provenance(provider="lmstudio", model=settings.model, role=settings.role, metrics=metrics)
        outcome = "completed"
        health_outcome = "ok"
        health_metrics = dict(stream_metrics)
        return text
    except Exception as exc:
        failure = str(exc)
        timeout_failure = isinstance(exc, requests.exceptions.Timeout) or "timed out" in failure.lower()
        if timeout_failure and ready:
            # The model held the lease and failed to produce inside its budget.
            health_outcome = "timeout"
            model_lifecycle_service.update_generation_lease(
                lease_id,
                state="DRAINING",
                instance_id=request_model,
                cfg=lifecycle_cfg,
                details={"reason": "generation_timeout"},
            )
            drained = model_lifecycle_service.drain_model_instance(
                request_model,
                model=settings.model,
                route=route,
                cfg=lifecycle_cfg,
            )
            if not drained.get("confirmed"):
                outcome = "unknown_outcome"
                raise RuntimeError(
                    f"LM Studio generation outcome uncertain; fallback suppressed: {drained.get('error') or drained}"
                ) from exc
            outcome = "timed_out_drained"
            raise RuntimeError("LM Studio generation timed out; previous instance drained.") from exc
        if timeout_failure and not ready:
            outcome = "unknown_outcome"
            raise RuntimeError("LM Studio load outcome uncertain; fallback suppressed.") from exc
        raise
    finally:
        model_lifecycle_service.release_generation_lease(
            lease_id,
            cfg=lifecycle_cfg,
            outcome=outcome,
            error=failure,
        )
        _record_model_health(
            settings.model,
            outcome=health_outcome,
            cfg=lifecycle_cfg,
            metrics=health_metrics,
            error=failure,
        )


def _call_chat_with_tools(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    tools: list[dict],
    timeout: int,
    post: Callable,
    max_tokens: int = 900,
    config: dict | None = None,
) -> ToolModelResponse:
    route = _route_from_context(prompt, settings.role, system)
    if settings.provider == "lmstudio":
        messages = _build_messages(prompt, system, config, model=settings.model)
    else:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    payload = {
        "model": settings.model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "tools": tools,
        "tool_choice": "auto",
    }
    lease_id = ""
    lifecycle_cfg: dict | None = None
    ready: dict = {}
    outcome = "failed"
    failure = ""
    health_outcome = "inconclusive"
    health_metrics: dict = {}
    request_model = settings.model
    if settings.provider == "lmstudio":
        lifecycle_cfg = model_lifecycle_service.resolve_config(config)
        payload = model_lifecycle_service.prepare_lmstudio_payload(
            payload,
            model=settings.model,
            route=route,
            config=config,
        )
        lease = model_lifecycle_service.acquire_generation_lease(
            settings.model,
            route=route,
            cfg=lifecycle_cfg,
        )
        if not lease.get("ok"):
            _record_model_health(
                settings.model,
                outcome="inconclusive",
                cfg=lifecycle_cfg,
                error=str(lease.get("error") or ""),
            )
            raise RuntimeError(f"LM Studio generation queue failed: {lease.get('error') or lease}")
        lease_id = str(lease["lease_id"])
        try:
            model_lifecycle_service.update_generation_lease(lease_id, state="LOADING", cfg=lifecycle_cfg)
            if post is requests.post:
                ready = model_lifecycle_service.ensure_model_loaded(
                    settings.model,
                    route=route,
                    exclusive_lease_id=lease_id,
                    cfg=lifecycle_cfg,
                )
                if not ready.get("ok"):
                    health_outcome = "load_failed"
                    raise RuntimeError(f"LM Studio model preparation failed: {ready.get('error') or ready}")
                request_model = str(
                    ready.get("instance_id")
                    or (ready.get("instance") or {}).get("instance_id")
                    or settings.model
                )
                payload["model"] = request_model
            model_lifecycle_service.update_generation_lease(
                lease_id,
                state="GENERATING",
                instance_id=request_model,
                cfg=lifecycle_cfg,
            )
        except Exception as exc:
            model_lifecycle_service.release_generation_lease(
                lease_id,
                cfg=lifecycle_cfg,
                outcome="preparation_failed",
                error=str(exc),
            )
            # This block returns before the outer finally, so health is recorded here.
            _record_model_health(
                settings.model,
                outcome=health_outcome,
                cfg=lifecycle_cfg,
                error=str(exc),
            )
            raise
    try:
        started = time.monotonic()
        response = post(
            f"{settings.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        if settings.provider == "lmstudio" and _is_system_role_error(response):
            _mark_no_system_role(settings.model)
            payload["messages"] = _build_messages(prompt, system, config, force_merge=True)
            response = post(
                f"{settings.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        _raise_http(f"{settings.provider} chat tools request", response)
        parsed = _parse_chat_response(response.json())
        if not parsed.text and not parsed.tool_calls:
            health_outcome = "empty_output"
            raise RuntimeError(f"{settings.provider} chat tools request returned no text or tool calls.")
        elapsed = max(0.001, time.monotonic() - started)
        metrics = (
            {
                "lease_id": lease_id,
                "instance_id": request_model,
                "route": route,
                "duration_seconds": round(elapsed, 3),
                "streaming": False,
            }
            if lease_id
            else {}
        )
        _record_provenance(provider=settings.provider, model=settings.model, role=settings.role, metrics=metrics)
        outcome = "completed"
        health_outcome = "ok"
        health_metrics = {"duration_seconds": round(elapsed, 3)}
        return parsed
    except Exception as exc:
        failure = str(exc)
        timeout_failure = isinstance(exc, requests.exceptions.Timeout) or "timed out" in failure.lower()
        if lease_id and timeout_failure and ready and lifecycle_cfg is not None:
            health_outcome = "timeout"
            model_lifecycle_service.update_generation_lease(
                lease_id,
                state="DRAINING",
                instance_id=request_model,
                cfg=lifecycle_cfg,
                details={"reason": "tool_generation_timeout"},
            )
            drained = model_lifecycle_service.drain_model_instance(
                request_model,
                model=settings.model,
                route=route,
                cfg=lifecycle_cfg,
            )
            if not drained.get("confirmed"):
                outcome = "unknown_outcome"
                raise RuntimeError("LM Studio tool generation outcome uncertain; fallback suppressed.") from exc
            outcome = "timed_out_drained"
            raise RuntimeError("LM Studio tool generation timed out; previous instance drained.") from exc
        if lease_id and timeout_failure and not ready:
            outcome = "unknown_outcome"
            raise RuntimeError("LM Studio tool load outcome uncertain; fallback suppressed.") from exc
        raise
    finally:
        if lease_id and lifecycle_cfg is not None:
            model_lifecycle_service.release_generation_lease(
                lease_id,
                cfg=lifecycle_cfg,
                outcome=outcome,
                error=failure,
            )
            _record_model_health(
                settings.model,
                outcome=health_outcome,
                cfg=lifecycle_cfg,
                metrics=health_metrics,
                error=failure,
            )


def _is_lmstudio_retryable(error: str) -> bool:
    err = (error or "").lower()
    if "fallback suppressed" in err or "outcome uncertain" in err:
        return False
    return any(
        token in err
        for token in (
            "failed to load model",
            "error loading model",
            "out of memory",
            "failed to allocate",
            "paging file is too small",
            "model unloaded",
            "model is unloaded",
            "no models loaded",
            "operation canceled",
            "internal server error",
            "channel error",
            "timed out",
        )
    )


def _call_lmstudio_chat_with_fallback(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    timeout: int,
    post: Callable,
    candidates: list[str],
    config: dict | None = None,
    max_tokens: int | None = None,
) -> str:
    errors: list[str] = []
    for index, candidate in enumerate(candidates):
        candidate_settings = ProviderSettings(
            role=settings.role,
            provider=settings.provider,
            model=candidate,
            base_url=settings.base_url,
            api_key=settings.api_key,
        )
        try:
            candidate_max_tokens = max_tokens or (
                700 if _route_from_context(prompt, settings.role, system) == "quick" else 1200
            )
            text = _call_lmstudio_chat(
                prompt,
                candidate_settings,
                system=system,
                timeout=timeout,
                post=post,
                max_tokens=max(1, int(candidate_max_tokens)),
                config=config,
            )
            if index:
                previous = last_model_provenance()
                _record_provenance(
                    provider="lmstudio",
                    model=candidate,
                    role=settings.role,
                    fallback_reason="preferred_local_model_failed",
                    preferred_unavailable=True,
                    metrics=previous.get("metrics"),
                )
            return text
        except Exception as exc:
            message = str(exc)
            errors.append(f"{candidate}: {message[:220]}")
            if index == len(candidates) - 1 or not _is_lmstudio_retryable(message):
                break
            time.sleep(0.4)
    raise RuntimeError("LM Studio local model route failed. Tried: " + " | ".join(errors))


def _call_lmstudio_tools_with_fallback(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    timeout: int,
    post: Callable,
    candidates: list[str],
    tools: list[dict],
    config: dict | None = None,
) -> ToolModelResponse:
    errors: list[str] = []
    for index, candidate in enumerate(candidates):
        candidate_settings = ProviderSettings(
            role=settings.role,
            provider=settings.provider,
            model=candidate,
            base_url=settings.base_url,
            api_key=settings.api_key,
        )
        try:
            max_tokens = 700 if _route_from_context(prompt, settings.role, system) == "quick" else 1200
            response = _call_chat_with_tools(
                prompt,
                candidate_settings,
                system=system,
                tools=tools,
                timeout=timeout,
                post=post,
                max_tokens=max_tokens,
                config=config,
            )
            if index:
                previous = last_model_provenance()
                _record_provenance(
                    provider="lmstudio",
                    model=candidate,
                    role=settings.role,
                    fallback_reason="preferred_local_model_failed",
                    preferred_unavailable=True,
                    metrics=previous.get("metrics"),
                )
            return response
        except Exception as exc:
            message = str(exc)
            errors.append(f"{candidate}: {message[:220]}")
            if index == len(candidates) - 1 or not _is_lmstudio_retryable(message):
                break
            time.sleep(0.4)
    native_error = "LM Studio local tool route failed. Tried: " + " | ".join(errors)
    try:
        return _call_lmstudio_json_tools_with_fallback(
            prompt,
            settings,
            system=system,
            timeout=timeout,
            post=post,
            candidates=candidates,
            tools=tools,
            config=config,
        )
    except Exception as exc:
        raise RuntimeError(f"{native_error} | JSON fallback failed: {exc}") from exc


def _call_lmstudio_json_tools_with_fallback(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    timeout: int,
    post: Callable,
    candidates: list[str],
    tools: list[dict],
    config: dict | None = None,
) -> ToolModelResponse:
    errors: list[str] = []
    json_prompt = _tool_json_prompt(prompt, tools)
    for index, candidate in enumerate(candidates):
        candidate_settings = ProviderSettings(
            role=settings.role,
            provider=settings.provider,
            model=candidate,
            base_url=settings.base_url,
            api_key=settings.api_key,
        )
        try:
            text = _call_lmstudio_chat(
                json_prompt,
                candidate_settings,
                system=system,
                timeout=timeout,
                post=post,
                max_tokens=900,
                config=config,
            )
            return _parse_tool_json_response(text)
        except Exception as exc:
            message = str(exc)
            errors.append(f"{candidate}: {message[:220]}")
            if index == len(candidates) - 1 or not _is_lmstudio_retryable(message):
                break
            time.sleep(0.4)
    raise RuntimeError("LM Studio JSON tool route failed. Tried: " + " | ".join(errors))


def _call_lmstudio_fallback(
    prompt: str,
    *,
    role: str,
    system: str | None,
    timeout: int,
    config: dict,
    environ: Mapping[str, str] | None,
    post: Callable,
    fallback_reason: str,
    max_tokens: int | None = None,
) -> str:
    fallback_cfg = dict(config or {})
    normalized_role = (role or "worker").strip().lower()
    fallback_cfg[f"{normalized_role}_provider"] = "lmstudio"
    if normalized_role == "planner":
        fallback_cfg["planner_provider"] = "lmstudio"
        if str(fallback_cfg.get("planner_model", "")).lower().startswith(("gpt-", "o1", "o3", "o4")):
            fallback_cfg.pop("planner_model", None)
    elif normalized_role == "worker":
        fallback_cfg["worker_provider"] = "lmstudio"

    settings = resolve_settings(normalized_role, config=fallback_cfg, environ=environ, model=None)
    candidates = select_lmstudio_models(
        prompt,
        role=normalized_role,
        model=None,
        system=system,
        config=fallback_cfg,
    )
    text = _call_lmstudio_chat_with_fallback(
        prompt,
        settings,
        system=system,
        timeout=timeout,
        post=post,
        candidates=candidates or [settings.model],
        config=fallback_cfg,
        max_tokens=max_tokens,
    )
    provenance = last_model_provenance()
    _record_provenance(
        provider=str(provenance.get("provider") or "lmstudio"),
        model=str(provenance.get("model") or settings.model),
        role=normalized_role,
        fallback_reason=fallback_reason,
        preferred_unavailable=True,
        metrics=provenance.get("metrics"),
    )
    return text


def _call_lmstudio_tools_fallback(
    prompt: str,
    *,
    role: str,
    system: str | None,
    timeout: int,
    config: dict,
    environ: Mapping[str, str] | None,
    post: Callable,
    tools: list[dict],
    fallback_reason: str,
) -> ToolModelResponse:
    fallback_cfg = dict(config or {})
    normalized_role = (role or "worker").strip().lower()
    fallback_cfg[f"{normalized_role}_provider"] = "lmstudio"
    if normalized_role == "planner":
        fallback_cfg["planner_provider"] = "lmstudio"
        if str(fallback_cfg.get("planner_model", "")).lower().startswith(("gpt-", "o1", "o3", "o4")):
            fallback_cfg.pop("planner_model", None)
    elif normalized_role == "worker":
        fallback_cfg["worker_provider"] = "lmstudio"

    settings = resolve_settings(normalized_role, config=fallback_cfg, environ=environ, model=None)
    candidates = select_lmstudio_models(
        prompt,
        role=normalized_role,
        model=None,
        system=system,
        config=fallback_cfg,
    )
    response = _call_lmstudio_tools_with_fallback(
        prompt,
        settings,
        system=system,
        timeout=timeout,
        post=post,
        candidates=candidates or [settings.model],
        tools=tools,
        config=fallback_cfg,
    )
    provenance = last_model_provenance()
    _record_provenance(
        provider=str(provenance.get("provider") or "lmstudio"),
        model=str(provenance.get("model") or settings.model),
        role=normalized_role,
        fallback_reason=fallback_reason,
        preferred_unavailable=True,
        metrics=provenance.get("metrics"),
    )
    return response


def _call_gemini(prompt: str, settings: ProviderSettings) -> str:
    if not settings.api_key:
        raise RuntimeError("Gemini provider selected but no GEMINI_API_KEY or gemini_api_key is configured.")
    from google import genai

    client = genai.Client(api_key=settings.api_key)
    response = client.models.generate_content(model=settings.model, contents=prompt)
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini request returned no text.")
    return text


def call_text(
    prompt: str,
    *,
    role: str = "worker",
    model: str | None = None,
    system: str | None = None,
    timeout: int = 120,
    max_tokens: int | None = None,
    config: dict | None = None,
    environ: Mapping[str, str] | None = None,
    post: Callable = requests.post,
    get: Callable = requests.get,
    credential_broker=None,
) -> str:
    cfg = load_config() if config is None else config
    settings = resolve_settings(role, config=cfg, environ=environ, model=model)
    if settings.provider == "openai":
        if not _openai_key_is_valid(settings, timeout=timeout, get=get, credential_broker=credential_broker):
            return _call_lmstudio_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
                fallback_reason="openai_session_unlinked_or_unavailable",
                max_tokens=max_tokens,
            )
        try:
            return _call_openai_responses(
                prompt,
                settings,
                system=system,
                timeout=timeout,
                max_tokens=max_tokens,
                post=post,
                credential_broker=credential_broker,
            )
        except Exception as exc:
            return _call_lmstudio_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
                fallback_reason=f"openai_request_failed:{type(exc).__name__}",
                max_tokens=max_tokens,
            )
    if settings.provider == "gemini":
        return _call_gemini(prompt, settings)
    candidates = select_lmstudio_models(
        prompt,
        role=role,
        model=model,
        system=system,
        config=cfg,
    )
    return _call_lmstudio_chat_with_fallback(
        prompt,
        settings,
        system=system,
        timeout=timeout,
        post=post,
        candidates=candidates or [settings.model],
        config=cfg,
        max_tokens=max_tokens,
    )


def call_with_tools(
    prompt: str,
    *,
    tools: list[dict],
    role: str = "worker",
    model: str | None = None,
    system: str | None = None,
    timeout: int = 120,
    config: dict | None = None,
    environ: Mapping[str, str] | None = None,
    post: Callable = requests.post,
    get: Callable = requests.get,
    credential_broker=None,
) -> ToolModelResponse:
    cfg = load_config() if config is None else config
    settings = resolve_settings(role, config=cfg, environ=environ, model=model)
    if settings.provider == "openai":
        if not _openai_key_is_valid(settings, timeout=timeout, get=get, credential_broker=credential_broker):
            return _call_lmstudio_tools_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
                tools=tools,
                fallback_reason="openai_session_unlinked_or_unavailable",
            )
        try:
            return _call_openai_with_tools(
                prompt,
                settings,
                system=system,
                tools=tools,
                timeout=timeout,
                credential_broker=credential_broker,
            )
        except Exception as exc:
            return _call_lmstudio_tools_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
                tools=tools,
                fallback_reason=f"openai_request_failed:{type(exc).__name__}",
            )
    if settings.provider == "gemini":
        text = _call_gemini(prompt, settings)
        return ToolModelResponse(text=text, tool_calls=[])
    candidates = select_lmstudio_models(
        prompt,
        role=role,
        model=model,
        system=system,
        config=cfg,
    )
    return _call_lmstudio_tools_with_fallback(
        prompt,
        settings,
        system=system,
        timeout=timeout,
        post=post,
        candidates=candidates or [settings.model],
        tools=tools,
        config=cfg,
    )


class ModelWrapper:
    def __init__(
        self,
        *,
        role: str = "worker",
        model: str | None = None,
        system: str | None = None,
        timeout: int = 120,
        max_tokens: int | None = None,
        caller: Callable | None = None,
    ):
        self.role = role
        self.model = model
        self.system = system
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._caller = caller or call_text

    def generate_content(self, contents):
        prompt = contents if isinstance(contents, str) else str(contents)
        text = self._caller(
            prompt,
            role=self.role,
            model=self.model,
            system=self.system,
            timeout=self.timeout,
            max_tokens=self.max_tokens,
        )
        return TextResponse(text=text)


def get_model_wrapper(
    *,
    role: str = "worker",
    model: str | None = None,
    system: str | None = None,
    timeout: int = 120,
    max_tokens: int | None = None,
) -> ModelWrapper:
    return ModelWrapper(
        role=role,
        model=model,
        system=system,
        timeout=timeout,
        max_tokens=max_tokens,
    )
