"""Regenerate selected JARVIS project briefs through the read-only learning pass."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from actions.project_learning import learn_repository


DEFAULT_PROJECTS = {
    "network-management": (Path(r"F:\network_management"), "network_management"),
    "quantule-mapper": (Path(r"F:\quantule_mapper"), "quantule_mapper"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "projects",
        nargs="*",
        default=None,
        help="Project IDs: " + ", ".join(sorted(DEFAULT_PROJECTS)),
    )
    args = parser.parse_args()

    selected = args.projects or list(DEFAULT_PROJECTS)
    unknown = sorted(set(selected) - set(DEFAULT_PROJECTS))
    if unknown:
        parser.error("unknown project ID(s): " + ", ".join(unknown))

    failed = False
    for project_id in selected:
        root, display_name = DEFAULT_PROJECTS[project_id]
        print(json.dumps({"event": "start", "project": project_id, "root": str(root)}), flush=True)
        started = time.time()
        result = learn_repository(
            root,
            project_id=project_id,
            display_name=display_name,
            intent=(
                "Verify current repository architecture, entry points, operational boundaries, "
                "tests, risks, and durable memory using read-only evidence."
            ),
            params={
                "max_read_files": 36,
                "max_batches": 4,
                "map_max_tokens": 500,
                "synthesis_max_tokens": 700,
                "synthesis_timeout_seconds": 300,
            },
        )
        summary = {
            "event": "complete",
            "project": project_id,
            "ok": result.get("ok"),
            "status": result.get("status"),
            "elapsed_seconds": round(time.time() - started, 1),
            "snapshot_hash": result.get("snapshot_hash"),
            "files_read_count": result.get("files_read_count"),
            "files_mapped_count": result.get("files_mapped_count"),
            "brief_path": result.get("brief_path"),
            "memory_path": result.get("memory_path"),
            "diagnostics": result.get("diagnostics"),
            "takeaways": result.get("takeaways"),
        }
        print(json.dumps(summary, indent=2), flush=True)
        failed = failed or not bool(result.get("ok"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
