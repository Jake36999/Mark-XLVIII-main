"""Derived cross-Canvas relationship index stored beside local RAG data."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.canvas_document import CanvasValidationError, content_revision, load_document
from core.vault_activity import database_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _connect(vault_root: str | Path) -> sqlite3.Connection:
    path = database_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS canvas_files (
            path TEXT PRIMARY KEY,
            revision TEXT NOT NULL,
            title TEXT,
            view_kind TEXT,
            project_id TEXT,
            source_refs_json TEXT NOT NULL,
            node_count INTEGER NOT NULL,
            edge_count INTEGER NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            superseded_by TEXT,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS canvas_nodes (
            canvas_path TEXT NOT NULL,
            node_id TEXT NOT NULL,
            node_type TEXT NOT NULL,
            canonical_ref TEXT,
            task_id TEXT,
            project_id TEXT,
            managed INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(canvas_path,node_id)
        );
        CREATE INDEX IF NOT EXISTS idx_canvas_nodes_ref ON canvas_nodes(canonical_ref);
        CREATE INDEX IF NOT EXISTS idx_canvas_nodes_task ON canvas_nodes(task_id);
        CREATE TABLE IF NOT EXISTS canvas_edges (
            canvas_path TEXT NOT NULL,
            edge_id TEXT NOT NULL,
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            relation TEXT,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(canvas_path,edge_id)
        );
        CREATE TABLE IF NOT EXISTS canvas_references (
            canvas_path TEXT NOT NULL,
            reference_type TEXT NOT NULL,
            reference_id TEXT NOT NULL,
            source_node_id TEXT,
            PRIMARY KEY(canvas_path,reference_type,reference_id,source_node_id)
        );
        """
    )
    connection.commit()
    return connection


def _canvas_meta(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    extension = payload.get("jarvis") if isinstance(payload.get("jarvis"), dict) else {}
    return {
        "title": str(extension.get("title") or path.stem),
        "view_kind": str(extension.get("view_kind") or "canvas"),
        "project_id": str(extension.get("project_id") or ""),
        "superseded_by": str(extension.get("superseded_by") or ""),
        "stale": bool(extension.get("stale")),
    }


def index_canvas(vault_root: str | Path, path: str | Path) -> dict[str, Any]:
    root = Path(vault_root).resolve()
    target = Path(path).resolve()
    relative_path = target.relative_to(root)
    if ".jarvis" in {part.lower() for part in relative_path.parts}:
        return {"ok": True, "ignored": True, "reason": "derived_vault_path"}
    relative = str(relative_path).replace("\\", "/")
    if not target.exists():
        with closing(_connect(root)) as connection, connection:
            connection.execute("DELETE FROM canvas_files WHERE path=?", (relative,))
            connection.execute("DELETE FROM canvas_nodes WHERE canvas_path=?", (relative,))
            connection.execute("DELETE FROM canvas_edges WHERE canvas_path=?", (relative,))
            connection.execute("DELETE FROM canvas_references WHERE canvas_path=?", (relative,))
        return {"ok": True, "path": relative, "deleted": True}
    try:
        payload = load_document(target)
    except CanvasValidationError as exc:
        return {"ok": False, "path": relative, "diagnostics": exc.diagnostics, "source_preserved": True}
    meta = _canvas_meta(payload, target)
    source_refs: list[str] = []
    with closing(_connect(root)) as connection, connection:
        connection.execute("DELETE FROM canvas_nodes WHERE canvas_path=?", (relative,))
        connection.execute("DELETE FROM canvas_edges WHERE canvas_path=?", (relative,))
        connection.execute("DELETE FROM canvas_references WHERE canvas_path=?", (relative,))
        for node in payload.get("nodes", []):
            managed = node.get("jarvis") if isinstance(node.get("jarvis"), dict) else {}
            canonical_ref = str(node.get("file") or managed.get("source_path") or "")
            task_id = str(managed.get("task_id") or "")
            project_id = str(managed.get("project_id") or meta["project_id"] or "")
            connection.execute(
                "INSERT INTO canvas_nodes VALUES(?,?,?,?,?,?,?,?)",
                (
                    relative,
                    str(node.get("id")),
                    str(node.get("type") or "unknown"),
                    canonical_ref,
                    task_id,
                    project_id,
                    int(str(node.get("id") or "").startswith("jarvis-")),
                    json.dumps(node, ensure_ascii=False, sort_keys=True),
                ),
            )
            for ref_type, ref_value in (("note", canonical_ref), ("task", task_id), ("project", project_id)):
                if ref_value:
                    connection.execute(
                        "INSERT OR IGNORE INTO canvas_references VALUES(?,?,?,?)",
                        (relative, ref_type, ref_value, str(node.get("id"))),
                    )
                    if ref_type == "note":
                        source_refs.append(ref_value)
        for edge in payload.get("edges", []):
            connection.execute(
                "INSERT INTO canvas_edges VALUES(?,?,?,?,?,?)",
                (
                    relative,
                    str(edge.get("id")),
                    str(edge.get("fromNode")),
                    str(edge.get("toNode")),
                    str(edge.get("label") or edge.get("relation") or "related"),
                    json.dumps(edge, ensure_ascii=False, sort_keys=True),
                ),
            )
        connection.execute(
            """
            INSERT OR REPLACE INTO canvas_files
            (path,revision,title,view_kind,project_id,source_refs_json,node_count,edge_count,stale,superseded_by,indexed_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                relative,
                content_revision(target),
                meta["title"],
                meta["view_kind"],
                meta["project_id"],
                json.dumps(sorted(set(source_refs))),
                len(payload.get("nodes", [])),
                len(payload.get("edges", [])),
                int(meta["stale"]),
                meta["superseded_by"],
                _now(),
            ),
        )
    return {"ok": True, "path": relative, "node_count": len(payload.get("nodes", [])), "edge_count": len(payload.get("edges", [])), "revision": content_revision(target)}


def rebuild_canvas_index(vault_root: str | Path) -> dict[str, Any]:
    root = Path(vault_root).resolve()
    paths = sorted(path for path in root.rglob("*.canvas") if ".jarvis" not in path.relative_to(root).parts)
    results = [index_canvas(root, path) for path in paths]
    existing = {str(path.relative_to(root)).replace("\\", "/") for path in paths}
    with closing(_connect(root)) as connection, connection:
        stale = [str(row[0]) for row in connection.execute("SELECT path FROM canvas_files").fetchall() if str(row[0]) not in existing]
        for path in stale:
            connection.execute("DELETE FROM canvas_files WHERE path=?", (path,))
            connection.execute("DELETE FROM canvas_nodes WHERE canvas_path=?", (path,))
            connection.execute("DELETE FROM canvas_edges WHERE canvas_path=?", (path,))
            connection.execute("DELETE FROM canvas_references WHERE canvas_path=?", (path,))
    return {"ok": all(item.get("ok") for item in results), "canvas_count": len(paths), "results": results, "removed": stale}


def relationships(vault_root: str | Path, canvas_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(vault_root).resolve()
    relative = ""
    if canvas_path:
        target = Path(canvas_path)
        if not target.is_absolute():
            target = root / target
        relative = str(target.resolve().relative_to(root)).replace("\\", "/")
    with closing(_connect(root)) as connection, connection:
        if relative:
            references = [dict(row) for row in connection.execute("SELECT * FROM canvas_references WHERE canvas_path=? ORDER BY reference_type,reference_id", (relative,)).fetchall()]
            shared = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT other.canvas_path,other.reference_type,other.reference_id,file.title,file.view_kind,file.stale,file.superseded_by
                    FROM canvas_references own
                    JOIN canvas_references other ON other.reference_type=own.reference_type AND other.reference_id=own.reference_id AND other.canvas_path<>own.canvas_path
                    LEFT JOIN canvas_files file ON file.path=other.canvas_path
                    WHERE own.canvas_path=?
                    ORDER BY other.canvas_path,other.reference_type,other.reference_id
                    """,
                    (relative,),
                ).fetchall()
            ]
            record = connection.execute("SELECT * FROM canvas_files WHERE path=?", (relative,)).fetchone()
            return {"ok": record is not None, "canvas": dict(record) if record else None, "references": references, "related_canvases": shared}
        files = [dict(row) for row in connection.execute("SELECT * FROM canvas_files ORDER BY path").fetchall()]
    return {"ok": True, "canvases": files}
