"""Deterministic completeness check for a generated vault document.

Exists because "artifact" steps (the `document` role's vault_create_note
dispatch) get zero independent review today -- side_effects=local_write
isn't in dual_orchestrator.WorkflowRuntime._requires_independent_review's
trigger set ({"model_reasoning", "review"} step types, or
external_write/destructive side effects), so a document node's actual
output is never checked against what it was supposed to contain. This
closes that gap for the specific case a closing verification node can
decide purely from the compiled canvas graph -- see canvas_plan.py's
`_ancestor_roles_and_documents` -- rather than the harder, deferred problem
of computing a code "blast radius" from an implementation node's OpenClaw
delegation, which reports no structured touched-files list today.

Deterministic topic-coverage, not an LLM judgment: the alternative (a model
call) would just redo, after the fact, review work that belongs at
generation time -- this checks the artifact that already exists, cheaply
and without another model dependency in the loop.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "do", "each", "for", "from",
    "in", "into", "is", "it", "its", "of", "on", "only", "or", "should",
    "that", "the", "this", "to", "with", "any", "other", "relevant",
}


def _topics(requirements_text: str) -> list[str]:
    """One topic per deliverable-shaped line (a bullet, or a sentence) with
    at least two words. Splitting rather than scoring the whole blob at
    once keeps one under-covered requirement visible instead of averaged
    away by strong coverage of the rest."""
    lines = [line.strip("-* \t") for line in re.split(r"[\n.]", requirements_text) if line.strip()]
    return [line for line in lines if len(line.split()) >= 2]


def _meaningful_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_]+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def check_document_completeness(
    note_path: str, requirements_text: str, *, topic_coverage_floor: float = 0.5, pass_ratio: float = 0.7
) -> dict[str, Any]:
    """Score each topic derived from `requirements_text` by how much of its
    own meaningful vocabulary actually appears in the note -- cheap and
    approximate, but the alternative today is nothing at all.

    `ok` requires only `pass_ratio` (default 70%) of topics to individually
    clear `topic_coverage_floor`, not all of them: `requirements_text` is
    often the document node's own raw prose (sentence-split, not authored as
    a checklist), so a stray filler sentence becoming an unmeetable "topic"
    must not single-handedly reject an otherwise complete document. Per-
    topic detail is always returned so a REPAIR verdict carries an
    actionable, specific defect list rather than a bare pass/fail.
    """
    path = Path(note_path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "note_path": note_path, "error": f"Could not read the generated document: {exc}"}

    topics = _topics(requirements_text)
    if not topics:
        ok = bool(content.strip())
        return {
            "ok": ok,
            "note_path": note_path,
            "topics": [],
            "summary": "No structured requirements to check against; confirmed the note is non-empty." if ok
            else "No structured requirements to check against, and the note is empty.",
        }

    note_words = _meaningful_words(content)
    results: list[dict[str, Any]] = []
    for topic in topics:
        topic_words = _meaningful_words(topic)
        if not topic_words:
            continue
        coverage = len(topic_words & note_words) / len(topic_words)
        results.append({"topic": topic, "coverage": round(coverage, 2), "covered": coverage >= topic_coverage_floor})

    if not results:
        return {"ok": bool(content.strip()), "note_path": note_path, "topics": [], "summary": "Requirements carried no scorable words."}

    covered_count = sum(1 for r in results if r["covered"])
    ok = (covered_count / len(results)) >= pass_ratio
    missing = [r["topic"] for r in results if not r["covered"]]
    summary = f"{covered_count}/{len(results)} required topics covered."
    if missing:
        summary += " Missing or thin: " + "; ".join(missing)[:500]
    return {"ok": ok, "note_path": note_path, "topics": results, "summary": summary}
