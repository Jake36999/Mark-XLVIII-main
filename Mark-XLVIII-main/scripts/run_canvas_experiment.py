"""Drive actions.canvas_plan.decompose_goal_to_canvas from outside the live
GUI process, for the spec-then-rebuild experiment ladder (2026-09-23).

Why this exists rather than typing into the running app: the GUI's linked
DeepInfra session lives only in that process's own in-memory credential
broker (core/session_credentials.py's SessionCredentialBroker is a per-process
singleton, spawned as its own subprocess) -- a separate script gets its own,
empty one. This script re-links from the one thing that *is* durable across
processes: core/session_key_store.py's saved-key file, the same "remember"
mechanism the credential UI writes to. Same vault (DEFAULT_NOTES_ROOT), same
planner/worker/research provider config as the live app -- this is not an
isolated test harness, it writes into the real Jarvis_notes vault the app
itself reads.

Usage: python scripts/run_canvas_experiment.py "<goal text>" [--hint "<project hint>"]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.session_credentials import get_session_broker
from core.session_key_store import load_session_key


def _link_deepinfra() -> dict:
    key = load_session_key("deepinfra")
    if not key:
        return {"ok": False, "error": "no saved deepinfra key in config/session_keys.env"}
    from ui import _load_api_config  # reuses the exact same base_url/model resolution the UI uses

    cfg = _load_api_config()
    base_url = str(cfg.get("deepinfra_url") or "https://api.deepinfra.com/v1/openai")
    model = str(cfg.get("worker_model") or cfg.get("deepinfra_model") or "openai/gpt-oss-20b")
    return get_session_broker().link("deepinfra", key, base_url=base_url, model=model)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("goal")
    parser.add_argument("--hint", default="")
    parser.add_argument("--canvas-name", default=None)
    args = parser.parse_args()

    link_result = _link_deepinfra()
    if link_result.get("state") not in {"linked", "degraded"}:
        print(json.dumps({"ok": False, "stage": "link", "result": link_result}, indent=2))
        return 1
    print(f"[link] deepinfra: {link_result.get('state')} ({link_result.get('model_count', '?')} models seen)")

    from actions.canvas_plan import decompose_goal_to_canvas

    result = decompose_goal_to_canvas(
        args.goal,
        project_hint=args.hint,
        canvas_name=args.canvas_name,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "raw_text"}, indent=2, default=str))
    if not result.get("ok"):
        print("\n--- raw_text (first 3000 chars) ---")
        print(str(result.get("raw_text") or "")[:3000])
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
