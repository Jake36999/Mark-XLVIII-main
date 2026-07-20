from __future__ import annotations

import json
import re
from typing import Any


ASSISTANT_IDENTITY = {
    "assistant_name": "JARVIS",
    "platform_name": "MARK XLVIII",
    "summary": "JARVIS is the assistant. MARK XLVIII is the local platform and shell.",
}


CAPABILITY_HELP: dict[str, dict[str, Any]] = {
    "web_search": {
        "title": "Web, News, Research, Prices",
        "categories": ["web", "news", "research"],
        "summary": "Searches the web for current facts, news, research topics, prices, and comparisons.",
        "details": "Use modes search, news, research, price, and compare. Prefer this over guessing for current information.",
        "examples": ["check the latest AI news", "research local RAG options", "compare GPU prices"],
        "safety": "Read-only web access.",
        "keywords": ["web", "internet", "news", "latest", "current", "research", "price", "compare"],
    },
    "reminder": {
        "title": "Reminders",
        "categories": ["productivity", "schedule"],
        "summary": "Creates timed reminders using the local Windows Task Scheduler integration.",
        "details": "Requires date, time, and message. The router should call this for concrete reminder requests.",
        "examples": ["remind me tomorrow at 9 to check the router", "set a reminder for 18:30"],
        "safety": "Creates local scheduled tasks only after the user asks for a reminder.",
        "keywords": ["reminder", "remind", "schedule", "task scheduler"],
    },
    "weather_report": {
        "title": "Weather",
        "categories": ["web", "utility"],
        "summary": "Fetches a weather report for a city.",
        "details": "Use when the user asks for weather or forecasts.",
        "examples": ["what is the weather in London", "forecast for Manchester"],
        "safety": "Read-only weather lookup.",
        "keywords": ["weather", "forecast", "temperature", "rain"],
    },
    "browser_control": {
        "title": "Browser Control",
        "categories": ["browser", "automation"],
        "summary": "Controls browsers for navigation, searching, clicking, typing, screenshots, and tab actions.",
        "details": "Use for direct browser workflows. Web facts should usually use web_search first.",
        "examples": ["open this URL in Edge", "click the login button", "take a browser screenshot"],
        "safety": "Can interact with pages. Sensitive or destructive web actions should stay confirmation-gated.",
        "keywords": ["browser", "chrome", "edge", "website", "tab", "click", "form"],
    },
    "file_controller": {
        "title": "Files and Folders",
        "categories": ["filesystem", "local"],
        "summary": "Lists, reads, creates, moves, copies, renames, searches, and reports on files and folders.",
        "details": "Use for local filesystem requests. Destructive operations remain controlled by routing/policy.",
        "examples": ["list my downloads", "find large files", "read this file"],
        "safety": "Can mutate files when explicitly requested. Destructive actions require care.",
        "keywords": ["file", "folder", "directory", "read", "write", "copy", "move", "delete"],
    },
    "jarvis_memory": {
        "title": "Vault Memory and Local RAG",
        "categories": ["memory", "rag", "obsidian"],
        "summary": "Creates vault notes, indexes Jarvis_notes locally, queries memory, builds graph/task views, and exports DAG candidates.",
        "details": "The Obsidian vault is canonical. Remember Me is optional and disabled by default for Mark runtime.",
        "examples": ["remember this", "search your memory for local models", "show memory graph"],
        "safety": "Writes Markdown into the configured Jarvis_notes vault.",
        "keywords": ["memory", "remember", "vault", "obsidian", "rag", "graph", "tasks", "dag"],
    },
    "project_operator": {
        "title": "Project Operator",
        "categories": ["projects", "operator"],
        "summary": "Works with registered projects through Mark/Aletheia for status, scouting, code maps, handoffs, OpenClaw delegation, and gated operations.",
        "details": "Uses project registry policies for safe, confirmation-gated, and blocked operations. OpenClaw is an on-demand continuity worker, not an always-on swarm.",
        "examples": ["list my projects", "scout network_management", "delegate mark_platform to OpenClaw"],
        "safety": "Destructive or high-impact project actions are confirmation-gated.",
        "keywords": ["project", "repo", "operator", "scout", "handoff", "code map", "aletheia", "openclaw", "clawteam", "delegate"],
    },
    "model_lifecycle": {
        "title": "LM Studio Model Lifecycle",
        "categories": ["models", "lmstudio", "local"],
        "summary": "Reports loaded LM Studio models, protects baseline speech/worker models, and unloads non-baseline task models when idle.",
        "details": "Uses LM Studio's native /api/v1 model list/unload endpoints and request ttl fields. The parallel field is reported as one loaded instance's concurrency setting, not as multiple loaded model copies.",
        "examples": ["what models are loaded", "clean up idle models", "show baseline models"],
        "safety": "Never unloads configured baseline models and skips cleanup while Mark has active model requests or OpenClaw guard activity.",
        "keywords": ["lmstudio", "lm studio", "model", "models", "loaded", "unload", "cleanup", "ttl", "baseline"],
    },
    "screen_process": {
        "title": "Screen and Camera Vision",
        "categories": ["vision", "screen"],
        "summary": "Captures the screen or webcam and sends the image for analysis.",
        "details": "Use once per visual request. Camera stream can be closed with close_camera.",
        "examples": ["what is on my screen", "look at the camera", "analyze this UI"],
        "safety": "Captures visual context only when requested.",
        "keywords": ["screen", "camera", "vision", "image", "look", "see"],
    },
    "system_status": {
        "title": "System Status",
        "categories": ["system", "monitoring"],
        "summary": "Reports CPU, memory, GPU, temperature, uptime, and process metrics.",
        "details": "Use for computer health and performance questions.",
        "examples": ["check system status", "how hot is the CPU", "GPU usage"],
        "safety": "Read-only local telemetry.",
        "keywords": ["system", "cpu", "ram", "memory", "gpu", "temperature", "uptime"],
    },
    "speech": {
        "title": "Local Speech",
        "categories": ["speech", "audio"],
        "summary": "Router mode supports local speech-to-text and text-to-speech without Gemini Live.",
        "details": "STT uses Vosk by default. TTS can use Windows, EdgeTTS, Kokoro, or OpenAI-compatible local endpoints such as Orpheus.",
        "examples": ["does your text to speech work", "is the microphone active"],
        "safety": "Uses configured local audio devices and local/cloud TTS only when configured.",
        "keywords": ["speech", "voice", "microphone", "stt", "tts", "audio", "text to speech", "speech to text"],
    },
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tool_help(name: str, declaration: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(CAPABILITY_HELP.get(name, {}))
    declaration = declaration or {}
    if not base:
        title = name.replace("_", " ").title()
        base = {
            "title": title,
            "categories": ["tool"],
            "summary": str(declaration.get("description") or title),
            "details": str(declaration.get("description") or ""),
            "examples": [],
            "safety": "Use through the router and existing confirmation gates.",
            "keywords": [name, title.lower()],
        }
    return base


def build_registry(
    declarations: list[dict[str, Any]] | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    declarations = declarations or []
    config = config or {}
    by_name = {item.get("name"): item for item in declarations if item.get("name")}
    tools = []
    names = sorted(set(by_name) | set(CAPABILITY_HELP))
    for name in names:
        declaration = by_name.get(name, {})
        help_data = _tool_help(name, declaration)
        tools.append(
            {
                "name": name,
                "title": help_data["title"],
                "summary": help_data["summary"],
                "categories": help_data.get("categories", []),
                "keywords": help_data.get("keywords", []),
                "safety": help_data.get("safety", ""),
                "schema": declaration.get("parameters") or {"type": "OBJECT", "properties": {}},
                "available": name == "speech" or name in by_name,
            }
        )
    return {
        "name": "mark_capability_registry",
        "protocol": "mcp-like-jsonrpc",
        "identity": ASSISTANT_IDENTITY,
        "voice": {
            "enabled": bool(config.get("voice_enabled", True)),
            "stt_engine": config.get("stt_engine", "vosk"),
            "tts_engine": config.get("tts_engine", "windows"),
            "gemini_live_required": False,
            "gemini_live_optional": True,
        },
        "methods": [
            "tools/list",
            "tools/get",
            "tools/search",
            "tools/call",
            "capabilities/health",
        ],
        "tools": tools,
    }


def _search(registry: dict[str, Any], query: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = [term for term in _normalize(query).split() if len(term) > 1]
    if not terms:
        return registry["tools"][:limit]
    results = []
    for tool in registry["tools"]:
        haystack = _normalize(
            " ".join(
                [
                    tool.get("name", ""),
                    tool.get("title", ""),
                    tool.get("summary", ""),
                    " ".join(tool.get("categories", [])),
                    " ".join(tool.get("keywords", [])),
                ]
            )
        )
        score = sum(haystack.count(term) for term in terms)
        if score:
            compact = {k: tool[k] for k in ("name", "title", "summary", "categories", "available")}
            compact["score"] = score
            results.append(compact)
    results.sort(key=lambda item: (-item["score"], item["name"]))
    return results[:limit]


def _get_tool(registry: dict[str, Any], name: str) -> dict[str, Any] | None:
    normalized = (name or "").strip().lower().replace("-", "_")
    for tool in registry["tools"]:
        if tool["name"].lower() == normalized:
            return tool
    matches = _search(registry, normalized, limit=1)
    if matches:
        return next((tool for tool in registry["tools"] if tool["name"] == matches[0]["name"]), None)
    return None


def _deep_help(registry: dict[str, Any], name: str) -> dict[str, Any]:
    tool = _get_tool(registry, name)
    if not tool:
        return {"ok": False, "error": f"Unknown capability: {name}"}
    help_data = _tool_help(tool["name"])
    return {
        "ok": True,
        "identity": registry["identity"],
        "tool": tool,
        "details": help_data.get("details", ""),
        "examples": help_data.get("examples", []),
        "safety": help_data.get("safety", ""),
    }


def _mcp_response(registry: dict[str, Any], method: str, params: dict[str, Any]) -> dict[str, Any]:
    method = (method or "tools/list").strip()
    params = params or {}
    if method == "tools/list":
        return {"ok": True, "method": method, "tools": registry["tools"]}
    if method == "tools/get":
        tool = _get_tool(registry, str(params.get("name") or params.get("tool") or ""))
        return {"ok": bool(tool), "method": method, "tool": tool}
    if method == "tools/search":
        return {"ok": True, "method": method, "tools": _search(registry, str(params.get("query") or ""), int(params.get("limit") or 8))}
    if method == "tools/call":
        tool = _get_tool(registry, str(params.get("name") or params.get("tool") or ""))
        return {
            "ok": bool(tool),
            "method": method,
            "tool": tool,
            "call_policy": "metadata_only",
            "message": "This registry describes tools but does not execute them. Use JARVIS router tool calls for execution.",
        }
    if method == "capabilities/health":
        return {"ok": True, "method": method, "tool_count": len(registry["tools"]), "voice": registry["voice"]}
    return {"ok": False, "method": method, "error": f"Unsupported registry method: {method}"}


def capability_registry(
    parameters: dict[str, Any] | None = None,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
    *,
    declarations: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    params = dict(parameters or {})
    registry = build_registry(declarations, config=config)
    operation = str(params.get("operation") or "list").strip().lower()
    try:
        if operation == "health":
            result = {"ok": True, "identity": registry["identity"], "tool_count": len(registry["tools"]), "voice": registry["voice"]}
        elif operation == "list":
            result = {"ok": True, "identity": registry["identity"], "tools": registry["tools"]}
        elif operation == "search":
            result = {"ok": True, "identity": registry["identity"], "results": _search(registry, str(params.get("query") or ""), int(params.get("limit") or 8))}
        elif operation in {"describe", "help"}:
            result = _deep_help(registry, str(params.get("tool_name") or params.get("name") or params.get("query") or ""))
        elif operation == "manifest":
            result = {"ok": True, "manifest": registry}
        elif operation in {"mcp", "jsonrpc"}:
            result = _mcp_response(registry, str(params.get("method") or "tools/list"), params.get("params") or {})
        else:
            result = {"ok": False, "error": f"Unknown capability_registry operation: {operation}"}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    return json.dumps(result, ensure_ascii=False, indent=2)
