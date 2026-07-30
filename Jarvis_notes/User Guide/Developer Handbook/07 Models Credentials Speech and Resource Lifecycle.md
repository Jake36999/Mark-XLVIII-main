---
id: "developer-models-credentials-speech"
title: "Models, Credentials, Speech, and Resource Lifecycle"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-30T01:49:08Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "models", "lmstudio", "credentials", "speech", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.97
content_hash: "9fdc3242050b62103b9c2b44dbbc2fa944b34cf9ab14ffac5afc88653d1ba91a"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Models, Credentials, Speech, and Resource Lifecycle

> [!abstract] Split compute model
> High-capability models plan, synthesize, and review. Smaller local models handle bounded work. Model lifecycle leases and quality floors prevent the runtime from treating every installed model or LM Studio parallel slot as an active agent.

## Provider Roles

| Role | Preferred behavior |
| --- | --- |
| Planner | Session-linked OpenAI when healthy; otherwise strongest local model meeting the floor |
| Research | Qwen 14B DeepResearch, Marco 8B DeepResearch, then approved reasoning fallback |
| Reasoning/code | DeepSeek 8B or Qwen 9B route according to health |
| Worker/extraction | Qwen 4B baseline and bounded local alternatives |
| Vision | Qwen VL route |
| Speech | Orpheus baseline plus Windows SAPI fallback |
| Embeddings | Nomic Embed Q4 loaded on demand |

The model registry records role suitability, structured-output reliability, tool support, context window, VRAM requirement, parallel capacity, health, and known failure modes.

## Prompt-Based Model Routes

Trusted system directives can pin a route. Otherwise the router classifies the request:

- greetings and short prompts: `quick`;
- plans and architecture: `main`;
- proofs, diagnosis, physics, and trade-offs: `reasoning`;
- code, debugging, and tests: `code`;
- images, OCR, and screenshots: `vision`;
- deep research and cited reports: `research`;
- bounded delegated tasks: `worker`.

Source evidence cannot pin its own route; only the trusted system channel may use an internal route directive.

> [!danger] Keyword routing is fragile in both directions — pin the route where it matters
> The classifier reads the *prompt*. The tool-summary prompt necessarily concatenates tool output, so an unpinned summary call let attacker-influenceable content select its own model class. It also self-poisoned: the prompt's own anti-fabrication boilerplate contained the literal phrase "cited report content", and `cited report` is a `research` keyword — so **every tool summary in the system** classified as research and chained into `qwen2.5-14b-deepresearch → marco-deepresearch-8b → deepseek-r1-8b`, with streaming and a 1800-second ceiling.
>
> Removing the offending words was not sufficient: the remaining text contained "plan", which scores as `main` — also a heavy chain. The durable fix is the pin. `_handle_router_text_command` now sends the summary call with `[jarvis-route:worker]` on the trusted system channel, which short-circuits keyword matching entirely. Measured: the summary chain went from seven candidates including three 8–14B models down to three small ones.

## Local-First Model Economics (2026-07-29)

This host serves every model from one LM Studio instance holding a single task model at a time, so each extra candidate in a chain is a cold multi-gigabyte load. Optimising for the *system* rather than for the largest runnable model is a correctness concern, not a micro-optimisation: live testing measured a 1109-second turn in which roughly 90% of the wall-clock was walking dead candidates.

| Control | Behavior |
| --- | --- |
| `model_fallback_max_candidates` | Caps a chain (default 3). `0` disables the cap; missing or malformed falls back to the default. The role's explicitly configured model is preserved even when the cap would truncate it away — it takes the last-resort slot rather than vanishing. |
| `warm_model_preference_enabled` | Stable partition of already-loaded models ahead of cold ones, from `model_lifecycle.list_models()["loaded"]` behind a ~10 s TTL cache. A **partition, never a re-rank**, applied only to candidates that already survived route selection — otherwise a warm general model could outrank the only model that can serve the route. Runs *before* the cooldown filter, so a warm-but-cooling model is still dropped. Fails open: a probe failure leaves order untouched. |
| `task_model_ttl_seconds` | Now actually enforced (it was configured but never read). |

### Duplicate work removed

When native tool-calling failed on every candidate, the JSON-tools compatibility pass re-walked **the same full chain again** — doubling an already-expensive failure into a second round of cold loads for no new information. It now retries only the first candidate, which is what that pass is for.

### Cloud providers are supplementary

Keys are entered per session in the UI and never stored, so on a purely local session the answer to "is OpenAI linked?" is always no — but asking it cost an IPC round trip that *spawned the broker subprocess*, on every planner turn, just to be told no. `SessionCredentialBroker.has_linked_session()` answers that without IPC: `link()` is the only way a key enters and it starts the process, so a `False` is exact rather than a guess. Brokers lacking the method (test doubles) fall through to the normal `status()` path unchanged.

### Context budgets come from the loaded profile, not the advertised one

A model's advertised context window is not what it gets here. `MODEL_PROFILES` declares 32768 for `qwen/qwen3-4b-2507`; `lmstudio_model_load_profiles` actually loads it at **4096** — an eightfold overestimate, and the reason overflow was invisible. Sizing a prompt from the advertised number produced the live `n_keep: 4223 >= n_ctx: 4096` failure, and worse, that failure looked like "the small model cannot cope" and pushed the chain into larger models.

`model_registry.effective_profile()` merges the capability profile with the real configured `context_length`; `char_budget_for()` converts that into a usable character budget — about 11,500 characters for the 4096-token worker, falling under 9,000 once room is reserved for the reply itself. The tool-summary evidence block was a flat **24,000** characters against that, so overflow was structural rather than occasional. It is now derived from the model that will actually run the work.

> [!tip] The local-first principle, stated once
> Decompose work to fit the profile of the model it will be delegated to. `core/repo_slicer` and `project_learning._source_batches` already do this for repository learning; `char_budget_for()` is the general form.

## Quality Floors

Before an important workflow selects a model, the registry can require minimum structured-output reliability, tool support, and context capacity. If no healthy model meets the role floor, the workflow should pause instead of silently downgrading.

Every generated artifact can record provider, model, role, fallback reason, context/token budget, confidence, availability, and whether the preferred model was unavailable.

## Session-Only OpenAI Credential Broker

The OpenAI key is owned by a dedicated child process:

1. The masked UI field sends the key over an inherited multiprocessing pipe.
2. The broker stores it in a mutable byte buffer and returns an opaque session handle.
3. Linking calls `GET /v1/models`, verifies the configured model, then performs a minimal Responses API probe.
4. OpenAI requests are made inside the broker process.
5. The key is never intentionally written to configuration, environment variables, command arguments, work items, or logs.
6. Unlink and process shutdown overwrite the broker buffer on a best-effort basis and terminate the child.

Error classification preserves a linked key for quota, policy, region, rate-limit, model-access, server, and network failures. Only confirmed invalid authentication clears it.

> [!warning] Best-effort memory clearing
> Python and HTTP libraries can create immutable copies. Process isolation, minimal copies, redacted logs, and broker termination are the primary controls.

## OpenAI to Local Fallback

For text and tool calls, an unlinked or unavailable OpenAI session falls back to LM Studio. OpenAI request failures also fall back when the failure is safe to retry locally. Model provenance records the fallback reason.

The runtime does not silently read an environment key as a replacement for the session UI key.

## LM Studio Lifecycle

Current endpoints:

- OpenAI-compatible inference: `http://localhost:1234/v1`.
- Native model management: `http://localhost:1234/api/v1`.

Exactly one baseline model is kept warm: **`qwen/qwen3-4b-2507`**. `config/runtime.json`'s `baseline_models` is authoritative, and the lifecycle resolver now agrees with it.

> [!danger] This note previously listed `orpeus_text_to_speech` as a second baseline. That was wrong (corrected 2026-07-30)
> The documentation matched a **bug**, not the intended policy. `model_lifecycle._resolved_config()` was appending `tts_model` and, for the Orpheus engine, `orpeus_text_to_speech` into the effective baseline list — silently overriding `baseline_models` and contradicting a decision recorded on 2026-07-24 and pinned by `tests/test_speech_runtime.py::test_runtime_config_gates_filler_on_user_idle`: three always-resident models held RAM at roughly 70% stationary, so speech should load on demand and idle out like any other task model.
>
> The promotion also made that TTL unreachable for speech, since baseline models are never unloaded — so the intended behaviour could not happen even in principle. The promotion is gone; `worker_model` is still tolerated if omitted from the list, because the always-warm worker is baseline by definition.

Task models receive a 300-second TTL. Only one non-baseline task model is allowed to remain loaded. An idle cleanup loop runs every 300 seconds and never unloads a protected active request or baseline model.

> [!important] `unload_non_baseline(keep=...)` protects the caller's own next call
> With speech no longer baseline, the TTS path had a new hazard: it cleans up immediately *before* speaking, so it could unload the very voice it was about to load again. `core/tts.py` now names the configured voice in `keep`, which is honoured even under `force=True` — forcing a cleanup should not sabotage the caller's own next call. This is a narrower guarantee than permanent residency, which is the point.

> [!warning] The TTL was configured but not enforced, and TTS thrashed against it
> `core/tts.py` releases idle task models before **every spoken reply**, and its only guard was `active_snapshot()["active_count"]` — which is already zero by then, because the generation lease was released when the reply was composed. "Idle" and "used two seconds ago" were indistinguishable, so a specialist was evicted at the end of one turn and cold-loaded again on the next.
>
> `model_lifecycle.recently_used_models()` reads `completed_at` from the existing generation-lease table, and `unload_non_baseline` now skips a non-baseline model used within the TTL unless `force=True`. VRAM safety is unchanged: `max_task_models_loaded` still evicts at the next load and the idle sweep still fires once the TTL elapses. This *delays* eviction; it does not remove it. An explicit user "unload models" passes `force=True` and is unaffected. Fails open — an unreadable lease table means no recency information and cleanup behaves exactly as before.
>
> Measured after the fix: across eleven live turns, **zero evictions**, and only one model was ever loaded.

## Generation Leases

Before local inference, `model_router`:

1. classifies baseline versus task route;
2. acquires a persistent SQLite generation lease;
3. waits if the relevant generation class is busy;
4. loads the requested model through the native API;
5. updates the lease through `RESERVED`, `LOADING`, `GENERATING`, and optional `DRAINING` states;
6. records queue/load/generation metrics;
7. releases the lease with a terminal outcome.

Stale leases are expired when the owner process is gone or the lease deadline passes. This makes cross-process coordination stronger than an in-memory lock.

Research calls stream output so first-token and total-generation timing can be monitored. On timeout, the runtime drains or unloads the instance before considering fallback. If the prior outcome is uncertain, fallback is suppressed to avoid two simultaneous answers.

## TTS Architecture

The primary local path is an OpenAI-compatible Orpheus FastAPI bridge at `http://127.0.0.1:5006/v1` backed by LM Studio.

Current safeguards:

- split text into ordered chunks of about 120 characters at sentence boundaries;
- one synthesis worker, regardless of LM Studio parallel slots;
- one audio chunk buffered ahead;
- one pending utterance for the whole player;
- generation lease for each Orpheus chunk;
- turn generation ID so cancelled/stale chunks are discarded;
- optional release of idle specialist models before latency-sensitive speech;
- Windows SAPI fallback while Orpheus warms or after primary failure.

> [!important] Chunking is ordered, not duplicated
> A single producer synthesizes chunk N+1 while chunk N is played. Multiple agents never receive the complete response for simultaneous speech.

The TTS player calls `set_speaking(true)` before playback and `set_speaking(false)` only after the utterance finishes or is cancelled.

## STT Architecture

The default microphone path is local Vosk with English `en-us`. The router merges partial transcripts, watches audio RMS, and waits for the configured silence interval before submitting a complete turn.

Listening is blocked while JARVIS is speaking and for a post-TTS cooldown. Mute/unmute resets recognizer state so an earlier partial phrase cannot leak into the next turn.

The optional filler prompt is eligible only after 15 minutes with no user input and is suppressed while the assistant, TTS, or a workflow is busy.

## English Output Guard

Router, workflow worker, document analysis, and review prompts explicitly request English. Ambient non-English speech does not persist a language preference. A future explicit language-switch feature should remain current-turn scoped unless the user deliberately saves a preference.

## Related Notes

- [[01 Runtime Architecture and Turn Lifecycle]]
- [[04 Fan-Out Workers Review and Recovery]]
- [[08 Storage Configuration and Operations]]
