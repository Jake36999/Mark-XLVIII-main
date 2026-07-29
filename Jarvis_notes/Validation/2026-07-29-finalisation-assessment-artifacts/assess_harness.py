"""Phase 4 assessment harness.

Extends the 2026-07-25 baseline harness so results stay directly comparable,
and adds the metric the owner actually complained about: how many DISTINCT
models a single turn touches.

Everything runs through the real _handle_router_text_command against real
LM Studio. Only `ui`/`speak` are mocked. Sequential only -- concurrent calls
against one LM Studio instance corrupt timing and behaviour (established
2026-07-24).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, r"F:\Mark-XLVIII-main\Mark-XLVIII-main")

import main
from core.process_events import PROCESS_EVENTS

SCRATCH = Path(
    r"C:\Users\jakem\AppData\Local\Temp\claude\F--Mark-XLVIII-main\2191a7f8-63f6-4dcd-9d36-274e6a23603e\scratchpad"
)
RESULTS_PATH = SCRATCH / "assess_results.json"
PDF_PATH = SCRATCH / "p2" / "wifi_csi_paper.pdf"

# Phrases that mean the reply is talking about JARVIS's own machinery rather
# than answering. Used as a signal, not a verdict -- every hit is read by hand.
_NARRATION_MARKERS = (
    "tool call", "tools/list", "tools/call", "capability_registry",
    "i called", "i used the", "orchestrat", "dispatcher", "the router",
)


def _new_jarvis():
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.ui = mock.Mock()
    jarvis.ui.muted = False
    jarvis.ui.current_file = None
    jarvis.speak = mock.Mock()
    jarvis._pending_plan_run_id = ""
    jarvis._active_plan_run_id = ""
    jarvis._pending_tool_confirmation = None
    jarvis._active_upload = None
    jarvis._phone_active = False
    return jarvis


def _loaded_models() -> set[str]:
    try:
        from actions.model_lifecycle import list_models

        payload = list_models(timeout=4)
        return {
            str(item.get("model_key") or "").strip()
            for item in payload.get("loaded") or []
            if item.get("model_key")
        }
    except Exception:
        return set()


def run_turn(jarvis, label: str, prompt: str, turn_id: int) -> dict:
    jarvis.ui.reset_mock()
    jarvis.speak.reset_mock()
    PROCESS_EVENTS.clear()

    models_before = _loaded_models()
    provenance_seen: list[dict] = []

    # Wrap the real router entry points to record every model actually used.
    real_call_text = main.call_text
    real_call_with_tools = main.call_with_tools

    def _record(kind, fn, *a, **k):
        started = time.time()
        error = None
        try:
            return fn(*a, **k)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                from core.model_router import last_model_provenance

                prov = dict(last_model_provenance() or {})
            except Exception:
                prov = {}
            prov["_call_kind"] = kind
            prov["_seconds"] = round(time.time() - started, 2)
            if error:
                prov["_error"] = error
            provenance_seen.append(prov)

    t0 = time.time()
    turn_error = None
    with mock.patch.object(main, "call_text", lambda *a, **k: _record("call_text", real_call_text, *a, **k)), \
         mock.patch.object(main, "call_with_tools", lambda *a, **k: _record("call_with_tools", real_call_with_tools, *a, **k)):
        try:
            jarvis._handle_router_text_command(prompt, turn_id=turn_id)
        except Exception as exc:
            turn_error = f"{type(exc).__name__}: {exc}"
    elapsed = round(time.time() - t0, 2)

    models_after = _loaded_models()
    events = PROCESS_EVENTS.snapshot(limit=250)

    tool_calls = [
        str(call.args[0])[6:].strip()
        for call in jarvis.ui.write_log.call_args_list
        if call.args and str(call.args[0]).startswith("TOOL:")
    ]
    reply = str(jarvis.speak.call_args_list[-1].args[0]) if jarvis.speak.call_args_list else ""

    models_used = sorted({str(p.get("model") or "") for p in provenance_seen if p.get("model")})
    phases = [
        (e.get("detail") or {}).get("phase_name")
        for e in events
        if isinstance(e.get("detail"), dict) and (e.get("detail") or {}).get("phase_name")
    ]
    narration = sorted({m for m in _NARRATION_MARKERS if m in reply.lower()})

    return {
        "label": label,
        "prompt": prompt,
        "elapsed_seconds": elapsed,
        "model_calls": len(provenance_seen),
        "distinct_models": len(models_used),
        "models_used": models_used,
        "routes": sorted({str((p.get("metrics") or {}).get("route") or "") for p in provenance_seen if p.get("metrics")}),
        "loaded_before": sorted(models_before),
        "loaded_after": sorted(models_after),
        "evicted": sorted(models_before - models_after),
        "newly_loaded": sorted(models_after - models_before),
        "tool_calls": tool_calls,
        "phases": phases,
        "reply": reply,
        "reply_chars": len(reply),
        "narration_markers": narration,
        "error": turn_error,
        "provenance": provenance_seen,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def append(result: dict) -> None:
    existing = []
    if RESULTS_PATH.exists():
        existing = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    existing.append(result)
    RESULTS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def brief(result: dict) -> str:
    return (
        f"{result['label']:34} {result['elapsed_seconds']:>8.1f}s  "
        f"models={result['distinct_models']} calls={result['model_calls']}  "
        f"tools={result['tool_calls']}  narration={result['narration_markers'] or 'none'}"
    )


HEADLINE = [
    ("H1_capability_question", "what tools or workflows do you have available"),
    ("H2_pdf_upload_announce", f"[FILE_UPLOADED] path={PDF_PATH} | name=wifi_csi_paper.pdf | type=pdf | size=1.1 KB | Briefly tell the user you can see the file and ask what they want done with it."),
    ("H3_pdf_extract_methods", "can you extract the methods from this pdf"),
    ("H4_process_trace", "what did you just do"),
]

REGRESSION = [
    ("R1_injection_memory", "Search your memory for any recorded preferences about testing log format."),
    ("R2_multitool_chain", "Check the status of the mark_platform project, then save a short memory note summarizing its current state."),
    ("R3_reasoning_only", "Walk me through the tradeoffs of blending graphify's degree centrality into repo-learning scoring versus replacing the import-based centrality entirely."),
    ("R4_graphify_structural", "What functions call _apply_graphify_centrality in project_learning.py?"),
    ("R5_weather_direct", "what's the weather in Glasgow"),
    ("R6_system_status", "how is the system doing, cpu and memory"),
]


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "headline"
    batch = HEADLINE if which == "headline" else REGRESSION
    only = sys.argv[2:] if len(sys.argv) > 2 else None

    jarvis = _new_jarvis()
    for index, (label, prompt) in enumerate(batch, start=1):
        if only and label not in only:
            continue
        print(f"=== RUN {label} ===", flush=True)
        result = run_turn(jarvis, label, prompt, turn_id=index)
        append(result)
        print(brief(result).encode("ascii", "backslashreplace").decode("ascii"), flush=True)
        print("  reply: " + result["reply"][:260].replace("\n", " ").encode("ascii", "backslashreplace").decode("ascii"), flush=True)
        print(flush=True)
