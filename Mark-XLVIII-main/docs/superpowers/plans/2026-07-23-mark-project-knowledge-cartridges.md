# Mark Project Knowledge Cartridges

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Design/scoping doc — build **after** the YAML frontmatter hardening lands and the folder/topic-learning assessment is run. Steps use `- [ ]`.

**Goal:** Give JARVIS project- and topic-scoped memory "cartridges" — isolated knowledge that is quarantined until contextually relevant — while keeping one always-loaded general space that holds the *map* (indexes, overviews, recent-event logs) of everything. Directed dives mount a cartridge; general operation never drags a project's full detail into unrelated turns.

---

## Grounding: what `D:\remember_me` (Mnemosyne) already proved

The owner's prior system, `project-Mnemosyne-main`, implemented this pattern end-to-end. The load-bearing patterns to **adopt**:

1. **Collections = cartridges.** Notes and documents are grouped into collections; retrieval scopes by `collection_id`. Notably, Mnemosyne used **namespacing within one store** (a `collection_id` filter), *not* separate physical indexes. That is strong evidence the cheaper design is sufficient — see the storage decision below.
2. **A memory-type classifier is the router.** `MemoryClassifier` sorts extracted facts into `episodic` / `semantic` / `preference`, and **only semantic + preference are durable** ("trainable"); episodic is transient. This is exactly the *recent-event-log vs durable-knowledge* split — already solved. The classifier *is* the "automated inference check."
3. **A condenser extracts atomic facts** (entity / relation / attribute / event) before classification — the granular version of MARK's consolidation.

What to **defer** (not reject):
- Mnemosyne fine-tunes a **per-user LoRA adapter** on semantic+preference facts. MARK's *near-term* "get smarter over time" is model-swapping + consolidation + retrieval routing — **do not build a training pipeline in this plan.** But fine-tuning is a real future direction: the owner intends to train **small dedicated tooling/utility sub-agents** (not large models locally — compute too high, and data synthesis is still R&D) via the `F:\knowledge_compiler_engine (DAG Engine)` stack. So the cartridge is a retrieval container *for now*; its condensed, classified facts are also exactly the shape of training data. **Standing instruction: whenever a phase surfaces a place where a small dedicated agent could be trained, or where we could generate a training DAG to support JARVIS or a skill, log it in `docs/superpowers/dag-training-opportunities.md` — do not build it, just capture it.**

External references (owner-supplied, consult during build): **cocoindex** (incremental index kept in sync with source — the cartridge watcher pattern), **context-mode** (context-window mount/unmount budgeting), **UltraRAG** (per-cartridge pipeline construction), **dzhng/deep-research** & **deer-flow** (the deep-research expansion function; sandbox only for high models / OpenClaw), **composio** (long-horizon context management).

---

## First: reconcile the two "tier" words (do this before anything else)

I shipped `memory_tier: short_term | long_term | archive` (a **lifecycle** axis) to the live vault on 2026-07-23. The owner's structure uses "tier" for a **structural 0–4** axis. Two meanings for one word is a latent trap.

**Resolution:** the structural 0–4 becomes the authoritative "tier"; rename the frontmatter field `memory_tier` → `lifecycle`. They compose as orthogonal axes and **unify at the archive end** (`lifecycle: archive` ≡ Tier 4). This rename is Task 1 — it touches a field already live, so it needs the backup-first, integrity-self-checked migration discipline (and the YAML hardening should land first so the rewrite is safe).

### The structural tiers → MARK components

| Tier | Role | RAG | Maps to |
|---|---|---|---|
| **0** control plane | routing config, background fns | no | `.jarvis/`, dual-orchestrator YAML, `project_registry.json` + a new selector config |
| **1** general categories | top-level knowledge-role folders | general container | new deliberate taxonomy (today folders are by note-type) |
| **2** index / overview / **event log** | the always-loaded *map* | general container | MOCs + Project Memory + the `vault_activity` journal (**= the episodic event log**) |
| **3** project knowledge | per-project **cartridge** | own container | NEW — the real build |
| **4** archive | user-only | **omitted** | `lifecycle: archive` + `rag_index: false` |

The general container indexes Tiers 1–2 only: enough for JARVIS to know every project exists, its shape, and its recent activity — never the detail. Detail lives in Tier 3 and loads on a directed dive.

---

## Architecture

**Two retrieval scopes, always:**
- **General** (Tiers 1–2) — always mounted. Overviews, indexes, and a bounded per-project **event log** (sourced from the `vault_activity` journal, not free text, so it cannot itself drift).
- **Cartridge(s)** (Tier 3) — mounted per turn/plan by the selector. A turn declares its mounted set → "one project or multiple" is just the size of that set.

**The selector, in build order (never learned-first — it mis-routes silently):**
1. **Explicit** — the turn/plan names the project → mount it. Ships immediately, always reliable.
2. **Registry-confidence** — match the query against project registry metadata (name, aliases, key terms) with a threshold: above → auto-mount; below → *ask*. This is Mnemosyne's classifier idea applied to routing.
3. **Learned** (later, earned) — embedding-match against cartridge centroids.

**Provisioning:** the `vault_watch` watcher (already hardened) gains a "new project folder → provision a cartridge" hook. Building it embeds the project with the warm Nomic baseline; because embedding is a baseline model it won't fight the one-task-model slot. The build emits `ProcessEvent`s so the user **sees it happen** (the trace UI already renders these) — directly answering the UX ask.

**The knowledge-expansion flow (the payoff, via dual-orchestrator):** a `knowledge_expansion` workflow — YAML + Python hooks — that: selects/mounts the cartridge → runs deep research *scoped to it* → interprets through a **project-specific system prompt** (the "lens") → condenses results into durable cartridge notes and archives the raw dump. This is where JARVIS gets sharper on a topic over time without polluting general recall.

---

## Storage decision (the one real fork)

- **Namespaced (Mnemosyne's actual approach):** one index DB, `collection_id`/`project_id` filter. Simpler, fewer moving parts, proven by the owner's own system. Semantic space is shared — cartridges give lexical + metadata isolation, not full semantic isolation (accepted: per-project embeddings are too heavy, and building a dedicated container at registration time is the compromise).
- **Per-file:** one SQLite index per cartridge. Cleaner "drop and rebuild one project," true index isolation. More plumbing + a container registry.

**Recommendation:** start **namespaced** (matches the proven prior design and the existing `query_local(project_id=...)` filter — MARK is already a soft cartridge), with the cartridge boundary as a hard filter and a per-project embedding *build pass* at registration. Promote to per-file only if the assessment shows cross-project semantic bleed that filtering can't contain.

---

## Build phases

- [x] **Phase 0 — tier reconciliation.** `memory_tier` → `lifecycle` rename; adopt the structural vocabulary (confirmed **0-3**, not 0-4 -- that was a mistype). Done 2026-07-25: full `Jarvis_notes` backup taken, dry-run counted 115 notes, `scripts/migrate-lifecycle-field.py --apply` run, post-migration `core.note_integrity.scan_vault()` reported clean (160 notes, 0 errors). Code updated to match: `actions/jarvis_memory.py` (`note_tier`, `create_note`, `move_note`, `query_local`), `actions/memory_consolidation.py`, `main.py`'s tool schema (accepts `lifecycle`, with `memory_tier`/`tier` kept as tool-call synonyms only). See [[Jarvis_notes/workflows/memory-tiering-and-graphify-index/Plan|Workflow 2]] for the full write-up.
- [ ] **Phase 1 — general/cartridge scopes.** Add a `cartridge` (project) dimension to `query_local`; mount API (a turn declares its cartridge set); general scope = Tiers 1–2 only. Explicit selector.
- [ ] **Phase 2 — provisioning + UX.** Watcher hook: new project → build cartridge with progress `ProcessEvent`s. Registry-confidence selector with confirm-below-threshold.
- [ ] **Phase 3 — episodic event log.** A bounded, structured per-project recent-activity log in the general space, sourced from `vault_activity`.
- [ ] **Phase 4 — `knowledge_expansion` workflow.** Dual-orchestrator YAML: mount → scoped research → project-lens interpretation → condense to cartridge + archive raw. Reuses `memory_consolidation` for the condense step.

---

## Verification (per phase)
- Retrieval scoped to a cartridge returns that project's notes and **not** a same-named term from another project (the assessment provides the collision fixtures).
- The general scope answers "what projects exist / what changed" without loading any cartridge detail.
- Provisioning emits visible progress and never blocks a foreground turn.
- Disabled flag → today's single-index behaviour, unchanged.

## Non-goals
- No LoRA / fine-tuning (deliberate divergence from Mnemosyne).
- No sandboxed code execution here (owner's note: restrict sandboxes to high models / OpenClaw).
- No per-project embedding *models* (only per-project embedded *content*).

## Open questions for the owner
1. Namespaced vs per-file — accept the namespaced-first recommendation, or require physical separation from day one?
2. Tier-1 taxonomy — what are the "4–5 clear overarching categories" you want at root?
3. Should the `knowledge_expansion` deep-research step reuse the existing `deep_research_report` workflow, or wrap `dzhng/deep-research`-style external tooling?
