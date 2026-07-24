---
id: "jarvis-20260724T174146Z-41557e56"
title: "Local Model Characterization Benchmark - Timeout Diagnosis and Overseer Selection"
type: "report"
status: "active"
created: "2026-07-24T17:41:46Z"
updated: "2026-07-24T17:48:19Z"
project_id: "jarvis_notes"
source: "claude"
tags: ["validation", "lmstudio-performance", "model-benchmark", "vram", "overseer", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T17:41:46Z"
review_after: ""
source_version: 1
content_hash: "91017346e6e6f63d7fd529e39977b7fdf1d4b1d518ad25ecde85bdffdfdc77d6"
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
> Empirical characterization of the local models, run to settle the "timeout cascade" question from [[2026-07-24-live-prompt-testing-16-prompts]]. Each model was loaded in isolation (`lms load --gpu max --parallel 1`, cold), then run through 10 graded probes via the LM Studio streaming API (pinned model, no router fallback, 600s ceiling). VRAM on **both** GPUs was sampled every 2s via Windows perf counters (the cross-vendor read the owner's `Get-Counter` approach unlocked). Raw data, harness, and GPU CSV are in this folder. 58 runs total.

## The headline: the timeout cascade was never about load time

**Every model cold-loaded in under 30 seconds** — including the 14B. There is no model in the stack that is slow to load.

| Model | Cold-load | Combined VRAM (GTX 1080 + RX 5500 XT) |
|---|---|---|
| deepseek-r1-0528-qwen3-8b | **6.3 s** | 3145 + 4313 = 7458 MiB |
| mistralai/mistral-7b-instruct-v0.3 | **8.2 s** | 3119 + 3704 = 6823 MiB |
| qwen2.5-14b-deepresearch-i1 | **14.9 s** | 4096 + 4976 = **9072 MiB** |
| marco-deepresearch-8b | **11.6 s** | 3050 + 3697 = 6747 MiB |
| qwen/qwen3.5-9b | **27.2 s** | 3876 + 3920 = 7796 MiB |
| qwen/qwen3-4b-2507 (baseline) | 5.5 s | 2118 + 3064 = 5182 MiB |
| google/gemma-4-e4b (baseline) | 23.3 s | 3080 + 2856 = 5936 MiB |

So the 18-minute cascade in the live test was **100% the JIT-load-on-demand path colliding with the router's short generation-timeout and the health-cooldown logic** — not model slowness. The fix is therefore not "make the models faster to load" (they're already fast); it is **preload and warm-keep the overseer once, and stop conflating load-timeout with generation-timeout.** A ~8 s one-time preload of the chosen overseer erases the entire failure class.

## Two things this also settles for the owner

1. **Cross-vendor pooling works, confirmed empirically.** Every model's weights spread across *both* cards, and the 14B used **9.1 GB combined — which cannot fit on a single 8 GB card.** So the Vulkan runtime (`llama.cpp-win-x86_64-vulkan-avx2`, already selected) is genuinely pooling the two GPUs into one ~16 GB space, exactly as you described. Nothing is misconfigured on the runtime side.
2. **There is real VRAM headroom.** The biggest model tested (14B) used 9.1 GB of the ~16 GB pool. That means a mid-size overseer (mistral-7b ≈ 6.8 GB) can stay resident **alongside** the fast worker (qwen3-4b ≈ 5.2 GB) — ~12 GB combined — so both the planner and worker roles can be kept warm with zero cold-loads during a session.

## The real bottleneck for overseer use: generation throughput × reasoning-token bloat

Load is cheap; **generation is where the large models cost time**, and it splits sharply by model type:

| Model | Warm throughput | Reasoning model? | Produces a bounded final answer? |
|---|---|---|---|
| qwen3-4b (baseline) | **45–56 tok/s** | no | yes — clean |
| mistral-7b-instruct | 22–40 tok/s | **no** | **yes — clean on every probe** |
| gemma-4b (baseline) | 24–35 tok/s | partial | mostly (its "reasoning" mode blew one probe) |
| deepseek-r1-8b | ~25 tok/s | **yes** | **no — reasons past the budget** |
| qwen3.5-9b | **8–9 tok/s** | yes | rarely |
| marco-deepresearch-8b | ~5 tok/s | yes | rarely |
| qwen2.5-14b-deepresearch | **4.6–6 tok/s** | no | yes, but slowly |

**The reasoning models are the trap, not the large models.** deepseek-r1, qwen3.5-9b, and marco stream their entire chain-of-thought before any answer, and on bounded prompts they **exhaust the token budget mid-thought and never emit the final answer** (`finish_reason: length`, empty final content). Concretely:
- deepseek-r1 could not produce the `S1`/`S2` JSON at all — it spent 1600–2700 reasoning characters thinking and got cut off before the JSON (`json_parseable: false`).
- qwen3.5-9b could not even answer `B1` ("reply with OK") within 256 tokens — it wrote 1017 characters of reasoning and never said "OK".
- This is the model-level root cause of the live test's "**narrated instead of answered**" and empty-reply failures (P2, P8). It's not a prompt problem; these models structurally over-think bounded tasks.

Meanwhile **mistral-7b-instruct — the model the live test wrote off as "times out" — was the single best-behaved candidate**: no reasoning bloat, valid clean JSON on both structured probes, a valid tool call, completed both reasoning tasks, ~30–40 tok/s. It only ever "timed out" in the live test because it was being cold-loaded through the pathological JIT path.

## Long-context is weak across the whole stack

- `L1` (a ~2000-token needle-in-doc): only qwen3.5-9b found the needle, and it took 164 s. Every other model missed it, including the 14B.
- `L2` (~6000-token needle): **failed on every model** — but this one is a *context-budget artifact*, not a quality result: at the 8192 context I loaded with, a ~6k-token input leaves no room, so LM Studio returned empty (`usage: {}`, no output, ~8 s). Real takeaway: **at 8192 ctx these models can't reliably handle ~6k-token inputs, and even 2k-token retrieval is unreliable.** The overseer should be fed *bounded, pre-retrieved* context, never a large raw document.

## Per-model verdict (overseer suitability)

| Model | Verdict as planner/overseer | Why |
|---|---|---|
| **mistral-7b-instruct-v0.3** | ✅ **Recommended interactive overseer** | Clean structured JSON + tool calls, no reasoning bloat, 8 s load, 30–40 tok/s, 6.8 GB. Weak long-context (feed it bounded context). |
| **qwen2.5-14b-deepresearch** | ✅ **Quality tier, non-interactive only** | Best raw quality, clean structured output, spans both cards (9 GB) — but 4.6 tok/s means multi-minute plans. Use for "quality when time allows", not chat. |
| qwen3-4b (baseline) | ✅ Excellent worker / quick-overseer | 45–56 tok/s, valid JSON + tools, 5.2 GB. Already the reliable default. |
| gemma-4b (baseline) | ⚠ Usable fallback | Decent, but its reasoning mode over-thought one probe. |
| deepseek-r1-8b | ❌ Not as a bounded overseer | Reasons past budgets; no reliable bounded/structured output. |
| qwen3.5-9b | ❌ | Slow (8 tok/s) + blows budgets; couldn't say "OK". |
| marco-deepresearch-8b | ❌ | Slow (5 tok/s), over-thinks, failed the tool-call probe. |

## Concrete settings this hands to Track A2

1. **Preload + warm-keep one overseer at startup.** Recommend **mistral-7b-instruct** for the interactive planner/reviewer role. ~8 s one-time cost; eliminates the cold-load cascade entirely.
2. **Split the timeouts** the router currently conflates: **load-timeout ≈ 60 s** (covers the 27 s worst case with margin) and a **per-model generation-timeout** (≈90 s for mistral, ≈200 s if the 14B is used). This alone would have prevented every timeout in the live test.
3. **Drop the reasoning models (deepseek-r1, qwen3.5-9b, marco) from the planner/overseer candidate list.** Keep them only for tasks with a large token budget AND answer-extraction (LM Studio splits `reasoning_content` from `content`, so the deterministic layer can pull the final answer out from after the thinking — a small, well-defined piece of work if you ever want to use them).
4. **Bound the overseer's context** (≤ ~4k input): long-context retrieval is unreliable here, so pre-retrieve and hand it only what it needs.
5. **VRAM admission using the measured footprints** (finally uses the declared-but-unused `vram_gb`): mistral-7b (6.8 GB) + qwen3-4b worker (5.2 GB) ≈ 12 GB fit together in the 16 GB pool — keep both warm.
6. **Set `--parallel 1–2`** for the single-user case (the benchmark ran everything at `--parallel 1` cleanly; the live config's `4` multiplies KV-cache memory for no single-user benefit).

## Measurement caveats (honesty)

- **`tok/s` is meaningless for the trivial one-chunk responses** (B1/B2 sometimes show absurd values like 1985 or 5984 tok/s) — that's a near-zero generation-time division artifact. Only the multi-token generations (R/S/Y probes, 4–56 tok/s) are meaningful.
- **`L2`'s universal failure is a context-overflow artifact** at 8192 ctx, not a model-quality signal (see above). A rerun at higher context would separate "can't fit" from "can't retrieve" — but the practical conclusion (don't feed the overseer 6k raw tokens) stands either way.
- VRAM figures are peak dedicated allocation per card sampled at 2 s intervals during each model's loaded window; the AMD card is read via the `\GPU Adapter Memory\Dedicated Usage` perf counter, cross-checked against `nvidia-smi` for the Nvidia card.
- LM Studio was restored to its as-found state (qwen3-4b + orpheus reloaded) at the end of the run.

## Artifacts
- `bench_run.py` (harness), `bench_prompts.py` (probe matrix), `analyze.py` (correlation), `bench_results.jsonl` (58 raw runs), `gpu_samples.csv` (both-card VRAM/util timeline), `gpu_monitor.ps1`, `bench_run.log` — all in this folder.
