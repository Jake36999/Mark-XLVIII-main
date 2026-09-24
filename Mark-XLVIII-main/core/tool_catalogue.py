"""Weighted tool relevance scoring for role-scoped tool grants.

Ported from a legacy AI harness (`Agent backend`) whose skill registry let
each skill declare its own `allowed_tools`, selected deterministically by a
keyword/trigger scorer before any model call -- the missing piece behind a
finding from live testing: canvas `research`-role nodes never had live tool
access at all (`dual_orchestrator.py`'s model_reasoning dispatch always
called `call_text`, never `call_with_tools`), so no role could reach for a
tool regardless of the task.

Rather than building a parallel keyword catalogue, this combines two
scoring signals Mark-XLVIII already has:

- **Lexical**: `actions.capability_registry.select_capability`'s existing L0
  card selector -- term-overlap against each capability's curated
  `keywords`, already maintained per tool, not duplicated here.
- **Semantic**: `actions.jarvis_memory`'s existing embedding pipeline
  (`_embed_texts`/`_cosine_similarity`), best-effort. The owner flagged a
  pure keyword/trigger matcher (the legacy harness's own approach) as
  potentially "too narrow or limiting"; a second, independent signal is the
  fix, using infrastructure that already exists rather than a new one.

The two signals are combined by Reciprocal Rank Fusion (RRF) -- rank
position, not raw score magnitude, the same mechanism a separate knowledge-
base project (`Resource-Library`'s librarian) uses to fuse lexical and
vector rankings, and for the same reason: a keyword term-count and a cosine
similarity live on different, incomparable scales, but "where did this
candidate rank" is always comparable.

Graceful by design throughout: any failure (no embedding provider linked,
capability_registry unavailable, an empty query) degrades to whatever
signal *is* available, down to an empty ranking -- this module suggests
tools, it never blocks a dispatch on being able to.
"""
from __future__ import annotations

from typing import Any

from core.capability_schema import ids_by_kind

# The only tool ids dual_orchestrator.py's `_dispatch_tool` actually knows
# how to run. `select_capability` ranks across every live-chat capability
# (~20), most unreachable from a compiled workflow tool step -- results are
# filtered to this set so a suggestion is never for something dispatch would
# just raise `Tool dispatcher is not registered` on. Sourced from
# core.capability_schema (2026-09-24 migration) rather than hardcoded here a
# second time -- this frozenset used to drift from capability_registry.py's
# real list (the exact symptom the capability-router proposal was written
# about); the fix is one declared source, not a more careful hand-copy.
DISPATCHABLE_TOOL_IDS = ids_by_kind("tool")

_RRF_K = 60  # matches the source vault's own rrf_k default -- no measurement yet justifies a different constant here


def lexical_candidates(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Dispatchable tool ids ranked by `capability_registry`'s existing
    keyword selector, most relevant first. Never raises: an import or
    lookup failure yields an empty list."""
    try:
        from actions.capability_registry import select_capability

        result = select_capability(query, limit=max(limit, len(DISPATCHABLE_TOOL_IDS)))
    except Exception:
        return []
    candidates = result.get("candidates") if isinstance(result, dict) else None
    if not isinstance(candidates, list):
        return []
    return [c for c in candidates if isinstance(c, dict) and c.get("id") in DISPATCHABLE_TOOL_IDS][:limit]


def _semantic_scores(query: str, tool_ids: frozenset[str]) -> dict[str, float]:
    """Cosine similarity between the query and each tool's own summary/
    details text, using whatever embedding provider `jarvis_memory` is
    already configured with. Returns {} on any failure or unavailability
    (no provider linked, model not loaded, embeddings disabled) -- this is
    an enhancement signal, never a requirement."""
    if not query.strip() or not tool_ids:
        return {}
    try:
        from actions.capability_registry import CAPABILITY_HELP
        from actions.jarvis_memory import _cosine_similarity, _embed_texts
        from core.runtime_config import load_runtime_config

        cfg = load_runtime_config()
        ordered_ids = sorted(tool_ids)
        texts = [query] + [
            f"{CAPABILITY_HELP.get(tool_id, {}).get('summary', '')} {CAPABILITY_HELP.get(tool_id, {}).get('details', '')}".strip()
            for tool_id in ordered_ids
        ]
        vectors, status = _embed_texts(texts, cfg)
        if not status.get("ok", True) and not vectors:
            return {}
        if len(vectors) != len(texts):
            return {}
        query_vector, tool_vectors = vectors[0], vectors[1:]
        return {
            tool_id: _cosine_similarity(query_vector, vector)
            for tool_id, vector in zip(ordered_ids, tool_vectors)
        }
    except Exception:
        return {}


def rank_tools(
    query: str,
    *,
    allowed_tools: list[str] | None = None,
    limit: int = 5,
    use_semantic: bool = True,
) -> list[dict[str, Any]]:
    """Dispatchable tool ids ranked by fused lexical + semantic relevance.

    `allowed_tools`, when given, is the hard ceiling (a role's declared
    `_ROLE_SPECS[...]["allowed_tools"]`) -- this never suggests a tool
    outside it, it only orders and scores within it. Every dispatchable tool
    id gets a rank even at zero relevance, so a caller can see the full
    picture rather than a silently-truncated list.
    """
    candidate_ids = DISPATCHABLE_TOOL_IDS if allowed_tools is None else DISPATCHABLE_TOOL_IDS & set(allowed_tools)
    if not candidate_ids:
        return []

    lexical = [c for c in lexical_candidates(query, limit=len(candidate_ids)) if c["id"] in candidate_ids]
    lexical_rank = {c["id"]: index for index, c in enumerate(lexical)}

    semantic = _semantic_scores(query, frozenset(candidate_ids)) if use_semantic else {}
    semantic_rank = {
        tool_id: index
        for index, tool_id in enumerate(sorted(semantic, key=lambda t: -semantic[t]))
    } if semantic else {}

    fused: list[dict[str, Any]] = []
    for tool_id in candidate_ids:
        rrf_score = 0.0
        if tool_id in lexical_rank:
            rrf_score += 1.0 / (_RRF_K + lexical_rank[tool_id])
        if tool_id in semantic_rank:
            rrf_score += 1.0 / (_RRF_K + semantic_rank[tool_id])
        fused.append(
            {
                "tool_id": tool_id,
                "score": round(rrf_score, 6),
                "lexical_rank": lexical_rank.get(tool_id),
                "semantic_score": round(semantic[tool_id], 4) if tool_id in semantic else None,
            }
        )
    fused.sort(key=lambda item: (-item["score"], item["tool_id"]))
    return fused[:limit]


def relevant_tool_ids(
    query: str, *, allowed_tools: list[str] | None = None, limit: int = 5, floor: float = 0.0
) -> list[str]:
    """Just the ranked tool ids, restricted to those scoring above `floor`.

    `floor` defaults to 0.0 (any signal at all, lexical or semantic, beats
    nothing) rather than a tuned cutoff -- there is no evaluation set yet to
    justify one, the same reasoning the source vault's own relevance
    workbench exists to eventually replace a guessed constant with."""
    return [item["tool_id"] for item in rank_tools(query, allowed_tools=allowed_tools, limit=limit) if item["score"] > floor]
