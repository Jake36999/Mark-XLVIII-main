"""Live validation of canonical vault, local RAG, tasks, and Canvas synchronization."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions import jarvis_canvas as canvas
from actions import jarvis_memory as memory


VAULT = ROOT.parent / "Jarvis_notes"
KEYWORD_PREFIX = "quartz-lantern-2741"
TASK_ID = "live-validation-vault-roundtrip"


def main() -> int:
    keyword = f"{KEYWORD_PREFIX}-{time.time_ns()}"
    cfg = memory.resolve_config(
        {
            "jarvis_notes_root": str(VAULT),
            "remember_enabled": False,
            "rag_embedding_provider": "lmstudio",
            "rag_embedding_model": "text-embedding-nomic-embed-text-v1.5@q4_k_m",
        }
    )
    canvas_cfg = {
        "jarvis_notes_root": str(VAULT),
        "jarvis_canvas_folder": "Canvases/JARVIS",
        "jarvis_canvas_max_task_nodes": 80,
        "jarvis_canvas_history_limit": 5,
    }
    note_path = VAULT / "Validation" / "2026-07-21-live-vault-roundtrip.md"
    canvas_path = VAULT / "Canvases" / "JARVIS" / "live-validation-task-dashboard.canvas"
    note = memory.create_note(
        note_type="progress_tracker",
        title="Live Validation - Vault and Canvas Roundtrip",
        content=(
            f"Validation retrieval marker: **{keyword}**.\n\n"
            f"- [ ] Validate gated Canvas synchronization [task:{TASK_ID}] "
            "owner:agent permission:execute"
        ),
        content_mode="full_body",
        status="active",
        tags=["validation", "rag", "canvas", "tasks"],
        source="codex-live-validation",
        cfg=cfg,
        sync=False,
        note_id="validation-vault-canvas-2026-07-21",
        path=note_path,
        metadata_extra={
            "workflow_id": "live-validation",
            "rag_index": True,
            "sensitivity": "internal",
            "confidence": 1.0,
        },
        reindex=False,
    )
    reindex = memory.reindex_local(cfg)
    query = memory.query_local(keyword, cfg=cfg, limit=5)
    tasks_before = memory.tasks_local(cfg, include_done=True)
    matching_before = [item for item in tasks_before.get("tasks", []) if item.get("task_id") == TASK_ID]

    synced = canvas.sync_task_canvas(cfg=canvas_cfg, canvas_path=canvas_path, max_nodes=80)
    payload = canvas.load_canvas(canvas_path)
    task_node = next(
        node
        for node in payload["nodes"]
        if (node.get("jarvis") or {}).get("task_id") == TASK_ID
    )
    task_node["text"] = task_node["text"].replace("## [ ]", "## [x]")
    canvas.write_canvas(canvas_path, payload)
    gated = canvas.apply_canvas_task_changes(canvas_path, cfg=canvas_cfg, confirmed=False)
    applied = canvas.apply_canvas_task_changes(canvas_path, cfg=canvas_cfg, confirmed=True)
    _, body_after_apply, _ = memory.read_note(note_path)

    resynced = canvas.sync_task_canvas(cfg=canvas_cfg, canvas_path=canvas_path, max_nodes=80)
    conflict_payload = canvas.load_canvas(canvas_path)
    conflict_node = next(
        node
        for node in conflict_payload["nodes"]
        if (node.get("jarvis") or {}).get("task_id") == TASK_ID
    )
    conflict_node["text"] = conflict_node["text"].replace("## [x]", "## [ ]")
    canvas.write_canvas(canvas_path, conflict_payload)
    current = note_path.read_text(encoding="utf-8")
    memory.atomic_write(
        note_path,
        current.replace(
            "Validate gated Canvas synchronization",
            "Validate gated Canvas synchronization - concurrent user edit preserved",
            1,
        ),
    )
    conflict = canvas.apply_canvas_task_changes(canvas_path, cfg=canvas_cfg, confirmed=True)
    tasks_after = memory.tasks_local(cfg, include_done=True)
    matching_after = [item for item in tasks_after.get("tasks", []) if item.get("task_id") == TASK_ID]
    review = memory.run_task_review(scheduled=False, cfg=cfg)

    results = query.get("results") or []
    query_match = any(
        (item.get("source_id") or item.get("id") or item.get("note_id"))
        == "validation-vault-canvas-2026-07-21"
        for item in results
    )
    semantic_used = bool(query.get("semantic_candidates")) and bool((query.get("embedding") or {}).get("ok"))
    result = {
        "ok": all(
            (
                note.get("ok") is True,
                reindex.get("ok") is True,
                query_match,
                bool(matching_before),
                synced.get("ok") is True,
                gated.get("ok") is False,
                applied.get("ok") is True,
                "- [x] Validate gated Canvas synchronization" in body_after_apply,
                bool(conflict.get("conflicts")),
                bool(matching_after),
                review.get("ok") is True,
            )
        ),
        "note_path": str(note_path),
        "canvas_path": str(canvas_path),
        "retrieval_marker": keyword,
        "index": {
            "indexed_notes": reindex.get("indexed_notes"),
            "changed_notes": reindex.get("changed_notes"),
            "embedding": reindex.get("embedding"),
        },
        "query_match": query_match,
        "query_methods": sorted(
            {
                str(item.get("retrieval_method") or "unspecified")
                for item in results
            }
        ),
        "query_embedding": query.get("embedding"),
        "semantic_candidates": query.get("semantic_candidates"),
        "semantic_used": semantic_used,
        "task_found_before": bool(matching_before),
        "confirmation_gate_rejected": gated.get("ok") is False,
        "confirmed_change_applied": applied.get("ok") is True,
        "conflict_detected": bool(conflict.get("conflicts")),
        "conflict_count": len(conflict.get("conflicts") or []),
        "task_review_status": review.get("status"),
        "canvas_nodes": resynced.get("node_count"),
        "canvas_edges": resynced.get("edge_count"),
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
