"""Deterministic (no LM Studio) instrumentation: does graphify-informed file
selection let the agent reach relevant source files with a smaller token
budget than the pre-graphify (import-only-centrality) fallback would need?

Methodology: call the real select_reading_set() twice against the same real
inventory of the mark_platform root -- once with the real graphify graph,
once with the graph path overridden to a nonexistent file (forces the
documented no-op fallback, byte-identical to pre-graphify behavior). Compare,
for a set of files known to matter for orienting to "how does the graphify
integration work": (a) their rank position in the take-order, (b) the
cumulative bytes of higher-ranked files that would need to be included
before reaching them -- a direct proxy for "how many tokens of context do
you have to spend before this file is available to the agent".
"""
import copy
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"F:\Mark-XLVIII-main\Mark-XLVIII-main")

from actions.project_learning import inventory_repository, select_reading_set
from actions.jarvis_memory import resolve_config

ROOT = Path(r"F:\Mark-XLVIII-main")
REAL_GRAPH = ROOT / "graphify-out" / "graph.json"
NONEXISTENT_GRAPH = ROOT / "graphify-out" / "_does_not_exist.json"

TARGET_FILES = [
    "Mark-XLVIII-main/actions/graphify_query.py",
    "Mark-XLVIII-main/actions/project_learning.py",
    "Mark-XLVIII-main/core/repo_slicer.py",
    "Mark-XLVIII-main/actions/capability_registry.py",
    "Mark-XLVIII-main/actions/canvas_plan.py",
    "Mark-XLVIII-main/actions/jarvis_memory.py",
]

cfg = resolve_config()
exclude_roots = [cfg["notes_root"]]

print("Building inventory (git ls-files, respects .gitignore)...")
t0 = time.time()
inventory = inventory_repository(ROOT, max_inventory_files=5000, exclude_roots=exclude_roots)
print(f"inventory built in {time.time() - t0:.1f}s: ok={inventory.get('ok')} file_count={inventory.get('file_count')}")
assert inventory.get("ok"), inventory

assert REAL_GRAPH.exists(), f"expected real graph at {REAL_GRAPH}"
assert not NONEXISTENT_GRAPH.exists()


def run_condition(label: str, graph_path: Path) -> dict:
    inv = copy.deepcopy(inventory)
    # High max_files/budget so we see the FULL take-order, not a truncated one.
    selected = select_reading_set(
        inv,
        max_files=5000,
        max_total_bytes=50_000_000,
        max_file_bytes=500_000,
        graphify_graph_path=graph_path,
    )
    cumulative = 0
    rank_by_path = {}
    cumulative_bytes_by_path = {}
    for idx, record in enumerate(selected):
        path = str(record.get("path") or "")
        size = int(record.get("size") or 0)
        cumulative += size
        rank_by_path[path] = idx + 1  # 1-indexed rank in take-order
        cumulative_bytes_by_path[path] = cumulative

    targets = {}
    for target in TARGET_FILES:
        rank = rank_by_path.get(target)
        cum_bytes = cumulative_bytes_by_path.get(target)
        targets[target] = {"rank": rank, "cumulative_bytes_to_reach": cum_bytes}

    # Also record score for the target files to see the graphify boost directly.
    scores = {
        str(r.get("path")): {"score": r.get("score"), "graphify_centrality": r.get("graphify_centrality")}
        for r in inv.get("files", [])
        if str(r.get("path")) in TARGET_FILES
    }

    return {
        "label": label,
        "total_selected": len(selected),
        "total_bytes": cumulative,
        "targets": targets,
        "scores": scores,
    }


print("\nRunning OFF condition (graph path forced nonexistent -- pre-graphify fallback)...")
off = run_condition("graphify_off", NONEXISTENT_GRAPH)

print("Running ON condition (real graph)...")
on = run_condition("graphify_on", None)  # None -> default resolution -> real graph at ROOT/graphify-out/graph.json

print("\n=== RESULTS ===")
print(json.dumps({"off": off, "on": on}, indent=2))

out_path = Path(
    r"C:\Users\jakem\AppData\Local\Temp\claude\F--Mark-XLVIII-main\2191a7f8-63f6-4dcd-9d36-274e6a23603e\scratchpad\graphify_token_efficiency_results.json"
)
out_path.write_text(json.dumps({"off": off, "on": on}, indent=2, ensure_ascii=False), encoding="utf-8")
print("\nwritten to", out_path)
