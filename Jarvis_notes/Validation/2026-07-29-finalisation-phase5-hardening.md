---
id: "jarvis-20260729T212437Z-6cfa65ba"
title: "Finalisation Workflow: Phase 5 Hardening"
type: "report"
status: "active"
created: "2026-07-29T21:24:37Z"
updated: "2026-07-29T21:24:44Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "hardening", "routing", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-29T21:24:37Z"
review_after: ""
source_version: 1
content_hash: "b18310ca2e7af6965e3ae68dd6b9a22039927ad87597c9cdf8b83941a75ff25f"
supersedes: []
contradicts: []
depends_on: []
depended_on_by: []
extends: []
extended_by: []
implements: []
implemented_by: []
consumes: []
consumed_by: []
related: []
deleted: false
deleted_at: ""
lifecycle: "short_term"
sync_error: ""
---

> [!info] Scope
> Phase 5 of the finalisation workflow: fixing what the Phase 4 live assessment actually revealed, then re-running only the affected scenarios rather than the whole battery. Two carried-forward findings addressed, plus one regression from my own earlier phase that this round's scrutiny surfaced.

## Finding 1: structural code questions did not reach the tool built for them

Phase 4's R4 asked *"What functions call `_apply_graphify_centrality` in `project_learning.py`?"* — the exact shape `graphify_query` exists to answer. It went to `project_operator` instead, with an invented `project_id` of `project_learning`, and was policy-blocked.

Root cause was deterministic, not model whim: the router offered **both** tools, because the filename `project_learning.py` tripped the `project` keyword. Given a choice between the right tool and a plausible-looking wrong one, the model picked wrong.

**Fixed** by detecting the question shape and removing the choice. `_is_structural_code_question` requires *both* an asking form (`what/which/who ... calls/uses/depends on/references`) *and* a code-shaped subject (a snake_case identifier, a `.py` file, or a call form), then returns `graphify_query` alone — following the early-return pattern the router already uses for plan and news prompts. Requiring both halves is what keeps ordinary English like *"who uses this feature the most"* out of it.

Verified live: R4 now calls `graphify_query`, gets a real 270-node BFS traversal, and answers honestly that the returned evidence was truncated and did not show the specific caller. Not a perfect answer — the model chose `mode='query'` on the filename rather than `mode='explain'` on the symbol — but it is the right tool, on real data, reported without fabrication. Parameter choice within a correctly-selected tool remains a model-behaviour issue.

## Finding 2: an invented project id read as a dead end

`project_operator` was already returning `known_projects` in its block payload — the information needed to recover was right there — but the reply relayed only "that project is unknown".

**Fixed** by adding a plain-prose `hint` alongside the structured policy, naming the real registered ids and pointing symbol/file questions at `graphify_query`. The structured payload is unchanged; this just gives the summarising model a sentence it can actually use.

## Finding 3 (self-inflicted): word-boundary matching silently dropped plurals

Not on the Phase 4 list — surfaced while investigating Finding 1. The Phase 2 collision fix (single-word routing keywords match on word boundaries, so `ram` stops firing inside *program*/*diagram*) was too strict on the trailing side: `projects`, `files`, `tools`, and `notes` stopped matching their singular keywords entirely.

**Fixed** by allowing a simple plural suffix. Only the *leading* boundary does the collision work, so relaxing the trailing side costs nothing: verified that `ram`/*programs*, `ram`/*diagram*, `repo`/*weather_report*, `read`/*already*, and `move`/*remove* all remain correctly blocked while the plurals match again.

This one is worth recording plainly: a fix I shipped two phases ago quietly degraded routing, and it took a later phase's scrutiny to notice. The tests now cover both directions.

## Finding 4 (self-inflicted): the rebalanced prompt over-applied its own grounding rule

Phase 3 rewrote `core/prompt.txt` to lead with answering the user, including *"if you do not have it, say so plainly instead of filling the gap."* Aimed at factual claims — but on a re-run of the reasoning scenario, JARVIS declined a pure tradeoff question with *"I don't have a direct tool to evaluate tradeoffs"*, which is the rule misfiring on analysis.

**Fixed** with one clarifying line: the grounding rule is about facts, not about thinking; when asked to reason, compare, weigh tradeoffs or advise, answer from judgement, and *"I have no tool for that" is not an answer*.

Verified live: the same prompt now produces a real comparative analysis covering accuracy, scalability and robustness of the two centrality approaches.

Honest caveat on attribution: this scenario produced three different behaviours across identical runs before the change (raw tool dead end, good analysis, refusal). Local tool-selection is non-deterministic, so a single post-fix run is not proof. The clarifying line is defensible on its own terms regardless of that sample.

## Residual, deliberately not engineered away

The fixed reasoning reply still opens with meta-commentary — *"no tool call is required"* — before getting to the analysis. That is a milder instance of exactly the narration Phase 3 targeted, and it comes from model behaviour on a 4B local model rather than from a code path. Recording it rather than adding more prompt pressure, which risks trading one over-correction for another.

## Verification

- Re-ran only the affected scenarios (R3, R4), not the full battery.
- New tests: structural-question routing (positive and negative), plural tolerance, collision non-regression, and the unknown-project hint.
- Full suite green.

## Related
[[Validation/2026-07-29-finalisation-live-assessment]]
[[Validation/2026-07-25-expanded-live-validation]]
