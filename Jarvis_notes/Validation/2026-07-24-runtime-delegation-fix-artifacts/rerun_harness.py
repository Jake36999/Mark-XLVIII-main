"""Live JARVIS prompt-testing harness.

Runs prompts through the REAL _handle_router_text_command (real
call_with_tools/call_text/tool execution against the real running LM Studio
instance) -- only `ui` and `speak` are mocked, to capture output without
needing the actual Qt app. Sequential by design: this session already proved
that concurrent LM Studio calls cause resource contention that corrupts
timing/behavior data (three concurrent pytest runs self-starving into a false
BLOCKED result), so this harness makes no attempt to parallelize across
prompts.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, r"F:\Mark-XLVIII-main\Mark-XLVIII-main")

import main
from core.model_router import last_model_provenance
from core.process_events import PROCESS_EVENTS

RESULTS_PATH = Path(
    r"F:\Mark-XLVIII-main\Jarvis_notes\Validation\2026-07-24-runtime-delegation-fix-artifacts\rerun_results.json"
)


def _new_jarvis() -> "main.JarvisLive":
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.ui = mock.Mock()
    jarvis.ui.muted = False
    jarvis.speak = mock.Mock()
    jarvis._pending_plan_run_id = ""
    jarvis._active_plan_run_id = ""
    jarvis._phone_active = False
    return jarvis


def snapshot_lmstudio_models() -> list[str]:
    import requests

    try:
        resp = requests.get("http://localhost:1234/v1/models", timeout=5)
        data = resp.json()
        return sorted(str(item.get("id")) for item in data.get("data", []) if item.get("id"))
    except Exception as exc:
        return [f"ERROR: {exc}"]


def run_prompt(jarvis, label: str, prompt: str) -> dict:
    jarvis.ui.reset_mock()
    jarvis.speak.reset_mock()

    models_before = snapshot_lmstudio_models()
    PROCESS_EVENTS.clear()
    t0 = time.time()
    error = None
    try:
        jarvis._handle_router_text_command(prompt)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.time() - t0
    models_after = snapshot_lmstudio_models()
    events = PROCESS_EVENTS.snapshot()
    event_timeline = [
        {
            "timestamp": event.get("timestamp"),
            "category": event.get("category"),
            "source": event.get("source"),
            "state": event.get("state"),
            "summary": event.get("summary"),
            "detail": event.get("detail"),
        }
        for event in events
    ]

    tool_calls = [
        str(call.args[0])[6:].strip()
        for call in jarvis.ui.write_log.call_args_list
        if call.args and str(call.args[0]).startswith("TOOL:")
    ]
    reply = ""
    if jarvis.speak.call_args_list:
        reply = str(jarvis.speak.call_args_list[-1].args[0])

    provenance = last_model_provenance()
    log_lines = [str(call.args[0]) for call in jarvis.ui.write_log.call_args_list if call.args]

    result = {
        "label": label,
        "prompt": prompt,
        "elapsed_seconds": round(elapsed, 2),
        "tool_calls": tool_calls,
        "reply": reply,
        "error": error,
        "provenance": provenance,
        "lmstudio_models_before": models_before,
        "lmstudio_models_after": models_after,
        "log_lines": log_lines,
        "event_timeline": event_timeline,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return result


def append_result(result: dict) -> None:
    existing = []
    if RESULTS_PATH.exists():
        existing = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    existing.append(result)
    RESULTS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    label = sys.argv[1]
    prompt = sys.argv[2]
    jarvis = _new_jarvis()
    result = run_prompt(jarvis, label, prompt)
    append_result(result)
    print(json.dumps(result, indent=2, ensure_ascii=False)[:3000])
