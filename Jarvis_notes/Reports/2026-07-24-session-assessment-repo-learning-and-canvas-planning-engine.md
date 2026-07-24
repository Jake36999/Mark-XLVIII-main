---
id: "jarvis-20260724T024327Z-995818ea"
title: "Session Assessment - Repo Learning and Canvas Planning Engine"
type: "report"
status: "complete"
created: "2026-07-24T02:43:27Z"
updated: "2026-07-24T02:43:39Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["assessment", "canvas-plan", "repo-slicer", "planning", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T02:43:27Z"
review_after: ""
source_version: 1
content_hash: "30ac969cd958208b8e9215564d72330048e8748addbf161967bb297daf4aa276"
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
> A holistic assessment of everything built and validated this session, ahead of the owner testing the system directly. Distinct from the earlier [[2026-07-24-jarvis-live-capability-test-planning-research-and-canvas-execution|live capability test report]], which this draws on but does not repeat in full.

## Scorecard

| Area | State |
| --- | --- |
| Repository learning (file selection) | **Fixed and confirmed live** — the exact files the original assessment flagged as missing are now read/mapped |
| Repository learning (final synthesis) | **Still fragile** — separate, unresolved bottleneck under heavy evidence load |
| Canvas planning engine (T1-T6) | **Built, unit-tested, and run live end to end** — one real bug found and fixed by the live run |
| Canvas planning reachability (T7) | **Fixed this session** — was previously untestable by JARVIS itself; now a registered tool |
| Mode 1 plan approval | **Retrofitted** to the same schema as canvas plans; existing approve/revise logic untouched |
| Mode 1 task decomposition | **Not adaptive** — confirmed via live test to be a fixed keyword router, no model reasoning |
| Dashboard layout | **Fixed and confirmed** — empirically verified the old code produced 7 overlaps, the fix produces 0 |
| Test coverage | 667 tests passing, zero known regressions |
| Canvas execution automation | **Not built** — nothing triggers `execute_canvas_plan` on its own yet |
| Implementation/verification canvas roles | **Never live-tested** — deliberately avoided this session (OpenClaw delegation, real pytest runs) |

---

## What was built this session

1. **`core/repo_slicer.py`** — AST-based code slicing (ranked, deduplicated function/class bodies) replacing raw file dumps and signature-only outlines for repository learning.
2. **File-selection hardening** in `project_learning.select_reading_set` — import centrality + code mass + a weighted per-category quota, specifically to stop keyword scoring from starving out large, interconnected source modules.
3. **The canvas planning engine (Mode 2), T1 through T7** — compiling a hand-drawn Obsidian Canvas graph into the same `jarvis_dual_orchestrator/v1` workflow schema Markdown plans use, then approving, reviewing, and running it:
   - T1 compiler (role → step, least-privileged default, OpenClaw only via the existing gated path)
   - T2 status write-back (canvas node color/metadata only, human text never touched)
   - T3 per-node completion SOP (documentation notes, forward-scout context handed to downstream nodes, optional handoff notes)
   - T4 approval binding — a plan-identity fingerprint deliberately immune to the system's own write-backs, so nothing it does to itself can trigger a false re-approval prompt
   - T5 review node as a dual critic (model critique + human gate, reusing the same approval schema)
   - T6 execution driver, including the `retry_escalated_item` fix
   - T7 — wiring `canvas_plan` into `main.py`/`core/tool_dispatcher.py`/`capability_registry.py` so it's an actual reachable JARVIS tool, plus retrofitting Mode 1's own approval flow to the same schema
4. **`core/approval_response.py`** — the shared Approve/Correct/Deny checkbox+callout schema, deliberately planning-mode-agnostic.
5. **Dashboard layout fix** — `sync_plan_canvas`/`sync_task_canvas` now re-layout on every sync instead of only at creation.
6. **README rewrite** and `docs/superpowers/plans/2026-07-23-mark-canvas-planning-engine.md` kept current throughout.
7. **Live capability testing** across Mode 1 planning, research/report synthesis, repository learning, and the canvas engine — against the real running LM Studio instance and the real vault, no mocks.

---

## Strengths

- **The safety architecture held under real testing, not just unit tests.** Approval envelopes, the drift-immune fingerprint, least-privileged role defaults, and the human review gate all behaved correctly when actually run — including in the one scenario that hit a real bug (T2's status write-back correctly and visibly showed the failure; nothing was silently lost).
- **"Compile onto existing machinery" paid off.** Canvas planning reused the existing dual orchestrator, its review/repair machinery, its approval envelope, and its command/hook registries almost entirely — the new surface area was genuinely narrow (a compiler, a fingerprint, a reviewer callback, a driver), which is why it was tractable to build and test this thoroughly in one session.
- **Live testing found real bugs unit tests structurally could not.** Both the "recompile from a mutated canvas" bug (T6) and the retry-attempt-counter bug (today) exist specifically because every earlier unit test mocked `call_text` and used a `review`-role-specific test shape. Actually running the system against real models is what surfaced them — worth treating as a standing argument for periodic live smoke-tests, not just relying on the mocked suite.
- **The quality gates are doing their job.** Both the original repo-learning assessment and today's re-run correctly refused to publish synthesis with broken citations or an incomplete sentence, rather than let something plausible-but-wrong through. That's the intended behavior of a deterministic-runtime-owns-safety design, and it held under real model output, not just crafted test inputs.
- **Extensive, disciplined test coverage.** 667 tests, added incrementally alongside nearly every change, with genuine TDD in most of this session's work (tests written to fail first, then made to pass).

## Weaknesses and open gaps

- **Mode 1 planning doesn't reason about task complexity at all.** `_steps_from_prompt` is a hardcoded keyword lookup across ~7 categories; nothing adapts step count or granularity to what the goal actually requires. If adaptive planning is something you want, this is the piece that would need to change — today it's a coincidence of wording, not a decision.
- **Local-model synthesis reliability is the recurring bottleneck**, not file/evidence selection. Three separate live observations this session (repo-learning's rejected final synthesis, the deep-research test's stage-1 JSON parse failure, the canvas review's transient RuntimeError) all point the same direction: small local models under real load intermittently produce malformed structured output or fail independent-review calls. The system's response (fallback, escalate, reject-and-refuse-to-publish) is correct and safe, but the underlying reliability gap is unaddressed.
- **Canvas planning has no automatic trigger.** Nothing invokes `propose_canvas_plan`/`execute_canvas_plan` on its own — a human or JARVIS has to explicitly call the tool, and there's no scheduled poller to auto-resume a run paused at a review gate. You'll need to drive this by hand (or ask JARVIS to) for now.
- **Implementation and verification canvas roles were never live-tested.** This session's live test deliberately used only `research`/`review` roles to avoid triggering real OpenClaw delegation or a real multi-minute test-suite run inside a smoke test. The first real use of an `implementation` or `verification` canvas node will be genuinely untested territory.
- **Three open questions from the original canvas-planning scoping doc were never revisited:** whether a node's `type` should live as a managed frontmatter property versus a naming convention; whether the review node's critic should be a hard gate or advisory (it ended up a de facto hard gate — ESCALATE blocks — without an explicit decision either way); and what OpenClaw sandbox isolation level implementation nodes should actually get.
- **Citation/dedup quality gate is looser than its own stated prompt.** The research-synthesis prompt asks for a citation on every factual bullet; the automated check only requires that at least one valid citation exists anywhere in the whole text. Near-duplicate sources (two URL variants of the same article) also weren't deduplicated.
- **Repo-wide git hygiene remains a backlog item**, not from this session's work but pre-existing across the wider codebase (per your own explanation — Codex's and earlier work, not yet committed). Not a risk given how you work, but worth knowing the gap is still there beyond the files this session touched.
- **Other scoped-but-unbuilt plans are still open**: VRAM-aware model admission (has a fresh draft plan from today's test, never built), project knowledge cartridges, the Home Assistant bridge.

## What to expect when you test it yourself

- Mode 1 plans for anything outside "research/report," "code/repo," "repository learning," "job-runner," or "document analysis" wording will come back as generic 4-step boilerplate — that's the keyword router, not a bug, but likely to feel underwhelming for a nuanced ask.
- Repository learning on a large or interconnected repo may still come back `quality_state: degraded` — check the "Risks, Gaps, And Questions" section before assuming something broke; it's very likely the synthesis-reliability gap above, and the file selection itself is probably fine now.
- To actually exercise canvas planning, you'll need to either draw a `.canvas` graph yourself and ask JARVIS to `propose`/`evaluate_approval`/`execute` it, or ask JARVIS to do so — nothing runs on its own yet.
- If you build or test an `implementation`-role canvas node, know that this is genuinely the first time that path will run for real — go in expecting to find something, the same way today's `research`/`review` test did.

## Path forward — open for discussion, not a recommendation

Once you've had a pass at it yourself, options on the table (not mutually exclusive):
1. Build the missing automatic trigger / scheduled resume for canvas plan runs.
2. Investigate the transient independent-reviewer `RuntimeError` more deeply — right now it's handled gracefully but not understood.
3. Make Mode 1's task decomposition genuinely complexity-aware instead of a fixed keyword router.
4. Tighten citation/dedup checking in the research-synthesis quality gate.
5. Deliberately live-test an `implementation` and a `verification` canvas node in a low-stakes scenario.
6. Resolve the three open canvas-planning design questions above.
7. Pick back up one of the other scoped-but-unbuilt plans (VRAM admission, cartridges, Home Assistant bridge).
8. Something you find while testing that isn't on this list at all.
