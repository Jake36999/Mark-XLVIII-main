from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import requests

from actions import model_lifecycle as model_lifecycle_service


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_WORKER_MODEL = "qwen/qwen3-4b"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1"
DEFAULT_LMSTUDIO_URL = "http://localhost:1234/v1"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
OPENAI_KEY_CHECK_TTL_SECONDS = 600
_OPENAI_KEY_CHECK_CACHE: dict[tuple[str, str], tuple[bool, float]] = {}
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


def load_config(path: Path = CONFIG_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


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
    text = f"{system or ''}\n{prompt or ''}".lower()
    stripped = (prompt or "").strip().lower()
    if stripped in {"hi", "hello", "hey", "hello jarvis", "hey jarvis", "hi jarvis"}:
        return "quick"
    if any(token in text for token in ("screenshot", "image", "vision", "visual", "ocr", "photo", "camera", "diagram")):
        return "vision"
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
    return _dedupe([candidate for candidate in candidates if candidate])


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
    env = os.environ if environ is None else environ
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
            api_key=_env_get(env, "OPENAI_API_KEY") or cfg.get("openai_api_key"),
        )

    if provider == "gemini":
        return ProviderSettings(
            role=normalized_role,
            provider=provider,
            model=str(selected_model or cfg.get("gemini_model") or DEFAULT_GEMINI_MODEL),
            base_url="",
            api_key=_env_get(env, "GEMINI_API_KEY") or cfg.get("gemini_api_key"),
        )

    return ProviderSettings(
        role=normalized_role,
        provider="lmstudio",
        model=str(selected_model),
        base_url=_clean_base_url(cfg.get("lmstudio_url") or cfg.get("llm_url"), DEFAULT_LMSTUDIO_URL),
        api_key=_env_get(env, "LMSTUDIO_API_KEY") or cfg.get("lmstudio_api_key"),
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


def _parse_chat_response(data: dict) -> ToolModelResponse:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Chat request returned no choices.")
    message = choices[0].get("message") or {}
    return ToolModelResponse(
        text=(message.get("content") or "").strip(),
        tool_calls=_parse_chat_tool_calls(message),
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
    get: Callable,
) -> bool:
    if not settings.api_key:
        return False

    cache_key = (settings.base_url, settings.api_key)
    now = time.monotonic()
    cached = _OPENAI_KEY_CHECK_CACHE.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    try:
        response = get(
            f"{settings.base_url}/models",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=min(timeout, 15),
        )
        valid = 200 <= int(getattr(response, "status_code", 0)) < 300
    except Exception:
        valid = False

    _OPENAI_KEY_CHECK_CACHE[cache_key] = (valid, now + OPENAI_KEY_CHECK_TTL_SECONDS)
    return valid


def _call_openai_responses(
    prompt: str,
    settings: ProviderSettings,
    *,
    system: str | None,
    timeout: int,
    post: Callable,
) -> str:
    if not settings.api_key:
        raise RuntimeError("OpenAI provider selected but no OPENAI_API_KEY or openai_api_key is configured.")

    payload: dict = {
        "model": settings.model,
        "input": prompt,
    }
    if system:
        payload["instructions"] = system

    response = post(
        f"{settings.base_url}/responses",
        json=payload,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    _raise_http("OpenAI Responses request", response)
    text = _parse_openai_responses(response.json())
    if not text:
        raise RuntimeError("OpenAI Responses request returned no text.")
    return text


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
    messages: list[dict] = []
    if system:
        prompt = f"{system.strip()}\n\nUser request:\n{prompt}"
    messages.append({"role": "user", "content": prompt})

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
    token = model_lifecycle_service.mark_request_start(settings.model, kind=route)
    try:
        response = post(
            f"{settings.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        _raise_http("LM Studio chat request", response)
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LM Studio chat request returned no choices.")
        text = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("LM Studio chat request returned no text.")
        return text
    finally:
        model_lifecycle_service.mark_request_done(token)


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
    messages: list[dict] = []
    if system and settings.provider == "lmstudio":
        prompt = f"{system.strip()}\n\nUser request:\n{prompt}"
    elif system:
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
    token = None
    if settings.provider == "lmstudio":
        payload = model_lifecycle_service.prepare_lmstudio_payload(
            payload,
            model=settings.model,
            route=route,
            config=config,
        )
        token = model_lifecycle_service.mark_request_start(settings.model, kind=route)
    try:
        response = post(
            f"{settings.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        _raise_http(f"{settings.provider} chat tools request", response)
        return _parse_chat_response(response.json())
    finally:
        model_lifecycle_service.mark_request_done(token)


def _is_lmstudio_retryable(error: str) -> bool:
    err = (error or "").lower()
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
            max_tokens = 700 if _route_from_context(prompt, settings.role, system) == "quick" else 1200
            return _call_lmstudio_chat(
                prompt,
                candidate_settings,
                system=system,
                timeout=timeout,
                post=post,
                max_tokens=max_tokens,
                config=config,
            )
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
            return _call_chat_with_tools(
                prompt,
                candidate_settings,
                system=system,
                tools=tools,
                timeout=timeout,
                post=post,
                max_tokens=max_tokens,
                config=config,
            )
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
    return _call_lmstudio_chat_with_fallback(
        prompt,
        settings,
        system=system,
        timeout=timeout,
        post=post,
        candidates=candidates or [settings.model],
        config=fallback_cfg,
    )


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
    return _call_lmstudio_tools_with_fallback(
        prompt,
        settings,
        system=system,
        timeout=timeout,
        post=post,
        candidates=candidates or [settings.model],
        tools=tools,
        config=fallback_cfg,
    )


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
    config: dict | None = None,
    environ: Mapping[str, str] | None = None,
    post: Callable = requests.post,
    get: Callable = requests.get,
) -> str:
    cfg = load_config() if config is None else config
    settings = resolve_settings(role, config=cfg, environ=environ, model=model)
    if settings.provider == "openai":
        if not _openai_key_is_valid(settings, timeout=timeout, get=get):
            return _call_lmstudio_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
            )
        try:
            return _call_openai_responses(prompt, settings, system=system, timeout=timeout, post=post)
        except Exception:
            return _call_lmstudio_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
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
) -> ToolModelResponse:
    cfg = load_config() if config is None else config
    settings = resolve_settings(role, config=cfg, environ=environ, model=model)
    if settings.provider == "openai":
        if not _openai_key_is_valid(settings, timeout=timeout, get=get):
            return _call_lmstudio_tools_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
                tools=tools,
            )
        try:
            return _call_chat_with_tools(
                prompt,
                settings,
                system=system,
                tools=tools,
                timeout=timeout,
                post=post,
                config=cfg,
            )
        except Exception:
            return _call_lmstudio_tools_fallback(
                prompt,
                role=role,
                system=system,
                timeout=timeout,
                config=cfg,
                environ=environ,
                post=post,
                tools=tools,
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
        caller: Callable | None = None,
    ):
        self.role = role
        self.model = model
        self.system = system
        self.timeout = timeout
        self._caller = caller or call_text

    def generate_content(self, contents):
        prompt = contents if isinstance(contents, str) else str(contents)
        text = self._caller(
            prompt,
            role=self.role,
            model=self.model,
            system=self.system,
            timeout=self.timeout,
        )
        return TextResponse(text=text)


def get_model_wrapper(*, role: str = "worker", model: str | None = None, system: str | None = None) -> ModelWrapper:
    return ModelWrapper(role=role, model=model, system=system)
