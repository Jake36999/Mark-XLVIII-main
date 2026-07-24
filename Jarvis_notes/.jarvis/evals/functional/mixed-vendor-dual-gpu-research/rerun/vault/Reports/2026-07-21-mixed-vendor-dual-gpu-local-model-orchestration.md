---
id: "jarvis-20260721T165537Z-1b16c730"
title: "Mixed-Vendor Dual-GPU Local Model Orchestration"
type: "report"
status: "draft"
created: "2026-07-21T16:55:37Z"
updated: "2026-07-21T16:55:37Z"
project_id: "functional_eval_research"
source: "daemon"
tags: ["web", "research", "report"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-21T16:55:37Z"
review_after: ""
source_version: 1
content_hash: "9850a14a95d4e82e66b7363a1d46d2ae49386740a205e0fdb06d468603a97054"
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
date_from: ""
date_to: ""
fallback_reason: "LM Studio local model route failed. Tried: qwen2.5-14b-deepresearch-i1: LM Studio chat request failed: {\"error\":\"Model unloaded.\"} | marco-deepresearch-8b: LM Studio chat request failed: {\"error\":\"Model unloaded.\"} | deepseek-r1-0528-qwen3-8b: LM Studio chat request failed: {\"error\":\"Model unloaded.\"} | qwen/qwen3-4b-2507: LM Studio chat request failed: <!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<title>Error</title>\n</head>\n<body>\n<pre>Internal Server Error</pre>\n</body>\n</html>\n | mistralai/mistral-7b-instruct-v0.3: LM Studio chat request failed: {\"error\":\"Model unloaded.\"} | google/gemma-4-e4b: LM Studio chat request failed: {\n    \"error\": {\n        \"message\": \"Failed to load model \\\"google/gemma-4-e4b\\\". Error: Operation canceled.\",\n        \"type\": \"invalid_request_error\",\n        \"param\": \"model\",\n        \"co | qwen/qwen3-vl-4b: LM Studio chat request failed: {\"error\":\"Model unloaded.\"}"
model_name: ""
model_provider: "deterministic"
model_role: ""
original_query: "Assess reliable mixed-vendor dual-GPU local-model orchestration with LM Studio and llama.cpp. Cover memory allocation, concurrency, model loading, telemetry, failure recovery, and practical recommendations. Use current primary sources, preserve uncertainty, consolidate duplicate findings, and keep high-contrast findings separate."
quality_state: "degraded_unsynthesized"
retrieved_at: "2026-07-21T16:43:29Z"
search_mode: "research"
source_count: 10
sync_error: ""
synthesis_state: "deterministic_extract"
workflow_id: "deep_research_report"
---

# Mixed-Vendor Dual-GPU Local Model Orchestration

## Summary

Retrieved 10 cited sources for 'Assess reliable mixed-vendor dual-GPU local-model orchestration with LM Studio and llama.cpp. Cover memory allocation, concurrency, model loading, telemetry, failure recovery, and practical recommendations. Use current primary sources, preserve uncertainty, consolidate duplicate findings, and keep high-contrast findings separate.' covering current search window. Generated at 2026-07-21T16:43:29Z.

## Findings

- Split Large Models Across GPUs: LM Studio Multi-GPU Setup 2026: Configure LM Studio multi- GPU to split Llama 3.3 70B, Mixtral, and DeepSeek across 2-4 GPUs . Layer-splitting, VRAM balancing, and GPU offload settings explained. [1]
- LM Studio Production Architecture: Reliable Local LLM Inference: Design a production-grade local AI inference architecture with LM Studio : multi-node scaling, observability, and failure mitigation for senior developers. [2]
- Best Dual-GPU Local AI Setup: RTX 3090, 5060 Ti (2026): Dual RTX 3090, 2x RTX 5060 Ti, 2x 2080 Ti modded, mixed setups: real configs for Qwen 3.6, MoE, 70B. Tensor vs pipeline parallelism, llama.cpp/vLLM. [3]
- LM Studio 0.3.14: Multi-GPU Controls ️: Advanced controls for multi- GPU setups: enable/disable specific GPUs , choose allocation strategy, limit model weight to dedicated GPU memory , and more. [4]
- Local LLM Inference Optimization: The Complete Guide: A practical guide to hardware, OS, and llama.cpp tuning, built from a year of experiments on a single consumer CUDA workstation. [5]
- Accelerate Larger LLMs Locally on RTX With LM Studio | NVIDIA Blog: How to Accelerate Larger LLMs Locally on RTX With LM Studio GPU offloading makes massive models accessible on local RTX AI PCs and workstations. [6]
- Multi-GPU Local LLMs 2026: Dual RTX 4090 for 70B at 100 tok/s: Dual RTX 4090s (48 GB combined) run Llama 3.3 70B at ~100 tok/sec — only 5-10% slower than a theoretical single 48 GB GPU . This is the most cost-effective multi- GPU setup for 70B models in 2026. [7]
- Run any LLM on Distributed Multiple GPUs Locally Using Llama_cpp: In this tutorial, we will explore the efficient utilization of the Llama.cpp library to run fine-tuned LLMs on distributed multiple GPUs , unlocking ultra-fast performance. [8]
- Splitting LLMs Across Multiple GPUs: Techniques, Tools, and Best ...: Learn how to split large language models (LLMs) across multiple GPUs using top techniques, tools, and best practices for efficient distributed training. [9]
- Local LLM Deployment with Ollama and llama.cpp: A Comprehensive Guide: Learn how to deploy and optimize large language models locally using Ollama and llama.cpp. This guide covers installation, model customization with Modelfiles, and performance optimization through quantization for efficient GPU inference. [10]

## Actions

- Review the cited articles in Obsidian.
- Promote useful claims into project notes only after source review.

## Sources

1. Split Large Models Across GPUs: LM Studio Multi-GPU Setup 2026 (markaicode.com), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://markaicode.com/lm-studio-multi-gpu-split-large-models/

2. LM Studio Production Architecture: Reliable Local LLM Inference (markaicode.com), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://markaicode.com/architecture/lm-studio-local-ai-architecture/

3. Best Dual-GPU Local AI Setup: RTX 3090, 5060 Ti (2026) (insiderllm.com), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://insiderllm.com/guides/multi-gpu-local-ai/

4. LM Studio 0.3.14: Multi-GPU Controls ️ (lmstudio.ai), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://lmstudio.ai/blog/lmstudio-v0.3.14

5. Local LLM Inference Optimization: The Complete Guide (carteakey.dev), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://carteakey.dev/blog/local-inference/local-llm-optimization/

6. Accelerate Larger LLMs Locally on RTX With LM Studio | NVIDIA Blog (blogs.nvidia.com), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://blogs.nvidia.com/blog/ai-decoded-lm-studio/

7. Multi-GPU Local LLMs 2026: Dual RTX 4090 for 70B at 100 tok/s (promptquorum.com), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://www.promptquorum.com/local-llms/multi-gpu-local-llms

8. Run any LLM on Distributed Multiple GPUs Locally Using Llama_cpp (medium.com), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://medium.com/@yash9439/run-any-llm-on-distributed-multiple-gpus-locally-using-llama-cpp-2ff478a0dc3c

9. Splitting LLMs Across Multiple GPUs: Techniques, Tools, and Best ... (digitalocean.com), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://www.digitalocean.com/community/tutorials/splitting-llms-across-multiple-gpus

10. Local LLM Deployment with Ollama and llama.cpp: A Comprehensive Guide (dasroot.net), retrieved: 2026-07-21T16:43:29Z, backend: ddg_html
   https://dasroot.net/posts/2026/01/local-llm-deployment-ollama-llama.cpp/
