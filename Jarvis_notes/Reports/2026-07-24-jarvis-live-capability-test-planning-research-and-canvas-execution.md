---
id: "jarvis-20260724T015914Z-83146d33"
title: "JARVIS Live Capability Test - Planning, Research, and Canvas Execution"
type: "report"
status: "complete"
created: "2026-07-24T01:59:14Z"
updated: "2026-07-24T01:59:20Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["capability-test", "live-deployment", "planning", "research", "canvas-plan", "repo-slicer", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T01:59:14Z"
review_after: ""
source_version: 1
content_hash: "98541afec9608a6514f4a40652ef8a2d2522eef02a66137440cb8729a8f1ca8c"
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
memory_tier: "short_term"
---

> [!info] Scope
> Live tests run against the actual running LM Studio instance and the real `Jarvis_notes` vault — no mocked models, no isolated test directories. All artifacts this produced are tagged `capability-test` for easy cleanup. This report answers three specific questions: is task decomposition sensibly granular (not over- or under-scoped for the model actually doing the work), has report generation quality improved, and does the system show any "if I want to research X, I should also research Y" lateral reasoning.

## Executive Summary

- **Task granularity: there mostly isn't any, yet.** Mode 1's `create_plan` does not adapt to a prompt's actual complexity — it is a deterministic keyword router across ~7 fixed categories, each with a fixed 3-4 step template. A prompt that matches no category gets a generic 4-step boilerplate with the raw prompt text pasted in, regardless of how complex the underlying goal is. No model reasons about the specific goal at plan-creation time at all.
- **Report generation is genuinely better on well-scoped topics, and shows real adjacent-topic reasoning** — but is still gated to "degraded" on large, evidence-heavy repository synthesis, for a *different* reason than before.
- **Lateral/adjacent reasoning does happen**, concretely observed in a real model-synthesized report, but only in the deep-research synthesis path — not in plan creation, which never calls a model.
- **Two real, previously-untested bugs were found by actually running the canvas planning engine live** against real models: a transient reviewer-role failure, and a genuine retry-attempt-counter gap that silently blocks any non-review node's retry.

---

## Test 1 — Mode 1 planning: task decomposition granularity

**Method:** two live `create_plan` calls against the real vault, no mocking.

**Prompt A** (VRAM-aware model admission — genuinely complex, ~6 distinct sub-problems): produced 4 generic steps — "Inspect the approved local context and capability health for: [the entire 500-char prompt pasted in]", "Execute the approved objective through the safest registered capability", "Validate the result...", "Create an execution summary...". Zero mention of `model_registry.MODEL_PROFILES`, byte-based budgets, or GPU pools anywhere in the actual work items.

**Prompt B** (WiFi CSI research, matches the "research" keyword category): got a *different*, richer 4-step template — "[parallel] Collect cited web sources...", "[parallel] Query local vault context...", "Synthesize the gathered evidence... identify unresolved contradictions", "Record research artifacts..." — and genuinely found 5 real citations (ScienceDirect, IEEE Xplore, a curated GitHub list).

**Root cause, confirmed by reading `plan_workflow._steps_from_prompt`:** it is a plain Python function doing substring/keyword matching against ~7 hardcoded phrase categories (repository learning, job-runner, documentation MOC, task ownership, code/repo/development, research/report, document/folder analysis) with a generic catch-all fallback. **No LLM call happens anywhere during plan creation.** The granularity of a plan's steps is entirely a property of which — if any — of the 7 categories the prompt's wording happens to match, not the goal's actual complexity.

**What this means for "don't ask an 8B model to write a print statement each, but don't expect too much either":** the current design actually avoids over-decomposition by construction (every category tops out at 3-4 steps) — but at the cost of *never* adapting to complexity. A one-line bug fix and a multi-file architecture change that both contain the word "implement" get the identical 3-step template ("Delegate the approved development objective to OpenClaw...", "Review the OpenClaw result...", "Record project artifacts..."). The real per-task sizing appears to be *deferred* to whatever executes each broad step (OpenClaw, a worker model) rather than being decided at the plan level — which is a defensible design (keep orchestration coarse, let execution-time agents self-scope) but it is *not* currently something that reasons about complexity; it's an accident of the architecture, not a tested/tuned behavior.

**Bonus finding:** local RAG retrieval, independent of any model call, automatically surfaced Jake's own prior WiFi/CSI work (a past plan note, a past execution run, the `network_management` Project Brief) as related context for Prompt B. This is real, useful adjacency — via retrieval, not generation.

---

## Test 2 — Report/research generation quality

**Method:** live call to `jarvis_memory.create_report_from_search(mode="research")` on the WiFi CSI topic — this is the one path in Mode 1 that actually invokes a model (`role="research"`) to synthesize findings from real search results.

**Result:** `quality_state: "validated"` in 115.9s. The generated report:
- Correctly grounded its recommendations in the *real* local hardware profile pulled from `runtime.json` ("Given the local host's hardware profile — a GTX 1080 and RX 5500 XT with 31.93GB RAM...") — not hallucinated, genuinely read from config.
- **Showed real adjacent-topic reasoning**, unprompted: flagged compatibility with the existing llama.cpp/Vulkan inference stack, raised multi-zone detection architecture as a consideration, recommended monitoring for signal degradation in high-interference zones, and explicitly cautioned against relying on CSI without a complementary sensor for critical use cases. This is a genuine, if modest, example of "if you want X, you should also think about Y."

**Real gaps found:**
- Two of the five sources were near-duplicates of the same ScienceDirect article (one `/abs/` URL variant, one not) — the search/dedup layer let this through.
- The synthesis prompt explicitly required "every factual bullet must end with a source marker," but the final Findings/Actions sections carry only one citation marker across several factual claims. The automated quality gate only checks that *at least one* valid marker exists anywhere in the combined text, not that individual bullets are cited — so under-citation currently passes validation even though it violates the prompt's own instruction.
- A first-stage "evidence normalization" pass failed with a JSON parse error from the model's own malformed output; the system correctly caught this and fell back rather than crashing, but it's a real, observed small-model reliability gap.

---

## Test 3 — Repository learning (the direct test of this session's own repo_slicer work)

**Method:** live `learn_repository` re-run on the exact same 123-file repository (`knowledge_compiler_engine / DAG Engine`) that the original learning assessment flagged as producing a degraded result while missing the pipeline core entirely. Force-refreshed, no cache.

**File selection: confirmed, substantially fixed.** The reading set now includes `src/pipeline/dag_runtime.py` (the actual import hub), `dataset_formatter.py`, `sft_formatter.py`, `sie_projection.py`, `dag_scoring_pass.py`, `Agent_Forge_orchestrator.py`, `src/core/models.py`, and `src/validation/pipeline_firewall.py` — every one of these is a pipeline-core module the *original* assessment explicitly said was missing. Two files (`semantic_slicer_AG.py`, `cognitive_processor.py`) still fall just outside the 36-file budget, ranked 15th and 24th by centrality+mass — a budget behaving as designed, not a bug.

**But `quality_state` is still "degraded" — for a different, more specific reason than before.** The "Architecture And Components" section reads "A model-generated architecture synthesis was unavailable," and the diagnostics show the *final consolidation* step's own output was rejected for citing files with malformed citation syntax (several genuinely-read files, cited without brackets or with a bare `git` token) and for an incomplete sentence in the RAG takeaways. **The quality gate is working exactly as intended — it correctly refused to publish a synthesis with broken citations rather than let a plausible-sounding but ungrounded architecture summary through** — but the underlying problem has moved: it's no longer "the model was never shown the right files," it's "the final synthesis step still can't reliably produce well-formed, correctly-cited prose once given this much evidence (36 mapped files)." This is the same failure family observed in Test 2's first-stage JSON error — small local models under real evidence load, not a retrieval problem.

**Honest bottom line:** the repo_slicer + file-selection work this session set out to fix — and did fix — the *input* half of the original finding. The *synthesis reliability* half was never in scope for that work and remains open.

---

## Test 4 — Canvas planning engine, end to end, live (never previously run against real models)

**Method:** hand-built a 3-node canvas (`research -> review -> research`) about a real, safe, low-stakes question (a local speech-to-text fallback for MARK), then ran the full T1-T6 pipeline live: `propose_canvas_plan` -> approve -> `execute_canvas_plan` -> resume.

**What worked:** compilation, the approval envelope, status write-back to the canvas (color + `jarvis` metadata), and the first research node's own dispatch all worked correctly and produced a genuinely good one-sentence answer (a real, sensible embedded-STT suggestion) from the worker model.

**Two real bugs found, neither caught by this session's unit tests (which all mocked `call_text`):**

1. **A transient failure in the automated independent-review pass.** The research node's own answer was fine, but the *second*, automatic model-review pass (`role="reviewer"`) threw a `RuntimeError`, which the system correctly caught and converted to an `ESCALATE` rather than silently failing. Calling the exact same `role="reviewer"` request in isolation immediately afterward succeeded — this looks like a transient model-swap/load race under back-to-back real calls, not a permanent break.

2. **The actual bug: `retry_escalated_item` doesn't reset the attempt counter.** Resuming the run via `execute_canvas_plan` (the system's own, real recovery path) completed in 0.1 seconds — no model was called at all. The node's `attempt` was already at 1 from the first dispatch, and only the `review`-role step got a bumped `retry_policy: {max_attempts: 3}` in this session's work; every other role (`research`, `implementation`, `verification`) is still on the schema default of `max_attempts: 1`. Resetting state to `PENDING` without resetting `attempt` means `_execute_item` immediately re-checks the attempt budget, finds it already exhausted, and converts straight to `REJECT_REPLAN` without a second try. **In effect, any non-review node that escalates for a transient reason today is permanently and silently un-retryable** — `retry_escalated_item` exists and runs, but is a no-op for anything except the one role that happens to have a larger budget. T2's status write-back correctly and visibly reflected the failure (red node, `REJECT_REPLAN`), so nothing was silently lost — but the run itself is now permanently blocked.

This is exactly the kind of gap that only surfaces from running the real system rather than a mocked test suite, and it's a small, well-scoped, clearly-diagnosed fix (either bump `max_attempts` more broadly, or have `retry_escalated_item` also reset `attempt`).

---

## Consolidated findings, prioritized

1. **(Real bug, cheap fix) `retry_escalated_item` needs to reset the attempt counter**, or non-`review` roles need a larger default `max_attempts` — right now a transient failure on any research/implementation/verification node is unrecoverable via the system's own resume path.
2. **(Real, but not urgent) Mode 1's task decomposition is a fixed keyword router, not complexity-aware.** If step-level granularity actually matters, this is where it would need to be built — today it's a coincidence of which of 7 phrase categories a prompt happens to match, not a reasoned decision.
3. **(Data quality) Citation/dedup gaps**: near-duplicate sources aren't deduped, and the quality gate only requires *a* citation somewhere rather than checking bullet-level compliance with the synthesis prompt's own stated requirement.
4. **(Confirmed fixed, worth stating plainly) File selection for repository learning is substantially better** — the exact pipeline-core files the original assessment said were missing are now read and mapped. The remaining "degraded" outcome on this specific repo is a *separate*, still-open problem in final-synthesis reliability under heavy evidence load, not a regression of this session's work.
5. **(Positive finding, low priority)** Adjacent-topic/lateral reasoning does happen in the real research-synthesis path (inference-stack compatibility, multi-zone architecture, sensor redundancy) — worth knowing it's there when evaluating whether deeper multi-hop research planning is worth building.

## Test artifacts (all tagged `capability-test`, safe to delete)

- `Plans/2026-07-24-capability-test-vram-admission.md`
- `Plans/2026-07-24-capability-test-wifi-csi-research.md`
- `Reports/2026-07-24-capability-test-wifi-csi-deep-research.md`
- `Canvases/JARVIS/capability-test-speech-fallback.canvas` + its approval note under `Plans/canvas-approval-capability_test_speech.md`
- `Projects/dag-engine-capability-test/` (Project Brief + Project Memory)
