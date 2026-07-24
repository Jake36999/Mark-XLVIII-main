# DAG Training Opportunities — running ledger

**Purpose:** A standing capture log for places where a **small dedicated tooling/utility sub-agent** could be trained to support JARVIS, or where we could generate a training **DAG** (via the `F:\knowledge_compiler_engine (DAG Engine)` stack) to synthesise that data.

**Scope discipline (owner directive, 2026-07-23):** *do not build training pipelines from these.* Large local fine-tuning is out (compute cost; data-synthesis for large DAGs is still R&D — the 1000+-line chemical-agent run produced unsafe behaviour). The target is **small, tooling-focused sub-agents** (routing, classification, structured-output utilities), especially once Alexa is a comms layer and JARVIS's server/remote capabilities are in play. This file only *identifies and captures* candidates as they surface during other work.

**Each entry:** what the agent/DAG would do · why a small dedicated model beats the general path · where the training signal already exists in MARK · confidence.

---

## Seeded candidates (from work through 2026-07-23)

### 1. Model-route selector
- **Task:** given a prompt + role, pick the right local model/route (quick/worker/reasoning/code/vision/research).
- **Why dedicated:** `core/model_router._route_from_context` is hand-written keyword heuristics; a tiny classifier would route better and is a bounded, low-risk utility.
- **Signal already present:** every generation logs role + provenance + outcome in the health store (`model_health`) and provenance records. Label = which model actually succeeded well. That's a ready-made routing dataset.
- **Confidence:** high. Bounded output space, abundant labels, low blast radius.

### 2. Memory-type / fact classifier
- **Task:** classify an extracted fact as `episodic | semantic | preference` (Mnemosyne's `MemoryClassifier`), and whether a note is `promote | merge | archive | flag` (my `memory_consolidation` detection).
- **Why dedicated:** consolidation currently uses token-Jaccard + heuristics; a small classifier would generalise better and is the exact pattern Mnemosyne trained around.
- **Signal already present:** every consolidation *proposal the user approves or edits* is a labelled example. The condenser/classifier split in `D:\remember_me` is a template.
- **Confidence:** high, and it compounds — it also feeds the cartridge selector (#3).

### 3. Cartridge / project selector
- **Task:** given a query, decide which project cartridge(s) to mount (the hard problem in the cartridge plan).
- **Why dedicated:** mis-routing here is silent; a purpose-trained selector with a confidence gate beats keyword matching.
- **Signal already present:** once cartridges exist, every explicit-mount turn is a labelled (query → project) pair. Bootstrap from explicit routing, train once there's a track record.
- **Confidence:** medium — depends on cartridge phase shipping first; captured now so we log the labels from day one.

### 4. Structured-output / frontmatter repair utility
- **Task:** coerce messy note frontmatter (CRLF, unquoted YAML, exploded tags) into the canonical form; emit structured integrity verdicts.
- **Why dedicated:** `core/note_integrity` detects these deterministically; a small model could *repair* ambiguous cases the deterministic path can't.
- **Signal already present:** the pre/post pairs from this session's two vault repairs (backup vs repaired note) are literal training pairs.
- **Confidence:** medium. Deterministic repair covers most cases; reserve the model for the long tail.

### 5. Tool/capability selector
- **Task:** map a user request to the right MARK tool(s) + operation (the capability-registry L0 selection step).
- **Why dedicated:** progressive disclosure already narrows this; a small selector could replace part of the planner's tool-routing for common requests, cheaply and fast.
- **Signal already present:** `main.py` hard-routing tables + every successful tool dispatch (request → tool → outcome) in the run history.
- **Confidence:** medium-high. Bounded label set (the registered tool list), lots of dispatch history.
- **2026-07-24 update:** a live, owner-run test caught a concrete failure of exactly this kind — "run the test suite and confirm tests/test_tts_read_trigger.py passes" matched the `_router_tool_names_for_text` keyword rule for `("test", "build", ...)`, which offers `code_helper`, `dev_agent`, and `project_operator` as candidates. The model picked `project_operator` against an unrelated registered project and returned a generic status; `code_helper`'s `action=run` was the correct choice and was available in the same candidate set. Hardened the two tools' descriptions as a cheap mitigation (see `Jarvis_notes/Validation/2026-07-24-canvas-node-live-test-and-hardening.md`), but the underlying selection is still keyword-based, not learned — this is now a labeled (prompt → wrong tool chosen → correct tool available) example worth keeping if this is ever built.

---

## Seeded candidates (from the 2026-07-24 live capability test)

### 6. Task-decomposition granularity model
- **Task:** given a plan prompt, decide the right number/size of work steps for a plan, instead of a fixed lookup.
- **Why dedicated:** `plan_workflow._steps_from_prompt` is a pure keyword-substring router across ~7 hardcoded categories with zero model involvement — confirmed live, a genuinely complex prompt (VRAM admission) and a simple one both get whatever fixed 3-4-step template their wording happens to match, with no complexity awareness at all.
- **Signal already present:** not yet — would need instrumenting (e.g. did a plan's steps get further split at execution time, did the human revise the plan for being under/over-scoped). Flagging now so the instrumentation question is on record before anything is built.
- **Confidence:** medium. Real, confirmed gap; but the "right" granularity is genuinely hard to label without deliberately collecting it first.

### 7. Structured-output retry/repair classifier
- **Task:** when a local model's structured-output call (an evidence-normalization JSON blob, a review verdict) fails to parse, decide whether a bounded reformulated retry is likely to succeed versus escalating immediately.
- **Why dedicated:** the live test captured two real instances of exactly this failure mode in one session — a JSON parse error during evidence normalization (graceful deterministic fallback) and a transient `RuntimeError` from the independent-reviewer role (worked fine calling the same role again in isolation seconds later). Right now both are handled by a blanket escalate/fallback with no attempt to distinguish "will probably work on retry" from "will not."
- **Signal already present:** the two captured failures above are the first literal labeled examples (failure text + immediate-retry outcome). Worth preserving verbatim if this is ever built.
- **Confidence:** medium — only two data points so far; the pattern is real but the dataset doesn't exist yet.
- **2026-07-24 update:** a third occurrence, in a third distinct context — the canvas implementation-node live test hit `reviewer_unavailable:RuntimeError` on `_default_model_review`'s independent-review call for all 3 test items (see `Jarvis_notes/Validation/2026-07-24-canvas-node-live-test-and-hardening.md`). Same failure shape as the two prior instances (transient, role-agnostic, not reproduced on a bare retry in isolation elsewhere in the same session). Three independent occurrences across three different roles/sessions is a real pattern, not noise — worth raising this candidate's priority over the other still-medium-confidence entries.

### 8. Citation-format normalizer
- **Task:** normalize a model's own citation references (`file:x` vs `[file:x]`, near-duplicate URLs, bare non-file tokens like a stray `git`) into the canonical form the quality gate expects, before validation runs.
- **Why dedicated:** the live DAG Engine repository-learning test produced exactly this — the model's final synthesis cited real, correctly-read files using malformed citation syntax, and the quality gate correctly rejected the result rather than publish it. The files WERE read; only the citation string was wrong.
- **Signal already present:** that exact reject event (raw malformed citation → the actual correct file path it should have referenced) is a literal training pair, captured in `Jarvis_notes/Reports/2026-07-24-jarvis-live-capability-test-planning-research-and-canvas-execution.md`.
- **Confidence:** medium-high. Narrow, bounded transformation task; would reduce a real, observed synthesis-reliability failure without touching the underlying research model at all.

---

## How to add an entry
When any plan/phase surfaces a candidate: append a numbered entry in the same shape. Do **not** start building it. If a candidate's training signal is being generated by current work (e.g. approvals, dispatch logs), note that so the data is retained rather than discarded.
