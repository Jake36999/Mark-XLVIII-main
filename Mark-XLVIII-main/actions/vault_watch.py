"""Debounced filesystem watcher for the canonical JARVIS vault index."""

from __future__ import annotations

import atexit
import threading
import time
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from core.process_events import emit_process_event


class _MarkdownEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: "VaultWatcher"):
        self.watcher = watcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        paths = [str(getattr(event, "src_path", "")), str(getattr(event, "dest_path", ""))]
        visible_paths = [
            path
            for path in paths
            if path and ".jarvis" not in {part.lower() for part in Path(path).parts}
        ]
        if any(path.lower().endswith((".md", ".canvas")) for path in visible_paths):
            event_type = str(getattr(event, "event_type", "modified") or "modified").lower()
            if event_type in {"created", "modified", "moved", "deleted"}:
                self.watcher.mark_event(
                    event_type,
                    src_path=paths[0],
                    dst_path=paths[1],
                )


class VaultWatcher:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = dict(cfg)
        self.root = Path(cfg["notes_root"]).resolve()
        self.debounce_seconds = float(cfg.get("rag_watch_debounce_seconds", 2.0))
        self._observer: Observer | None = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._dirty = threading.Event()
        self._lock = threading.Lock()
        self._last_event_at = 0.0
        self._last_index_at = ""
        self._last_result: dict[str, Any] = {}
        self._last_error = ""
        self._pending_events: list[dict[str, Any]] = []
        self._startup_pending = False

    def mark_dirty(self) -> None:
        with self._lock:
            self._last_event_at = time.monotonic()
            self._dirty.set()

    def mark_event(self, event_type: str, *, src_path: str = "", dst_path: str = "") -> None:
        with self._lock:
            self._pending_events.append(
                {
                    "event_type": str(event_type or "modified").lower(),
                    "src_path": src_path,
                    "dst_path": dst_path,
                }
            )
            self._last_event_at = time.monotonic()
            self._dirty.set()

    def _drain_events(self) -> list[dict[str, Any]]:
        with self._lock:
            raw = self._pending_events
            self._pending_events = []
        grouped: dict[str, dict[str, Any]] = {}
        for event in raw:
            key = str(event.get("dst_path") or event.get("src_path") or "").casefold()
            if not key:
                continue
            current = grouped.get(key)
            if current is None:
                grouped[key] = {**event, "coalesced_count": 1}
                continue
            current["coalesced_count"] = int(current.get("coalesced_count") or 1) + 1
            if event.get("src_path"):
                current.setdefault("src_path", event["src_path"])
            if event.get("dst_path"):
                current["dst_path"] = event["dst_path"]
            incoming = str(event.get("event_type") or "modified")
            if incoming == "deleted" or current.get("event_type") not in {"created", "moved"}:
                current["event_type"] = incoming
        return list(grouped.values())

    def _loop(self) -> None:
        while not self._stop.wait(0.25):
            if not self._dirty.is_set():
                continue
            if time.monotonic() - self._last_event_at < self.debounce_seconds:
                continue
            self._dirty.clear()
            self.scan_once()

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._observer and self._observer.is_alive():
                return self.status()
            self.root.mkdir(parents=True, exist_ok=True)
            self._stop.clear()
            self._observer = Observer()
            self._observer.schedule(_MarkdownEventHandler(self), str(self.root), recursive=True)
            self._observer.start()
            self._worker = threading.Thread(target=self._loop, name="jarvis-vault-index", daemon=True)
            self._worker.start()
            self._startup_pending = True
            self._last_event_at = 0.0
            self._dirty.set()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop.set()
            observer = self._observer
            if observer:
                observer.stop()
                observer.join(timeout=5)
            self._observer = None
            worker = self._worker
            if worker and worker.is_alive() and worker is not threading.current_thread():
                worker.join(timeout=5)
            self._worker = None
        return self.status()

    def scan_once(self) -> dict[str, Any]:
        try:
            emit_process_event(category="vault", source="vault_watcher", summary="Reconciling changed vault paths and derived indexes.", state="running")
            from actions.jarvis_memory import reindex_local, reindex_paths_local
            from core.vault_activity import (
                baseline_vault,
                mark_events_indexed,
                process_event_batch,
                startup_reconciliation,
            )

            events = self._drain_events()
            markdown_events = [
                event
                for event in events
                if str(event.get("dst_path") or event.get("src_path") or "").lower().endswith(".md")
            ]
            canvas_events = [
                event
                for event in events
                if str(event.get("dst_path") or event.get("src_path") or "").lower().endswith(".canvas")
            ]
            startup = self._startup_pending
            self._startup_pending = False
            if startup:
                activity = startup_reconciliation(self.root)
            elif markdown_events:
                activity = process_event_batch(self.root, markdown_events)
            else:
                baseline_vault(self.root)
                activity = {"ok": True, "event_ids": [], "changed_paths": [], "deleted_paths": []}

            if activity.get("changed_paths") or activity.get("deleted_paths"):
                result = reindex_paths_local(
                    activity.get("changed_paths") or [],
                    activity.get("deleted_paths") or [],
                    cfg=self.cfg,
                )
            else:
                result = reindex_local(self.cfg)
            from core.canvas_index import index_canvas, rebuild_canvas_index

            if startup:
                canvas_index = rebuild_canvas_index(self.root)
            else:
                canvas_paths: list[str] = []
                for event in canvas_events:
                    if event.get("src_path"):
                        canvas_paths.append(str(event["src_path"]))
                    if event.get("dst_path") and event.get("dst_path") != event.get("src_path"):
                        canvas_paths.append(str(event["dst_path"]))
                canvas_index = {
                    "ok": True,
                    "results": [
                        index_canvas(self.root, canvas_path)
                        for canvas_path in canvas_paths
                    ],
                }
            embedding = result.get("embedding") if isinstance(result.get("embedding"), dict) else {}
            mark_events_indexed(
                self.root,
                activity.get("event_ids") or [],
                embedding_state=str(embedding.get("status") or "unknown"),
                ok=bool(result.get("ok")),
            )
            self._last_result = result
            self._last_error = ""
            self._last_index_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            emit_process_event(
                category="vault",
                source="vault_watcher",
                summary=f"Vault reconciliation completed; {len(activity.get('event_ids') or [])} change event(s) recorded.",
                state="completed" if result.get("ok") else "degraded",
                severity="info" if result.get("ok") else "warning",
                detail={"canvas_event_count": len(canvas_events), "embedding_state": embedding.get("status")},
            )
            return {
                "ok": bool(result.get("ok")),
                "watcher": self.status(),
                "activity": activity,
                "reindex": result,
                "canvas_index": canvas_index,
            }
        except Exception as exc:
            self._last_error = str(exc)
            emit_process_event(category="vault", source="vault_watcher", summary=f"Vault reconciliation failed with {type(exc).__name__}.", state="failed", severity="error")
            return {"ok": False, "error": str(exc), "watcher": self.status()}

    def status(self) -> dict[str, Any]:
        running = bool(self._observer and self._observer.is_alive())
        return {
            "ok": True,
            "running": running,
            "root": str(self.root),
            "debounce_seconds": self.debounce_seconds,
            "pending_change": self._dirty.is_set(),
            "pending_event_count": len(self._pending_events),
            "last_index_at": self._last_index_at,
            "last_error": self._last_error,
            "last_index_summary": {
                key: self._last_result.get(key)
                for key in ("indexed_notes", "changed_notes", "unchanged_notes", "removed_notes")
                if key in self._last_result
            },
        }


_WATCHER: VaultWatcher | None = None
_WATCHER_LOCK = threading.Lock()


def get_vault_watcher(cfg: dict[str, Any]) -> VaultWatcher:
    global _WATCHER
    root = Path(cfg["notes_root"]).resolve()
    with _WATCHER_LOCK:
        if _WATCHER is None or _WATCHER.root != root:
            if _WATCHER is not None:
                _WATCHER.stop()
            _WATCHER = VaultWatcher(cfg)
        return _WATCHER


def start_configured_watcher() -> dict[str, Any]:
    from actions.jarvis_memory import resolve_config

    cfg = resolve_config()
    watcher = get_vault_watcher(cfg)
    return watcher.start() if cfg.get("rag_watch_enabled") else watcher.status()


@atexit.register
def _shutdown_watcher() -> None:
    if _WATCHER is not None:
        _WATCHER.stop()
