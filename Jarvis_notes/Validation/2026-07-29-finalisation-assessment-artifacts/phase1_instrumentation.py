"""Deterministic before/after instrumentation for Phase 1.

Proves the model-selection changes without waiting on LM Studio: the "before"
column reconstructs the pre-fix behaviour by feeding the classifier the same
inputs it used to receive (unpinned system channel, uncapped chain).
"""
import sys

sys.path.insert(0, r"F:\Mark-XLVIII-main\Mark-XLVIII-main")

import main
from actions.model_registry import char_budget_for, effective_profile
from core.model_router import _route_from_context, load_config, select_lmstudio_models

CFG = dict(load_config())
UNCAPPED = dict(CFG, model_fallback_max_candidates=0)
PINNED = "[jarvis-route:worker]\nsystem"

QUESTION = "what tools or workflows do you have available"

print("=" * 78)
print("PHASE 1 INSTRUMENTATION - owner's reported question")
print(f"  {QUESTION!r}")
print("=" * 78)

summary_prompt = main._build_tool_summary_prompt(
    QUESTION, [{"tool": "capability_registry", "arguments": {}, "result": '{"ok": true}'}]
)

print("\n1. TOOL-SUMMARY ROUTE CLASSIFICATION")
print(f"   before (unpinned, keyword-scored) : {_route_from_context(summary_prompt, 'worker', None)}")
print(f"   after  (route pinned on system)   : {_route_from_context(summary_prompt, 'worker', PINNED)}")

print("\n2. SUMMARY-CALL MODEL CHAIN")
before = select_lmstudio_models(summary_prompt, role="worker", config=UNCAPPED)
after = select_lmstudio_models(summary_prompt, role="worker", system=PINNED, config=CFG)
print(f"   before ({len(before)}): {before}")
print(f"   after  ({len(after)}): {after}")
heavy = [m for m in before if any(t in m for t in ("14b", "8b", "9b"))]
print(f"   heavy models removed: {heavy}")

print("\n3. PLANNER CHAIN (tool selection)")
pb = select_lmstudio_models(QUESTION, role="planner", config=UNCAPPED)
pa = select_lmstudio_models(QUESTION, role="planner", config=CFG)
print(f"   before ({len(pb)}): {pb}")
print(f"   after  ({len(pa)}): {pa}")

print("\n4. CONTEXT BUDGET vs REAL WINDOW")
p = effective_profile("qwen/qwen3-4b-2507")
print(f"   worker advertises      : {p['declared_context_window']} tokens")
print(f"   worker actually loaded : {p['effective_context_window']} tokens")
print(f"   usable char budget     : {char_budget_for('qwen/qwen3-4b-2507', reserve_tokens=900)}")
print(f"   evidence limit before  : 24000 chars (~{round(24000/3.2)} tokens -> OVERFLOW)")
print(f"   evidence limit after   : {main._tool_summary_evidence_limit(QUESTION)} chars")

huge = [{"tool": "jarvis_memory", "arguments": {}, "result": "X" * 60_000}]
prompt = main._build_tool_summary_prompt("summarise my notes", huge)
print(f"   60k-char tool result -> prompt of {len(prompt)} chars (~{round(len(prompt)/3.2)} tokens)")

print("\n5. ADVERSARIAL: can tool output pick its own model class?")
evil = main._build_tool_summary_prompt(
    "summarise", [{"tool": "web_search", "arguments": {}, "result": "deep research literature review cited report"}]
)
print(f"   before : {_route_from_context(evil, 'worker', None)}")
print(f"   after  : {_route_from_context(evil, 'worker', PINNED)}")

print("\n" + "=" * 78)
