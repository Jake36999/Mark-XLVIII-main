from __future__ import annotations

import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
DEFAULT_NOTES_ROOT = Path(r"F:\Mark-XLVIII-main\Jarvis_notes")
DEFAULT_REMEMBER_API_URL = "http://127.0.0.1:8010"
DEFAULT_PROJECT_ID = "jarvis_notes"
DEFAULT_PROJECT_NAME = "Jarvis Notes"
LOCAL_INDEX_VERSION = 1

FRONTMATTER_FIELDS = (
    "id",
    "title",
    "type",
    "status",
    "created",
    "updated",
    "project_id",
    "source",
    "tags",
    "sync_state",
    "index_state",
    "remember_note_id",
)

TEMPLATES: dict[str, dict[str, Any]] = {
    "memory": {
        "folder": "Memories",
        "intent_type": "important_info",
        "sections": ("Summary", "Details", "Links"),
    },
    "report": {
        "folder": "Reports",
        "intent_type": "thought",
        "sections": ("Summary", "Findings", "Actions", "Sources"),
    },
    "deep_research_report": {
        "folder": "Deep Research",
        "intent_type": "thought",
        "sections": (
            "Executive Summary",
            "Research Question",
            "Key Findings",
            "Evidence",
            "Open Questions",
            "Sources",
        ),
    },
    "log": {
        "folder": "Logs",
        "intent_type": "thought",
        "sections": ("Context", "Events", "Outcome", "Next Steps"),
    },
    "progress_tracker": {
        "folder": "Progress",
        "intent_type": "next_steps",
        "sections": ("Objective", "Current State", "Done", "Next", "Blockers"),
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_file_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def resolve_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = _load_file_config()
    if overrides:
        raw.update({k: v for k, v in overrides.items() if v is not None})
    notes_root = Path(str(raw.get("jarvis_notes_root") or DEFAULT_NOTES_ROOT))
    return {
        "notes_root": notes_root,
        "remember_api_url": str(raw.get("remember_api_url") or DEFAULT_REMEMBER_API_URL).rstrip("/"),
        "remember_project_id": str(raw.get("remember_project_id") or DEFAULT_PROJECT_ID),
        "remember_project_name": str(raw.get("remember_project_name") or DEFAULT_PROJECT_NAME),
        "remember_project_root": str(raw.get("remember_project_root") or notes_root.parent),
        "remember_enabled": bool(raw.get("remember_enabled", False)),
        "remember_api_token": str(raw.get("remember_api_token") or ""),
        "remember_auth_header": str(raw.get("remember_auth_header") or "Authorization"),
    }


def _slug(text: str, fallback: str = "note") -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return (text or fallback)[:80].strip("-") or fallback


def _stable_memory_id(category: str, key: str) -> str:
    return f"memory-{_slug(category, 'notes')}-{_slug(key, 'item')}"


def _coerce_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = re.split(r"[,#]", tags)
    if not isinstance(tags, (list, tuple, set)):
        return []
    result = []
    seen = set()
    for tag in tags:
        clean = _slug(str(tag), "")
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _format_frontmatter_value(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def render_frontmatter(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for field in FRONTMATTER_FIELDS:
        if field in metadata:
            lines.append(f"{field}: {_format_frontmatter_value(metadata.get(field))}")
    for field in sorted(k for k in metadata if k not in FRONTMATTER_FIELDS):
        lines.append(f"{field}: {_format_frontmatter_value(metadata.get(field))}")
    lines.append("---")
    return "\n".join(lines)


def parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    text = markdown.lstrip("\ufeff")
    if not text.startswith("---\n"):
        return {}, markdown
    end = text.find("\n---", 4)
    if end < 0:
        return {}, markdown
    raw = text[4:end].strip()
    body = text[end + 4 :].lstrip("\r\n")
    metadata: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            metadata[key] = json.loads(value)
        except Exception:
            metadata[key] = value.strip('"').strip("'")
    return metadata, body


def read_note(path: Path) -> tuple[dict[str, Any], str, str]:
    markdown = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(markdown)
    return metadata, body, markdown


def iter_note_paths(cfg: dict[str, Any] | None = None) -> list[Path]:
    cfg = cfg or resolve_config()
    root = Path(cfg["notes_root"])
    if not root.exists():
        return []
    paths = []
    for path in root.rglob("*.md"):
        if any(part in {".obsidian", ".jarvis"} for part in path.parts):
            continue
        paths.append(path)
    return sorted(paths)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _template_body(note_type: str, title: str, content: str) -> str:
    sections = TEMPLATES[note_type]["sections"]
    lines = [f"# {title}", ""]
    first_section = True
    for section in sections:
        lines.append(f"## {section}")
        if first_section and content:
            lines.append("")
            lines.append(content.strip())
        else:
            lines.append("")
        lines.append("")
        first_section = False
    return "\n".join(lines).rstrip() + "\n"


def _note_path(cfg: dict[str, Any], note_type: str, title: str, metadata: dict[str, Any]) -> Path:
    folder = TEMPLATES[note_type]["folder"]
    created = str(metadata.get("created") or _now())[:10]
    name = f"{created}-{_slug(title)}.md"
    return Path(cfg["notes_root"]) / folder / name


def create_note(
    *,
    note_type: str,
    title: str,
    content: str = "",
    tags: Any = None,
    status: str = "draft",
    source: str = "user",
    cfg: dict[str, Any] | None = None,
    sync: bool = True,
    note_id: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    note_type = (note_type or "memory").strip().lower()
    if note_type not in TEMPLATES:
        note_type = "memory"
    title = (title or "Untitled").strip()
    timestamp = _now()
    metadata = {
        "id": note_id or f"jarvis-{timestamp.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}",
        "title": title,
        "type": note_type,
        "status": status or "draft",
        "created": timestamp,
        "updated": timestamp,
        "project_id": cfg["remember_project_id"],
        "source": source or "user",
        "tags": _coerce_tags(tags),
        "sync_state": "backend_pending" if cfg.get("remember_enabled") else "local_only",
        "index_state": "index_pending",
        "remember_note_id": "",
    }
    target = path or _note_path(cfg, note_type, title, metadata)
    body = _template_body(note_type, title, content or "")
    atomic_write(target, f"{render_frontmatter(metadata)}\n\n{body}")
    result = {
        "ok": True,
        "local_written": True,
        "path": str(target),
        "metadata": metadata,
        "sync": None,
    }
    if sync:
        result["sync"] = sync_note(target, cfg=cfg)
        result["metadata"] = read_note(target)[0]
    return result


def update_note_frontmatter(path: Path, updates: dict[str, Any]) -> dict[str, Any]:
    metadata, body, _ = read_note(path)
    metadata.update(updates)
    metadata["updated"] = _now()
    atomic_write(path, f"{render_frontmatter(metadata)}\n\n{body.rstrip()}\n")
    return metadata


def _headers(cfg: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = cfg.get("remember_api_token")
    if token:
        header = str(cfg.get("remember_auth_header") or "Authorization")
        headers[header] = str(token) if header.lower() != "authorization" else f"Bearer {token}"
    return headers


def build_project_register_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    timestamp = _now()
    root = str(cfg["notes_root"])
    return {
        "project_id": cfg["remember_project_id"],
        "project_name": cfg["remember_project_name"],
        "project_root": cfg["remember_project_root"],
        "notes_root": root,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def build_remember_payload(path: Path, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    metadata, _, markdown = read_note(path)
    note_type = str(metadata.get("type") or "memory")
    template = TEMPLATES.get(note_type, TEMPLATES["memory"])
    status = str(metadata.get("status") or "draft")
    if status not in {"draft", "synced", "reviewed", "archived"}:
        status = "draft"
    source = str(metadata.get("source") or "user")
    if source not in {"user", "daemon", "ral_suggestion", "snapshot"}:
        source = "user"
    return {
        "markdown": markdown,
        "schema_version": 1,
        "id": str(metadata.get("id") or path.stem),
        "project_id": cfg["remember_project_id"],
        "project_name": cfg["remember_project_name"],
        "project_root": cfg["remember_project_root"],
        "notes_root": str(cfg["notes_root"]),
        "created_at": str(metadata.get("created") or _now()),
        "updated_at": str(metadata.get("updated") or _now()),
        "intent_type": template["intent_type"],
        "source": source,
        "status": status,
        "sync_state": str(metadata.get("sync_state") or "backend_pending"),
        "index_state": str(metadata.get("index_state") or "index_pending"),
        "queryable_state": str(metadata.get("index_state") or "index_pending"),
        "confidence": 0.8,
        "tags": _coerce_tags(metadata.get("tags")),
        "linked_entities": [],
        "trace": {"source_path": str(path)},
        "retrieval": {},
    }


def _summarize_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:1000]


def sync_note(path: Path, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not cfg.get("remember_enabled"):
        metadata = update_note_frontmatter(
            path,
            {"sync_state": "local_only", "index_state": "index_pending", "sync_error": ""},
        )
        return {"ok": True, "skipped": True, "reason": "remember_me_disabled", "path": str(path), "metadata": metadata}
    api = cfg["remember_api_url"]
    headers = _headers(cfg)
    try:
        project_response = requests.post(
            f"{api}/remember/projects/register",
            json=build_project_register_payload(cfg),
            headers=headers,
            timeout=8,
        )
        project_response.raise_for_status()
        ingest_response = requests.post(
            f"{api}/remember/notes/ingest",
            json=build_remember_payload(path, cfg),
            headers=headers,
            timeout=20,
        )
        ingest_response.raise_for_status()
        payload = _summarize_response(ingest_response)
        remember_note_id = ""
        if isinstance(payload, dict):
            remember_note_id = str(payload.get("note_id") or payload.get("id") or payload.get("source_id") or "")
        metadata = update_note_frontmatter(
            path,
            {
                "status": "synced",
                "sync_state": "backend_synced",
                "index_state": "index_pending",
                "remember_note_id": remember_note_id,
                "sync_error": "",
            },
        )
        return {"ok": True, "path": str(path), "metadata": metadata, "response": payload}
    except requests.exceptions.RequestException as exc:
        state = "backend_pending"
        if getattr(exc, "response", None) is not None:
            state = "backend_failed"
        metadata = update_note_frontmatter(
            path,
            {"sync_state": state, "index_state": "index_pending", "sync_error": str(exc)[:500]},
        )
        return {"ok": False, "path": str(path), "metadata": metadata, "error": str(exc)}


def find_pending_notes(cfg: dict[str, Any] | None = None) -> list[Path]:
    cfg = cfg or resolve_config()
    root = Path(cfg["notes_root"])
    if not root.exists():
        return []
    pending = []
    for path in root.rglob("*.md"):
        if any(part in {".obsidian", ".jarvis"} for part in path.parts):
            continue
        try:
            metadata, _, _ = read_note(path)
        except Exception:
            continue
        sync_state = str(metadata.get("sync_state") or "")
        remember_note_id = str(metadata.get("remember_note_id") or "")
        if sync_state in {"", "backend_pending", "backend_failed"} or not remember_note_id:
            pending.append(path)
    return pending


def sync_pending(cfg: dict[str, Any] | None = None, limit: int | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not cfg.get("remember_enabled"):
        return {"ok": True, "skipped": True, "reason": "remember_me_disabled", "count": 0, "synced": 0, "failed": 0, "results": []}
    notes = find_pending_notes(cfg)
    if limit:
        notes = notes[: max(0, int(limit))]
    results = [sync_note(path, cfg=cfg) for path in notes]
    return {
        "ok": all(item.get("ok") for item in results) if results else True,
        "count": len(results),
        "synced": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "results": results,
    }


def health(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    root = Path(cfg["notes_root"])
    root.mkdir(parents=True, exist_ok=True)
    state: Any = None
    backend_available = False
    error = ""
    if cfg.get("remember_enabled"):
        try:
            response = requests.get(f"{cfg['remember_api_url']}/remember/debug/state", headers=_headers(cfg), timeout=5)
            response.raise_for_status()
            state = _summarize_response(response)
            backend_available = True
        except requests.exceptions.RequestException as exc:
            error = str(exc)
    else:
        error = "Remember Me backend disabled; using local Mark-native index."
    return {
        "ok": True,
        "notes_root": str(root),
        "templates": sorted(TEMPLATES.keys()),
        "backend_available": backend_available,
        "backend_enabled": bool(cfg.get("remember_enabled")),
        "remember_api_url": cfg["remember_api_url"],
        "remember_project_id": cfg["remember_project_id"],
        "backend_state": state,
        "error": error,
    }


def _local_search(query: str, cfg: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    root = Path(cfg["notes_root"])
    terms = [term for term in re.split(r"\W+", query.lower()) if len(term) > 2]
    results = []
    if not root.exists() or not terms:
        return results
    for path in root.rglob("*.md"):
        if ".obsidian" in path.parts:
            continue
        try:
            metadata, body, _ = read_note(path)
        except Exception:
            continue
        haystack = f"{metadata.get('title', '')}\n{body}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            snippet = re.sub(r"\s+", " ", body).strip()[:500]
            results.append(
                {
                    "title": metadata.get("title") or path.stem,
                    "path": str(path),
                    "score": score,
                    "content": snippet,
                    "retrieval_method": "local_lexical_fallback",
                }
            )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def local_index_path(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or resolve_config()
    return Path(cfg["notes_root"]) / ".jarvis" / "memory.sqlite"


def _connect_index(cfg: dict[str, Any] | None = None) -> sqlite3.Connection:
    path = local_index_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            type TEXT,
            status TEXT,
            created TEXT,
            updated TEXT,
            project_id TEXT,
            source TEXT,
            tags TEXT,
            body TEXT,
            headings TEXT,
            wikilinks TEXT,
            tasks TEXT,
            mtime REAL
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            note_id UNINDEXED,
            title,
            body,
            tags,
            path UNINDEXED
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
        (str(LOCAL_INDEX_VERSION),),
    )
    return conn


def _extract_headings(body: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"(?m)^#{1,6}\s+(.+)$", body or "")]


def _extract_wikilinks(body: str) -> list[str]:
    links = []
    seen = set()
    for match in re.finditer(r"\[\[([^\]|#]+)", body or ""):
        link = match.group(1).strip()
        if link and link.lower() not in seen:
            seen.add(link.lower())
            links.append(link)
    return links


def _extract_tasks(body: str) -> list[dict[str, Any]]:
    tasks = []
    for line_no, line in enumerate((body or "").splitlines(), start=1):
        match = re.match(r"\s*[-*]\s+\[([ xX])\]\s+(.+)", line)
        if not match:
            continue
        done = match.group(1).lower() == "x"
        tasks.append({"line": line_no, "done": done, "text": match.group(2).strip()})
    return tasks


def _note_record(path: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    metadata, body, _ = read_note(path)
    headings = _extract_headings(body)
    title = str(metadata.get("title") or (headings[0] if headings else path.stem))
    note_id = str(metadata.get("id") or path.stem)
    tags = _coerce_tags(metadata.get("tags"))
    wikilinks = _extract_wikilinks(body)
    tasks = _extract_tasks(body)
    return {
        "id": note_id,
        "path": str(path),
        "title": title,
        "type": str(metadata.get("type") or ""),
        "status": str(metadata.get("status") or ""),
        "created": str(metadata.get("created") or ""),
        "updated": str(metadata.get("updated") or ""),
        "project_id": str(metadata.get("project_id") or cfg["remember_project_id"]),
        "source": str(metadata.get("source") or ""),
        "tags": tags,
        "body": body,
        "headings": headings,
        "wikilinks": wikilinks,
        "tasks": tasks,
        "mtime": path.stat().st_mtime,
    }


def reindex_local(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    root = Path(cfg["notes_root"])
    root.mkdir(parents=True, exist_ok=True)
    paths = iter_note_paths(cfg)
    conn = _connect_index(cfg)
    try:
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM notes_fts")
        for path in paths:
            try:
                record = _note_record(path, cfg)
            except Exception:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO notes(
                    id, path, title, type, status, created, updated, project_id,
                    source, tags, body, headings, wikilinks, tasks, mtime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["path"],
                    record["title"],
                    record["type"],
                    record["status"],
                    record["created"],
                    record["updated"],
                    record["project_id"],
                    record["source"],
                    json.dumps(record["tags"], ensure_ascii=False),
                    record["body"],
                    json.dumps(record["headings"], ensure_ascii=False),
                    json.dumps(record["wikilinks"], ensure_ascii=False),
                    json.dumps(record["tasks"], ensure_ascii=False),
                    record["mtime"],
                ),
            )
            conn.execute(
                "INSERT INTO notes_fts(note_id, title, body, tags, path) VALUES (?, ?, ?, ?, ?)",
                (
                    record["id"],
                    record["title"],
                    record["body"],
                    " ".join(record["tags"]),
                    record["path"],
                ),
            )
        conn.commit()
        for path in paths:
            try:
                update_note_frontmatter(path, {"index_state": "indexed_local"})
            except Exception:
                pass
        return {"ok": True, "backend": "local_sqlite", "index_path": str(local_index_path(cfg)), "indexed_notes": len(paths)}
    finally:
        conn.close()


def _fts_query(query: str) -> str:
    terms = [term for term in re.split(r"[^a-zA-Z0-9_]+", query or "") if len(term) > 1]
    return " OR ".join(f"{term}*" for term in terms)


def _row_to_result(row: sqlite3.Row, score: float, method: str) -> dict[str, Any]:
    body = row["body"] or ""
    snippet = re.sub(r"\s+", " ", body).strip()[:600]
    return {
        "source_id": row["id"],
        "title": row["title"],
        "path": row["path"],
        "type": row["type"],
        "status": row["status"],
        "tags": json.loads(row["tags"] or "[]"),
        "content": snippet,
        "score": score,
        "retrieval_method": method,
        "citation": f"[note:{row['id']}]",
    }


def query_local(query: str, cfg: dict[str, Any] | None = None, limit: int = 5) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not local_index_path(cfg).exists():
        reindex_local(cfg)
    conn = _connect_index(cfg)
    try:
        fts = _fts_query(query)
        rows = []
        if fts:
            try:
                rows = conn.execute(
                    """
                    SELECT n.*, bm25(notes_fts) AS rank
                    FROM notes_fts
                    JOIN notes n ON n.id = notes_fts.note_id
                    WHERE notes_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                    """,
                    (fts, int(limit)),
                ).fetchall()
            except sqlite3.Error:
                rows = []
        results = []
        for row in rows:
            rank = float(row["rank"] or 0.0)
            results.append(_row_to_result(row, 1.0 / (1.0 + abs(rank)), "local_fts"))
        if not results:
            for item in _local_search(query, cfg, limit):
                item["citation"] = f"[path:{item['path']}]"
                results.append(item)
        return {"ok": True, "backend": "local_sqlite", "query": query, "results": results[:limit]}
    finally:
        conn.close()


def graph_local(cfg: dict[str, Any] | None = None, limit: int = 250) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not local_index_path(cfg).exists():
        reindex_local(cfg)
    conn = _connect_index(cfg)
    try:
        rows = conn.execute("SELECT * FROM notes ORDER BY updated DESC, mtime DESC LIMIT ?", (int(limit),)).fetchall()
        title_to_id = {_slug(row["title"], row["id"]): row["id"] for row in rows}
        nodes = []
        edges = []
        seen_nodes = set()
        for row in rows:
            note_id = row["id"]
            nodes.append({"id": note_id, "type": "note", "label": row["title"], "path": row["path"], "note_type": row["type"]})
            seen_nodes.add(note_id)
            project_id = row["project_id"] or cfg["remember_project_id"]
            project_node = f"project:{project_id}"
            if project_node not in seen_nodes:
                seen_nodes.add(project_node)
                nodes.append({"id": project_node, "type": "project", "label": project_id})
            edges.append({"source": project_node, "target": note_id, "type": "contains"})
            for tag in json.loads(row["tags"] or "[]"):
                tag_node = f"tag:{tag}"
                if tag_node not in seen_nodes:
                    seen_nodes.add(tag_node)
                    nodes.append({"id": tag_node, "type": "tag", "label": tag})
                edges.append({"source": note_id, "target": tag_node, "type": "has_tag"})
            for link in json.loads(row["wikilinks"] or "[]"):
                target = title_to_id.get(_slug(link, ""))
                if target:
                    edges.append({"source": note_id, "target": target, "type": "wikilink"})
                else:
                    link_node = f"missing:{_slug(link, 'link')}"
                    if link_node not in seen_nodes:
                        seen_nodes.add(link_node)
                        nodes.append({"id": link_node, "type": "missing_note", "label": link})
                    edges.append({"source": note_id, "target": link_node, "type": "wikilink_missing"})
        return {"ok": True, "backend": "local_sqlite", "nodes": nodes, "edges": edges}
    finally:
        conn.close()


def tasks_local(cfg: dict[str, Any] | None = None, include_done: bool = True) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not local_index_path(cfg).exists():
        reindex_local(cfg)
    conn = _connect_index(cfg)
    try:
        rows = conn.execute("SELECT * FROM notes ORDER BY updated DESC, mtime DESC").fetchall()
        tasks = []
        for row in rows:
            for task in json.loads(row["tasks"] or "[]"):
                if task.get("done") and not include_done:
                    continue
                tasks.append(
                    {
                        "note_id": row["id"],
                        "title": row["title"],
                        "path": row["path"],
                        "line": task.get("line"),
                        "done": bool(task.get("done")),
                        "text": task.get("text", ""),
                        "citation": f"[note:{row['id']}:L{task.get('line')}]",
                    }
                )
        return {"ok": True, "backend": "local_sqlite", "tasks": tasks}
    finally:
        conn.close()


def dag_candidates(cfg: dict[str, Any] | None = None, write: bool = False) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    task_result = tasks_local(cfg, include_done=False)
    candidates = []
    for index, task in enumerate(task_result.get("tasks", []), start=1):
        workflow_id = f"dag-{_slug(task['title'], 'note')}-{index}"
        candidate = {
            "workflow_id": workflow_id,
            "title": task["text"],
            "status": "review_pending",
            "source_note_id": task["note_id"],
            "source_path": task["path"],
            "nodes": [
                {
                    "id": "task",
                    "kind": "action",
                    "title": task["text"],
                    "epistemic_provenance": {"source": task["citation"]},
                }
            ],
        }
        candidates.append(candidate)
    output_path = ""
    if write and candidates:
        out_dir = Path(cfg["notes_root"]) / ".jarvis" / "dag_candidates"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"candidates-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        atomic_write(Path(output_path), json.dumps(candidates, ensure_ascii=False, indent=2))
    return {"ok": True, "backend": "local_sqlite", "count": len(candidates), "candidates": candidates, "output_path": output_path}


def export_training_candidates(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not local_index_path(cfg).exists():
        reindex_local(cfg)
    conn = _connect_index(cfg)
    out_path = Path(cfg["notes_root"]) / ".jarvis" / "training_candidates.jsonl"
    count = 0
    try:
        rows = conn.execute("SELECT * FROM notes ORDER BY updated DESC, mtime DESC").fetchall()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                tags = json.loads(row["tags"] or "[]")
                if row["status"] != "reviewed" and "reviewed" not in tags and "training" not in tags:
                    continue
                payload = {
                    "id": row["id"],
                    "title": row["title"],
                    "type": row["type"],
                    "tags": tags,
                    "text": row["body"],
                    "source_path": row["path"],
                }
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                count += 1
        return {"ok": True, "backend": "local_sqlite", "output_path": str(out_path), "count": count}
    finally:
        conn.close()


def query_memory(
    query: str,
    *,
    cfg: dict[str, Any] | None = None,
    scope: str = "project",
    limit: int = 5,
) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not cfg.get("remember_enabled"):
        return query_local(query, cfg=cfg, limit=limit)
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "query is required", "results": []}
    endpoint = "/remember/query/global" if scope == "global" else "/remember/query/project"
    payload = {"query": query, "limit": limit}
    if endpoint.endswith("/project"):
        payload["project_id"] = cfg["remember_project_id"]
    try:
        response = requests.post(
            f"{cfg['remember_api_url']}{endpoint}",
            json=payload,
            headers=_headers(cfg),
            timeout=20,
        )
        response.raise_for_status()
        data = _summarize_response(response)
        return {"ok": True, "backend": "remember_me", "endpoint": endpoint, "response": data}
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "backend": "local_fallback",
            "error": str(exc),
            "results": _local_search(query, cfg, limit),
        }


def reindex_project(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or resolve_config()
    if not cfg.get("remember_enabled"):
        return reindex_local(cfg)
    try:
        response = requests.post(
            f"{cfg['remember_api_url']}/remember/semantic/reindex/project/{cfg['remember_project_id']}",
            headers=_headers(cfg),
            timeout=120,
        )
        response.raise_for_status()
        updated = 0
        for path in Path(cfg["notes_root"]).rglob("*.md"):
            if any(part in {".obsidian", ".jarvis"} for part in path.parts):
                continue
            try:
                metadata, _, _ = read_note(path)
            except Exception:
                continue
            if metadata.get("project_id") != cfg["remember_project_id"]:
                continue
            if metadata.get("sync_state") == "backend_synced":
                update_note_frontmatter(path, {"index_state": "indexed"})
                updated += 1
        return {"ok": True, "updated_notes": updated, "response": _summarize_response(response)}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": str(exc)}


def list_templates() -> dict[str, Any]:
    return {
        "ok": True,
        "templates": {
            name: {"folder": template["folder"], "sections": list(template["sections"])}
            for name, template in TEMPLATES.items()
        },
    }


def mirror_memory_update(memory_update: dict[str, Any], cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not isinstance(memory_update, dict):
        return []
    cfg = cfg or resolve_config()
    results = []
    for category, items in memory_update.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value is None:
                continue
            note_id = _stable_memory_id(str(category), str(key))
            title = f"{str(category).replace('_', ' ').title()}: {str(key).replace('_', ' ').title()}"
            content = str(value)
            target = Path(cfg["notes_root"]) / "Memories" / _slug(str(category), "notes") / f"{_slug(str(key), 'memory')}.md"
            if target.exists():
                metadata, _, _ = read_note(target)
                timestamp = _now()
                metadata.update(
                    {
                        "id": metadata.get("id") or note_id,
                        "title": title,
                        "type": "memory",
                        "status": "draft",
                        "updated": timestamp,
                        "project_id": cfg["remember_project_id"],
                        "source": "daemon",
                        "tags": sorted(set(_coerce_tags(metadata.get("tags")) + ["memory", str(category)])),
                        "sync_state": "backend_pending" if cfg.get("remember_enabled") else "local_only",
                        "index_state": "index_pending",
                    }
                )
                body = _template_body("memory", title, content)
                atomic_write(target, f"{render_frontmatter(metadata)}\n\n{body}")
                result = {"ok": True, "local_written": True, "path": str(target), "metadata": metadata}
                result["sync"] = sync_note(target, cfg=cfg)
            else:
                result = create_note(
                    note_type="memory",
                    title=title,
                    content=content,
                    tags=["memory", str(category)],
                    source="daemon",
                    cfg=cfg,
                    note_id=note_id,
                    path=target,
                    sync=True,
                )
            results.append(result)
    return results


def jarvis_memory(
    parameters: dict[str, Any] | None = None,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = dict(parameters or {})
    cfg = resolve_config(params.pop("_config", None))
    operation = str(params.get("operation") or "health").strip().lower()
    try:
        if operation == "health":
            result = health(cfg)
        elif operation == "create_note":
            result = create_note(
                note_type=str(params.get("note_type") or params.get("type") or "memory"),
                title=str(params.get("title") or "Untitled"),
                content=str(params.get("content") or params.get("body") or ""),
                tags=params.get("tags"),
                status=str(params.get("status") or "draft"),
                source=str(params.get("source") or "user"),
                cfg=cfg,
                sync=bool(params.get("sync", True)),
            )
        elif operation == "sync_pending":
            result = sync_pending(cfg, limit=params.get("limit"))
        elif operation == "query":
            result = query_memory(
                str(params.get("query") or params.get("content") or ""),
                cfg=cfg,
                scope=str(params.get("scope") or "project").strip().lower(),
                limit=int(params.get("limit") or 5),
            )
        elif operation == "reindex_local":
            result = reindex_local(cfg)
        elif operation == "query_local":
            result = query_local(
                str(params.get("query") or params.get("content") or ""),
                cfg=cfg,
                limit=int(params.get("limit") or 5),
            )
        elif operation == "graph":
            result = graph_local(cfg, limit=int(params.get("limit") or 250))
        elif operation == "tasks":
            result = tasks_local(cfg, include_done=bool(params.get("include_done", True)))
        elif operation == "dag_candidates":
            result = dag_candidates(cfg, write=bool(params.get("write", False)))
        elif operation == "export_training_candidates":
            result = export_training_candidates(cfg)
        elif operation == "reindex":
            result = reindex_project(cfg)
        elif operation == "list_templates":
            result = list_templates()
        else:
            result = {"ok": False, "error": f"Unknown jarvis_memory operation: {operation}"}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    return json.dumps(result, ensure_ascii=False, indent=2)
