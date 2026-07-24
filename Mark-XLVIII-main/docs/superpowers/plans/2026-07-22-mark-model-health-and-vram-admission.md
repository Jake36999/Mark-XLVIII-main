# Mark Model Health Probes and VRAM Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MARK's model layer act on two things it currently only declares — whether a model actually works, and how much VRAM it costs.

**Architecture:** Extend `actions/model_lifecycle.py` with a persisted health/cooldown store and a VRAM-budget admission gate, both backed by the existing `.jarvis/model-runtime.sqlite`. Gate model selection in `actions/model_registry.py` and `core/model_router.py` on recorded health. No changes to approval, orchestration, or generation concurrency.

**Tech Stack:** Python 3.11 stdlib, `requests`, `sqlite3` (WAL), `unittest` with the existing `FakeResponse` mock convention.

---

## Context

Two gaps found while reviewing the current implementation against the Developer Handbook:

**1. Nothing measures whether a model works.** `registry_status()` (`actions/model_registry.py:156`) marks a model `available: True` purely because LM Studio lists it. There is no probe anywhere in `actions/model_lifecycle.py`. The functional evaluation recorded a 728-second degraded research run, and Qwen 3.5 9B averaging 111s while "twice returning reasoning without a usable final verdict" — both models remain first choice on their routes, because listing implies health. `Reports/evals/functional/functional-eval-final.md` lists this as prioritised refactor #1; it is still open.

**2. The hardware profile is never read by any scheduling decision.** `MODEL_PROFILES` declares `vram_gb` per model and `config/runtime.json` declares `lmstudio_host_profile` with both GPUs and their exact VRAM. The only consumers of `lmstudio_host_profile` in the entire codebase are `actions/jarvis_memory.py:2683` and `:2835`, where it is used to compose sentences for a research report. The live admission rule is `max_task_models_loaded: 1` — a flat count that ignores whether the model needs 4 GB or 12 GB.

The intended outcome: fail over from a broken model in seconds rather than minutes, and stop paying repeated cold-load cost for models that would comfortably fit alongside each other.

---

## Design Decisions

### Residency is not concurrency

`_lease_connect()` (`actions/model_lifecycle.py:611`) creates `one_active_generation_global`, a unique partial index that permits exactly one active generation across the whole machine. **This plan does not change that.** One generation at a time remains the safety property.

What changes is what may stay *resident*. Today a research turn that alternates between the 4B worker and the embedder pays a full unload/load cycle each time it switches, because the budget is a count of one. With a byte budget, both stay loaded and the turn pays the load cost once.

> The win is eliminating reload thrash, not running models in parallel. State this in the PR description so the change is not mistaken for a concurrency increase.

### Passive telemetry first, active probes second

`_lmstudio_response_text()` (`core/model_router.py:543`) already computes `duration_seconds`, `completion_tokens`, `tokens_per_second` and `first_token_seconds` for every call, streaming and non-streaming — and then discards them. Health scoring therefore needs **persistence and a gate, not new measurement plumbing**.

Real traffic is also a more honest signal than a synthetic probe: a model that passes a 20-token probe can still fail an 8,000-token synthesis. Active probes are the fallback for a cold model with no recent sample, not the primary source.

### Distinguish "model is bad" from "machine was busy"

A timeout while another generation held the lease, an OOM caused by a third-party process, or LM Studio being unreachable are **not** evidence that a model is unreliable. Only attribute failure to a model when the failure is attributable: generation timeout while holding the lease, empty output, malformed structured output, or a load failure specific to that model. Everything else records as `inconclusive` and does not advance the failure counter. Getting this wrong will blacklist working models.

### Measured weights, estimated overhead

The field probe is complete (see Discovery Results below). LM Studio reports `size_bytes` for **every** model, loaded or not, so the largest term in the footprint calculation is measured rather than guessed. The remaining terms — KV cache, compute buffers, runtime overhead — are still estimated, and `quantization.bits_per_weight`, `params_string` and `max_context_length` are all reported to inform that estimate.

`MODEL_PROFILES[*].vram_gb` is retired as an input. It is systematically ~1.7–2× the measured weight size and is wrong in the direction that wastes capacity.

### Mixed-vendor pools do not sum

The host has an NVIDIA GTX 1080 (8.08 GB) and an AMD RX 5500 XT (7.98 GB) under llama.cpp Vulkan. LM Studio owns placement; MARK cannot direct a model to a specific card through the native API. Therefore:

- Track a **total** budget of `sum(vram_gb) - reserve` for aggregate residency.
- Apply a **per-model ceiling** of the largest single card, since one model cannot straddle two devices in the general case.
- Reserve headroom on the primary card for the desktop compositor — a display-attached GPU never has its full nominal VRAM available.

Explicit placement control is out of scope.

---

## Discovery Results (LM Studio field probe — complete)

Ran `scripts/probe-lmstudio-model-fields.py` against the live instance on 2026-07-22. 17 models present, 3 loaded.

**LM Studio reports per model, whether loaded or not:**

```
key, display_name, type, publisher, architecture, format,
size_bytes,                       <- measured weights on disk
params_string,                    <- "4B", "8B", ...
quantization.{name, bits_per_weight},
max_context_length,               <- real ceiling
capabilities.{vision, trained_for_tool_use, reasoning},
variants, selected_variant,
loaded_instances[].{id, config.{context_length, eval_batch_size,
                                parallel, flash_attention,
                                offload_kv_cache_to_gpu}}
```

**This makes admission viable and invalidates four assumptions in `MODEL_PROFILES`.**

| Model | Weights (GB) | Declared `vram_gb` | Real max ctx | Declared ctx |
|---|---:|---:|---:|---:|
| `qwen/qwen3-4b-2507` | 2.33 | 4 | 262144 | 32768 |
| `qwen/qwen3-vl-4b` | 3.10 | 5 | 262144 | 32768 |
| `mistralai/mistral-7b-instruct-v0.3` | 4.07 | 6 | 32768 | 32768 |
| `marco-deepresearch-8b` | 4.47 | 8 | 131072 | 32768 |
| `deepseek-r1-0528-qwen3-8b` | 4.68 | 8 | 131072 | 32768 |
| `google/gemma-4-e4b` | 5.89 | 8 | 131072 | 32768 |
| `qwen/qwen3.5-9b` | 6.10 | 8 | 262144 | 32768 |
| `qwen2.5-14b-deepresearch-i1` | **6.20** | **12** | 131072 | 32768 |

1. **Declared VRAM is roughly double the truth.** The 14B research model's weights are 6.20 GB, not 12 GB. It fits on one 8 GB card with room for a real KV cache — the `offload_kv_cache_to_gpu: false` workaround in its load profile was sized against a number that was never measured. Meaningful headroom is being left on the table.

2. **Declared context windows are understated for nearly every model.** `MODEL_PROFILES` says `32768` almost universally; the truth ranges to 262144. Worse, the uncalibrated fallback in `_profile_for()` declares `8192`, which fails the `min_context: 16000` floor for planner, research and review — so an unprofiled but capable model is silently excluded from exactly the roles it could serve.

3. **`_profile_for()` substring matching mis-resolves a real model.** `qwen3-8b` is present on this machine and resolves to the `deepseek-r1-0528-qwen3-8b` profile, because its key is a substring of DeepSeek's. It therefore inherits `tool_use: False` while LM Studio reports `trained_for_tool_use: True`. This is a live defect, not a hypothetical one.

4. **Declared `tool_use` contradicts LM Studio for the research models.** `marco-deepresearch-8b` and `qwen2.5-14b-deepresearch-i1` are both declared `tool_use: False`; LM Studio reports both as `trained_for_tool_use: True`.

**Also found:** `model_routes.vision` lists `qwen3-vl-30b-a3b-instruct`, which is not installed — the dead fallback flagged as a blocker in `Reports/evals/RAL-final.md` is still advertised. Seven installed models (`unlimited-ocr`, `dag_coding_assistant`, `theorist_version_4`, `dag_theorist`, `dag-llama3`, `qwen3-8b`, both embedding variants) have no profile and fall to the uncalibrated default.

**Consequence for this plan:** a new Part B (profile reconciliation) is inserted, and VRAM admission moves to Part C. Both admission and the quality floors read `MODEL_PROFILES`; building a byte budget on a table this inaccurate would encode the errors rather than fix them.

---

## Non-Goals

- No change to generation concurrency; `one_active_generation_global` stays.
- No change to approval envelopes, workflow compilation, or the dual orchestrator.
- No GPU placement control.
- No change to the credential broker or any speech path.
- No new external dependencies.

---

## Configuration Additions

Add to `config/runtime.json`. Both features ship **disabled** and are switched on after live validation.

```json
{
  "model_health_enabled": false,
  "model_health_probe_enabled": false,
  "model_health_probe_timeout_seconds": 45,
  "model_health_probe_max_tokens": 64,
  "model_health_sample_ttl_seconds": 3600,
  "model_health_failure_threshold": 2,
  "model_health_cooldown_seconds": [300, 900, 3600],
  "model_health_slow_first_token_seconds": 90,

  "vram_admission_enabled": false,
  "vram_reserve_gb": 1.5,
  "vram_safety_margin_ratio": 0.15,
  "vram_kv_cache_bytes_per_token": 131072
}
```

`core/runtime_config.py` rejects secret-looking fields on serialization — none of these trip that check, but re-run its tests after editing the file.

---

## Part A — Model Health and Cooldown ✅ COMPLETE (2026-07-22)

**Delivered:** persisted `model_health` table in the existing `.jarvis/model-runtime.sqlite`, passive telemetry from every LM Studio call, a bounded active probe, health-gated selection, and cooldown visibility in status, Operations, and the process trace. 39 new tests across `tests/test_model_lifecycle.py` and `tests/test_model_router.py`.

Verified live against the running instance:

- Probe of `qwen/qwen3-4b-2507` returned `ready` in 4.6s, recorded `healthy` with `source: probe`; the second call correctly skipped with `reason: recent_sample`; no lease leaked.
- Two simulated timeouts put `deepseek-r1-0528-qwen3-8b` into cooldown (`timeout x2; cooling down for 299s`). It disappeared from the conversational candidate chain, and `select_for_role` moved to `qwen/qwen3.5-9b` while reporting `cooling_down: ['deepseek-r1-0528-qwen3-8b']`.

**Design decision not in the original plan — asymmetric degradation.** `select_lmstudio_models` (conversational routing) filters cooling-down models but **never returns an empty list**: if every candidate is cooling down it preserves the original order and proceeds, because a chat turn still needs an answer. `select_for_role` (which gates START PLAN via `plan_workflow.py:1414`) does the opposite and fails with an explicit reason naming the cooling-down models. This matches the Handbook 07 rule that a workflow pauses rather than silently downgrading, while keeping the assistant usable when everything is degraded.

**Also note:** `registry_status` now separates `installed` (inventory) from `available` (measured selectability). `select_for_role`'s existing `available` filter therefore picks up health gating without further change.

**Regression:** 384 collected (315 original baseline + 19 Part B + 50 Part A). Non-Qt configuration: **376 passed, 1 failed** — the same pre-existing `test_plan_workflow` bundle-path bug documented under Part B. No pre-existing test was modified.

**Now enabled.** `model_health_enabled` and `model_health_probe_enabled` are both `true` in `config/runtime.json` as of 2026-07-22. `load_runtime_config()` reads from disk on every call and `main.py` never caches it, so no restart was required.

### Probe wiring (follow-up, complete)

The probe is reachable two ways:

1. **On demand** — `model_lifecycle` gained `probe` and `model_health` operations, declared in `main.py:TOOL_DECLARATIONS`, so JARVIS can check a model before committing to a long job.
2. **On cold selection** — `select_for_role(..., probe=True)`, wired into `plan_workflow.approve_plan` (`actions/plan_workflow.py:1416`). START PLAN is deliberate and already slow, so a bounded probe is proportionate there; conversational turns are never probed.

Guards: at most `MAX_COLD_PROBES = 2` probes per selection; the probe waits only `health_probe_wait_seconds` (default 5) for the generation lease and skips rather than blocking a busy machine; a skipped probe is not a failure; probe-subsystem errors never block selection.

**Live probing found a real defect on this host.** `qwen/qwen3.5-9b` returns `empty_output` to the probe — it emits reasoning tokens with no final content, exactly the failure `Reports/evals/RAL-final.md` recorded as "twice returned reasoning without a usable final verdict". Selection failed over to `qwen2.5-14b-deepresearch-i1`, which probed clean. This is the 728-second failure mode being caught in seconds, on a cold model, before any workflow committed to it.

**Bug found by that same live run and fixed.** A single probe failure leaves `consecutive_failures = 1`, below the cooldown threshold, so the model stayed `available` with state `failing` — and the original fast path treated any non-`unknown`/`stale` state as measured-good, handing the just-failed model straight back on the next call. Two fixes: only `healthy` and `degraded` count as measured-good (`MEASURED_GOOD_STATES`), and health is now a sort key (`_HEALTH_RANK`) so a measured-good model outranks an equally-specified failing peer. Both are regression-tested.

**Test isolation:** `tests/test_plan_workflow.py` `cfg()` now sets both health flags to `false`. START PLAN can run a live probe, and those tests must not depend on a running LM Studio or write to the real health store.

**Regression after probe wiring:** 397 collected; **393 passed, 1 failed** — the same pre-existing `test_plan_workflow` bundle-path bug.

### Original task list

### Task A1: Health store tests

**Files:**
- Modify: `tests/test_model_lifecycle.py`

- [x] **Step 1: Write failing tests**

Follow the existing `FakeResponse` / `lifecycle_config()` conventions at the top of the file. Point `model_runtime_db_path` at a temp file per test, as `lifecycle_config()` already does.

Cover:
- recording a success clears `consecutive_failures` and stores latency;
- two attributable failures (threshold) set `cooldown_until` in the future;
- a third failure escalates to the next backoff tier;
- an `inconclusive` outcome does **not** advance the failure counter;
- `health_snapshot()` reports a model as cooling down until the deadline passes, then as eligible again;
- a sample older than `model_health_sample_ttl_seconds` is reported as `stale`, not `healthy`;
- the table is created on a fresh database and survives a second connection (cross-process durability).

- [x] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_model_lifecycle.py -q
```

Expected: fails, no health API exists.

### Task A2: Health store implementation

**Files:**
- Modify: `actions/model_lifecycle.py`

- [x] **Step 1: Extend the schema**

Add to the `executescript` block inside `_lease_connect()` (line ~622) so it is created by the same bootstrap that already handles WAL, `busy_timeout`, and the `_initialized_lease_dbs` guard:

```sql
CREATE TABLE IF NOT EXISTS model_health (
    model TEXT PRIMARY KEY,
    last_outcome TEXT NOT NULL,
    last_checked_at REAL NOT NULL,
    last_source TEXT NOT NULL,          -- 'passive' | 'probe'
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    cooldown_until REAL,
    ewma_first_token_seconds REAL,
    ewma_tokens_per_second REAL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
```

Additive DDL inside an existing `CREATE TABLE IF NOT EXISTS` script needs no migration path — matching how the lease tables already bootstrap.

- [x] **Step 2: Implement the API**

```python
def record_model_outcome(model, *, outcome, source="passive", metrics=None,
                         error="", cfg=None) -> dict
def model_health(model, *, cfg=None) -> dict
def health_snapshot(cfg=None) -> dict
def is_model_cooling_down(model, *, cfg=None) -> tuple[bool, str]
```

`outcome` is one of `ok`, `timeout`, `empty_output`, `malformed_output`, `load_failed`, `inconclusive`. Only the four attributable failures advance `consecutive_failures`. Backoff reads `model_health_cooldown_seconds` by index, clamped to the last tier. A success zeroes the counter and clears `cooldown_until`. EWMA smoothing factor 0.3 over `first_token_seconds` and `tokens_per_second`.

Treat a first-token time above `model_health_slow_first_token_seconds` as a `degraded` observation — recorded and surfaced, but not itself a failure.

- [x] **Step 3: Run tests**

```bash
python -m pytest tests/test_model_lifecycle.py -q
```

### Task A3: Wire passive telemetry

**Files:**
- Modify: `core/model_router.py`
- Modify: `tests/test_model_router.py`

- [x] **Step 1: Write failing tests**

Assert that a completed LM Studio call records `ok` with its metrics, a timeout records `timeout`, an empty response records `empty_output`, and that a failure occurring **while waiting for a lease** records `inconclusive`.

- [x] **Step 2: Implement**

In `_call_lmstudio_chat` (line ~633) and the tool-call variants, call `record_model_outcome()` at the same point the generation lease is released — the metrics dict returned by `_lmstudio_response_text()` maps directly onto the `metrics` argument. Wrap in `try/except` and swallow: **health recording must never fail a working generation.**

- [x] **Step 3: Run tests**

```bash
python -m pytest tests/test_model_router.py tests/test_model_lifecycle.py -q
```

### Task A4: Bounded active probe

**Files:**
- Modify: `actions/model_lifecycle.py`
- Modify: `tests/test_model_lifecycle.py`

- [x] **Step 1: Write failing tests**

A probe runs only when there is no sample newer than `model_health_sample_ttl_seconds`; it respects `model_health_probe_timeout_seconds`; a probe returning empty text records `empty_output`; a probe is skipped entirely when `model_health_probe_enabled` is false.

- [x] **Step 2: Implement `probe_model()`**

Small fixed prompt with a deterministic expected shape (e.g. `Reply with the single word: ready`), `max_tokens` from config, hard timeout, non-streaming. Acquire a generation lease like any other call — a probe must not bypass the concurrency guarantee. Record the outcome through `record_model_outcome(source="probe")`.

- [x] **Step 3: Run tests**

### Task A5: Gate selection on health

**Files:**
- Modify: `actions/model_registry.py`
- Modify: `core/model_router.py`
- Modify: `tests/test_model_registry.py` (create if absent)

- [x] **Step 1: Write failing tests**

- `registry_status()` includes `health`, `cooldown_until` and `last_error` per model.
- `select_for_role()` skips a cooling-down model and picks the next candidate.
- `select_lmstudio_models()` returns the fallback chain with cooling-down entries removed.
- **When every candidate for a route is cooling down, the result is an explicit failure, not a silent downgrade below the role's quality floor.** This upholds the Handbook 07 rule that a workflow pauses rather than quietly degrading.
- With `model_health_enabled: false`, behaviour is byte-for-byte unchanged.

- [x] **Step 2: Implement**

In `registry_status()` (line ~156), merge `health_snapshot()` into each record so `available` reflects measured state rather than mere listing. In `select_for_role()` (line ~211), drop cooling-down candidates before the sort. In `select_lmstudio_models()` (`core/model_router.py:218`), filter the assembled candidate list.

- [x] **Step 3: Run focused then full suite**

```bash
python -m pytest tests/test_model_registry.py tests/test_model_router.py tests/test_model_lifecycle.py -q
python -m pytest tests -q --ignore=tests/test_process_trace_ui.py --ignore=tests/test_ui_setup_config.py
```

### Task A6: Surface health in status and trace

**Files:**
- Modify: `actions/model_lifecycle.py` (the `status` operation, line ~966)
- Modify: `core/operations_state.py`

- [x] **Step 1: Add health to `model_lifecycle.status`**

So `model_lifecycle.status` — the documented health check in Handbook 08 — reports cooldown state and observed latency alongside loaded instances.

- [x] **Step 2: Emit a process event on cooldown entry**

Category `model`, severity reflecting degradation, summary naming the model and reason. `core/process_events.py` already redacts prompts and secrets; a model name and failure class are safe operational metadata. This makes fail-over visible in the Router trace instead of silent.

- [x] **Step 3: Run tests**

```bash
python -m pytest tests/test_process_events.py tests/test_model_lifecycle.py -q
```

---

## Part B — Profile Reconciliation ✅ COMPLETE (2026-07-22)

Fix the table that both admission and the quality floors depend on. Small, self-contained, and independently valuable — the `qwen3-8b` mis-resolution is a live defect regardless of the rest of this plan.

**Delivered:** `tests/test_model_registry.py` (19 tests, all passing), exact-match profile resolution, LM Studio-reported capability precedence with field provenance, route inventory diagnostics, and the dead vision route removed. Verified live against the running instance: `qwen3-8b` resolves to its own profile, the research models report tool-capable, and route diagnostics return `checked: 22, missing: []`.

**Regression:** 334 collected (315 baseline + 19 new). In the standard non-Qt configuration, 327 collected → **326 passed, 1 failed**. No pre-existing test was modified.

The single failure is `tests/test_plan_workflow.py::PlanWorkflowTests::test_user_edit_pauses_stale_run_and_survives_versioned_resume`, which is **pre-existing and unrelated** — that test file contains no reference to `model_registry`, and the traceback terminates in `_validate_plan_bundle` (`actions/plan_workflow.py:967`) before `select_for_role` is imported at line 1414. Root cause: after `revise_plan`, `metadata["run_bundle"]` is empty, so `Path("")` becomes `Path(".")`; `Path(".").exists()` is `True`, which defeats the missing-bundle guard on the following line, and the read of a relative `work-items.json` raises `FileNotFoundError` instead of returning the intended "The plan run bundle is missing" error. Tracked separately from this plan.

**Deviation from plan:** `vram_gb` and `context_window` were **not** stripped from `MODEL_PROFILES` (Task B2, step 2). `scripts/ral-evaluate.py:256` and `tests/test_red_team_eval.py:37` read profile dicts generically, and `test_every_configured_local_model_has_a_capability_profile` asserts every routed model has an entry. The fields are now inert — `registry_status()` overrides them with reported values and Task C1 reads `size_bytes` instead — so removing them is cosmetic and was not worth breaking two consumers. Left in place as documentation.

### Task B1: Exact-match profile resolution

**Files:**
- Modify: `actions/model_registry.py`
- Create: `tests/test_model_registry.py` (if Task A5 has not already created it)

- [x] **Step 1: Write failing tests**

- `_profile_for("qwen3-8b")` does **not** return the `deepseek-r1-0528-qwen3-8b` profile.
- Exact key match wins; explicit alias match is second; no match returns the uncalibrated default.
- A model whose key is a strict substring of another model's key resolves to its own profile or to the default — never to the longer key's profile.

- [x] **Step 2: Replace bidirectional substring matching**

`_profile_for()` (line ~125) currently does `if normalize_model_id(key) in normalized or normalized in normalize_model_id(key)`. Replace with exact match on the normalized key, then an explicit `MODEL_ALIASES` dict for known variant spellings (e.g. `@q4_k_m` suffixes), then the default. Keep `normalize_model_id()` as-is.

- [x] **Step 3: Run tests**

### Task B2: Derive capabilities from LM Studio

**Files:**
- Modify: `actions/model_registry.py`
- Modify: `tests/test_model_registry.py`

- [x] **Step 1: Write failing tests**

- `registry_status()` uses `max_context_length` from LM Studio in preference to the declared `context_window`.
- It uses `capabilities.trained_for_tool_use` in preference to the declared `tool_use`, so `marco-deepresearch-8b` and `qwen2.5-14b-deepresearch-i1` are correctly reported as tool-capable.
- It uses `capabilities.vision` rather than inferring vision from the role list.
- A model with **no** profile still gets its real reported context and capabilities, so it is no longer failed by `min_context` on a fabricated `8192`.
- `structured_output` remains hand-declared — LM Studio does not report it, and it is the one field that genuinely requires calibration.

- [x] **Step 2: Implement**

In `registry_status()` (line ~156), merge reported fields over declared ones when building each record. Record which fields were reported and which were declared, so `select_for_role()` failure reasons stay diagnosable.

Strip `vram_gb` and `context_window` from `MODEL_PROFILES` once nothing reads them; leave `roles`, `structured_output`, `parallel_capacity` and `known_failures`, which remain hand-curated judgements.

- [x] **Step 3: Run tests**

### Task B3: Prune the dead vision route

**Files:**
- Modify: `config/runtime.json`
- Modify: `actions/model_registry.py`
- Modify: `tests/test_model_registry.py`

- [x] **Step 1: Write a failing test**

Capability health reports a configured-but-absent model as unavailable rather than advertising it as a usable fallback.

- [x] **Step 2: Remove `qwen3-vl-30b-a3b-instruct` from `model_routes.vision`**

It is not installed. `Reports/evals/RAL-final.md` lists resolving-or-removing it as prioritised next step #5; this closes it. Add a startup diagnostic that reports any route entry absent from LM Studio's inventory, so the next dead route surfaces on its own.

- [x] **Step 3: Run tests**

---

## Part C — VRAM Admission

Land Parts A and B first: A's telemetry is what proves C did not make things worse, and B is what C reads.

### Task C1: Footprint estimation

**Files:**
- Modify: `actions/model_lifecycle.py`
- Modify: `tests/test_model_lifecycle.py`

- [ ] **Step 1: Update the test fixture**

`models_payload()` in `tests/test_model_lifecycle.py` omits most real fields. Extend it to match the live shape recorded in Discovery Results — `size_bytes`, `params_string`, `quantization`, `max_context_length`, `capabilities`. Existing tests must still pass against the enriched fixture.

- [ ] **Step 2: Write failing tests**

- Footprint = `size_bytes` + KV-cache estimate + overhead, times `(1 + vram_safety_margin_ratio)`.
- KV estimate uses the resolved `context_length` from `load_profile_for()`, not `max_context_length` — a model loaded at 4096 does not reserve cache for 262144.
- KV cache is excluded when the load profile sets `offload_kv_cache_to_gpu: false` (currently `qwen2.5-14b-deepresearch-i1`).
- A model missing `size_bytes` returns `None` and is treated as **unknown-and-large**, not as zero.
- Sanity anchor: `qwen/qwen3-4b-2507` at 4096 context estimates well under 4 GB; `qwen2.5-14b-deepresearch-i1` at 8192 estimates under the 8 GB per-model ceiling.

- [ ] **Step 3: Implement `estimate_model_footprint_gb(model, cfg, *, listed=None)`**

Read `size_bytes` from the `list_models()` payload — no extra HTTP call, the data is already fetched on the `ensure_model_loaded` path. Reuse `load_profile_for()` (line ~271) for effective context length and the KV flag. Use `quantization.bits_per_weight` and `params_string` to refine the KV term rather than a flat per-token constant.

> `vram_gb` is no longer read, so the `model_registry` ↔ `model_lifecycle` import-cycle risk noted earlier is resolved by construction. Confirm no import of `MODEL_PROFILES` is added here.

- [ ] **Step 4: Run tests**

### Task C2: Budget and admission

**Files:**
- Modify: `actions/model_lifecycle.py`
- Modify: `tests/test_model_lifecycle.py`

- [ ] **Step 1: Write failing tests**

- `vram_budget(cfg)` derives total and per-model-ceiling from `lmstudio_host_profile.gpus` minus `vram_reserve_gb`.
- A model larger than the largest single card is rejected with a clear reason even if the total would fit.
- `admit(model)` returns `fits` when resident total plus footprint is within budget.
- `admit(model)` returns an eviction list when it does not fit.
- Baseline models are never proposed for eviction.
- A model holding an active generation lease is never proposed for eviction.
- An unknown footprint forces the current conservative behaviour (evict to one task model) rather than optimistic admission.

- [ ] **Step 2: Implement**

```python
def vram_budget(cfg=None) -> dict
def resident_footprint(cfg=None, *, get=requests.get) -> dict
def admit(model, *, route="main", cfg=None, get=requests.get) -> dict
def plan_eviction(model, *, cfg=None, get=requests.get) -> list[dict]
```

Eviction order: least-recently-used first, using `last_checked_at` from `model_health` as the recency signal — another reason Part A lands first. Cross-check active leases via `persistent_generation_snapshot()` (line ~851).

- [ ] **Step 3: Run tests**

### Task C3: Gate the load path

**Files:**
- Modify: `actions/model_lifecycle.py`
- Modify: `tests/test_model_lifecycle.py`

- [ ] **Step 1: Write failing tests**

- With `vram_admission_enabled: false`, `ensure_model_loaded` behaves exactly as today (the existing tests must pass untouched — do not edit them to fit new behaviour).
- With it enabled and budget available, a second task model loads **without** unloading the first.
- With it enabled and budget exhausted, only the specific evictees are unloaded — not every non-baseline model.
- `max_task_models_loaded` still applies as a hard ceiling.
- A load failure whose body indicates insufficient memory records `load_failed` health **and** logs the footprint estimate versus budget, so a wrong estimate is diagnosable.

- [ ] **Step 2: Implement**

Replace the check at `actions/model_lifecycle.py:443`:

```python
if route_kind == "task" and listed["task_loaded_count"] >= int(cfg["max_task_models_loaded"]):
    cleanup = unload_non_baseline(...)
```

with an admission call that returns a targeted eviction list, falling back to the current `unload_non_baseline` behaviour when admission is disabled or the footprint is unknown. Add `evict_instances(instance_ids, ...)` beside `unload_non_baseline` (line ~899) rather than modifying it — `cleanup_idle` and the idle loop depend on its current semantics.

Raise the `max_task_models_loaded` default to `2` **only** in the follow-up config change after live validation, not in this task.

- [ ] **Step 3: Run tests**

### Task C4: Report the budget

**Files:**
- Modify: `actions/model_lifecycle.py` (`status`, line ~966)
- Modify: `core/operations_state.py`
- Modify: `tests/test_model_lifecycle.py`

- [ ] **Step 1: Add budget to status and Operations**

Report total budget, resident footprint, headroom, and whether each figure is measured or estimated. Never present an estimate as measured — the same honesty rule the Operations rail already follows for service state.

- [ ] **Step 2: Run tests**

---

## Documentation

- [ ] Update `Jarvis_notes/User Guide/Developer Handbook/07 Models Credentials Speech and Resource Lifecycle.md` — health probes, cooldown, and the byte budget replacing the flat count.
- [ ] Update `Jarvis_notes/User Guide/Developer Handbook/09 Implementation Log and Known Boundaries.md` — move "local hardware is capacity-constrained" from a flat-policy statement to a budgeted one, and record the new test count.
- [ ] Update `Jarvis_notes/User Guide/Developer Handbook/08 Storage Configuration and Operations.md` — the new `model_health` table and config keys.
- [ ] Follow the Handbook 09 "Change Discipline" steps: update notes, run focused tests, run the full suite, reindex the vault, then query the changed subsystem through `jarvis_memory.query_local` to confirm JARVIS can retrieve the new contract.

---

## Verification

**Automated**

```bash
python -m pytest tests/test_model_lifecycle.py tests/test_model_router.py tests/test_model_registry.py -q
python -m pytest tests -q --ignore=tests/test_process_trace_ui.py --ignore=tests/test_ui_setup_config.py
```

Baseline before starting is **315 collected**. Every pre-existing test must still pass unmodified; a pre-existing test that needs editing to accommodate this work is a signal the change went further than intended.

**Live, with LM Studio running and both flags enabled**

1. **Health fail-over.** Point a route's first model at a deliberately bad id or set its probe timeout to 1s. Confirm the router fails over within seconds, the trace shows a cooldown event, and `model_lifecycle.status` reports the cooldown deadline. Confirm it becomes eligible again after the deadline.
2. **No false blacklisting.** Run a normal research turn to completion. Confirm the research model's `consecutive_failures` stays 0 and a lease wait never records an attributable failure.
3. **Profiles reflect reality.** Re-run `scripts/probe-lmstudio-model-fields.py` and confirm `_profile_for("qwen3-8b")` no longer returns DeepSeek's profile, that the research models report as tool-capable, and that no installed model is failed by a fabricated `8192` context.

4. **Residency win.** With admission enabled, run a turn that uses the 4B worker and then the embedder. Confirm both are resident simultaneously and the second use logs `already_loaded: True` rather than a load. This is the headline result — capture before/after timings.
5. **Budget respected.** Request the 14B research model while the worker is resident. Confirm targeted eviction of only what is needed, that the baseline and Orpheus survive, and that LM Studio does not report an OOM.
6. **The 14B fits properly.** With measured footprint in place, try `qwen2.5-14b-deepresearch-i1` with `offload_kv_cache_to_gpu: true` at 8192 context — the estimate says 6.20 GB of weights leaves room on an 8 GB card. If it holds, the workaround in its load profile can be retired and research generation should speed up materially. If it OOMs, keep the workaround and record the real ceiling.
7. **Concurrency unchanged.** Confirm `persistent_generation_snapshot()` still shows at most one active generation throughout, and that `one_active_generation_global` was never dropped.
8. **Clean shutdown.** Run `model_lifecycle.unload_non_baseline`; confirm only `qwen/qwen3-4b-2507` and `orpeus_text_to_speech` remain, matching the state every prior validation run closed on.

**Rollback:** set `model_health_enabled` and `vram_admission_enabled` to `false`. Both features are additive and read-only when disabled; the `model_health` table can be left in place.

---

## Risks

| Risk | Mitigation |
|---|---|
| A wrong footprint estimate causes an OOM that looks like a model fault | Log estimate vs. budget on every load failure; classify LM Studio OOM as `inconclusive`, never as model failure |
| Transient failures blacklist a good model | Only attributable outcomes count; threshold of 2; success clears immediately; cooldown is time-boxed, never permanent |
| Two resident models slow generation through memory pressure | Concurrency is unchanged at one; measure tokens/sec before and after in live check 3 and revert the budget if throughput drops |
| Import cycle between `model_registry` and `model_lifecycle` | Resolved by construction: C1 reads `size_bytes` from the LM Studio payload and never imports `MODEL_PROFILES`. Verify no such import appears in the diff |
| Part B changes which models pass a quality floor | Real reported context/capabilities are strictly more accurate than the fabricated ones; run the full suite and re-check `select_for_role` output per role before and after |
| Scope creep into placement control or parallel generation | Explicit non-goals; `one_active_generation_global` must survive the diff untouched |

---

## Why this file lives here

`Jarvis_notes/Plans` is owned by `plan_workflow` — those notes carry executable work-item tables, approval projections and hashes, and "start plan" resolves the latest one. A hand-authored file there could be picked up by that machinery. `docs/superpowers/plans/` is the existing convention for engineering plans written for a human or coding agent to execute, alongside `2026-07-06-mark-model-provider-split.md` and `2026-07-06-mark-project-operator.md`.
