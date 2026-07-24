"""Live validation for concurrent execution, bounded repair, and cancellation."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions import dual_orchestrator as do


def delayed(payload: dict) -> dict:
    time.sleep(float(payload.get("delay", 0.1)))
    return {"ok": True, "name": payload.get("name", "step")}


def registry() -> do.PythonHookRegistry:
    hooks = do.PythonHookRegistry()
    hooks.register(
        do.HookSpec(
            hook_id="validation_delay",
            version="1",
            handler=delayed,
            input_schema={"type": "object"},
            output_schema={"type": "object", "required": ["ok", "name"]},
            timeout_seconds=10,
        )
    )
    return hooks


def step(step_id: str, *, depends_on: list[str] | None = None, delay: float = 0.1, review: bool = False) -> dict:
    return {
        "step_id": step_id,
        "orchestrator": "deterministic",
        "step_type": "python_hook",
        "target": "validation_delay",
        "description": f"Live validation step {step_id}",
        "depends_on": depends_on or [],
        "inputs": {"name": step_id, "delay": delay},
        "risk_tier": "T1",
        "side_effects": "none",
        "retry_policy": {"safe": True, "max_attempts": 3},
        "acceptance_criteria": {"required": True, "independent_review": review},
        "on_failure": "repair",
    }


def workflow(workflow_id: str, steps: list[dict]) -> dict:
    return {
        "schema_version": do.DIALECT,
        "workflow_id": workflow_id,
        "version": "1",
        "name": workflow_id.replace("_", " ").title(),
        "max_steps": max(1, len(steps)),
        "steps": steps,
    }


def prepare(root: Path, run_id: str, raw: dict, hooks: do.PythonHookRegistry, reviewer=None, max_workers: int = 3):
    manifest = do.compile_workflow(raw, hook_registry=hooks)
    bundle = root / ".jarvis" / "runs" / run_id
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "workflow.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    (bundle / "work-items.json").write_text(json.dumps(manifest), encoding="utf-8")
    envelope = do.build_approval_envelope(
        vault_root=root,
        plan_id=f"plan-{run_id}",
        plan_version=1,
        approval_projection_hash=f"projection-{run_id}",
        workflow_hash=manifest["workflow_hash"],
        manifest_hash=manifest["manifest_hash"],
        approved_action_ids=[item["id"] for item in manifest["items"]],
    )
    (bundle / "approval.json").write_text(json.dumps(envelope), encoding="utf-8")
    runtime = do.WorkflowRuntime(root, hook_registry=hooks, reviewer=reviewer, max_workers=max_workers)
    runtime.register_run(
        run_id=run_id,
        plan_id=f"plan-{run_id}",
        plan_version=1,
        bundle_path=bundle,
        manifest=manifest,
        approval_projection_hash=f"projection-{run_id}",
    )
    runtime.approve_run(run_id)
    return runtime


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="jarvis-workflow-live-") as tmp:
        base = Path(tmp)
        hooks = registry()

        concurrent_root = base / "concurrent"
        concurrent = prepare(
            concurrent_root,
            "run-concurrent",
            workflow(
                "live_concurrent",
                [
                    step("left", delay=0.5),
                    step("right", delay=0.5),
                    step("join", depends_on=["left", "right"], delay=0.1),
                ],
            ),
            hooks,
            max_workers=3,
        )
        started = time.monotonic()
        concurrent_result = concurrent.execute_run("run-concurrent")
        concurrent_seconds = time.monotonic() - started

        review_calls = {"count": 0}

        def reviewer(_item, _result, _defects):
            review_calls["count"] += 1
            if review_calls["count"] == 1:
                return "REPAIR", ["live_validation_first_pass_repair"]
            return "ACCEPT", []

        repair_root = base / "repair"
        repair = prepare(
            repair_root,
            "run-repair",
            workflow("live_repair", [step("reviewed", delay=0.05, review=True)]),
            hooks,
            reviewer=reviewer,
            max_workers=1,
        )
        repair_result = repair.execute_run("run-repair")

        cancel_root = base / "cancel"
        cancel = prepare(
            cancel_root,
            "run-cancel",
            workflow(
                "live_cancel",
                [
                    step("active", delay=0.8),
                    step("pending", depends_on=["active"], delay=0.1),
                ],
            ),
            hooks,
            max_workers=1,
        )
        cancel_holder: list[dict] = []
        thread = threading.Thread(target=lambda: cancel_holder.append(cancel.execute_run("run-cancel")), daemon=True)
        thread.start()
        time.sleep(0.2)
        cancel.request_cancel("run-cancel", reason="live_validation_interrupt")
        thread.join(timeout=5)
        cancel_result = cancel_holder[0] if cancel_holder else cancel.status("run-cancel")

        repair_item = repair_result["items"][0]
        cancel_states = {item["item_id"]: item["state"] for item in cancel_result["items"]}
        result = {
            "ok": all(
                (
                    concurrent_result["run"]["status"] == "COMPLETED",
                    concurrent_seconds < 0.95,
                    repair_result["run"]["status"] == "COMPLETED",
                    repair_item["attempt"] == 2,
                    repair_item["repair_count"] == 1,
                    review_calls["count"] == 2,
                    not thread.is_alive(),
                    cancel_result["run"]["cancel_requested"] == 1,
                    cancel_states.get("pending") == "CANCELLED",
                    any(event["event_type"] == "cancel_requested" for event in cancel_result["events"]),
                )
            ),
            "concurrency": {
                "status": concurrent_result["run"]["status"],
                "elapsed_seconds": round(concurrent_seconds, 3),
                "sequential_floor_seconds": 1.1,
                "states": {item["item_id"]: item["state"] for item in concurrent_result["items"]},
            },
            "repair": {
                "status": repair_result["run"]["status"],
                "attempt": repair_item["attempt"],
                "repair_count": repair_item["repair_count"],
                "review_calls": review_calls["count"],
                "verdicts": [
                    event["details"].get("verdict")
                    for event in repair_result["events"]
                    if event["event_type"] == "item_reviewed"
                ],
            },
            "cancellation": {
                "status": cancel_result["run"]["status"],
                "cancel_requested": bool(cancel_result["run"]["cancel_requested"]),
                "thread_stopped": not thread.is_alive(),
                "states": cancel_states,
                "checkpoints": [item["phase"] for item in cancel_result["checkpoints"]],
            },
        }
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
