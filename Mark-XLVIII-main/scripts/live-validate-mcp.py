"""External live validation for the loopback JARVIS MCP HTTP transport."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8766"


def request(path: str, *, token: str = "", origin: str = "", payload: dict | None = None) -> tuple[int, dict]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["MCP-Protocol-Version"] = "2025-11-25"
    req = urllib.request.Request(URL + path, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def rpc(request_id: int, method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


def wait_for_server(process: subprocess.Popen, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"MCP server exited with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", 8766), timeout=0.25):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("MCP server did not listen on 127.0.0.1:8766")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="jarvis-mcp-validation-") as tmp:
        root = Path(tmp)
        token_file = root / "session.token"
        out_file = root / "stdout.log"
        err_file = root / "stderr.log"
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with out_file.open("w", encoding="utf-8") as stdout, err_file.open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "core.mcp_server",
                    "--transport",
                    "http",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8766",
                    "--token-file",
                    str(token_file),
                ],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )
            try:
                wait_for_server(process)
                token = token_file.read_text(encoding="ascii").strip()
                unauthorized_status, _ = request("/")
                bad_origin_status, _ = request("/", token=token, origin="http://untrusted.invalid")
                health_status, health = request("/", token=token, origin="http://127.0.0.1")
                _, initialized = request(
                    "/mcp", token=token, origin="http://127.0.0.1", payload=rpc(1, "initialize")
                )
                _, listed = request(
                    "/mcp", token=token, origin="http://127.0.0.1", payload=rpc(2, "tools/list")
                )
                _, read_call = request(
                    "/mcp",
                    token=token,
                    origin="http://127.0.0.1",
                    payload=rpc(
                        3,
                        "tools/call",
                        {"name": "capability_registry", "arguments": {"operation": "health"}},
                    ),
                )
                _, write_call = request(
                    "/mcp",
                    token=token,
                    origin="http://127.0.0.1",
                    payload=rpc(
                        4,
                        "tools/call",
                        {
                            "name": "reminder",
                            "arguments": {
                                "operation": "create",
                                "message": "JARVIS MCP validation only",
                                "time": "2099-01-01 00:00",
                            },
                        },
                    ),
                )
                result = {
                    "ok": all(
                        (
                            unauthorized_status == 401,
                            bad_origin_status == 403,
                            health_status == 200 and health.get("ok") is True,
                            initialized.get("result", {}).get("protocolVersion") == "2025-11-25",
                            len(listed.get("result", {}).get("tools", [])) >= 18,
                            read_call.get("result", {}).get("isError") is False,
                            write_call.get("result", {}).get("isError") is True,
                        )
                    ),
                    "server_started": True,
                    "unauthorized_status": unauthorized_status,
                    "bad_origin_status": bad_origin_status,
                    "authenticated_health": health_status == 200 and health.get("ok") is True,
                    "protocol": initialized.get("result", {}).get("protocolVersion"),
                    "tool_count": len(listed.get("result", {}).get("tools", [])),
                    "read_call_error": read_call.get("result", {}).get("isError"),
                    "unapproved_write_rejected": write_call.get("result", {}).get("isError"),
                }
                print(json.dumps(result, indent=2))
                return 0 if result["ok"] else 1
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
