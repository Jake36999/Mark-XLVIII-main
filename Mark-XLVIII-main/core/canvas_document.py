"""Structural JSON Canvas parsing, validation, and revision helpers.

This module has no model-facing behavior. It preserves user-owned extension
fields and reports corruption before any caller attempts a write.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any


NODE_TYPES = {"text", "file", "link", "group"}
SIDES = {"top", "right", "bottom", "left"}


class CanvasValidationError(ValueError):
    def __init__(self, diagnostics: list[dict[str, Any]]):
        self.diagnostics = diagnostics
        message = "; ".join(str(item.get("message") or "Invalid Canvas") for item in diagnostics[:4])
        super().__init__(message or "Invalid Obsidian Canvas JSON.")


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def content_revision(path: str | Path) -> str:
    target = Path(path)
    return hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else ""


def proposal_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _finite_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def validate_document(payload: Any) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return [{"code": "invalid_root", "message": "Canvas root must be a JSON object."}]
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    if not isinstance(nodes, list):
        diagnostics.append({"code": "invalid_nodes", "message": "Canvas nodes must be an array."})
        nodes = []
    if not isinstance(edges, list):
        diagnostics.append({"code": "invalid_edges", "message": "Canvas edges must be an array."})
        edges = []

    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        prefix = f"nodes[{index}]"
        if not isinstance(node, dict):
            diagnostics.append({"code": "invalid_node", "path": prefix, "message": f"{prefix} must be an object."})
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            diagnostics.append({"code": "missing_node_id", "path": prefix, "message": f"{prefix} has no id."})
        elif node_id in node_ids:
            diagnostics.append({"code": "duplicate_node_id", "path": prefix, "message": f"Duplicate node id: {node_id}"})
        else:
            node_ids.add(node_id)
        node_type = str(node.get("type") or "")
        if node_type not in NODE_TYPES:
            diagnostics.append({"code": "unknown_node_type", "path": prefix, "severity": "warning", "message": f"Unknown node type {node_type or '<missing>'}; it will be preserved and pinned."})
        for field in ("x", "y", "width", "height"):
            if not _finite_integer(node.get(field)):
                diagnostics.append({"code": "invalid_geometry", "path": f"{prefix}.{field}", "message": f"{prefix}.{field} must be a finite integer."})
        if _finite_integer(node.get("width")) and int(node["width"]) <= 0:
            diagnostics.append({"code": "invalid_width", "path": f"{prefix}.width", "message": f"{prefix}.width must be positive."})
        if _finite_integer(node.get("height")) and int(node["height"]) <= 0:
            diagnostics.append({"code": "invalid_height", "path": f"{prefix}.height", "message": f"{prefix}.height must be positive."})
        required = {"text": "text", "file": "file", "link": "url"}.get(node_type)
        if required and not isinstance(node.get(required), str):
            diagnostics.append({"code": "missing_node_content", "path": f"{prefix}.{required}", "message": f"{prefix} requires a string {required} field."})

    edge_ids: set[str] = set()
    for index, edge in enumerate(edges):
        prefix = f"edges[{index}]"
        if not isinstance(edge, dict):
            diagnostics.append({"code": "invalid_edge", "path": prefix, "message": f"{prefix} must be an object."})
            continue
        edge_id = str(edge.get("id") or "")
        if not edge_id:
            diagnostics.append({"code": "missing_edge_id", "path": prefix, "message": f"{prefix} has no id."})
        elif edge_id in edge_ids:
            diagnostics.append({"code": "duplicate_edge_id", "path": prefix, "message": f"Duplicate edge id: {edge_id}"})
        else:
            edge_ids.add(edge_id)
        for endpoint in ("fromNode", "toNode"):
            if str(edge.get(endpoint) or "") not in node_ids:
                diagnostics.append({"code": "dangling_edge", "path": f"{prefix}.{endpoint}", "message": f"{prefix} references a missing node through {endpoint}."})
        for side in ("fromSide", "toSide"):
            if side in edge and edge.get(side) not in SIDES:
                diagnostics.append({"code": "invalid_edge_side", "path": f"{prefix}.{side}", "message": f"{prefix}.{side} is invalid."})
    return diagnostics


def load_document(path: str | Path, *, validate: bool = True) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"nodes": [], "edges": []}
    raw = target.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanvasValidationError([
            {"code": "malformed_json", "message": f"Canvas JSON could not be parsed: {exc}"}
        ]) from exc
    if not isinstance(payload, dict):
        raise CanvasValidationError([{"code": "invalid_root", "message": "Canvas root must be a JSON object."}])
    payload = copy.deepcopy(payload)
    payload.setdefault("nodes", [])
    payload.setdefault("edges", [])
    diagnostics = validate_document(payload)
    errors = [item for item in diagnostics if item.get("severity") != "warning"]
    if validate and errors:
        raise CanvasValidationError(errors)
    return payload


def inspect_document(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    revision = content_revision(target)
    try:
        payload = load_document(target, validate=False)
        diagnostics = validate_document(payload)
    except CanvasValidationError as exc:
        return {
            "ok": False,
            "path": str(target),
            "revision": revision,
            "diagnostics": exc.diagnostics,
            "original_preserved": True,
        }
    errors = [item for item in diagnostics if item.get("severity") != "warning"]
    return {
        "ok": not errors,
        "path": str(target),
        "revision": revision,
        "node_count": len(payload.get("nodes", [])),
        "edge_count": len(payload.get("edges", [])),
        "unknown_top_level_fields": sorted(set(payload) - {"nodes", "edges"}),
        "diagnostics": diagnostics,
    }


def merge_managed(existing: dict[str, Any], generated: dict[str, Any], *, managed_prefix: str) -> dict[str, Any]:
    """Merge a derived view without deleting manual nodes or extension fields."""
    result = copy.deepcopy(existing)
    for key, value in generated.items():
        if key not in {"nodes", "edges"}:
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = {**copy.deepcopy(result[key]), **copy.deepcopy(value)}
            else:
                result[key] = copy.deepcopy(value)
    old_nodes = {str(node.get("id")): node for node in result.get("nodes", []) if isinstance(node, dict)}
    generated_nodes: list[dict[str, Any]] = []
    generated_ids: set[str] = set()
    for generated_node in generated.get("nodes", []):
        node = copy.deepcopy(generated_node)
        node_id = str(node.get("id") or "")
        generated_ids.add(node_id)
        previous = old_nodes.get(node_id)
        if previous:
            merged = copy.deepcopy(previous)
            merged.update(node)
            for field in ("x", "y", "width", "height"):
                if field in previous:
                    merged[field] = previous[field]
            node = merged
        generated_nodes.append(node)
    manual_nodes = [
        copy.deepcopy(node)
        for node in result.get("nodes", [])
        if isinstance(node, dict) and not str(node.get("id") or "").startswith(managed_prefix)
    ]
    result["nodes"] = manual_nodes + generated_nodes
    allowed = {str(node.get("id")) for node in result["nodes"]}

    manual_edges = [
        copy.deepcopy(edge)
        for edge in result.get("edges", [])
        if isinstance(edge, dict)
        and not str(edge.get("id") or "").startswith(managed_prefix)
        and str(edge.get("fromNode") or "") in allowed
        and str(edge.get("toNode") or "") in allowed
    ]
    result["edges"] = manual_edges + [
        copy.deepcopy(edge)
        for edge in generated.get("edges", [])
        if str(edge.get("fromNode") or "") in allowed and str(edge.get("toNode") or "") in allowed
    ]
    return result
