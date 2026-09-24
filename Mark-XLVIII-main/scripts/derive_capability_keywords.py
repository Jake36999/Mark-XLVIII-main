"""Derive `keywords` for core.capability_schema.py's tool capabilities via a
blind, two-step LLM pipeline, rather than hand-typing them.

Design: D:\\Resource-Library\\branch offerings\\Mark-XLVIII\\Application - A
Centralised Capability Router for Canvas Mode 2.md, "Deriving the `keywords`
Axis" section.

Deliberately offline only -- this must never run at compile or dispatch
time (see that section's own warning: the semantic tool-scoring signal
built earlier the same session dropped the whole test suite from 11s to 86s
by putting a live model call into the compile-time path once already).

Step A (once per capability): given only the capability's functional
description -- no mention that the output feeds an AI tool-router, which
would anchor the model's answers to patterns from other AI-tooling
documentation it has seen rather than genuine reasoning -- generate 5-8
realistic scenarios a person could be in where the capability would be
useful.

Step B (once per scenario, independently): given one scenario, generate the
words/phrases a person would plausibly actually type or say in that
situation.

Output is deduped into `derived_keywords`, written to a JSON cache file
(config/derived_capability_keywords.json) that capability_schema.py can
later be extended to read -- kept separate from CAPABILITY_HELP's existing
hand-typed `keywords` rather than overwriting them, so the two can be
compared before either is trusted.

Usage:
    python scripts/derive_capability_keywords.py [--sample N] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SCENARIO_SYSTEM_PROMPT = (
    "You are analysing a piece of software functionality in isolation. You are not told what "
    "system, product, or context it might be used within -- reason only from what it actually "
    "does. Given the functional description below, list realistic real-world situations a person "
    "could plausibly be in where this functionality would be genuinely useful, relevant, or worth "
    "considering -- not merely possible, but where a reasonable person would actually reach for "
    "something like this. 5-8 scenarios, each 1-2 sentences, written from the person's situation, "
    "not the tool's feature list. Return strict JSON only: {\"scenarios\": [\"...\", ...]}"
)

_KEYWORD_SYSTEM_PROMPT = (
    "You are given one situation a person is in. Write the words and short phrases that person "
    "would plausibly actually type or say when describing this situation or asking for help with "
    "it -- their own natural language, in the moment, not technical jargon and not the name of a "
    "tool or solution they don't yet know exists. 5-10 items. Return strict JSON only: "
    "{\"keywords\": [\"...\", ...]}"
)


def _link_deepinfra() -> dict:
    from core.session_credentials import get_session_broker
    from core.session_key_store import load_session_key

    key = load_session_key("deepinfra")
    if not key:
        return {"ok": False, "error": "no saved deepinfra key in config/session_keys.env"}
    from ui import _load_api_config

    cfg = _load_api_config()
    base_url = str(cfg.get("deepinfra_url") or "https://api.deepinfra.com/v1/openai")
    model = str(cfg.get("worker_model") or cfg.get("deepinfra_model") or "openai/gpt-oss-20b")
    return get_session_broker().link("deepinfra", key, base_url=base_url, model=model)


def _generate_scenarios(description: str, *, attempts: int = 2) -> list[str]:
    """Confirmed live (2026-09-24): a real run against the same prompt that
    produced 7 good scenarios for jarvis_memory produced zero on a later
    call, and capability_registry's scenarios once came back concatenated
    into a single array element instead of 8 separate ones -- ordinary LLM
    output-shape flakiness, not a prompt-design problem (the well-formed
    calls the same run produced were high quality). One retry on empty
    output is enough to not silently record "no keywords" for a capability
    that just had one bad API response."""
    from core.model_router import _extract_json_object, call_text

    for attempt in range(attempts):
        text = call_text(description, role="worker", system=_SCENARIO_SYSTEM_PROMPT, timeout=120)
        payload = _extract_json_object(text)
        scenarios = [str(s).strip() for s in (payload or {}).get("scenarios") or [] if str(s).strip()]
        if scenarios:
            return scenarios[:8]
    return []


def _extract_keywords(scenario: str) -> list[str]:
    from core.model_router import _extract_json_object, call_text

    text = call_text(f"Situation:\n{scenario}", role="worker", system=_KEYWORD_SYSTEM_PROMPT, timeout=90)
    payload = _extract_json_object(text)
    keywords = [str(k).strip().lower() for k in (payload or {}).get("keywords") or [] if str(k).strip()]
    return keywords[:10]


def derive_for_capability(capability) -> dict:
    description = f"{capability.summary}\n\n{capability.details}".strip()
    result = {"id": capability.id, "scenarios": [], "keywords": [], "error": ""}
    try:
        scenarios = _generate_scenarios(description)
    except Exception as exc:
        result["error"] = f"scenario_generation_failed:{type(exc).__name__}:{exc}"
        return result
    result["scenarios"] = scenarios
    if not scenarios:
        result["error"] = "no_scenarios_generated"
        return result

    all_keywords: list[str] = []
    for scenario in scenarios:
        try:
            all_keywords.extend(_extract_keywords(scenario))
        except Exception as exc:
            result.setdefault("scenario_errors", []).append(
                {"scenario": scenario, "error": f"{type(exc).__name__}:{exc}"}
            )
    result["keywords"] = sorted(dict.fromkeys(all_keywords))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0, help="Only process the first N tool capabilities (0 = all)")
    parser.add_argument("--out", default=str(ROOT / "config" / "derived_capability_keywords.json"))
    args = parser.parse_args()

    link_result = _link_deepinfra()
    if link_result.get("state") not in {"linked", "degraded"}:
        print(json.dumps({"ok": False, "stage": "link", "result": link_result}, indent=2))
        return 1
    print(f"[link] deepinfra: {link_result.get('state')} ({link_result.get('model_count', '?')} models seen)")

    from core.capability_schema import by_kind

    tools = list(by_kind("tool"))
    if args.sample:
        tools = tools[: args.sample]

    results = {}
    for capability in tools:
        print(f"[derive] {capability.id} ...")
        result = derive_for_capability(capability)
        results[capability.id] = result
        status = "ok" if not result.get("error") else f"ERROR: {result['error']}"
        print(f"  {status} -- {len(result['keywords'])} keywords from {len(result['scenarios'])} scenarios")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
