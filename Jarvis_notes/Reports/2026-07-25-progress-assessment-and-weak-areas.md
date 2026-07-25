---
id: "jarvis-20260725T080459Z-7a6688d7"
title: "Progress Assessment — Canvas Planning Engine, Track A2, and Weak Areas"
type: "report"
status: "active"
created: "2026-07-25T08:04:59Z"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["assessment", "canvas-plan", "planning", "hardening", "tier-short-term", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-25T08:04:59Z"
review_after: ""
source_version: 1
content_hash: "2b895e2d837975666f78eea5428d3de20ac8308ed8936991de93a46d8eac09bd"
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
> A full-system progress assessment after the WS1-WS4d canvas-planning capstone and Track A2 model-routing work landed and were pushed to GitHub. Distinct from [[2026-07-24-session-assessment-repo-learning-and-canvas-planning-engine]] (that one predates WS1-WS4d entirely and is now itself a superseded snapshot). This covers: what's built and validated, what's built but under-hardened, what's explicitly not built, test-coverage gaps, and a prioritized validation plan.

## Scorecard

| Area | State |
| --- | --- |
| Canvas planning engine (Mode 2, WS1-WS4d) | **Built and live-verified end to end** — decompose → critique/refine → propose → approve → execute, all against the real local model, real bugs found and fixed at every stage |
| Model routing / RAM (Track A2) | **Fixed and live-verified** — timeout cascades traced to candidate order (not load speed), reordered and re-tested with 2-6.9x speedups; RAM fixed via existing TTL infra, not new code |
| Developer documentation | **Was a total gap for WS1-WS4d** (zero coverage anywhere in the 13-note Handbook) — fixed this session with a new Handbook note; Project Brief/Memory had two actively false claims — corrected |
| VRAM-aware model admission | **Still not built** — confirmed via code (zero references in `model_lifecycle.py`) and via the plan doc's own checkboxes (Part C fully unchecked) |
| Dashboard (`dashboard/server.py`, 794 lines) | **Has real auth** (bearer tokens, PIN/QR pairing, AES-256 payload encryption) — contradicts an earlier assumption of "no auth at all." Zero test coverage; token passed in URL query params for WS/downloads; no brute-force protection on `/login` |
| OpenClaw delegation gating | **Unchanged, confirmed still real**: `delegate_openclaw` is listed under `safe_operations` for every registered project — no `confirmation_id` required beyond the single T4 canvas-approval checkbox |
| Test suite | **826 tests, zero known regressions** — but coverage is uneven; `main.py` (3541 lines) and `dashboard/server.py` (794 lines) both have zero dedicated test files |
| Memory consolidation | **Built, live, actively wired** — 28 tests, `memory_consolidation_enabled: true`, not a stub |
| STT (`core/stt.py`) | **Thinly tested at the engine level** — every test mocks `WhisperSTT`/`VoskSTT` out; the *surrounding* router-mode pipeline (turn-silence, retry/backoff) is well tested, the engines themselves are not |
| Home Assistant bridge | **Planned only** — a full plan doc exists, zero source anywhere |

---

## What's built and validated (this session)

**Canvas planning (Mode 2), WS1 through WS4d** — see the new [[13 Canvas Planning Engine and Reasoning-Backed Decomposition]] Handbook note for the full technical picture. In one line: a goal can now become a real, multi-branch, dependency-correct canvas plan with inherited context and concrete deliverables, critiqued and automatically refined before a human ever sees it, then compiled onto the exact same approval/execution machinery Mode 1 already used. Every stage was live-tested against the real local model, not just mocked — and every stage's live test found and fixed a real bug (layout inversions, an approval-note link gap, a model-approved-anyway ordering violation caught by a deterministic backstop, a branch-tagged node getting bumped out of its own column). Two focused before/after comparisons showed the context-inheritance mechanism (WS4d) prevents a genuine cross-branch architectural inconsistency, not just adds generic color.

**Track A2** — the 16-prompt live test's timeout cascades were root-caused to candidate order (reasoning models tried first, each burning ~180s before falling through), not cold-load time (every model loads in under 30s). Reordered `model_routes` to try `mistral-7b-instruct` first; re-verified with the original 10 problem prompts, 2-6.9x speedups, zero cooldown events. RAM usage (70% stationary with 3 always-loaded models) fixed by using the *existing* task-model TTL/idle-sweep infrastructure instead of building new preload logic — `baseline_models` is back down to one model.

**Documentation** (this session, in response to this request) — a new Developer Handbook note covering WS1-WS4d in full (the single biggest doc gap found); two actively false claims in Project Brief/Project Memory corrected (`project_operator.py` and `dual_orchestrator` were both marked "not implemented" despite being real, tested modules); User Guide Overview updated to mention canvas planning as an active capability instead of omitting it.

## What's built but under-hardened

- **Dashboard auth has real gaps, not zero auth.** Bearer-token auth exists and is checked on state-changing endpoints, but tokens travel as URL query params on the WebSocket and download endpoints (visible in logs/browser history), and there's no rate-limiting or lockout on PIN attempts at `/login`. Zero test coverage on a 794-line, network-facing file is the more immediate risk — a regression here would go unnoticed.
- **OpenClaw's blast radius is still gated by exactly one checkbox.** `delegate_openclaw` requiring no `confirmation_id` (it's in every project's `safe_operations`) was flagged as a real, deliberate-but-unresolved decision point back when WS1 first surfaced it live. It's still true today, now backed by a dedicated regression test that documents the behavior as expected rather than flags it as a gap — worth a real decision (leave as-is since T4 approval is already a genuine human gate, or add a per-operation confirmation requirement) rather than continuing to note it and move on.
- **Evidence-binding (WS4d) doesn't cover verification/implementation dependencies.** Deliberate scope cut, correct call given the blast radius of the alternative (normalizing `dual_orchestrator.py`'s shared `command`/`tool` result shapes, used by Mode 1 too) — but it means a node depending on a test run or an OpenClaw task still gets zero real evidence about what that dependency actually produced.
- **Multi-branch decomposition reliability is measured, not solved.** The retry wrapper helps, but live testing this session still saw genuine variance (succeeded cleanly on some attempts, needed the retry path on others) on goals with 2+ branches specifically.

## What's explicitly not built

- **VRAM-aware model admission** (Part C of an existing, partially-shipped plan — Parts A/B, health/cooldown and profile reconciliation, are live). `vram_gb`/`lmstudio_host_profile` are declared in config and read only for report prose, never by selection/admission logic. A newer plan doc (`2026-07-23-mark-vram-admission.md`) exists and is also fully unchecked.
- **Home Assistant bridge** — plan doc only, zero source.
- **A statistically controlled context-quality study.** WS4d's execution-quality finding is two real, illustrative comparisons — genuinely informative, not a rigorous sample.
- **`dual_orchestrator.py` result-shape normalization** — would unblock evidence-binding for verification/implementation dependencies; deliberately deferred given it touches Mode 1 workflows too.

## Test coverage gaps

826 tests total. Well-covered: canvas planning (147), memory/RAG (81 + 28 consolidation), model routing (120 combined across two files), model lifecycle (54), speech runtime (40). Thin or zero, ranked by how much it matters:

1. **`main.py` (3541 lines) — no dedicated test file.** Only exercised indirectly through other modules' tests. This is the actual turn-handling/router entry point; indirect coverage means a regression here could hide behind an unrelated test's mock.
2. **`dashboard/server.py` (794 lines) — zero tests**, and it's the one network-facing surface in the whole system.
3. **`core/stt.py` — engine-level logic never exercised for real**, only mocked out everywhere it's used.
4. **`actions/dev_agent.py` — zero dedicated test file.**
5. A long tail of small, single-purpose action modules with zero coverage (`security_audit.py`, `system_monitor.py`, `skill_registry.py`, `open_app.py`, `send_message.py`, `screen_processor.py`, `desktop.py`, `computer_control.py`, `file_controller.py`, `code_helper.py`, `browser_control.py`, `game_updater.py`, `proactive.py`, and others) — individually lower-stakes, but collectively a real gap if any of them handle anything destructive.

## Proposed validation priorities (impact ÷ effort, not a recommendation to build all of it)

| # | Item | Why here | Cost |
| --- | --- | --- | --- |
| 1 | Live-test `main.py`'s turn-handling path directly, or at minimum add a focused `test_main.py` for the router/turn-lifecycle logic that isn't already covered incidentally | Highest-traffic code path in the system with the least direct test ownership | Medium |
| 2 | Add test coverage for `dashboard/server.py`, focused on the auth boundary specifically (token checks, the unauthenticated `/login`/`/` surface, WS/download token handling) | The one network-facing surface; zero coverage today means a regression is silent | Medium |
| 3 | Decide (not just re-flag) the OpenClaw `safe_operations`/`confirmation_id` question | A real, already-identified decision point that's been noted three times across this session without a decision | Low (it's a decision, not a build) |
| 4 | A real live test of an `implementation`-role canvas node actually reaching OpenClaw (not a dry run) | Every canvas-planning live test this session deliberately avoided this exact path; it remains genuinely untested territory | Medium-High (real side effects) |
| 5 | Add real (non-mocked) coverage for `core/stt.py`'s two engines | Currently zero confidence the engines themselves work outside what the surrounding pipeline tests imply | Medium |
| 6 | VRAM-aware admission (Part C) | High value for the hardware-constrained design this whole project is about, but a large, separate, already-scoped effort | High |
| 7 | A statistically controlled context-quality comparison (WS4d follow-up) | Would turn a compelling illustrative finding into a rigorous one | High |

## Related

[[2026-07-24-session-assessment-repo-learning-and-canvas-planning-engine]] · [[Planning Subsystem Roadmap]] · [[13 Canvas Planning Engine and Reasoning-Backed Decomposition]]
