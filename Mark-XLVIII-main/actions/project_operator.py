import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from actions import model_lifecycle as model_lifecycle_service
from core.runtime_config import load_runtime_config


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
REGISTRY_PATH = BASE_DIR / "config" / "project_registry.json"

DESTRUCTIVE_PATTERNS = (
    r"\bremove-item\b",
    r"\brm\s+-",
    r"\brmdir\b",
    r"\bdel\s+",
    r"\bdelete\b",
    r"\bpurge\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+checkout\b.+--",
    r"\bgit\s+clean\b",
)

BRIDGE_OPERATIONS = {"scout", "code_map", "handoff"}
PROJECT_LEARNING_OPERATION = "learn_project"
OPENCLAW_OPERATION = "delegate_openclaw"
OPENCLAW_ROOT = BASE_DIR.parent / "ClawTeam-OpenClaw-main" / "ClawTeam-OpenClaw-main"
MAX_STRING_CHARS = 1500
MAX_LIST_ITEMS = 10
MAX_OPENCLAW_AGENTS = 3
DEFAULT_OPENCLAW_AGENT = "jarvis-worker"
MULTI_AGENT_TOKENS = (
    "multi-agent",
    "multi agent",
    "parallel",
    "split",
    "multiple files",
    "multi-file",
    "workers",
    "agents",
    "swarm",
)
OPENCLAW_BLOCKED_INTENT_PATTERNS = (
    (r"\b(?:hidden|undisclosed|unlogged)\s+(?:child\s+)?(?:task|action|step|work)", "Hidden or undisclosed work is not allowed."),
    (r"\b(?:bypass|evade|ignore|skip)\b.{0,48}\b(?:approval|confirmation|permission|policy)\b", "Approval and permission controls cannot be bypassed."),
    (r"\b(?:steal|exfiltrate|reveal|dump|print)\b.{0,48}\b(?:credential|secret|api\s*key|token|password)s?\b", "Credential or secret access is outside the delegation boundary."),
    (r"\b(?:purchase|send\s+(?:an?\s+)?(?:email|message)|publish|deploy\s+to\s+(?:production|prod))\b", "External side effects require a separately approved workflow."),
    (r"\b(?:interpret|conclude|determine)\b.{0,48}\b(?:physics|scientific|experimental)\b", "Scientific interpretation remains user- or Claude-owned."),
)


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    return json.loads(registry_path.read_text(encoding="utf-8"))


def list_projects(registry: dict[str, Any] | None = None) -> list[dict[str, str]]:
    data = registry or load_registry()
    projects = []
    for project_id, project in data.get("projects", {}).items():
        projects.append(
            {
                "project_id": project_id,
                "display_name": str(project.get("display_name", project_id)),
                "root": str(project.get("root", "")),
                "summary": str(project.get("summary", "")),
            }
        )
    return projects


def _contains_destructive_command(command: str) -> bool:
    lowered = command.lower()
    return any(re.search(pattern, lowered) for pattern in DESTRUCTIVE_PATTERNS)


def classify_operation(
    registry: dict[str, Any],
    project_id: str,
    operation: str,
    command: str = "",
    confirmation_id: str = "",
    confirmation_validator: Callable[[str, str, str, str], bool] | None = None,
) -> dict[str, Any]:
    projects = registry.get("projects", {})
    project = projects.get(project_id)
    if not project:
        known = sorted(projects.keys())
        # A plain sentence alongside the structured policy. Live assessment saw
        # a model invent a project_id from a filename, get blocked, and relay
        # only "that project is unknown" -- a dead end, even though the real
        # ids were sitting in the payload. Say what to do next in prose the
        # reply can actually use. Registered projects are code repositories;
        # questions about a symbol or file belong to graphify_query.
        return {
            "action": "block",
            "requires_confirmation": False,
            "reason": f"Unknown project_id '{project_id}'.",
            "known_projects": known,
            "hint": (
                f"'{project_id}' is not a registered project. Registered ids are: "
                f"{', '.join(known) if known else 'none'}. If this was a file or symbol name "
                "rather than a project, use graphify_query for questions about what calls, "
                "uses, or depends on it."
            ),
        }

    normalized_operation = (operation or "status").strip().lower()
    command = (command or "").strip()

    if normalized_operation in set(project.get("blocked_operations", [])):
        return {
            "action": "block",
            "requires_confirmation": True,
            "reason": f"Operation '{normalized_operation}' is blocked for {project_id}.",
        }

    if command and _contains_destructive_command(command):
        return {
            "action": "block",
            "requires_confirmation": True,
            "reason": "Destructive command text requires an explicit confirmation workflow.",
        }

    confirmed = False
    if confirmation_id and confirmation_validator is not None:
        try:
            confirmed = bool(confirmation_validator(project_id, normalized_operation, command, confirmation_id))
        except Exception:
            confirmed = False

    if normalized_operation in set(project.get("confirmation_operations", [])):
        return {
            "action": "allow" if confirmed else "confirm",
            "requires_confirmation": not confirmed,
            "reason": (
                f"Operation '{normalized_operation}' has trusted confirmation."
                if confirmed
                else f"Operation '{normalized_operation}' requires trusted confirmation."
            ),
        }

    command_lower = command.lower()
    for gated in project.get("confirmation_commands", []):
        if gated.lower() and gated.lower() in command_lower:
            return {
                "action": "allow" if confirmed else "confirm",
                "requires_confirmation": not confirmed,
                "reason": (
                    "Command has trusted confirmation."
                    if confirmed
                    else "Command matches a confirmation-gated project command and requires trusted confirmation."
                ),
            }

    if normalized_operation in set(project.get("safe_operations", [])):
        return {
            "action": "allow",
            "requires_confirmation": False,
            "reason": f"Operation '{normalized_operation}' is allowed.",
        }

    return {
        "action": "confirm",
        "requires_confirmation": True,
        "reason": f"Operation '{normalized_operation}' is not registered as safe.",
    }


def build_jsonrpc_request(tool_name: str, args: dict[str, Any], request_id: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools.call",
        "params": {
            "toolName": tool_name,
            "args": args,
        },
    }


def call_aletheia_tool(
    bridge: dict[str, Any],
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    host = str(bridge.get("host", "127.0.0.1"))
    port = int(bridge.get("port", 8765))
    timeout = float(bridge.get("timeout_seconds", 20))
    request = build_jsonrpc_request(tool_name, args)

    def roundtrip() -> str:
        with socket.create_connection((host, port), timeout=timeout) as client:
            client.settimeout(timeout)
            line = json.dumps(request, separators=(",", ":")) + "\n"
            client.sendall(line.encode("utf-8"))
            reader = client.makefile("r", encoding="utf-8", newline="\n")
            return reader.readline()

    try:
        response_line = roundtrip()
    except OSError as exc:
        from core.aletheia_supervisor import get_aletheia_supervisor

        health = get_aletheia_supervisor().ensure_available({"host": host, "port": port})
        if health.get("reachable"):
            try:
                response_line = roundtrip()
            except OSError as retry_exc:
                exc = retry_exc
                response_line = ""
        else:
            response_line = ""
        if response_line:
            pass
        else:
            return {
                "ok": False,
                "summary": (
                    "Aletheia bridge is not available. Start it with "
                    "scripts\\start-aletheia-operator.ps1, then retry."
                ),
                "error": {"code": "bridge_unavailable", "message": str(exc)},
                "health": health,
            }

    if not response_line:
        return {
            "ok": False,
            "summary": "Aletheia bridge returned an empty response.",
            "error": {"code": "empty_bridge_response", "message": ""},
        }

    try:
        payload = json.loads(response_line)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "summary": "Aletheia bridge returned invalid JSON.",
            "error": {"code": "invalid_bridge_json", "message": str(exc)},
        }

    if "error" in payload:
        return {
            "ok": False,
            "summary": "Aletheia tool call failed.",
            "error": payload["error"],
        }

    result = payload.get("result", {})
    if isinstance(result, dict):
        return result
    return {"ok": True, "summary": "Aletheia returned a non-object result.", "result": result}


def _build_bridge_call(project_id: str, operation: str, project: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    root = str(project["root"])
    if operation == "scout":
        return (
            "mcp_scout_workspace",
            {
                "project_id": project_id,
                "absolute_path": root,
                "max_files": 500,
                "include_summaries": True,
            },
        )
    if operation == "code_map":
        return (
            "mcp_code_intelligence",
            {
                "target_repo": root,
                "mode": "code_map",
                "max_files": 800,
            },
        )
    if operation == "handoff":
        return (
            "mcp_agent_workflow_run",
            {
                "objective": f"Prepare a concise operator handoff for {project_id}.",
                "target_repo": root,
                "profile": "safe",
                "include_report_preview": True,
                "pipeline_id": "investigation",
            },
        )
    raise ValueError(f"Unsupported bridge operation: {operation}")


def _slug(text: str, fallback: str = "item") -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text or fallback)[:48].strip("-") or fallback


def _tail(text: str, limit: int = 1500) -> str:
    text = text or ""
    return text if len(text) <= limit else text[-limit:]


def _is_git_repo(path: str) -> bool:
    root = Path(path)
    marker = root / ".git"
    return marker.exists()


def _explicit_multi_agent_requested(parameters: dict[str, Any]) -> bool:
    text = " ".join(
        str(parameters.get(key) or "")
        for key in ("intent", "task", "command", "description")
    ).lower()
    return any(token in text for token in MULTI_AGENT_TOKENS)


def _requested_openclaw_agents(parameters: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    requested = parameters.get("agents", parameters.get("agent_count", 1))
    try:
        count = int(requested)
    except (TypeError, ValueError):
        count = 1
    count = max(1, count)
    explicit_multi = _explicit_multi_agent_requested(parameters)
    if count > 1 and not explicit_multi:
        return 0, {
            "action": "block",
            "requires_confirmation": False,
            "reason": "Multiple OpenClaw agents require explicit parallel or multi-agent intent.",
            "requested_agents": count,
        }
    if count > MAX_OPENCLAW_AGENTS:
        return 0, {
            "action": "block",
            "requires_confirmation": False,
            "reason": f"OpenClaw delegation is capped at {MAX_OPENCLAW_AGENTS} agents.",
            "requested_agents": count,
        }
    return count, {"action": "allow", "requires_confirmation": False, "reason": "OpenClaw agent count allowed."}


def _classify_openclaw_intent(parameters: dict[str, Any]) -> dict[str, Any]:
    intent = " ".join(
        str(parameters.get(key) or "")
        for key in ("intent", "task", "description", "command")
    ).strip()
    if _contains_destructive_command(intent):
        return {
            "action": "block",
            "requires_confirmation": True,
            "reason": "Destructive command text cannot be delegated through OpenClaw.",
        }
    for pattern, reason in OPENCLAW_BLOCKED_INTENT_PATTERNS:
        if re.search(pattern, intent, flags=re.IGNORECASE | re.DOTALL):
            return {"action": "block", "requires_confirmation": True, "reason": reason}
    return {
        "action": "allow",
        "requires_confirmation": False,
        "reason": "Intent is within the bounded coding-continuity delegation policy.",
    }


def _openclaw_task(project_id: str, project: dict[str, Any], parameters: dict[str, Any], agent_index: int, agents: int) -> str:
    intent = str(parameters.get("intent") or parameters.get("task") or parameters.get("description") or "").strip()
    if not intent:
        intent = "Prepare a concise continuity handoff and identify safe next coding steps."
    suffix = f"\n\nWorker {agent_index + 1} of {agents}." if agents > 1 else ""
    return (
        f"Project: {project.get('display_name', project_id)} ({project_id})\n"
        f"Root: {project.get('root')}\n"
        f"Role: on-demand OpenClaw continuity worker for lightweight coding assistance.\n"
        f"Task: {intent}\n"
        "Constraints: avoid destructive commands, keep changes scoped, and report what you changed or found."
        f"{suffix}"
    )


def build_openclaw_spawn_command(
    *,
    project: dict[str, Any],
    team: str,
    agent_name: str,
    task: str,
    workspace: bool,
    model: str = "",
    openclaw_agent: str = "",
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "clawteam",
        "spawn",
        "subprocess",
        "openclaw",
        "agent",
        "--team",
        team,
        "--agent-name",
        agent_name,
        "--agent-type",
        "continuity",
        "--repo",
        str(project["root"]),
        "--task",
        task,
        "--no-keepalive",
    ]
    command.append("--workspace" if workspace else "--no-workspace")
    if model:
        command.extend(["--model", model])
    if openclaw_agent:
        command.extend(["--openclaw-agent", openclaw_agent])
    return command


def _record_openclaw_handoff(
    *,
    project_id: str,
    project: dict[str, Any],
    team: str,
    agents: int,
    intent: str,
) -> dict[str, Any]:
    try:
        from actions.jarvis_memory import create_note

        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        content = (
            f"## Objective\n{intent or 'OpenClaw continuity handoff'}\n\n"
            f"## Project\n- id: `{project_id}`\n- name: {project.get('display_name', project_id)}\n"
            f"- root: `{project.get('root')}`\n\n"
            f"## Delegation\n- backend: ClawTeam subprocess\n- team: `{team}`\n"
            f"- agents: {agents}\n- keepalive: false\n- created: {timestamp}\n\n"
            "## Guardrails\n- Use OpenClaw for continuity and lightweight coding assistance.\n"
            "- Avoid destructive commands.\n"
            "- Keep any changes scoped and report outcomes back to Mark/Codex/Claude."
        )
        return create_note(
            note_type="log",
            title=f"OpenClaw Delegation - {project.get('display_name', project_id)}",
            content=content,
            tags=["openclaw", "handoff", "project", project_id],
            source="project_operator",
            sync=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def delegate_openclaw(
    project_id: str,
    project: dict[str, Any],
    parameters: dict[str, Any],
    *,
    run: Any = subprocess.run,
) -> dict[str, Any]:
    count, agent_policy = _requested_openclaw_agents(parameters)
    if agent_policy["action"] != "allow":
        return {"ok": False, "project_id": project_id, "operation": OPENCLAW_OPERATION, "policy": agent_policy}

    intent_policy = _classify_openclaw_intent(parameters)
    if intent_policy["action"] != "allow":
        return {"ok": False, "project_id": project_id, "operation": OPENCLAW_OPERATION, "policy": intent_policy}

    if not OPENCLAW_ROOT.exists():
        return {
            "ok": False,
            "project_id": project_id,
            "operation": OPENCLAW_OPERATION,
            "error": {
                "code": "openclaw_root_missing",
                "message": f"ClawTeam/OpenClaw was not found at {OPENCLAW_ROOT}",
            },
        }

    team = str(parameters.get("team") or f"mark-{_slug(project_id)}")
    intent = str(parameters.get("intent") or parameters.get("task") or parameters.get("description") or "").strip()
    handoff_note = _record_openclaw_handoff(
        project_id=project_id,
        project=project,
        team=team,
        agents=count,
        intent=intent,
    )
    model_lifecycle_service.register_external_activity(f"openclaw:{team}", ttl_seconds=None)

    workspace = bool(parameters.get("workspace", _is_git_repo(str(project["root"]))))
    model = str(parameters.get("model") or "").strip()
    runtime_config = load_runtime_config()
    openclaw_agent = str(
        parameters.get("openclaw_agent")
        or runtime_config.get("openclaw_worker_agent")
        or DEFAULT_OPENCLAW_AGENT
    ).strip()
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(OPENCLAW_ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

    spawned: list[dict[str, Any]] = []
    for index in range(count):
        agent_name = str(parameters.get("agent_name") or f"openclaw-{_slug(project_id)}-{index + 1}-{uuid4_suffix()}")
        if count > 1 and parameters.get("agent_name"):
            agent_name = f"{agent_name}-{index + 1}"
        task = _openclaw_task(project_id, project, parameters, index, count)
        command = build_openclaw_spawn_command(
            project=project,
            team=team,
            agent_name=agent_name,
            task=task,
            workspace=workspace,
            model=model,
            openclaw_agent=openclaw_agent,
        )
        try:
            completed = run(
                command,
                cwd=str(OPENCLAW_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=int(parameters.get("timeout") or 120),
            )
            spawned.append(
                {
                    "agent_name": agent_name,
                    "returncode": completed.returncode,
                    "ok": completed.returncode == 0,
                    "stdout": _tail(completed.stdout),
                    "stderr": _tail(completed.stderr),
                    "command": command,
                }
            )
        except Exception as exc:
            spawned.append(
                {
                    "agent_name": agent_name,
                    "returncode": None,
                    "ok": False,
                    "error": str(exc),
                    "command": command,
                }
            )

    return {
        "ok": all(item.get("ok") for item in spawned),
        "project_id": project_id,
        "operation": OPENCLAW_OPERATION,
        "team": team,
        "agents": count,
        "workspace": workspace,
        "handoff_note": compact_for_mark(handoff_note),
        "spawned": compact_for_mark(spawned),
        "policy": {"agent_count": agent_policy, "intent": intent_policy},
    }


def uuid4_suffix() -> str:
    import uuid

    return uuid.uuid4().hex[:6]


def compact_for_mark(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) <= MAX_STRING_CHARS:
            return value
        return value[:MAX_STRING_CHARS].rstrip() + f"\n...[truncated {len(value) - MAX_STRING_CHARS} chars]"

    if isinstance(value, list):
        compacted = [compact_for_mark(item) for item in value[:MAX_LIST_ITEMS]]
        omitted = len(value) - len(compacted)
        if omitted > 0:
            compacted.append({"files_omitted": omitted})
        return compacted

    if isinstance(value, dict):
        return {key: compact_for_mark(item) for key, item in value.items()}

    return value


def project_operator(
    parameters: dict[str, Any],
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    registry = load_registry()
    project_id = str(parameters.get("project_id", "")).strip()
    operation = str(parameters.get("operation", "status")).strip().lower()
    command = str(parameters.get("command", "")).strip()
    confirmation_id = str(parameters.get("confirmation_id", "")).strip()

    if operation == "list":
        return json.dumps({"ok": True, "projects": list_projects(registry)}, indent=2)

    if operation == PROJECT_LEARNING_OPERATION:
        project = registry.get("projects", {}).get(project_id) if project_id else None
        explicit_path = str(parameters.get("path") or parameters.get("root") or "").strip()
        if project is not None:
            decision = classify_operation(registry, project_id, operation, command, confirmation_id)
            if decision["action"] != "allow":
                return json.dumps({"ok": False, "policy": decision}, indent=2)
        elif explicit_path:
            root = Path(explicit_path).expanduser().resolve()
            if not root.is_dir():
                return json.dumps({"ok": False, "error": f"Project directory was not found: {root}"}, indent=2)
            project_id = project_id or _slug(root.name, "local-project")
            project = {
                "display_name": str(parameters.get("display_name") or root.name or project_id),
                "root": str(root),
                "summary": "Explicit read-only project learning target supplied by the user.",
            }
            decision = {
                "action": "allow",
                "requires_confirmation": False,
                "reason": "Explicit directory learning is read-only; derivative notes are written only to Jarvis_notes.",
            }
        else:
            return json.dumps(
                {
                    "ok": False,
                    "error": "Provide a registered project_id or an explicit project directory path.",
                    "projects": list_projects(registry),
                },
                indent=2,
            )

        bridge_context: dict[str, Any] = {}
        if project_id in registry.get("projects", {}) and parameters.get("use_aletheia", True):
            for bridge_operation in ("scout", "code_map"):
                try:
                    tool_name, tool_args = _build_bridge_call(project_id, bridge_operation, project)
                    bridge_context[bridge_operation] = compact_for_mark(
                        call_aletheia_tool(registry.get("bridge", {}), tool_name, tool_args)
                    )
                except Exception as exc:
                    bridge_context[bridge_operation] = {"ok": False, "error": str(exc)}

        from actions.project_learning import learn_repository

        result = learn_repository(
            str(project["root"]),
            project_id=project_id,
            display_name=str(project.get("display_name") or project_id),
            intent=str(parameters.get("intent") or parameters.get("task") or ""),
            bridge_context=bridge_context,
            params=parameters,
        )
        result["policy"] = decision
        return json.dumps(compact_for_mark(result), indent=2)

    if not project_id:
        return json.dumps({"ok": True, "projects": list_projects(registry)}, indent=2)

    decision = classify_operation(registry, project_id, operation, command, confirmation_id)
    if decision["action"] != "allow":
        return json.dumps({"ok": False, "policy": decision}, indent=2)

    project = registry["projects"][project_id]
    if operation == OPENCLAW_OPERATION:
        result = delegate_openclaw(project_id, project, parameters)
        return json.dumps(compact_for_mark(result), indent=2)

    if operation in BRIDGE_OPERATIONS:
        tool_name, tool_args = _build_bridge_call(project_id, operation, project)
        result = call_aletheia_tool(registry.get("bridge", {}), tool_name, tool_args)
        return json.dumps(
            {
                "ok": bool(result.get("ok", False)),
                "project_id": project_id,
                "operation": operation,
                "tool_name": tool_name,
                "result": compact_for_mark(result),
            },
            indent=2,
        )

    return json.dumps(
        {
            "ok": True,
            "project_id": project_id,
            "operation": operation,
            "summary": project["summary"],
            "policy": decision,
        },
        indent=2,
    )
