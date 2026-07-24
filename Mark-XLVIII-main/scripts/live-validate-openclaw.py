from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions.project_operator import delegate_openclaw
from actions.model_lifecycle import (
    acquire_generation_lease,
    ensure_model_loaded,
    release_generation_lease,
    update_generation_lease,
)
from core.runtime_config import load_runtime_config


def main() -> int:
    root = ROOT / "runtime_validation" / "openclaw-live"
    root.mkdir(parents=True, exist_ok=True)
    team = f"jarvis-live-{time.time_ns()}"
    model = "qwen/qwen3-4b-2507"
    openclaw_agent = str(load_runtime_config().get("openclaw_worker_agent") or "jarvis-worker")
    lease = acquire_generation_lease(
        model,
        route="baseline",
        wait_seconds=90,
        run_id=team,
        step_id="openclaw-live",
    )
    if not lease.get("ok"):
        print(json.dumps(lease, indent=2, ensure_ascii=True))
        return 1
    lease_id = str(lease["lease_id"])
    try:
        update_generation_lease(lease_id, state="LOADING")
        loaded = ensure_model_loaded(model, route="baseline", exclusive_lease_id=lease_id, timeout=180)
        update_generation_lease(
            lease_id,
            state="GENERATING",
            instance_id=str(loaded.get("instance_id") or model),
            details={"backend": "openclaw"},
        )
        result = delegate_openclaw(
            "live_validation",
            {
                "display_name": "JARVIS OpenClaw Live Validation",
                "root": str(root),
            },
            {
                "agents": 1,
                "workspace": False,
                "team": team,
                "timeout": 180,
                "openclaw_agent": openclaw_agent,
                "intent": (
                    "Perform a read-only continuity scout of this empty disposable directory. "
                    "Do not create or modify files. Report that the directory is empty and suggest "
                    "one safe next step for a future coding task."
                ),
            },
        )
    except Exception as exc:
        release_generation_lease(lease_id, outcome="failed", error=str(exc))
        raise
    spawned = (result.get("spawned") or [{}])[0]
    if not result.get("ok") or not spawned.get("ok"):
        release_generation_lease(
            lease_id,
            outcome="failed",
            error=str(spawned.get("stderr") or result.get("error") or "OpenClaw spawn failed"),
        )
        print(json.dumps({"ok": False, "stage": "spawn", "result": result}, indent=2, ensure_ascii=True))
        return 1
    agent_name = str(spawned.get("agent_name") or "")
    session_id = f"clawteam-{team}-{agent_name}"
    transcript = (
        Path.home()
        / ".openclaw"
        / "agents"
        / openclaw_agent
        / "sessions"
        / f"{session_id}.jsonl"
    )
    trajectory = transcript.with_suffix(".trajectory.jsonl")
    assistant = {}
    deadline = time.monotonic() + 420
    try:
        while time.monotonic() < deadline:
            update_generation_lease(lease_id)
            if transcript.exists():
                for line in transcript.read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = event.get("message") or {}
                    if event.get("type") == "message" and message.get("role") == "assistant":
                        assistant = message
                if assistant and assistant.get("stopReason") not in {None, "toolUse"}:
                    break
            if trajectory.exists():
                for line in trajectory.read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "model.completed":
                        continue
                    data = event.get("data") or {}
                    snapshots = data.get("messagesSnapshot") or []
                    messages = [item for item in snapshots if item.get("role") == "assistant"]
                    if messages:
                        assistant = messages[-1]
                    elif data.get("assistantTexts"):
                        assistant = {
                            "content": [{"type": "text", "text": text} for text in data["assistantTexts"]],
                            "stopReason": "stop",
                            "provider": event.get("provider"),
                            "model": event.get("modelId"),
                        }
                    if assistant and assistant.get("stopReason") not in {None, "toolUse"}:
                        break
                if assistant and assistant.get("stopReason") not in {None, "toolUse"}:
                    break
            time.sleep(1)
    finally:
        release_generation_lease(
            lease_id,
            outcome="completed" if assistant and assistant.get("stopReason") != "error" else "failed",
            error=str(assistant.get("errorMessage") or ""),
        )

    text_parts = [
        item.get("text", "")
        for item in assistant.get("content") or []
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    assistant_text = "\n".join(text_parts).strip()
    normalized_text = assistant_text.lower()
    task_grounded = "empty" in normalized_text and (
        "next" in normalized_text or "initialize" in normalized_text or "create" in normalized_text
    )
    summary = {
        "ok": bool(
            result.get("ok")
            and assistant
            and assistant.get("stopReason") != "error"
            and task_grounded
        ),
        "spawn_ok": bool(result.get("ok")),
        "team": team,
        "agents": result.get("agents"),
        "handoff_note": (result.get("handoff_note") or {}).get("path"),
        "agent_name": agent_name,
        "openclaw_agent": openclaw_agent,
        "session_id": session_id,
        "transcript": str(transcript),
        "trajectory": str(trajectory),
        "assistant_stop_reason": assistant.get("stopReason"),
        "assistant_model": assistant.get("model"),
        "assistant_provider": assistant.get("provider"),
        "assistant_text": assistant_text,
        "assistant_error": assistant.get("errorMessage"),
        "task_grounded": task_grounded,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
