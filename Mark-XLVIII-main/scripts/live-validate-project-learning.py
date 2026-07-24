from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from actions.project_learning import inventory_repository
from actions.jarvis_memory import resolve_config
from actions.project_operator import load_registry, project_operator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded read-only JARVIS repository-learning smoke test.")
    parser.add_argument("--project-id", default="mark_platform")
    parser.add_argument("--path", default="")
    parser.add_argument("--max-read-files", type=int, default=16)
    parser.add_argument("--max-read-bytes", type=int, default=500_000)
    parser.add_argument("--max-batches", type=int, default=4)
    args = parser.parse_args()

    registry = load_registry()
    registered = (registry.get("projects") or {}).get(args.project_id) or {}
    source = Path(args.path or registered.get("root") or "").expanduser().resolve()
    if not source.is_dir():
        print(json.dumps({"ok": False, "error": f"Project directory was not found: {source}"}, indent=2))
        return 2

    memory_config = resolve_config()
    excluded_roots = [memory_config["notes_root"]]
    before = inventory_repository(source, exclude_roots=excluded_roots)
    result = json.loads(
        project_operator(
            {
                "operation": "learn_project",
                "project_id": args.project_id if registered and not args.path else "",
                "path": str(source) if args.path else "",
                "intent": "Learn about this project through a bounded read-only live validation.",
                "use_aletheia": False,
                "max_read_files": args.max_read_files,
                "max_read_bytes": args.max_read_bytes,
                "max_chars_per_file": 9_000,
                "max_batches": args.max_batches,
            }
        )
    )
    after = inventory_repository(source, exclude_roots=excluded_roots)
    summary = {
        "ok": result.get("ok"),
        "status": result.get("status"),
        "read_only": result.get("read_only"),
        "source_snapshot_unchanged": before.get("snapshot_hash") == after.get("snapshot_hash"),
        "inventory_file_count": result.get("inventory_file_count"),
        "files_read_count": result.get("files_read_count"),
        "files_mapped_count": result.get("files_mapped_count"),
        "map_batches": result.get("map_batches"),
        "brief_path": result.get("brief_path"),
        "memory_path": result.get("memory_path"),
        "snapshot_path": result.get("snapshot_path"),
        "diagnostics": result.get("diagnostics"),
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0 if summary["ok"] and summary["source_snapshot_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
