"""Benchmark prompt matrix for local-model characterization (2026-07-24).

Seven capability probes across lengths, each mapping to an overseer-relevant
failure mode observed in the 16-prompt live test. See
Jarvis_notes/Validation/2026-07-24-live-prompt-testing-16-prompts.md.
"""
from __future__ import annotations

# ---- long-context needle document (generated, deterministic) ----
_FILLER = (
    "The maintenance log records routine operational notes for the facility. "
    "Each entry documents ambient conditions, scheduled checks, and any deviations "
    "observed by the on-duty technician. Readings are taken at regular intervals and "
    "cross-referenced against the baseline profile established during commissioning. "
    "Minor fluctuations are considered normal and are not escalated unless they persist "
    "across three consecutive sampling windows. "
)


def _needle_doc(target_tokens: int, needle: str) -> str:
    # ~1.3 tokens/word rough; build filler then insert the needle near the middle.
    approx_words = int(target_tokens / 1.3)
    reps = max(1, approx_words // len(_FILLER.split()))
    paras = [_FILLER for _ in range(reps)]
    mid = len(paras) // 2
    paras.insert(mid, f" IMPORTANT OPERATIONAL NOTE: {needle} ")
    return "\n\n".join(paras)


_NEEDLE = "The internal build codename for the 2026 release is DUSKFALL-7."
_NEEDLE_ANSWER = "DUSKFALL-7"


# ---- structured-output schemas ----
_S1_INSTR = (
    "Return ONLY a valid JSON object and nothing else. No markdown code fences, no prose. "
    'It must match exactly: {"steps": [three short strings], "risk": one of "low", "medium", or "high"}. '
    'The task to plan: "add rate limiting to a public API endpoint".'
)
_S2_INSTR = (
    "Return ONLY a valid JSON object and nothing else. No markdown fences, no prose. Schema:\n"
    '{"feature": string, "milestones": [ {"name": string, "depends_on": [string], "risk": "low"|"medium"|"high"} ], '
    '"open_questions": [string]}\n'
    "Plan the feature: \"migrate a single-user local RAG index from SQLite to a vector database\". "
    "Include exactly 3 milestones with realistic dependencies."
)


# ---- reasoning ----
_R1 = (
    "You are scheduling four tasks A, B, C, D under these constraints:\n"
    "1. A must come before C.\n"
    "2. D must come after B.\n"
    "3. B cannot be first.\n"
    "4. C and D must be adjacent (in either order).\n"
    "Give the single valid ordering of all four tasks, then explain in 2-3 sentences why it is the only "
    "ordering that satisfies every constraint."
)

_R2_SCENARIO = (
    "You are planning the work to add a new 'session summary export' feature to a local-first assistant. "
    "The assistant stores everything as Markdown notes in an Obsidian vault; a background watcher indexes notes "
    "into a local SQLite RAG store; a deterministic Python runtime owns all tool dispatch and treats model output "
    "as non-authoritative proposals; and there is an approval-gate mechanism where a human checks a checkbox in a "
    "note before any side-effecting action runs. The new feature should: gather the current session's process-event "
    "trace, let the user pick a date range, render a Markdown summary note into the vault, and (only after approval) "
    "optionally email that summary to the user. The email step must never run without explicit human approval, and "
    "the summary note must be written before the email step is even offered. The vault watcher must not mis-attribute "
    "the assistant's own write as an external user edit. Sending email is a side-effecting action that the runtime "
    "classifies as requiring confirmation.\n\n"
    "Produce a dependency-ordered plan of 4-6 concrete steps. Critically, identify the ONE prerequisite step that is "
    "easy to overlook but that a later step silently depends on, and say which later step depends on it and why."
)


def _tool_prompt() -> str:
    # Faithful to JARVIS's own JSON-tool convention (core.model_router._tool_json_prompt).
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a city.",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_notes",
                "description": "Search the user's local vault notes.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            },
        },
    ]
    try:
        from core.model_router import _tool_json_prompt

        return _tool_json_prompt("What's the weather in Melbourne right now?", tools)
    except Exception:
        import json

        return (
            "You can call tools by returning JSON only. If a tool is needed return "
            '{"tool_calls":[{"name":"tool_name","arguments":{}}],"text":""}. '
            f"Tools: {json.dumps(tools)}. Request: What's the weather in Melbourne right now?"
        )


_Y1 = (
    "Synthesize the following sources into a short paragraph (3-4 sentences). Attribute each claim to its source "
    "number in square brackets, e.g. [1]. Do not add facts not present in the sources.\n\n"
    "[1] Qdrant is an open-source vector database written in Rust, known for low memory use and fast filtered search.\n"
    "[2] Chroma is a lightweight embedded vector store popular for local prototyping but historically weaker at scale.\n"
    "[3] SQLite with a vector extension keeps everything in a single portable file with zero extra services.\n"
    "[4] For a single-user local-first assistant, operational simplicity and zero extra running services often "
    "matter more than horizontal scalability."
)


# Each probe: id, kind, system, user, max_tokens, and (optional) a checker key.
PROMPTS = [
    {"id": "B1", "kind": "latency", "system": None,
     "user": "Reply with exactly this and nothing else: OK", "max_tokens": 256},
    {"id": "B2", "kind": "instruction", "system": None,
     "user": "List exactly three primary colors, one per line, with no other text.", "max_tokens": 400},
    {"id": "R1", "kind": "reasoning", "system": None, "user": _R1, "max_tokens": 500},
    {"id": "R2", "kind": "reasoning", "system": None, "user": _R2_SCENARIO, "max_tokens": 900},
    {"id": "S1", "kind": "structured", "system": None, "user": _S1_INSTR, "max_tokens": 300, "check": "json"},
    {"id": "S2", "kind": "structured", "system": None, "user": _S2_INSTR, "max_tokens": 600, "check": "json"},
    {"id": "T1", "kind": "tool", "system": None, "user": _tool_prompt(), "max_tokens": 300, "check": "toolcall"},
    {"id": "L1", "kind": "longctx", "system": None,
     "user": _needle_doc(2000, _NEEDLE) + "\n\nQuestion: What is the internal build codename mentioned in the document above? Answer with just the codename.",
     "max_tokens": 768, "check": "needle"},
    {"id": "L2", "kind": "longctx", "system": None,
     "user": _needle_doc(6000, _NEEDLE) + "\n\nQuestion: What is the internal build codename mentioned in the document above? Answer with just the codename.",
     "max_tokens": 768, "check": "needle"},
    {"id": "Y1", "kind": "synthesis", "system": None, "user": _Y1, "max_tokens": 400, "check": "attribution"},
]

NEEDLE_ANSWER = _NEEDLE_ANSWER

# Subset for the known-good baselines (comparison only).
BASELINE_SUBSET = {"B1", "R1", "S1", "T1"}

CANDIDATE_MODELS = [
    "deepseek-r1-0528-qwen3-8b",
    "mistralai/mistral-7b-instruct-v0.3",
    "qwen/qwen3.5-9b",
    "qwen2.5-14b-deepresearch-i1",
    "marco-deepresearch-8b",
]
BASELINE_MODELS = [
    "qwen/qwen3-4b-2507",
    "google/gemma-4-e4b",
]
