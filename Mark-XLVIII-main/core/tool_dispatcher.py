from __future__ import annotations

import ast
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft7Validator
from core.process_events import emit_process_event


class ToolDispatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class DispatchContext:
    source: str = "router"
    run_id: str = ""
    action_id: str = ""
    user_confirmed: bool = False


READ_ONLY_TOOLS = {
    "capability_registry",
    "graphify_query",
    "model_registry",
    "system_status",
    "weather_report",
    "web_search",
}

READ_ONLY_OPERATIONS: dict[str, set[str]] = {
    "memory_consolidation": {"detect", "candidates", "what_is_stale"},
    "dual_orchestrator": {"health", "validate", "compile", "preview_legacy", "status"},
    "jarvis_canvas": {
        "health", "status", "inspect", "validate", "preview_layout", "neighbors",
        "relationships", "cross_canvas", "reconcile", "task_changes", "propose_task_changes",
    },
    # propose/execute both write (a companion note; canvas status/annotations and
    # possibly OpenClaw dispatch, respectively). evaluate_approval can mint a
    # signed approval envelope, so it stays a write too. verify_approval only
    # ever reads the canvas and the envelope to check them, never writes.
    "canvas_plan": {"health", "verify_approval"},
    "jarvis_memory": {
        "health",
        "query",
        "query_local",
        "lookup_local",
        "deps",
        "consumers",
        "related",
        "context_pack",
        "graph",
        "tasks",
        "task_review_status",
        "watch_status",
        "dag_candidates",
        "list_templates",
        "integrity",
        "check_integrity",
        "vault_health",
    },
    "model_lifecycle": {"health", "status", "baseline", "loaded_models", "load_profile"},
    "plan_workflow": {"health", "run_status", "list_templates"},
    "project_operator": {"list", "status", "scout", "code_map", "handoff", "health"},
    "file_controller": {"list", "read", "find", "largest", "disk_usage", "info"},
    "file_processor": {"info", "extract_text", "summarize", "analyze", "validate", "stats", "list"},
    "browser_control": {"get_text", "get_url", "list_browsers", "screenshot"},
}

DESTRUCTIVE_ACTIONS = {
    "delete",
    "clean",
    "shutdown",
    "restart",
    "close_all",
    "stop",
    "heavy_training",
    "unload_non_baseline",
}

HEADLESS_TOOLS = {
    "web_search", "jarvis_memory", "memory_consolidation", "jarvis_canvas", "canvas_plan", "plan_workflow", "project_operator",
    "capability_registry", "dual_orchestrator", "model_lifecycle", "model_registry",
    "file_processor", "file_controller", "browser_control", "reminder", "weather_report",
    "system_status", "open_app", "desktop_control", "computer_settings", "computer_control",
    "send_message", "youtube_video", "code_helper", "dev_agent", "graphify_query",
}


def _json_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    converted: dict[str, Any] = {}
    for key, item in value.items():
        if key == "type" and isinstance(item, str):
            converted[key] = item.lower()
        else:
            converted[key] = _json_schema(item)
    return converted


def _declarations_from_main_source() -> list[dict[str, Any]]:
    main_module = sys.modules.get("main")
    loaded = getattr(main_module, "TOOL_DECLARATIONS", None) if main_module else None
    if isinstance(loaded, list):
        return [dict(item) for item in loaded if isinstance(item, dict) and item.get("name")]
    path = Path(__file__).resolve().parent.parent / "main.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "TOOL_DECLARATIONS" for target in node.targets):
                value = ast.literal_eval(node.value)
                if isinstance(value, list):
                    return [dict(item) for item in value if isinstance(item, dict) and item.get("name")]
    except Exception:
        return []
    return []


def load_tool_declarations() -> list[dict[str, Any]]:
    declarations = _declarations_from_main_source()
    if declarations:
        return declarations
    from actions.capability_registry import build_registry

    registry = build_registry()
    return [
        {
            "name": tool["name"],
            "description": tool.get("summary") or tool.get("title") or tool["name"],
            "parameters": tool.get("schema") or {"type": "object", "properties": {}},
        }
        for tool in registry.get("tools") or []
        if tool.get("available")
    ]


def _operation(arguments: dict[str, Any]) -> str:
    return str(arguments.get("operation") or arguments.get("action") or "").strip().lower()


def classify_effect(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    operation = _operation(arguments)
    if tool_name == "jarvis_memory" and operation == "run_task_review":
        effect = "write" if bool(arguments.get("scheduled")) else "read"
        return {"effect": effect, "requires_approval": effect == "write", "operation": operation}
    if tool_name == "file_processor" and operation in {"summarize", "analyze", "analyze_large", "analyze_folder"}:
        default_save = operation in {"summarize", "analyze_large", "analyze_folder"}
        saves_artifact = bool(arguments.get("save_to_vault", arguments.get("save", default_save)))
        effect = "write" if saves_artifact else "read"
        return {"effect": effect, "requires_approval": effect == "write", "operation": operation}
    if tool_name in READ_ONLY_TOOLS or operation in READ_ONLY_OPERATIONS.get(tool_name, set()):
        return {"effect": "read", "requires_approval": False, "operation": operation}
    if operation in DESTRUCTIVE_ACTIONS:
        return {"effect": "destructive", "requires_approval": True, "operation": operation}
    return {"effect": "write", "requires_approval": True, "operation": operation}


def _verify_workflow_authorization(context: DispatchContext, tool_name: str, arguments: dict[str, Any]) -> bool:
    if not context.run_id or not context.action_id:
        return False
    try:
        from actions.dual_orchestrator import load_workflow, manifest_content_hash, sha256_value, verify_approval_envelope, workflow_runtime

        runtime = workflow_runtime()
        status = runtime.status(context.run_id)
        run = status.get("run") or {}
        if run.get("status") not in {"APPROVED", "RUNNING", "REPAIRING"}:
            return False
        bundle = Path(str(run.get("bundle_path") or ""))
        manifest = json.loads((bundle / "work-items.json").read_text(encoding="utf-8"))
        workflow = load_workflow(bundle / "workflow.yaml")
        envelope = json.loads((bundle / "approval.json").read_text(encoding="utf-8"))
        item = next((value for value in manifest.get("items") or [] if value.get("id") == context.action_id), None)
        if not item or item.get("step_type") != "tool" or item.get("target") != tool_name:
            return False
        if context.action_id not in set(envelope.get("approved_action_ids") or []):
            return False
        if manifest.get("manifest_hash") != manifest_content_hash(manifest):
            return False
        if manifest.get("manifest_hash") != run.get("manifest_hash") or sha256_value(workflow) != run.get("workflow_hash"):
            return False
        if not verify_approval_envelope(runtime.vault_root, envelope):
            return False
        expected = item.get("inputs") or {}
        return expected == arguments
    except Exception:
        return False


def _handler(tool_name: str) -> Callable[[dict[str, Any]], Any] | None:
    if tool_name == "web_search":
        from actions.web_search import web_search

        return lambda args: web_search(parameters=args)
    if tool_name == "jarvis_memory":
        from actions.jarvis_memory import jarvis_memory

        return lambda args: jarvis_memory(args)
    if tool_name == "memory_consolidation":
        from actions.memory_consolidation import memory_consolidation

        return lambda args: memory_consolidation(args)
    if tool_name == "jarvis_canvas":
        from actions.jarvis_canvas import jarvis_canvas

        return lambda args: jarvis_canvas(args)
    if tool_name == "canvas_plan":
        from actions.canvas_plan import canvas_plan

        return lambda args: canvas_plan(args)
    if tool_name == "plan_workflow":
        from actions.plan_workflow import plan_workflow

        return lambda args: plan_workflow(args)
    if tool_name == "project_operator":
        from actions.project_operator import project_operator

        return lambda args: project_operator(args)
    if tool_name == "capability_registry":
        from actions.capability_registry import capability_registry

        return lambda args: capability_registry(args)
    if tool_name == "dual_orchestrator":
        from actions.dual_orchestrator import dual_orchestrator

        return lambda args: dual_orchestrator(args)
    if tool_name == "model_lifecycle":
        from actions.model_lifecycle import model_lifecycle

        return lambda args: model_lifecycle(args)
    if tool_name == "model_registry":
        from actions.model_registry import model_registry

        return lambda args: model_registry(args)
    if tool_name == "file_processor":
        from actions.file_processor import file_processor

        return lambda args: file_processor(parameters=args)
    if tool_name == "file_controller":
        from actions.file_controller import file_controller

        return lambda args: file_controller(parameters=args)
    if tool_name == "browser_control":
        from actions.browser_control import browser_control

        return lambda args: browser_control(parameters=args)
    if tool_name == "reminder":
        from actions.reminder import reminder

        return lambda args: reminder(parameters=args)
    if tool_name == "weather_report":
        from actions.weather_report import weather_action

        return lambda args: weather_action(parameters=args)
    if tool_name == "system_status":
        from actions.system_monitor import get_system_status

        return lambda _args: get_system_status()
    if tool_name == "open_app":
        from actions.open_app import open_app

        return lambda args: open_app(parameters=args)
    if tool_name == "desktop_control":
        from actions.desktop import desktop_control

        return lambda args: desktop_control(parameters=args)
    if tool_name == "computer_settings":
        from actions.computer_settings import computer_settings

        return lambda args: computer_settings(parameters=args)
    if tool_name == "computer_control":
        from actions.computer_control import computer_control

        return lambda args: computer_control(parameters=args)
    if tool_name == "send_message":
        from actions.send_message import send_message

        return lambda args: send_message(parameters=args)
    if tool_name == "youtube_video":
        from actions.youtube_video import youtube_video

        return lambda args: youtube_video(parameters=args)
    if tool_name == "code_helper":
        from actions.code_helper import code_helper

        return lambda args: code_helper(parameters=args)
    if tool_name == "dev_agent":
        from actions.dev_agent import dev_agent

        return lambda args: dev_agent(parameters=args)
    if tool_name == "graphify_query":
        from actions.graphify_query import graphify_query

        return lambda args: graphify_query(parameters=args)
    return None


def _decode_result(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class ToolDispatcher:
    def __init__(self, declarations: list[dict[str, Any]] | None = None) -> None:
        self.declarations = declarations or load_tool_declarations()
        self._by_name = {str(item["name"]): item for item in self.declarations if item.get("name")}
        self._lock = threading.RLock()

    def list_tools(self) -> list[dict[str, Any]]:
        tools = []
        for name, declaration in sorted(self._by_name.items()):
            tools.append(
                {
                    "name": name,
                    "description": str(declaration.get("description") or name),
                    "inputSchema": _json_schema(declaration.get("parameters") or {"type": "object", "properties": {}}),
                    "annotations": classify_effect(name, {}),
                    "available": name in HEADLESS_TOOLS,
                }
            )
        return tools

    def health(self) -> dict[str, Any]:
        tools = self.list_tools()
        return {
            "ok": True,
            "tool_count": len(tools),
            "available_count": sum(1 for tool in tools if tool["available"]),
            "read_only_calling": True,
            "approved_write_calling": True,
        }

    def call(self, tool_name: str, arguments: dict[str, Any] | None, *, context: DispatchContext | None = None) -> dict[str, Any]:
        name = str(tool_name or "").strip()
        args = dict(arguments or {})
        declaration = self._by_name.get(name)
        if declaration is None:
            emit_process_event(category="tool", source=name or "dispatcher", summary="Rejected an unknown tool request.", state="rejected", severity="warning")
            return {"ok": False, "error": {"code": "tool_not_found", "message": f"Unknown tool: {name}"}}
        schema = _json_schema(declaration.get("parameters") or {"type": "object", "properties": {}})
        errors = sorted(Draft7Validator(schema).iter_errors(args), key=lambda error: list(error.path))
        if errors:
            emit_process_event(category="tool", source=name, summary=f"Rejected invalid arguments for {name}.", state="rejected", severity="warning")
            return {
                "ok": False,
                "error": {"code": "invalid_arguments", "message": errors[0].message, "path": list(errors[0].path)},
            }
        decision = classify_effect(name, args)
        dispatch_context = context or DispatchContext()
        if decision["requires_approval"] and not _verify_workflow_authorization(dispatch_context, name, args):
            emit_process_event(category="approval", source=name, summary=f"{name} is waiting for an approval-bound workflow action.", state="blocked", severity="warning")
            return {
                "ok": False,
                "error": {
                    "code": "approval_required",
                    "message": "Effectful MCP tool calls must be bound to an approved JARVIS workflow action.",
                },
                "policy": decision,
            }
        handler = _handler(name)
        if handler is None:
            emit_process_event(category="tool", source=name, summary=f"{name} is registered but unavailable in the headless dispatcher.", state="unavailable", severity="warning")
            return {"ok": False, "error": {"code": "tool_unavailable", "message": f"Tool has no headless dispatcher: {name}"}}
        try:
            emit_process_event(category="tool", source=name, summary=f"Dispatching {name} through the guarded tool boundary.", state="running", detail={"effect": decision.get("effect")})
            with (self._lock if decision["effect"] != "read" else _NullLock()):
                value = _decode_result(handler(args))
            emit_process_event(category="tool", source=name, summary=f"{name} completed.", state="completed", detail={"effect": decision.get("effect")})
            return {"ok": True, "tool": name, "result": value, "policy": decision}
        except Exception as exc:
            emit_process_event(category="tool", source=name, summary=f"{name} failed with {type(exc).__name__}.", state="failed", severity="error", detail={"effect": decision.get("effect")})
            return {
                "ok": False,
                "tool": name,
                "error": {"code": "tool_failed", "message": f"{type(exc).__name__}: {str(exc)[:1000]}"},
                "policy": decision,
            }


class _NullLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: Any) -> None:
        return None


_DISPATCHER: ToolDispatcher | None = None
_DISPATCHER_LOCK = threading.RLock()


def get_tool_dispatcher() -> ToolDispatcher:
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        if _DISPATCHER is None:
            _DISPATCHER = ToolDispatcher()
        return _DISPATCHER
