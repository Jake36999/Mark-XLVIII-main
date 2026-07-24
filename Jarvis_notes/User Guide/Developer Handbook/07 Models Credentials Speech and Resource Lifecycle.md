---
id: "developer-models-credentials-speech"
title: "Models, Credentials, Speech, and Resource Lifecycle"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-23T03:00:54Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "models", "lmstudio", "credentials", "speech", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.97
content_hash: "ea7902aa06e2102c272308369ab59e9a84d7c85f53516182450383b40113c224"
memory_tier: "short_term"
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

Baseline models are kept warm:

- `qwen/qwen3-4b-2507`;
- `orpeus_text_to_speech`.

Task models receive a 300-second TTL. Only one non-baseline task model is allowed to remain loaded. An idle cleanup loop runs every 300 seconds and never unloads a protected active request or baseline model.

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
