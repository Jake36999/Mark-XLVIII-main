from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from core.runtime_config import load_runtime_config


BASE_DIR = Path(__file__).resolve().parent.parent
START_SCRIPT = BASE_DIR / "scripts" / "start-aletheia-operator.ps1"


class AletheiaSupervisor:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._lock = threading.RLock()

    def config(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = load_runtime_config()
        if overrides:
            cfg.update(overrides)
        return {
            "host": str(cfg.get("host") or cfg.get("aletheia_bridge_host") or "127.0.0.1"),
            "port": int(cfg.get("port") or cfg.get("aletheia_bridge_port") or 8765),
            "autostart": bool(cfg.get("aletheia_autostart", False)),
            "startup_timeout_seconds": int(cfg.get("aletheia_startup_timeout_seconds") or 30),
        }

    def probe(self, overrides: dict[str, Any] | None = None, timeout: float = 0.5) -> dict[str, Any]:
        cfg = self.config(overrides)
        started = time.monotonic()
        try:
            with socket.create_connection((cfg["host"], cfg["port"]), timeout=timeout):
                reachable = True
                error = ""
        except OSError as exc:
            reachable = False
            error = str(exc)
        process_alive = self._process is not None and self._process.poll() is None
        return {
            "ok": reachable,
            "reachable": reachable,
            "host": cfg["host"],
            "port": cfg["port"],
            "autostart": cfg["autostart"],
            "supervised_process_alive": process_alive,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "error": error,
        }

    def start(self, overrides: dict[str, Any] | None = None, *, force: bool = False) -> dict[str, Any]:
        cfg = self.config(overrides)
        current = self.probe(cfg)
        if current["reachable"]:
            return {**current, "started": False, "reason": "already_reachable"}
        if not force and not cfg["autostart"]:
            return {**current, "started": False, "reason": "autostart_disabled"}
        if not START_SCRIPT.is_file():
            return {**current, "started": False, "reason": "start_script_missing", "path": str(START_SCRIPT)}
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                flags = 0
                if os.name == "nt":
                    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                self._process = subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(START_SCRIPT)],
                    cwd=str(BASE_DIR),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    shell=False,
                )
        deadline = time.monotonic() + max(1, cfg["startup_timeout_seconds"])
        while time.monotonic() < deadline:
            health = self.probe(cfg)
            if health["reachable"]:
                return {**health, "started": True, "reason": "started"}
            if self._process is not None and self._process.poll() is not None:
                return {**health, "started": False, "reason": "process_exited", "returncode": self._process.returncode}
            time.sleep(0.25)
        return {**self.probe(cfg), "started": False, "reason": "startup_timeout"}

    def ensure_available(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        health = self.probe(overrides)
        if health["reachable"]:
            return health
        return self.start(overrides)


_SUPERVISOR = AletheiaSupervisor()


def get_aletheia_supervisor() -> AletheiaSupervisor:
    return _SUPERVISOR
