# Mark YAML Frontmatter Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

> **STATUS: ✅ COMPLETE (2026-07-23).** `parse_frontmatter` now uses `yaml.load` with a JSON-typed loader (`_FrontmatterLoader`: timestamp resolver removed, bool restricted to true/false), a `_coerce_loaded_frontmatter` layer (date/datetime→ISO, None→""), and `_legacy_parse_fields` as the `YAMLError` fallback. 30 frontmatter tests (13 characterization + 4 YAML-upgrade + CRLF/flow-list/round-trip). **Verified read-only across all 116 live vault notes: zero round-trip drift, zero integrity errors.** Also fixed block-style YAML lists (Obsidian's property editor writes these; the old parser silently dropped them to `""`) and a latent test-isolation bug where `jm.resolve_config` drops unknown keys, which had made `test_plan_workflow` depend on live LM Studio. Full suite: **562 passed.**

**Goal:** Replace the hand-rolled line-by-line frontmatter parser with a real YAML load, without changing the on-disk format, the stored types, or the `content_hash` of any existing note — removing the whole class of corruption that hit the live vault twice on 2026-07-23.

**Why now:** `parse_frontmatter` is a JSON-per-line reader. It has already caused two live-vault corruptions — CRLF doubling (30 notes) and tag explosion (9 notes) — because it silently mis-parses the exact YAML shapes codex-authored notes use. Both were patched point-wise; this removes the root cause. `core/note_integrity.py` now detects the symptoms, but the parser is still the disease.

---

## The hard constraint: a swap that changes nothing observable

The danger of "just use `yaml.safe_load`" is that YAML is **more** permissive than the current parser, so it changes types and values that the rest of the system depends on. The plan is a *behaviour-preserving* swap.

### What must not change
- **Stored types.** `render_frontmatter` serialises each value with `json.dumps`. YAML coerces aggressively, and those coercions would either break serialisation or silently change data:
  - `review_after: ""` → `""` (must stay a string, not become `null` → dropped).
  - `2026-07-22` → **a `datetime.date` object** (YAML implicit typing) → `json.dumps` raises. Must coerce back to the ISO string.
  - `2026-07-22T01:25:00Z` → possibly a `datetime`. Same.
  - `status: no`, `active: true`, `confidence: 0.8` → YAML makes these bool/float; the current parser keeps `0.8` as float via `json.loads` but `no` as the string `"no"`. Any type flip changes `content_hash` and can change behaviour.
  - `source_version: 9` → int (both agree; keep).
- **`content_hash` stability.** `_content_hash` hashes the *body*, not frontmatter, so it is safe — but `update_note_frontmatter` rewrites frontmatter, and a parse→render→parse round-trip must be idempotent or every note "changes" on next touch, spamming the vault watcher.
- **Leniency.** The current parser never raises; it returns best-effort. `yaml.safe_load` raises on malformed input. A note that "sort of parses" today must not start hard-failing.

*(Risk inventory seeded by a delegated JARVIS analysis 2026-07-23 — it correctly flagged implicit type coercion, timestamp misparsing, and null/empty handling as the top three; this plan adds the downstream `json.dumps` breakage it missed.)*

### Design
1. **Parse** the fence with `yaml.safe_load` inside a `try`; on any `YAMLError`, **fall back** to the current line parser (kept as `_legacy_parse_frontmatter`) so nothing regresses to a hard failure.
2. **Coerce on load** so stored types match today's: `date`/`datetime` → ISO-8601 string; `None` → `""` for known string fields, preserved as `None` otherwise; leave int/float/bool/list/str as-is. One `_coerce_loaded_frontmatter(dict)` function, tested against every field in the shared frontmatter schema.
3. **Normalise line endings first** (the CRLF fix already in place stays).
4. **Round-trip guarantee:** a `parse → render → parse` idempotency test over a corpus of real note shapes.

---

## Tasks

### Task 1: Characterisation tests (lock current behaviour first)
- [ ] Snapshot the *current* `parse_frontmatter` output for a corpus of real shapes drawn from the live vault: quoted JSON lists, unquoted flow lists, empty strings, ISO timestamps, `key: value with: colons`, booleans-looking strings, floats, ints, nested-ish values, BOM, CRLF. These become the contract the new parser must match (after the intended coercions).
- [ ] Run against the vault backup at `scratchpad/vault-backup-*` to harvest real examples.

### Task 2: Coercion layer
- [ ] `_coerce_loaded_frontmatter(data)` — date/datetime→ISO str, None-handling per the schema, everything else pass-through. Tests per type.

### Task 3: The swap with fallback
- [ ] `parse_frontmatter` uses `yaml.safe_load` + coercion; `_legacy_parse_frontmatter` retained as the `YAMLError` fallback. `yaml` is already a dependency (`import yaml` in `dual_orchestrator`, `project_learning`).
- [ ] Every characterisation test from Task 1 passes with the new parser.
- [ ] `parse → render_frontmatter → parse` is idempotent (no drift) across the corpus.
- [ ] Malformed frontmatter falls back, never raises.

### Task 4: Guardrails and rollout
- [ ] `note_integrity.inspect_note` gains a `type_coerced` info finding when a value would change type on re-parse (so a future format drift is visible).
- [ ] Full regression, then a **read-only** `note_integrity.scan_vault` on the live vault (parsing is read-side; no writes) to confirm the new parser reads every existing note cleanly.
- [ ] Optional one-time `scripts/normalise-frontmatter.py --apply` (backup-first, integrity-self-checked like the tier migration) to rewrite any note whose round-trip differs — bringing the whole vault to the canonical form in one audited pass.

---

## Verification
```bash
python -m pytest tests/test_jarvis_memory.py tests/test_note_integrity.py -q
python -m pytest tests -q --ignore=tests/test_process_trace_ui.py --ignore=tests/test_ui_setup_config.py
```
Baseline: **545 passed.** No pre-existing test may need editing except where it asserts a *type* that was previously wrong (document each such change).

**Live:** `jarvis_memory integrity` over the vault stays clean; spot-check that `Project Memory` notes still expose `snapshot_hash`/`project_root` as strings and that dates render as ISO text, not Python objects.

## Non-goals
- No change to the on-disk frontmatter *style* (still `key: <json-ish value>` via `render_frontmatter`).
- No new frontmatter fields or schema changes.
- Not switching `render_frontmatter` to a YAML dumper (that would reflow every note; out of scope).

## Risk table
| Risk | Mitigation |
|---|---|
| YAML coerces a value to a new type, changing `content_hash`/behaviour | Coercion layer + characterisation tests pin every schema field's type |
| Malformed note now hard-fails | `try/except YAMLError` → legacy fallback; test asserts no raise |
| Round-trip drift spams the watcher | Idempotency test; optional one-pass normaliser |
| A value with a date-like string becomes a `date` object | Explicit date/datetime→ISO coercion, tested |
