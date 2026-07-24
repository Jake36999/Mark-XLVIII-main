"""Deterministic point layout retained for the optional vault graph view.

Canvas documents use :mod:`core.canvas_layout`, which is rectangle-aware.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Iterable

from .models import GraphEdge, GraphNode


def _stable_unit(value: str) -> float:
    digest = hashlib.sha1(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def force_layout(
    nodes: Iterable[GraphNode],
    edges: Iterable[GraphEdge],
    width: float = 1000.0,
    height: float = 700.0,
    iterations: int = 90,
) -> dict[str, tuple[float, float]]:
    node_list, edge_list = list(nodes), list(edges)
    if not node_list:
        return {}
    if len(node_list) == 1:
        return {node_list[0].id: (width / 2.0, height / 2.0)}
    ids, id_set = [node.id for node in node_list], {node.id for node in node_list}
    degree = Counter()
    for edge in edge_list:
        if edge.source in id_set and edge.target in id_set:
            degree[edge.source] += 1
            degree[edge.target] += 1
    projects = sorted({node.project_id or "vault" for node in node_list})
    project_index = {project: index for index, project in enumerate(projects)}
    positions: dict[str, list[float]] = {}
    for index, node in enumerate(sorted(node_list, key=lambda item: item.id)):
        project = node.project_id or "vault"
        cluster_angle = 2.0 * math.pi * project_index[project] / max(1, len(projects))
        cluster_radius = min(width, height) * (0.18 if len(projects) > 1 else 0.0)
        centre_x = width / 2.0 + math.cos(cluster_angle) * cluster_radius
        centre_y = height / 2.0 + math.sin(cluster_angle) * cluster_radius
        angle = 2.0 * math.pi * (_stable_unit(node.id) + index / len(node_list))
        radius = 45.0 + _stable_unit(node.id + ":radius") * min(width, height) * 0.24
        positions[node.id] = [centre_x + math.cos(angle) * radius, centre_y + math.sin(angle) * radius]
    ideal = math.sqrt(width * height / max(1, len(node_list))) * 0.72
    temperature, margin = min(width, height) * 0.08, 45.0
    for _ in range(max(1, iterations)):
        displacement = {node_id: [0.0, 0.0] for node_id in ids}
        for left_index, left_id in enumerate(ids):
            for right_id in ids[left_index + 1 :]:
                dx, dy = positions[left_id][0] - positions[right_id][0], positions[left_id][1] - positions[right_id][1]
                distance = max(1.0, math.hypot(dx, dy))
                force = ideal * ideal / distance
                ux, uy = dx / distance, dy / distance
                displacement[left_id][0] += ux * force
                displacement[left_id][1] += uy * force
                displacement[right_id][0] -= ux * force
                displacement[right_id][1] -= uy * force
        for edge in edge_list:
            if edge.source not in positions or edge.target not in positions:
                continue
            dx = positions[edge.source][0] - positions[edge.target][0]
            dy = positions[edge.source][1] - positions[edge.target][1]
            distance = max(1.0, math.hypot(dx, dy))
            force = distance * distance / ideal * max(0.2, min(3.0, float(edge.weight or 1.0))) * 0.45
            ux, uy = dx / distance, dy / distance
            displacement[edge.source][0] -= ux * force
            displacement[edge.source][1] -= uy * force
            displacement[edge.target][0] += ux * force
            displacement[edge.target][1] += uy * force
        for node in node_list:
            displacement[node.id][0] += (width / 2.0 - positions[node.id][0]) * (0.008 + min(0.018, degree[node.id] * 0.001))
            displacement[node.id][1] += (height / 2.0 - positions[node.id][1]) * (0.008 + min(0.018, degree[node.id] * 0.001))
        for node_id in ids:
            dx, dy = displacement[node_id]
            distance = max(1.0, math.hypot(dx, dy))
            step = min(distance, temperature)
            positions[node_id][0] = min(width - margin, max(margin, positions[node_id][0] + dx / distance * step))
            positions[node_id][1] = min(height - margin, max(margin, positions[node_id][1] + dy / distance * step))
        temperature *= 0.955
    return {node_id: (point[0], point[1]) for node_id, point in positions.items()}
