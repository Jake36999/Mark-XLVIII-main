"""Unblock the notebook_packager_v3.1.py spec-writing run (canvas_plan-v3):
its research step (read_source_94ba6c) hit REJECT_REPLAN because the first
execute_canvas_plan call was made from a process whose credential broker was
never linked to DeepInfra, so it fell back to a dead local LM Studio route
and burned its repair budget on a route that was never going to work -- not
a genuine plan or model failure. Uses the new, explicit
WorkflowRuntime.retry_rejected_item to give that one item a fresh attempt now
that DeepInfra is linked correctly, then resumes the run via
execute_canvas_plan exactly as a second live-GUI call would.

Usage: python scripts/retry_and_resume_canvas_run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.session_credentials import get_session_broker
from core.session_key_store import load_session_key

NOTE_PATH = ROOT.parent / "Jarvis_notes" / "Plans" / "canvas-approval-canvas_plan.md"
RUN_ID = "canvas_plan-v3"
ITEM_ID = "read_source_94ba6c"


def _link_deepinfra() -> dict:
    key = load_session_key("deepinfra")
    if not key:
        return {"ok": False, "error": "no saved deepinfra key in config/session_keys.env"}
    from ui import _load_api_config

    cfg = _load_api_config()
    base_url = str(cfg.get("deepinfra_url") or "https://api.deepinfra.com/v1/openai")
    model = str(cfg.get("worker_model") or cfg.get("deepinfra_model") or "openai/gpt-oss-20b")
    return get_session_broker().link("deepinfra", key, base_url=base_url, model=model)


def main() -> int:
    link_result = _link_deepinfra()
    if link_result.get("state") not in {"linked", "degraded"}:
        print(json.dumps({"ok": False, "stage": "link", "result": link_result}, indent=2))
        return 1
    print(f"[link] deepinfra: {link_result.get('state')} ({link_result.get('model_count', '?')} models seen)")

    from actions import jarvis_canvas as canvas_actions
    from actions.canvas_plan import execute_canvas_plan
    from actions.dual_orchestrator import WorkflowRuntime

    resolved = canvas_actions.resolve_config(None)
    runtime = WorkflowRuntime(Path(resolved["notes_root"]))
    retry_result = runtime.retry_rejected_item(RUN_ID, ITEM_ID)
    print(f"[retry] {json.dumps(retry_result)}")
    # Not fatal if the item isn't currently REJECT_REPLAN (e.g. it already
    # moved to ESCALATE) -- execute_canvas_plan retries ESCALATE items itself.

    result = execute_canvas_plan(NOTE_PATH)
    print(json.dumps({k: v for k, v in result.items() if k != "run_status"}, indent=2, default=str))
    run_status = result.get("run_status") or {}
    print("\n--- items ---")
    for item in run_status.get("items", []):
        print(f"{item.get('item_id')}: {item.get('state')} (attempt={item.get('attempt')}) {item.get('error') or ''}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
