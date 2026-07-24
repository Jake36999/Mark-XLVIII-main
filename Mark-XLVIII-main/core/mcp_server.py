from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.runtime_config import load_runtime_config
from core.tool_dispatcher import DispatchContext, get_tool_dispatcher


PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "jarvis-mark", "version": "1.0.0"}


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=True, indent=2)}],
        "structuredContent": payload,
        "isError": not bool(payload.get("ok")),
    }


@dataclass
class TaskRecord:
    task_id: str
    future: Future
    status: str = "working"
    result: dict[str, Any] | None = None
    error: str = ""
    lock: threading.RLock = field(default_factory=threading.RLock)


class MCPTaskStore:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max(1, min(max_workers, 8)), thread_name_prefix="jarvis-mcp")
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.RLock()

    def submit(self, function, *args, **kwargs) -> TaskRecord:
        task_id = uuid.uuid4().hex
        future = self._executor.submit(function, *args, **kwargs)
        record = TaskRecord(task_id=task_id, future=future)
        with self._lock:
            self._tasks[task_id] = record

        def completed(done: Future) -> None:
            with record.lock:
                if done.cancelled():
                    record.status = "cancelled"
                else:
                    try:
                        record.result = done.result()
                        record.status = "completed"
                    except Exception as exc:
                        record.error = f"{type(exc).__name__}: {str(exc)[:1000]}"
                        record.status = "failed"

        future.add_done_callback(completed)
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        record = self.get(task_id)
        if record is None:
            return False
        cancelled = record.future.cancel()
        if cancelled:
            with record.lock:
                record.status = "cancelled"
        return cancelled


class JarvisMCPServer:
    def __init__(self) -> None:
        self.dispatcher = get_tool_dispatcher()
        self.tasks = MCPTaskStore()

    def _capability_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        from actions.capability_registry import capability_registry

        raw = capability_registry({"operation": "mcp", "method": method, "params": params})
        return json.loads(raw)

    def call_method(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}, "tasks": {"requests": {"tools": {"call": {}}}}},
                "serverInfo": SERVER_INFO,
                "instructions": "JARVIS tools use Mark approval gates. Effectful calls require an approved workflow action.",
            }
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return {}
        if method == "ping":
            return {"ok": True}
        if method == "tools/list":
            return {"tools": self.dispatcher.list_tools()}
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
            jarvis_meta = meta.get("jarvis") if isinstance(meta.get("jarvis"), dict) else {}
            context = DispatchContext(
                source="mcp",
                run_id=str(jarvis_meta.get("run_id") or ""),
                action_id=str(jarvis_meta.get("action_id") or ""),
            )
            if bool(meta.get("task")):
                record = self.tasks.submit(self.dispatcher.call, name, arguments, context=context)
                return {"task": {"taskId": record.task_id, "status": record.status, "pollInterval": 500}}
            return _tool_result(self.dispatcher.call(name, arguments, context=context))
        if method == "tasks/get":
            record = self.tasks.get(str(params.get("taskId") or ""))
            if record is None:
                raise KeyError("Unknown task")
            return {"taskId": record.task_id, "status": record.status, "pollInterval": 500}
        if method == "tasks/result":
            record = self.tasks.get(str(params.get("taskId") or ""))
            if record is None:
                raise KeyError("Unknown task")
            if record.status == "completed":
                return _tool_result(record.result or {"ok": False, "error": {"code": "empty_task_result"}})
            if record.status == "failed":
                return _tool_result({"ok": False, "error": {"code": "task_failed", "message": record.error}})
            return {"task": {"taskId": record.task_id, "status": record.status, "pollInterval": 500}}
        if method == "tasks/cancel":
            task_id = str(params.get("taskId") or "")
            return {"taskId": task_id, "cancelled": self.tasks.cancel(task_id)}
        if method.startswith(("cards/", "manifests/", "schemas/", "workflows/", "capabilities/")):
            return self._capability_method(method, params)
        raise KeyError(f"Unsupported method: {method}")

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32600, "message": "Invalid Request"}}
        notification = "id" not in request
        try:
            result = self.call_method(request["method"], request.get("params") or {})
            return None if notification else {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
        except KeyError as exc:
            return None if notification else {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": str(exc)}}
        except Exception as exc:
            return None if notification else {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": f"{type(exc).__name__}: {str(exc)[:1000]}"},
            }


def run_stdio(server: JarvisMCPServer | None = None) -> None:
    service = server or JarvisMCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = service.handle(request)
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {str(exc)[:500]}"}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=True, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def _token_path() -> Path:
    cfg = load_runtime_config()
    root = Path(str(cfg.get("jarvis_notes_root") or Path.cwd())).expanduser().resolve()
    return root / ".jarvis" / "mcp-session.token"


def load_or_create_token(path: Path | None = None) -> str:
    target = path or _token_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target.read_text(encoding="ascii").strip()
    token = secrets.token_urlsafe(32)
    target.write_text(token, encoding="ascii")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return token


def make_http_handler(server: JarvisMCPServer, token: str, allowed_origins: set[str] | None = None):
    origins = allowed_origins or {"http://127.0.0.1", "http://localhost", "null"}

    class Handler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            origin = self.headers.get("Origin")
            if origin and origin not in origins:
                self.send_error(403, "Origin not allowed")
                return False
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_error(401, "Unauthorized")
                return False
            return True

        def do_GET(self) -> None:
            if not self._authorized():
                return
            payload = json.dumps({"ok": True, "server": SERVER_INFO, "protocolVersion": PROTOCOL_VERSION}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:
            if not self._authorized():
                return
            if urlparse(self.path).path != "/mcp":
                self.send_error(404)
                return
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 2_000_000)
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                response = server.handle(request)
                payload = json.dumps(response or {}, ensure_ascii=True).encode("utf-8")
                status = 200
            except Exception as exc:
                payload = json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)[:500]}}).encode("utf-8")
                status = 400
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("JARVIS MCP: " + (format % args) + "\n")

    return Handler


def run_http(host: str = "127.0.0.1", port: int = 8766, token: str | None = None) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("JARVIS MCP HTTP must bind to loopback")
    service = JarvisMCPServer()
    secret = token or load_or_create_token()
    server = ThreadingHTTPServer((host, int(port)), make_http_handler(service, secret))
    server.serve_forever(poll_interval=0.25)


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS MCP server")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--token-file", default="")
    args = parser.parse_args()
    if args.transport == "stdio":
        run_stdio()
    else:
        token = load_or_create_token(Path(args.token_file).resolve()) if args.token_file else load_or_create_token()
        run_http(args.host, args.port, token)


if __name__ == "__main__":
    main()
