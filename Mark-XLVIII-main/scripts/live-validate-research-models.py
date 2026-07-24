from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions.model_lifecycle import (
    acquire_generation_lease,
    ensure_model_loaded,
    load_profile_for,
    persistent_generation_snapshot,
    release_generation_lease,
    status,
    unload_non_baseline,
    update_generation_lease,
)
from core.runtime_config import load_runtime_config


MODELS = (
    ("marco-deepresearch-8b", "Marco DeepResearch 8B", 384),
    ("qwen2.5-14b-deepresearch-i1", "Qwen2.5 14B DeepResearch i1", 96),
)


def _wait_for_idle(timeout: int = 900) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not (persistent_generation_snapshot().get("leases") or []):
            return
        time.sleep(2)
    raise TimeoutError("Timed out waiting for the model generation queue to become idle.")


def _probe(model: str, label: str, max_tokens: int, config: dict) -> dict:
    _wait_for_idle()
    run_id = f"research-live-{model}-{time.time_ns()}"
    lease = acquire_generation_lease(
        model,
        route="research",
        wait_seconds=900,
        run_id=run_id,
        step_id="readiness-probe",
    )
    if not lease.get("ok"):
        return {"ok": False, "model": model, "label": label, "stage": "lease", "error": lease}
    lease_id = str(lease["lease_id"])
    started = time.monotonic()
    try:
        update_generation_lease(lease_id, state="LOADING")
        loaded = ensure_model_loaded(
            model,
            route="research",
            exclusive_lease_id=lease_id,
            timeout=int(config.get("lmstudio_load_timeout_seconds") or 180),
        )
        load_seconds = round(time.monotonic() - started, 3)
        update_generation_lease(
            lease_id,
            state="GENERATING",
            instance_id=str(loaded.get("instance_id") or model),
            details={"validation": "research_model_readiness"},
        )
        before = status(config)
        generation_started = time.monotonic()
        response = requests.post(
            str(config.get("lmstudio_url") or "http://localhost:1234/v1").rstrip("/")
            + "/chat/completions",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a JARVIS research-planning model readiness probe. "
                            "Answer in English, do not use tools, and be concise."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return one sentence beginning READY: and name one strength you bring "
                            "to planning cited deep research."
                        ),
                    },
                ],
                "temperature": 0.0,
                "max_tokens": max_tokens,
                "stream": False,
                "ttl": int(config.get("task_model_ttl_seconds") or 300),
            },
            timeout=600,
        )
        generation_seconds = round(time.monotonic() - generation_started, 3)
        response.raise_for_status()
        payload = response.json()
        text = str((((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
        after = status(config)
        task_models = [item for item in after.get("loaded", []) if not item.get("baseline")]
        return {
            "ok": bool(text),
            "model": model,
            "label": label,
            "provider": "lmstudio",
            "role": "research",
            "max_tokens": max_tokens,
            "load_profile": load_profile_for(model, config),
            "load_seconds": load_seconds,
            "generation_seconds": generation_seconds,
            "response": text,
            "usage": payload.get("usage") or {},
            "loaded_task_models_before_request": [
                item.get("model_key") for item in before.get("loaded", []) if not item.get("baseline")
            ],
            "loaded_task_models_after_request": [item.get("model_key") for item in task_models],
            "single_task_model": len(task_models) == 1 and task_models[0].get("model_key") == model,
        }
    except Exception as exc:
        return {
            "ok": False,
            "model": model,
            "label": label,
            "provider": "lmstudio",
            "role": "research",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        release_generation_lease(lease_id, outcome="completed", error="")


def main() -> int:
    config = load_runtime_config()
    results = []
    cleanup_results = []
    for model, label, max_tokens in MODELS:
        result = _probe(model, label, max_tokens, config)
        results.append(result)
        _wait_for_idle()
        cleanup = unload_non_baseline(config, force=False)
        cleanup_results.append(
            {
                "after_model": model,
                "ok": cleanup.get("ok"),
                "skipped": cleanup.get("skipped", False),
                "unloaded": cleanup.get("unloaded", []),
                "failed": cleanup.get("failed", []),
            }
        )

    final_status = status(config)
    checks = {
        "both_responded": all(item.get("ok") for item in results),
        "sequential_single_task_model": all(item.get("single_task_model") for item in results),
        "cleanup_succeeded": all(item.get("ok") and not item.get("failed") for item in cleanup_results),
        "no_task_models_left": int(final_status.get("task_loaded_count") or 0) == 0,
        "no_leases_left": int((final_status.get("active") or {}).get("active_count") or 0) == 0,
    }
    summary = {
        "ok": all(checks.values()),
        "checks": checks,
        "results": results,
        "cleanup": cleanup_results,
        "final_loaded_models": [item.get("model_key") for item in final_status.get("loaded", [])],
    }
    result_path = ROOT / "runtime_validation" / "results" / "research-models.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
