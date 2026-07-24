"""Deterministic rectangle-aware layouts for Obsidian Canvas documents."""

from __future__ import annotations

import copy
import re
from collections import defaultdict, deque
from typing import Any


MARGIN = 70
LANE_GAP = 120
ROW_GAP = 70
DEFAULT_EDGE_LABELS = {"next", "contains", "source"}


def _rect(node: dict[str, Any]) -> tuple[int, int, int, int]:
    return int(node["x"]), int(node["y"]), int(node["width"]), int(node["height"])


def _overlap(a: dict[str, Any], b: dict[str, Any], margin: int = MARGIN) -> bool:
    ax, ay, aw, ah = _rect(a)
    bx, by, bw, bh = _rect(b)
    return not (
        ax + aw + margin <= bx
        or bx + bw + margin <= ax
        or ay + ah + margin <= by
        or by + bh + margin <= ay
    )


def _cross(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    def direction(p1, p2, p3):
        return (p3[0] - p1[0]) * (p2[1] - p1[1]) - (p2[0] - p1[0]) * (p3[1] - p1[1])
    p1, p2 = (a[0], a[1]), (a[2], a[3])
    p3, p4 = (b[0], b[1]), (b[2], b[3])
    return direction(p1, p2, p3) * direction(p1, p2, p4) < 0 and direction(p3, p4, p1) * direction(p3, p4, p2) < 0


def _node_text(node: dict[str, Any]) -> str:
    return " ".join(
        [
            str(node.get("text") or ""),
            str(node.get("file") or ""),
            str((node.get("jarvis") or {}).get("kind") or "") if isinstance(node.get("jarvis"), dict) else "",
        ]
    ).casefold()


def _semantic_lane(node: dict[str, Any], profile: str) -> str:
    text = _node_text(node)
    kind = str((node.get("jarvis") or {}).get("kind") or "") if isinstance(node.get("jarvis"), dict) else ""
    if node.get("type") == "file":
        return "source"
    if kind == "status" or "dashboard" in text or "**status:**" in text:
        return "plan"
    if "block" in text or "awaiting" in text:
        return "blocked"
    if "review" in text or "approval" in text:
        return "review"
    if "[x]" in text or "complete" in text or "accepted" in text:
        return "complete"
    if profile == "tasks" and kind == "task":
        return "action"
    if kind == "task" or "work item" in text or "[ ]" in text:
        return "action"
    if "status" in text or "dashboard" in text or "plan" in text:
        return "plan"
    return "plan"


def _is_pinned(node: dict[str, Any], managed_prefix: str) -> bool:
    node_id = str(node.get("id") or "")
    metadata = node.get("jarvis") if isinstance(node.get("jarvis"), dict) else {}
    if not node_id.startswith(managed_prefix) or node.get("type") not in {"text", "file", "link", "group"}:
        return True
    if bool(metadata.get("pinned")):
        return True
    baseline = metadata.get("layout_baseline")
    if isinstance(baseline, dict):
        current = {field: int(node.get(field, 0)) for field in ("x", "y", "width", "height")}
        expected = {field: int(baseline.get(field, current[field])) for field in current}
        if current != expected:
            return True
    return False


def _place_without_overlap(node: dict[str, Any], occupied: list[dict[str, Any]], x: int, y: int) -> None:
    node["x"], node["y"] = int(x), int(y)
    attempts = 0
    while any(_overlap(node, other) for other in occupied) and attempts < 500:
        node["y"] += max(ROW_GAP, int(node["height"]) + ROW_GAP)
        attempts += 1
    occupied.append(node)


def _dependency_layers(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    ids = {str(node.get("id")) for node in nodes}
    incoming: dict[str, int] = {node_id: 0 for node_id in ids}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source, target = str(edge.get("fromNode") or ""), str(edge.get("toNode") or "")
        if source in ids and target in ids:
            incoming[target] += 1
            outgoing[source].append(target)
    queue = deque(sorted(node_id for node_id, count in incoming.items() if count == 0))
    layers = {node_id: 0 for node_id in queue}
    while queue:
        source = queue.popleft()
        for target in sorted(outgoing[source]):
            layers[target] = max(layers.get(target, 0), layers[source] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    cycles = sorted(node_id for node_id, count in incoming.items() if count > 0)
    fallback = max(layers.values(), default=-1) + 1
    for node_id in cycles:
        layers[node_id] = fallback
    return layers, cycles


def geometry_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in payload.get("nodes", []) if isinstance(node, dict)]
    overlaps = []
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            if _overlap(left, right, margin=0):
                overlaps.append([left.get("id"), right.get("id")])
    by_id = {str(node.get("id")): node for node in nodes}
    segments = []
    for edge in payload.get("edges", []):
        left, right = by_id.get(str(edge.get("fromNode"))), by_id.get(str(edge.get("toNode")))
        if left and right:
            segments.append((left["x"] + left["width"] / 2, left["y"] + left["height"] / 2, right["x"] + right["width"] / 2, right["y"] + right["height"] / 2))
    crossings = sum(1 for index, first in enumerate(segments) for second in segments[index + 1 :] if _cross(first, second))
    if nodes:
        min_x = min(node["x"] for node in nodes)
        min_y = min(node["y"] for node in nodes)
        max_x = max(node["x"] + node["width"] for node in nodes)
        max_y = max(node["y"] + node["height"] for node in nodes)
        bounds = {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}
    else:
        bounds = {"x": 0, "y": 0, "width": 0, "height": 0}
    return {"overlap_count": len(overlaps), "overlaps": overlaps[:30], "edge_crossing_estimate": crossings, "bounds": bounds}


def layout_document(
    payload: dict[str, Any],
    *,
    profile: str = "plan",
    managed_prefix: str = "jarvis-",
    suppress_default_labels: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(payload)
    nodes = [node for node in result.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in result.get("edges", []) if isinstance(edge, dict)]
    pinned = [node for node in nodes if _is_pinned(node, managed_prefix)]
    managed = [node for node in nodes if node not in pinned]
    occupied = list(pinned)
    cycle_nodes: list[str] = []

    if profile in {"dependency", "evidence"}:
        layers, cycle_nodes = _dependency_layers(managed, edges)
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for node in managed:
            grouped[layers.get(str(node.get("id")), 0)].append(node)
        y = 0
        for layer in sorted(grouped):
            x = 0
            row_height = 0
            for node in sorted(grouped[layer], key=lambda item: str(item.get("id"))):
                _place_without_overlap(node, occupied, x, y)
                x += int(node["width"]) + LANE_GAP
                row_height = max(row_height, int(node["height"]))
            y += row_height + ROW_GAP + 70
    elif profile == "relationship":
        columns = max(1, min(4, int(len(managed) ** 0.5) or 1))
        for index, node in enumerate(sorted(managed, key=lambda item: str(item.get("id")))):
            _place_without_overlap(node, occupied, (index % columns) * 540, (index // columns) * 300)
    else:
        lane_order = ["source", "plan", "action", "review", "blocked", "complete"]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in managed:
            grouped[_semantic_lane(node, profile)].append(node)
        source_ids = [
            str(node.get("id"))
            for node in sorted(grouped.get("source", []), key=lambda item: str(item.get("id")))
        ]
        source_rank = {node_id: index for index, node_id in enumerate(source_ids)}
        incoming_sources: dict[str, list[int]] = defaultdict(list)
        for edge in edges:
            source = str(edge.get("fromNode") or "")
            target = str(edge.get("toNode") or "")
            if source in source_rank:
                incoming_sources[target].append(source_rank[source])

        def lane_sort_key(item: dict[str, Any]) -> tuple[int, str]:
            ranks = incoming_sources.get(str(item.get("id"))) or []
            return (min(ranks) if ranks else len(source_rank), str(item.get("id")))

        lane_x = 0
        for lane in lane_order:
            lane_nodes = sorted(grouped.get(lane, []), key=lane_sort_key)
            if not lane_nodes:
                continue
            width = max(int(node["width"]) for node in lane_nodes)
            if lane in {"action", "complete", "blocked"} and len(lane_nodes) > 6:
                rows = 6 if profile == "tasks" else 5
                cell_height = max(int(node["height"]) for node in lane_nodes) + ROW_GAP
                columns = (len(lane_nodes) + rows - 1) // rows
                for index, node in enumerate(lane_nodes):
                    column, row = index // rows, index % rows
                    _place_without_overlap(
                        node,
                        occupied,
                        lane_x + column * (width + ROW_GAP),
                        row * cell_height,
                    )
                lane_x += columns * (width + ROW_GAP) + LANE_GAP
            else:
                y = 0
                for node in lane_nodes:
                    _place_without_overlap(node, occupied, lane_x, y)
                    y = node["y"] + int(node["height"]) + ROW_GAP
                lane_x += width + LANE_GAP

    for node in managed:
        metadata = node.setdefault("jarvis", {})
        if isinstance(metadata, dict):
            metadata["layout_profile"] = profile
            metadata["layout_baseline"] = {field: int(node[field]) for field in ("x", "y", "width", "height")}
    if suppress_default_labels:
        for edge in edges:
            if str(edge.get("label") or "").strip().casefold() in DEFAULT_EDGE_LABELS:
                edge.pop("label", None)
    metrics = geometry_metrics(result)
    metrics.update({"profile": profile, "managed_count": len(managed), "pinned_count": len(pinned), "cycle_nodes": cycle_nodes})
    return result, metrics


def place_new_node(payload: dict[str, Any], node: dict[str, Any], *, anchor_id: str = "") -> dict[str, Any]:
    result = copy.deepcopy(node)
    occupied = [item for item in payload.get("nodes", []) if isinstance(item, dict)]
    by_id = {str(item.get("id")): item for item in occupied}
    anchor = by_id.get(anchor_id)
    if anchor:
        x = int(anchor["x"] + anchor["width"] + LANE_GAP)
        y = int(anchor["y"])
    elif occupied:
        x = min(int(item["x"]) for item in occupied)
        y = max(int(item["y"] + item["height"]) for item in occupied) + ROW_GAP
    else:
        x = y = 0
    _place_without_overlap(result, occupied, x, y)
    return result
