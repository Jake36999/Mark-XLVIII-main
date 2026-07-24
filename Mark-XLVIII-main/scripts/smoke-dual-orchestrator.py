"""Run a temporary end-to-end smoke test for plan approval artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from actions.jarvis_memory import resolve_config
from actions.plan_workflow import approve_plan, create_plan, start_plan


def main() -> int:
    with TemporaryDirectory(prefix="jarvis-plan-smoke-") as root:
        cfg = resolve_config(
            {
                "jarvis_notes_root": root,
                "remember_enabled": False,
            }
        )
        created = create_plan(
            "Inspect local capability health and prepare a concise read-only status report.",
            title="Plan - Dual Orchestrator Smoke",
            cfg=cfg,
            internet=False,
        )
        approved = (
            approve_plan(created.get("path", ""), cfg=cfg)
            if created.get("ok")
            else {"ok": False}
        )
        queued = (
            start_plan(created.get("path", ""), cfg=cfg, agent_count=1)
            if approved.get("ok")
            else {"ok": False}
        )
        manifest = (
            json.loads(Path(created["manifest_path"]).read_text(encoding="utf-8"))
            if created.get("ok")
            else {}
        )
        workflow = (
            yaml.safe_load(Path(created["workflow_path"]).read_text(encoding="utf-8"))
            if created.get("ok")
            else {}
        )
        approval = (
            json.loads(Path(approved["approval_path"]).read_text(encoding="utf-8"))
            if approved.get("ok")
            else {}
        )
        result = {
            "created": bool(created.get("ok")),
            "work_items": created.get("work_item_count", 0),
            "dialect": workflow.get("schema_version"),
            "manifest_schema": manifest.get("schema_version"),
            "approved": bool(approved.get("ok")),
            "signature_present": bool(approval.get("signature")),
            "hashes_bound": all(
                bool(approval.get(key))
                for key in (
                    "approval_projection_hash",
                    "workflow_hash",
                    "manifest_hash",
                )
            ),
            "queued_after_approval": bool(
                queued.get("ok") and queued.get("status") == "queued"
            ),
            "agent_count": queued.get("agent_count", 0),
        }
        print(json.dumps(result, indent=2))
        return 0 if all(
            (
                result["created"],
                result["dialect"] == "jarvis_dual_orchestrator/v1",
                result["approved"],
                result["signature_present"],
                result["hashes_bound"],
                result["queued_after_approval"],
            )
        ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
