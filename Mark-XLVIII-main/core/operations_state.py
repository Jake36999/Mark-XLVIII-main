"""Read-only operational telemetry provider for the desktop UI."""

from __future__ import annotations

import socket
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from core.runtime_config import load_runtime_config


def _tcp_state(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _workflow_operations(vault_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    path = vault_root / ".jarvis" / "workflows.sqlite"
    if not path.exists():
        return []
    try:
        with closing(sqlite3.connect(path, timeout=1)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT run_id,status,updated_at,bundle_path FROM workflow_runs ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 50)),),
            ).fetchall()
            result = []
            for row in rows:
                counts = connection.execute(
                    "SELECT state,COUNT(*) AS count FROM workflow_items WHERE run_id=? GROUP BY state",
                    (row["run_id"],),
                ).fetchall()
                states = {str(item["state"]): int(item["count"]) for item in counts}
                total = sum(states.values())
                complete = sum(states.get(state, 0) for state in ("ACCEPTED", "COMPLETED"))
                result.append(
                    {
                        "id": str(row["run_id"]),
                        "title": str(row["run_id"]),
                        "state": str(row["status"] or "unknown").casefold(),
                        "progress": round(complete / total * 100) if total else 0,
                        "kind": "workflow",
                        "updated": str(row["updated_at"] or ""),
                        "detail": f"Bundle: {row['bundle_path']}\n\nItem states: {states}",
                        "requires_approval": str(row["status"] or "").upper() in {"PENDING_APPROVAL", "AWAITING_DECISION"},
                    }
                )
            return result
    except sqlite3.Error:
        return []


def collect_operational_state(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(load_runtime_config() if config is None else config)
    vault_root = Path(str(cfg.get("jarvis_notes_root") or r"F:\Mark-XLVIII-main\Jarvis_notes")).resolve()
    health: list[dict[str, Any]] = []

    try:
        from actions.model_lifecycle import status as model_status

        models = model_status(cfg, timeout=2)
        model_health = models.get("health") or {}
        cooling = int(model_health.get("cooling_down_count") or 0)
        detail = (
            f"Loaded: {models.get('loaded_count', 0)}; "
            f"active requests: {(models.get('active') or {}).get('count', 0)}"
        )
        if cooling:
            detail = f"{detail}; cooling down: {cooling}"
        state = "ready" if models.get("reachable") else "offline"
        if models.get("reachable") and cooling:
            state = "degraded"
        health.append({"id": "models", "label": "Models", "state": state, "detail": detail})
    except Exception as exc:
        health.append({"id": "models", "label": "Models", "state": "unknown", "detail": str(exc)[:180]})

    try:
        from actions.jarvis_memory import resolve_config
        from actions.vault_watch import get_vault_watcher
        from core.vault_activity import journal_status

        memory_cfg = resolve_config({"jarvis_notes_root": str(vault_root)})
        watcher = get_vault_watcher(memory_cfg).status()
        journal = journal_status(vault_root)
        vault_state = "ready" if watcher.get("running") and not watcher.get("last_error") else ("degraded" if watcher.get("last_error") else "stopped")
        health.append(
            {
                "id": "vault",
                "label": "Vault",
                "state": vault_state,
                "detail": f"Watcher: {watcher.get('running')}; pending edits: {journal.get('pending_external_count', 0)}; last index: {watcher.get('last_index_at') or 'not yet'}",
            }
        )
    except Exception as exc:
        health.append({"id": "vault", "label": "Vault", "state": "unknown", "detail": str(exc)[:180]})

    speech_enabled = bool(cfg.get("voice_enabled", True))
    health.append(
        {
            "id": "speech",
            "label": "Speech",
            "state": "configured" if speech_enabled else "disabled",
            "detail": f"STT: {cfg.get('stt_engine', 'unknown')}; TTS: {cfg.get('tts_engine', 'unknown')}. Live queue transitions appear in Process Trace.",
        }
    )
    mcp_online = _tcp_state(str(cfg.get("mcp_http_host") or "127.0.0.1"), int(cfg.get("mcp_http_port") or 8766))
    health.append({"id": "mcp", "label": "MCP", "state": "ready" if mcp_online else "optional-offline", "detail": "Standalone HTTP transport is reachable." if mcp_online else "In-process dispatcher remains available; standalone HTTP transport is offline."})
    aletheia_online = _tcp_state(str(cfg.get("aletheia_bridge_host") or "127.0.0.1"), int(cfg.get("aletheia_bridge_port") or 8765))
    health.append({"id": "aletheia", "label": "Aletheia", "state": "ready" if aletheia_online else "optional-offline", "detail": "External bridge reachable." if aletheia_online else "Optional external bridge is offline; MARK-native runtime remains available."})

    return {
        "ok": True,
        "health": health,
        "operations": _workflow_operations(vault_root),
        "vault_root": str(vault_root),
    }
