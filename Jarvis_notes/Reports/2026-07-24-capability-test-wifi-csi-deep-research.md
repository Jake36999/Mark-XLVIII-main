---
id: "jarvis-20260724T014613Z-0ff03162"
title: "Capability Test - WiFi CSI Deep Research"
type: "report"
status: "draft"
created: "2026-07-24T01:46:13Z"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis_notes"
source: "daemon"
tags: ["web", "research", "report", "tier-short-term", "capability-test"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T01:46:13Z"
review_after: ""
source_version: 1
content_hash: "b0a5a2e921cf1c96c9b001292eee82512692d1f487f6b52831310bf46a81ca02"
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
fallback_reason: ""
lifecycle: "short_term"
model_metrics: "{'lease_id': 'bd1202ee3d314d3383d69bb222099046', 'instance_id': 'qwen/qwen3-vl-4b', 'route': 'vision', 'queue_wait_seconds': 0.0, 'load_time_seconds': 12.963, 'streaming': False, 'duration_seconds': 62.703, 'completion_tokens': 562, 'tokens_per_second': 8.963, 'first_token_seconds': None, 'finish_reason': 'stop', 'reasoning_tokens': 0}"
model_name: "qwen/qwen3-vl-4b"
model_provider: "lmstudio"
model_role: "research"
original_query: "WiFi CSI-based presence and room-occupancy detection: best current approaches for a local always-on assistant"
quality_state: "validated"
research_stages: [{"stage": "evidence_normalization", "batch": 1, "status": "deterministic_fallback", "claim_count": 4, "error": "Expecting ',' delimiter: line 23 column 1 (char 885)"}, {"stage": "evidence_normalization", "batch": 2, "status": "accepted", "claim_count": 1, "provenance": {"provider": "lmstudio", "model": "qwen/qwen3-4b-2507", "role": "worker", "fallback_reason": "", "preferred_model_unavailable": false, "metrics": {"lease_id": "544aeb3bc8eb4bf6822b5625ff2a3d96", "instance_id": "qwen/qwen3-4b-2507", "route": "vision", "queue_wait_seconds": 0.0, "load_time_seconds": "", "streaming": false, "duration_seconds": 3.641, "completion_tokens": 47, "tokens_per_second": 12.909, "first_token_seconds": "", "finish_reason": "stop", "reasoning_tokens": 0}, "recorded_at": 1784857488.7090232}}, {"stage": "final_consolidation", "status": "accepted", "source_count": 5, "claim_count": 5}]
retrieved_at: "2026-07-24T01:44:30Z"
search_mode: "research"
source_count: 5
sync_error: ""
synthesis_state: "model_synthesized"
workflow_id: "deep_research_report"
---

# Capability Test - WiFi CSI Deep Research

## Summary

WiFi CSI-based presence detection is a viable, non-invasive, and privacy-preserving method for detecting human occupancy in indoor environments without requiring cameras or physical sensors. Evidence supports its practicality in multi-zone residential settings and its ability to detect movement through walls using existing Wi-Fi infrastructure. However, implementation requires careful calibration and may be constrained by hardware capabilities and signal fidelity. The local host’s GPU and RAM profile suggests adequate compute resources for running CSI-based models, though real-world performance depends on network topology and CSI data quality.

## Findings

WiFi CSI can reliably detect human presence and movement through walls using only an existing router, without requiring additional hardware or cameras. Machine learning models, such as those processing CSI amplitude spectrograms, are capable of distinguishing occupied from unoccupied spaces. The method is particularly advantageous in multi-zone homes due to its cost-effectiveness and non-intrusive nature, and has been validated in real-world applicability studies. However, the effectiveness is contingent on the quality and consistency of CSI data, which may vary across devices and environments [5].

## Actions

Given the local host’s hardware profile — a GTX 1080 and RX 5500 XT with 31.93GB RAM — deploying a CSI-based occupancy detection system is feasible. Prioritize models that process CSI amplitude spectrograms for low-latency, real-time inference. Use GitHub repositories like 'CSI_Presence' or 'WiTrace' as starting points, but ensure compatibility with your local inference framework (llama.cpp Vulkan via LM Studio). Consider implementing multi-zone detection by leveraging multiple CSI sources from different routers or access points. Monitor for signal degradation in high-interference zones and validate performance with local test data. Avoid over-reliance on CSI without complementary sensor validation in critical use cases.

## Sources

1. Implementing Wi-Fi CSI-based room-level occupancy Estimation: an ... (sciencedirect.com), retrieved: 2026-07-24T01:44:31Z, backend: ddg_html
   https://www.sciencedirect.com/science/article/pii/S2352710225013920

2. WiFi CSI‑Based Human Presence and Occupancy Detection (github.com), retrieved: 2026-07-24T01:44:31Z, backend: ddg_html
   https://github.com/mizhab-as/WiTrace

3. Implementing Wi-Fi CSI-based room-level occupancy Estimation: an ... (sciencedirect.com), retrieved: 2026-07-24T01:44:31Z, backend: ddg_html
   https://www.sciencedirect.com/science/article/abs/pii/S2352710225013920

4. GitHub - peyamekenel/CSI_Presence (github.com), retrieved: 2026-07-24T01:44:31Z, backend: ddg_html
   https://github.com/peyamekenel/CSI_Presence

5. WiFi CSI Device-Free Sensing 2026: Hardware, Real-World Capabilities ... (edgeorbital.io), retrieved: 2026-07-24T01:44:31Z, backend: ddg_html
   https://www.edgeorbital.io/2026/04/07/wifi-csi-device-free-sensing-2026/
