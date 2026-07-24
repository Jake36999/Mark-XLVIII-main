from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions.document_workflow import analyze_path
from actions.model_lifecycle import persistent_generation_snapshot


def _wait_for_idle(timeout: int = 600) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not (persistent_generation_snapshot().get("leases") or []):
            return
        time.sleep(2)
    raise TimeoutError("Timed out waiting for other model generation leases.")


def _write_fixtures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "architecture.md": (
            "# Architecture\n\n"
            "The validation system treats Markdown as the readable authority, JSON as an executable manifest, "
            "SQLite as runtime state, and RAG as a derived retrieval layer. Approval hashes bind execution to "
            "the reviewed plan. Changes to scope or permissions invalidate approval. " * 4
        ),
        "operations.txt": (
            "Workers use bounded leases and deterministic checkpoints. Independent work may overlap, but local "
            "model generation is serialized by resource class. Interrupted non-retry-safe actions are marked "
            "unknown outcome and require review before retry. " * 4
        ),
        "risks.json": json.dumps(
            {
                "risks": [
                    "Untrusted source text cannot grant permissions.",
                    "User edits must survive reconciliation.",
                    "Specialist models must unload after their bounded task.",
                ],
                "owner": "validation",
                "status": "review",
            },
            indent=2,
        ),
    }
    for name, content in fixtures.items():
        (root / name).write_text(content + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    fixture_root = ROOT / "runtime_validation" / "document-map-reduce"
    _write_fixtures(fixture_root)
    instruction = f"Live validation {time.time_ns()}: summarize architecture, operations, and risks concisely."
    params = {
        "chunk_chars": 2000,
        "overlap_chars": 100,
        "max_files": 10,
        "max_total_bytes": 100_000,
        "save_to_vault": False,
        "resume": True,
        "role": "worker",
    }

    _wait_for_idle()
    started = time.monotonic()
    first = analyze_path(fixture_root, instruction=instruction, params=params)
    first_seconds = round(time.monotonic() - started, 3)

    _wait_for_idle()
    started = time.monotonic()
    second = analyze_path(fixture_root, instruction=instruction, params=params)
    second_seconds = round(time.monotonic() - started, 3)

    checks = {
        "first_ok": bool(first.get("ok")),
        "three_files": first.get("files_considered") == 3,
        "multiple_chunks": int(first.get("chunks") or 0) >= 2,
        "first_run_fresh": int(first.get("resumed_chunks") or 0) == 0,
        "second_ok": bool(second.get("ok")),
        "all_chunks_resumed": second.get("resumed_chunks") == second.get("chunks"),
        "same_checkpoint": first.get("checkpoint_path") == second.get("checkpoint_path"),
        "report_has_content": len(str(second.get("report") or "")) >= 100,
    }
    summary = {
        "ok": all(checks.values()),
        "checks": checks,
        "fixture_root": str(fixture_root),
        "first": {
            "seconds": first_seconds,
            "files_considered": first.get("files_considered"),
            "segments": first.get("segments"),
            "chunks": first.get("chunks"),
            "resumed_chunks": first.get("resumed_chunks"),
            "checkpoint_path": first.get("checkpoint_path"),
            "diagnostics": first.get("diagnostics"),
        },
        "second": {
            "seconds": second_seconds,
            "chunks": second.get("chunks"),
            "resumed_chunks": second.get("resumed_chunks"),
            "checkpoint_path": second.get("checkpoint_path"),
        },
        "report_preview": str(second.get("report") or "")[:1200],
    }
    result_path = ROOT / "runtime_validation" / "results" / "document-workflow.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
