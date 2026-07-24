# Mark VRAM-Aware Model Admission

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the flat `max_task_models_loaded: 1` admission rule with a **byte budget** derived from measured model footprints and the real two-GPU VRAM, so models that genuinely fit can be co-resident — eliminating reload thrash without ever risking an OOM. This is the headline capability the project is named for and the last major model-layer item.

**Status:** Supersedes Part C of `2026-07-22-mark-model-health-and-vram-admission.md`, refined now that its Parts A (health store) and B (profile reconciliation) have shipped and are enabled.

---

## What has changed since the original design (all now true)
- **`size_bytes` is available per model, loaded or not.** Confirmed live via `scripts/probe-lmstudio-model-fields.py`. The largest footprint term is measured, not guessed. `MODEL_PROFILES.vram_gb` is retired (it was ~2× the truth).
- **The health store exists** (`model_health` table). Eviction ordering can use its `last_checked_at` for LRU — no new recency mechanism.
- **Profiles are reconciled** — reported context/capabilities already override the declared table, so admission reads trustworthy data.

## Design decisions (unchanged and load-bearing)
- **Residency ≠ concurrency.** `one_active_generation_global` (one generation at a time, machine-wide) is **not touched**. The win is eliminating unload/reload thrash when a turn alternates models (e.g. worker → embedder), not parallel inference. Say this in the PR.
- **Mixed-vendor pools do not sum.** GTX 1080 (8.08 GB) + RX 5500 XT (7.98 GB) under Vulkan. Track a **per-card** budget and a **per-model ceiling = largest single card**; a model cannot straddle cards. Reserve headroom on the display-attached card for the compositor. LM Studio owns placement; MARK cannot pin a card, so admission is advisory-conservative.
- **Measured weights, estimated overhead.** Footprint = `size_bytes` + KV-cache estimate (from resolved `context_length` and the `offload_kv_cache_to_gpu` flag) + a safety margin. Never let an estimate override a measured value; an unknown footprint is treated as unknown-and-large, never zero.

## Config (ships disabled)
```json
{
  "vram_admission_enabled": false,
  "vram_reserve_gb": 1.5,
  "vram_safety_margin_ratio": 0.15,
  "vram_kv_cache_bytes_per_token": 131072
}
```
`lmstudio_host_profile` (already in `runtime.json`, currently only read to write report prose) becomes the budget source.

---

## Tasks

### Task 1: Footprint estimation
- [ ] `estimate_model_footprint_gb(model, cfg, *, listed=None)` in `actions/model_lifecycle.py`. Reads `size_bytes` from the `list_models` payload already fetched on the load path (no extra HTTP). KV term from `load_profile_for` context length + `bits_per_weight`; excluded when `offload_kv_cache_to_gpu` is false (the 14B's current workaround).
- [ ] Tests: measured preferred over declared; unknown `size_bytes` → `None` (unknown-and-large); the 14B at 8192 ctx estimates under the 8 GB per-model ceiling; the 4B at 4096 well under 4 GB. Enrich the `models_payload()` fixture to the real shape (`size_bytes`, `quantization`, `params_string`, `max_context_length`).
- [ ] **No `MODEL_PROFILES` import** — resolves the old cycle risk by construction.

### Task 2: Budget and admission
- [ ] `vram_budget(cfg)` — per-card and total from `lmstudio_host_profile.gpus` minus `vram_reserve_gb`; per-model ceiling = largest card.
- [ ] `resident_footprint(cfg)` — sum of currently-loaded model footprints.
- [ ] `admit(model, route, cfg)` → `fits` when resident + footprint ≤ budget; else an eviction list.
- [ ] `plan_eviction(model, cfg)` — LRU by `model_health.last_checked_at`; **never** evicts a baseline or a model holding an active generation lease (cross-check `persistent_generation_snapshot`).
- [ ] Tests: a model larger than the largest card is rejected even if the total fits; unknown footprint falls back to the current conservative "evict to one task model"; baseline/leased models never proposed.

### Task 3: Gate the load path
- [ ] Replace the `task_loaded_count >= max_task_models_loaded → unload_non_baseline` check in `ensure_model_loaded` with an admission call returning a *targeted* eviction list. Add `evict_instances(...)` beside `unload_non_baseline` (don't change the latter — `cleanup_idle`/idle loop depend on it).
- [ ] With `vram_admission_enabled: false`, behaviour is byte-for-byte today (existing lifecycle tests pass unedited).
- [ ] With it enabled and budget available, a second task model loads **without** unloading the first; when exhausted, only the specific evictees are unloaded.
- [ ] A load failure whose body indicates insufficient memory logs the footprint estimate vs budget and records `load_failed` health, so a wrong estimate is diagnosable and is classified as an instrument issue, not a model fault.

### Task 4: Report the budget
- [ ] `model_lifecycle.status` and `core/operations_state` report total/per-card budget, resident footprint, headroom, and whether each figure is measured or estimated (never present an estimate as measured).

---

## Verification
```bash
python -m pytest tests/test_model_lifecycle.py tests/test_model_router.py -q
python -m pytest tests -q --ignore=tests/test_process_trace_ui.py --ignore=tests/test_ui_setup_config.py
```

**Live (LM Studio up, flag on):**
1. **Residency win (headline):** a turn using the 4B worker then the embedder keeps both resident; the second use logs `already_loaded: True`, not a reload. Capture before/after timings.
2. **Budget respected:** request the 14B while the worker is resident → targeted eviction of only what's needed; baseline + Orpheus survive; no OOM.
3. **The 14B fits properly:** retry `qwen2.5-14b-deepresearch-i1` at 8192 ctx with `offload_kv_cache_to_gpu: true` — 6.20 GB of weights should leave room on an 8 GB card. If it holds, retire the KV-offload workaround and research generation speeds up. If it OOMs, keep the workaround and record the real ceiling.
4. **Concurrency unchanged:** `persistent_generation_snapshot` shows ≤1 active generation throughout; `one_active_generation_global` never dropped.

**Rollback:** `vram_admission_enabled: false`.

## Risk table
| Risk | Mitigation |
|---|---|
| Wrong estimate → OOM that looks like a model fault | Log estimate vs budget on load failure; classify LM Studio OOM as `inconclusive`, never model failure |
| Two resident models slow generation via memory pressure | Concurrency unchanged at one; measure tokens/sec before/after in live check 1; revert budget if throughput drops |
| Mistaken as a concurrency increase | Non-goal stated everywhere; `one_active_generation_global` must survive the diff untouched |
| Scope creep into GPU placement | Out of scope; LM Studio owns placement, admission is advisory |
