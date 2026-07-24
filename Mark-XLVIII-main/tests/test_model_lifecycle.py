import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import requests


class FakeResponse:
    def __init__(self, payload, status_code=200, text="OK"):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")

    def json(self):
        return self._payload


def lifecycle_config():
    from actions import model_lifecycle

    return model_lifecycle.resolve_config(
        {
            "lmstudio_native_url": "http://localhost:1234/api/v1",
            "baseline_models": ["qwen/qwen3-4b-2507", "orpeus_text_to_speech"],
            "task_model_ttl_seconds": 300,
            "idle_cleanup_seconds": 300,
            "max_task_models_loaded": 1,
            "model_runtime_db_path": str(Path(tempfile.gettempdir()) / f"jarvis-test-model-runtime-{uuid.uuid4().hex}.sqlite"),
        }
    )


def models_payload():
    return {
        "models": [
            {
                "type": "llm",
                "key": "qwen/qwen3-4b-2507",
                "display_name": "Qwen3 4B",
                "loaded_instances": [
                    {
                        "id": "qwen/qwen3-4b-2507",
                        "config": {"parallel": 4, "context_length": 4096},
                    }
                ],
            },
            {
                "type": "llm",
                "key": "deepseek-r1-0528-qwen3-8b",
                "display_name": "DeepSeek R1 Qwen 8B",
                "loaded_instances": [
                    {
                        "id": "deepseek-r1-0528-qwen3-8b:0",
                        "config": {"parallel": 2, "context_length": 8192},
                    }
                ],
            },
        ]
    }


class ModelLifecycleTests(unittest.TestCase):
    def test_task_generation_leases_queue_instead_of_overlapping(self):
        from actions import model_lifecycle

        with tempfile.TemporaryDirectory() as tmp:
            cfg = lifecycle_config()
            cfg.update(
                {
                    "lease_db_path": str(Path(tmp) / "model-runtime.sqlite"),
                    "generation_wait_seconds": 2,
                    "generation_lease_seconds": 60,
                }
            )
            first = model_lifecycle.acquire_generation_lease(
                "qwen2.5-14b-deepresearch-i1",
                route="research",
                cfg=cfg,
                wait_seconds=0,
            )
            acquired = []

            def wait_for_lease():
                acquired.append(
                    model_lifecycle.acquire_generation_lease(
                        "marco-deepresearch-8b",
                        route="research",
                        cfg=cfg,
                        wait_seconds=1,
                    )
                )

            thread = threading.Thread(target=wait_for_lease)
            thread.start()
            time.sleep(0.15)
            snapshot = model_lifecycle.persistent_generation_snapshot(cfg)
            self.assertEqual(len(snapshot["leases"]), 1)
            model_lifecycle.release_generation_lease(first["lease_id"], cfg=cfg)
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertTrue(acquired[0]["ok"])
            self.assertGreaterEqual(acquired[0]["queue_wait_seconds"], 0.1)
            model_lifecycle.release_generation_lease(acquired[0]["lease_id"], cfg=cfg)

    def test_baseline_speech_and_task_generation_share_global_single_flight(self):
        from actions import model_lifecycle

        with tempfile.TemporaryDirectory() as tmp:
            cfg = lifecycle_config()
            cfg.update(
                {
                    "lease_db_path": str(Path(tmp) / "model-runtime.sqlite"),
                    "generation_wait_seconds": 2,
                    "generation_lease_seconds": 60,
                }
            )
            speech = model_lifecycle.acquire_generation_lease(
                "orpeus_text_to_speech",
                route="speech",
                cfg=cfg,
                wait_seconds=0,
            )
            acquired = []

            thread = threading.Thread(
                target=lambda: acquired.append(
                    model_lifecycle.acquire_generation_lease(
                        "marco-deepresearch-8b",
                        route="research",
                        cfg=cfg,
                        wait_seconds=1,
                    )
                )
            )
            thread.start()
            time.sleep(0.15)
            self.assertTrue(thread.is_alive())
            model_lifecycle.release_generation_lease(speech["lease_id"], cfg=cfg)
            thread.join(timeout=2)

            self.assertFalse(thread.is_alive())
            self.assertTrue(acquired[0]["ok"])
            self.assertGreaterEqual(acquired[0]["queue_wait_seconds"], 0.1)
            model_lifecycle.release_generation_lease(acquired[0]["lease_id"], cfg=cfg)

    def test_cleanup_respects_cross_process_generation_lease(self):
        from actions import model_lifecycle

        with tempfile.TemporaryDirectory() as tmp:
            cfg = lifecycle_config()
            cfg.update({"lease_db_path": str(Path(tmp) / "model-runtime.sqlite")})
            lease = model_lifecycle.acquire_generation_lease(
                "deepseek-r1-0528-qwen3-8b",
                route="research",
                cfg=cfg,
                wait_seconds=0,
            )
            try:
                def fake_get(url, **kwargs):
                    raise AssertionError("cleanup must not query LM Studio while a persistent lease is active")

                result = model_lifecycle.cleanup_idle(cfg, get=fake_get)
            finally:
                model_lifecycle.release_generation_lease(lease["lease_id"], cfg=cfg)

            self.assertTrue(result["skipped"])
            self.assertEqual(result["reason"], "active_requests")

    def test_snapshot_reaps_lease_when_owner_process_has_exited(self):
        from actions import model_lifecycle

        with tempfile.TemporaryDirectory() as tmp:
            cfg = lifecycle_config()
            cfg.update({"lease_db_path": str(Path(tmp) / "model-runtime.sqlite")})
            lease = model_lifecycle.acquire_generation_lease(
                "deepseek-r1-0528-qwen3-8b",
                route="research",
                cfg=cfg,
                wait_seconds=0,
            )

            with mock.patch("actions.model_lifecycle._pid_is_alive", return_value=False):
                snapshot = model_lifecycle.persistent_generation_snapshot(cfg)

            self.assertTrue(lease["ok"])
            self.assertEqual(snapshot["leases"], [])

    def test_list_models_treats_parallel_as_instance_config(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()

        def fake_get(url, **kwargs):
            self.assertEqual(url, "http://localhost:1234/api/v1/models")
            return FakeResponse(models_payload())

        listed = model_lifecycle.list_models(cfg, get=fake_get)

        self.assertEqual(listed["loaded_count"], 2)
        self.assertEqual(listed["task_loaded_count"], 1)
        baseline = listed["loaded"][0]
        self.assertTrue(baseline["baseline"])
        self.assertEqual(baseline["parallel"], 4)

    def test_prepare_payload_adds_ttl_only_for_non_baseline_models(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()

        baseline_payload = model_lifecycle.prepare_lmstudio_payload(
            {"model": "qwen/qwen3-4b-2507"},
            model="qwen/qwen3-4b-2507",
            route="quick",
            config=cfg,
        )
        task_payload = model_lifecycle.prepare_lmstudio_payload(
            {"model": "deepseek-r1-0528-qwen3-8b"},
            model="deepseek-r1-0528-qwen3-8b",
            route="code",
            config=cfg,
        )

        self.assertNotIn("ttl", baseline_payload)
        self.assertEqual(task_payload["ttl"], 300)

    def test_unload_non_baseline_keeps_baseline_models(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()
        posts = []

        def fake_get(url, **kwargs):
            return FakeResponse(models_payload())

        def fake_post(url, **kwargs):
            posts.append((url, kwargs["json"]))
            return FakeResponse({"instance_id": kwargs["json"]["instance_id"]})

        result = model_lifecycle.unload_non_baseline(cfg, get=fake_get, post=fake_post)

        self.assertTrue(result["ok"])
        self.assertEqual(posts, [("http://localhost:1234/api/v1/models/unload", {"instance_id": "deepseek-r1-0528-qwen3-8b:0"})])
        self.assertEqual(len(result["kept"]), 1)
        self.assertEqual(result["kept"][0]["model_key"], "qwen/qwen3-4b-2507")

    def test_cleanup_idle_skips_while_requests_are_active(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()
        token = model_lifecycle.mark_request_start("deepseek-r1-0528-qwen3-8b", kind="code")
        try:
            def fake_get(url, **kwargs):
                raise AssertionError("cleanup should not query LM Studio while active")

            result = model_lifecycle.cleanup_idle(cfg, get=fake_get)
        finally:
            model_lifecycle.mark_request_done(token)

        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "active_requests")

    def test_tool_baseline_operation_returns_json(self):
        from actions import model_lifecycle

        result = json.loads(
            model_lifecycle.model_lifecycle(
                {"operation": "baseline", "_config": {"baseline_models": ["qwen/qwen3-4b-2507"]}}
            )
        )

        self.assertTrue(result["ok"])
        self.assertIn("qwen/qwen3-4b-2507", result["baseline_models"])

    def test_research_profile_caps_context_and_keeps_14b_kv_cache_off_gpu(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()
        payload = model_lifecycle.build_load_payload("qwen2.5-14b-deepresearch-i1", cfg)

        self.assertEqual(payload["context_length"], 8192)
        self.assertEqual(payload["eval_batch_size"], 256)
        self.assertTrue(payload["flash_attention"])
        self.assertFalse(payload["offload_kv_cache_to_gpu"])
        self.assertNotIn("parallel", payload)

    def test_embedding_load_payload_omits_llm_only_fields(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()
        payload = model_lifecycle.build_load_payload(
            "text-embedding-nomic-embed-text-v1.5@q4_k_m",
            cfg,
            model_type="embedding",
        )

        self.assertEqual(payload["model"], "text-embedding-nomic-embed-text-v1.5@q4_k_m")
        self.assertEqual(payload["context_length"], 2048)
        self.assertNotIn("eval_batch_size", payload)
        self.assertNotIn("flash_attention", payload)
        self.assertNotIn("offload_kv_cache_to_gpu", payload)

    def test_available_model_type_matches_native_embedding_metadata(self):
        from actions import model_lifecycle

        result = model_lifecycle._available_model_type(
            "text-embedding-nomic-embed-text-v1.5@q4_k_m",
            [
                {
                    "type": "embedding",
                    "key": "text-embedding-nomic-embed-text-v1.5@q4_k_m",
                    "display_name": "Nomic Embed Text v1.5",
                }
            ],
        )

        self.assertEqual(result, "embedding")

    def test_ensure_model_loaded_uses_native_load_profile(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()
        posts = []

        def fake_get(url, **kwargs):
            return FakeResponse({"models": []})

        def fake_post(url, **kwargs):
            posts.append((url, kwargs["json"]))
            return FakeResponse(
                {
                    "type": "llm",
                    "instance_id": "qwen2.5-14b-deepresearch-i1",
                    "load_time_seconds": 2.5,
                    "status": "loaded",
                    "load_config": kwargs["json"],
                }
            )

        result = model_lifecycle.ensure_model_loaded(
            "qwen2.5-14b-deepresearch-i1",
            route="research",
            cfg=cfg,
            get=fake_get,
            post=fake_post,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(posts[0][0], "http://localhost:1234/api/v1/models/load")
        self.assertEqual(posts[0][1]["context_length"], 8192)
        self.assertFalse(posts[0][1]["offload_kv_cache_to_gpu"])
        self.assertNotIn("ttl", posts[0][1])

    def test_ensure_model_loaded_normalizes_raw_runtime_config(self):
        from actions import model_lifecycle

        raw = {
            "lmstudio_native_url": "http://localhost:1234/api/v1",
            "lmstudio_explicit_load_enabled": True,
            "lmstudio_load_timeout_seconds": 91,
            "baseline_models": ["qwen/qwen3-4b-2507"],
        }
        posts = []

        def fake_get(url, **kwargs):
            return FakeResponse({"models": []})

        def fake_post(url, **kwargs):
            posts.append((url, kwargs))
            return FakeResponse({"instance_id": "qwen/qwen3-4b-2507", "status": "loaded"})

        result = model_lifecycle.ensure_model_loaded(
            "qwen/qwen3-4b-2507",
            route="quick",
            cfg=raw,
            get=fake_get,
            post=fake_post,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(posts[0][0], "http://localhost:1234/api/v1/models/load")
        self.assertEqual(posts[0][1]["timeout"], 91)


class ModelHealthStoreTests(unittest.TestCase):
    """Task A1: persisted per-model outcome history and cooldown state."""

    def setUp(self):
        from actions import model_lifecycle

        self.cfg = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(
                    Path(tempfile.gettempdir()) / f"jarvis-test-health-{uuid.uuid4().hex}.sqlite"
                ),
                "model_health_enabled": True,
                "model_health_failure_threshold": 2,
                "model_health_cooldown_seconds": [300, 900, 3600],
                "model_health_sample_ttl_seconds": 3600,
            }
        )
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.cfg["lease_db_path"]) + suffix)
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass

    def test_success_records_latency_and_clears_failures(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome(
            "marco-deepresearch-8b", outcome="timeout", cfg=self.cfg, now=1000.0
        )
        model_lifecycle.record_model_outcome(
            "marco-deepresearch-8b",
            outcome="ok",
            cfg=self.cfg,
            metrics={"first_token_seconds": 2.5, "tokens_per_second": 18.0},
            now=1010.0,
        )

        health = model_lifecycle.model_health("marco-deepresearch-8b", cfg=self.cfg, now=1010.0)
        self.assertEqual(health["last_outcome"], "ok")
        self.assertEqual(health["consecutive_failures"], 0)
        self.assertIsNone(health["cooldown_until"])
        self.assertAlmostEqual(health["ewma_first_token_seconds"], 2.5, places=3)
        self.assertAlmostEqual(health["ewma_tokens_per_second"], 18.0, places=3)

    def test_threshold_failures_open_a_cooldown(self):
        from actions import model_lifecycle

        for index in range(2):
            model_lifecycle.record_model_outcome(
                "qwen/qwen3.5-9b", outcome="timeout", cfg=self.cfg, now=1000.0 + index
            )

        health = model_lifecycle.model_health("qwen/qwen3.5-9b", cfg=self.cfg, now=1001.0)
        self.assertEqual(health["consecutive_failures"], 2)
        self.assertEqual(health["cooldown_until"], 1001.0 + 300)

        cooling, reason = model_lifecycle.is_model_cooling_down(
            "qwen/qwen3.5-9b", cfg=self.cfg, now=1001.0
        )
        self.assertTrue(cooling)
        self.assertIn("timeout", reason)

    def test_repeated_failures_escalate_the_backoff_tier(self):
        from actions import model_lifecycle

        for index in range(3):
            model_lifecycle.record_model_outcome(
                "qwen/qwen3.5-9b", outcome="empty_output", cfg=self.cfg, now=1000.0 + index
            )

        health = model_lifecycle.model_health("qwen/qwen3.5-9b", cfg=self.cfg, now=1002.0)
        self.assertEqual(health["consecutive_failures"], 3)
        self.assertEqual(health["cooldown_until"], 1002.0 + 900)

    def test_backoff_clamps_to_the_final_tier(self):
        from actions import model_lifecycle

        for index in range(9):
            model_lifecycle.record_model_outcome(
                "qwen/qwen3.5-9b", outcome="timeout", cfg=self.cfg, now=1000.0 + index
            )

        health = model_lifecycle.model_health("qwen/qwen3.5-9b", cfg=self.cfg, now=1008.0)
        self.assertEqual(health["cooldown_until"], 1008.0 + 3600)

    def test_inconclusive_outcome_does_not_advance_the_failure_counter(self):
        from actions import model_lifecycle

        # A lease wait, an unreachable backend, or a third-party OOM is not
        # evidence that this model is unreliable.
        for index in range(5):
            model_lifecycle.record_model_outcome(
                "qwen2.5-14b-deepresearch-i1",
                outcome="inconclusive",
                cfg=self.cfg,
                now=1000.0 + index,
            )

        health = model_lifecycle.model_health("qwen2.5-14b-deepresearch-i1", cfg=self.cfg, now=1005.0)
        self.assertEqual(health["consecutive_failures"], 0)
        self.assertIsNone(health["cooldown_until"])
        cooling, _ = model_lifecycle.is_model_cooling_down(
            "qwen2.5-14b-deepresearch-i1", cfg=self.cfg, now=1005.0
        )
        self.assertFalse(cooling)

    def test_cooldown_expires_and_the_model_becomes_eligible_again(self):
        from actions import model_lifecycle

        for index in range(2):
            model_lifecycle.record_model_outcome(
                "marco-deepresearch-8b", outcome="malformed_output", cfg=self.cfg, now=1000.0 + index
            )

        still_cooling, _ = model_lifecycle.is_model_cooling_down(
            "marco-deepresearch-8b", cfg=self.cfg, now=1001.0 + 299
        )
        self.assertTrue(still_cooling)

        expired, reason = model_lifecycle.is_model_cooling_down(
            "marco-deepresearch-8b", cfg=self.cfg, now=1001.0 + 301
        )
        self.assertFalse(expired)
        self.assertEqual(reason, "")

    def test_success_after_cooldown_resets_the_backoff_tier(self):
        from actions import model_lifecycle

        for index in range(3):
            model_lifecycle.record_model_outcome(
                "marco-deepresearch-8b", outcome="timeout", cfg=self.cfg, now=1000.0 + index
            )
        model_lifecycle.record_model_outcome(
            "marco-deepresearch-8b", outcome="ok", cfg=self.cfg, now=5000.0
        )
        model_lifecycle.record_model_outcome(
            "marco-deepresearch-8b", outcome="timeout", cfg=self.cfg, now=5001.0
        )

        health = model_lifecycle.model_health("marco-deepresearch-8b", cfg=self.cfg, now=5001.0)
        self.assertEqual(health["consecutive_failures"], 1)
        # Below the threshold of 2, so no cooldown is open yet.
        self.assertIsNone(health["cooldown_until"])

    def test_stale_sample_is_reported_as_stale_not_healthy(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome(
            "qwen/qwen3-4b-2507", outcome="ok", cfg=self.cfg, now=1000.0
        )

        fresh = model_lifecycle.model_health("qwen/qwen3-4b-2507", cfg=self.cfg, now=1100.0)
        self.assertEqual(fresh["state"], "healthy")

        stale = model_lifecycle.model_health("qwen/qwen3-4b-2507", cfg=self.cfg, now=1000.0 + 3601)
        self.assertEqual(stale["state"], "stale")

    def test_unknown_model_has_no_sample_and_is_not_cooling_down(self):
        from actions import model_lifecycle

        health = model_lifecycle.model_health("never-seen-model", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["state"], "unknown")
        self.assertEqual(health["sample_count"], 0)
        cooling, _ = model_lifecycle.is_model_cooling_down("never-seen-model", cfg=self.cfg, now=1000.0)
        self.assertFalse(cooling)

    def test_slow_first_token_is_recorded_as_degraded_not_as_failure(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome(
            "qwen/qwen3.5-9b",
            outcome="ok",
            cfg=self.cfg,
            metrics={"first_token_seconds": 111.0, "tokens_per_second": 1.2},
            now=1000.0,
        )

        health = model_lifecycle.model_health("qwen/qwen3.5-9b", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["state"], "degraded")
        self.assertEqual(health["consecutive_failures"], 0)

    def test_health_snapshot_lists_every_recorded_model(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome("model-a", outcome="ok", cfg=self.cfg, now=1000.0)
        for index in range(2):
            model_lifecycle.record_model_outcome(
                "model-b", outcome="timeout", cfg=self.cfg, now=1000.0 + index
            )

        snapshot = model_lifecycle.health_snapshot(self.cfg, now=1001.0)
        self.assertTrue(snapshot["ok"])
        by_model = {item["model"]: item for item in snapshot["models"]}
        self.assertEqual(by_model["model-a"]["state"], "healthy")
        self.assertEqual(by_model["model-b"]["state"], "cooling_down")
        self.assertEqual(snapshot["cooling_down_count"], 1)

    def test_health_survives_a_separate_connection(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome("model-a", outcome="ok", cfg=self.cfg, now=1000.0)

        # Cross-process durability: a fresh normalized config against the same
        # database file must observe the recorded sample.
        reopened = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(self.cfg["lease_db_path"]),
                "model_health_enabled": True,
            }
        )
        health = model_lifecycle.model_health("model-a", cfg=reopened, now=1000.0)
        self.assertEqual(health["last_outcome"], "ok")
        self.assertEqual(health["sample_count"], 1)

    def test_recording_is_a_no_op_when_health_is_disabled(self):
        from actions import model_lifecycle

        disabled = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(self.cfg["lease_db_path"]),
                "model_health_enabled": False,
            }
        )
        model_lifecycle.record_model_outcome("model-a", outcome="timeout", cfg=disabled, now=1000.0)
        model_lifecycle.record_model_outcome("model-a", outcome="timeout", cfg=disabled, now=1001.0)

        cooling, _ = model_lifecycle.is_model_cooling_down("model-a", cfg=disabled, now=1001.0)
        self.assertFalse(cooling)

    def test_model_identity_is_normalized(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome("Qwen/Qwen3-4B-2507", outcome="ok", cfg=self.cfg, now=1000.0)
        health = model_lifecycle.model_health("qwen/qwen3-4b-2507", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["sample_count"], 1)


class ReasoningBudgetTests(unittest.TestCase):
    """A reasoning model must not be blacklisted for our own token budget.

    `qwen/qwen3.5-9b` spends 110-190 completion tokens reasoning before it emits
    any content. Probed at 64 tokens it returns `finish_reason: length` with an
    empty `content` and 63 reasoning tokens. Recording that as `empty_output`
    blacklists a model that works correctly at a realistic budget.
    """

    def setUp(self):
        from actions import model_lifecycle

        self.cfg = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(
                    Path(tempfile.gettempdir()) / f"jarvis-test-reason-{uuid.uuid4().hex}.sqlite"
                ),
                "model_health_enabled": True,
                "model_health_probe_enabled": True,
                "model_health_probe_max_tokens": 64,
                "model_health_probe_reasoning_max_tokens": 512,
            }
        )
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(self.cfg["lease_db_path"]) + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _exhausted_response():
        return FakeResponse(
            {
                "choices": [
                    {"finish_reason": "length", "message": {"role": "assistant", "content": "", "reasoning_content": "Let me think about this..."}}
                ],
                "usage": {"completion_tokens": 64, "completion_tokens_details": {"reasoning_tokens": 63}},
            }
        )

    @staticmethod
    def _reasoning_inventory():
        return {
            "models": [
                {
                    "type": "llm",
                    "key": "qwen/qwen3.5-9b",
                    "display_name": "Qwen3.5 9B",
                    "max_context_length": 262144,
                    "capabilities": {"reasoning": {"default": "on"}, "trained_for_tool_use": True},
                    "loaded_instances": [{"id": "qwen/qwen3.5-9b", "config": {"context_length": 8192}}],
                }
            ]
        }

    def test_budget_exhaustion_is_not_attributed_to_the_model(self):
        from actions import model_lifecycle

        with mock.patch.object(
            model_lifecycle, "ensure_model_loaded", return_value={"ok": True, "instance_id": "qwen/qwen3.5-9b"}
        ):
            result = model_lifecycle.probe_model(
                "qwen/qwen3.5-9b",
                cfg=self.cfg,
                post=lambda *a, **k: self._exhausted_response(),
                get=lambda *a, **k: FakeResponse(self._reasoning_inventory()),
                now=1000.0,
            )

        self.assertEqual(result["outcome"], "inconclusive")
        self.assertEqual(result["reason"], "probe_budget_exhausted")
        health = model_lifecycle.model_health("qwen/qwen3.5-9b", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["consecutive_failures"], 0)

    def test_reasoning_models_get_the_larger_probe_budget(self):
        from actions import model_lifecycle

        captured = {}

        def fake_post(url, **kwargs):
            captured["max_tokens"] = kwargs["json"]["max_tokens"]
            return FakeResponse({"choices": [{"finish_reason": "stop", "message": {"content": "ready"}}]})

        with mock.patch.object(
            model_lifecycle, "ensure_model_loaded", return_value={"ok": True, "instance_id": "qwen/qwen3.5-9b"}
        ):
            model_lifecycle.probe_model(
                "qwen/qwen3.5-9b",
                cfg=self.cfg,
                post=fake_post,
                get=lambda *a, **k: FakeResponse(self._reasoning_inventory()),
                now=1000.0,
            )

        self.assertEqual(captured["max_tokens"], 512)

    def test_non_reasoning_models_keep_the_small_budget(self):
        from actions import model_lifecycle

        captured = {}

        def fake_post(url, **kwargs):
            captured["max_tokens"] = kwargs["json"]["max_tokens"]
            return FakeResponse({"choices": [{"finish_reason": "stop", "message": {"content": "ready"}}]})

        with mock.patch.object(
            model_lifecycle, "ensure_model_loaded", return_value={"ok": True, "instance_id": "qwen/qwen3-4b-2507"}
        ):
            model_lifecycle.probe_model(
                "qwen/qwen3-4b-2507",
                cfg=self.cfg,
                post=fake_post,
                get=lambda *a, **k: FakeResponse(models_payload()),
                now=1000.0,
            )

        self.assertEqual(captured["max_tokens"], 64)

    def test_genuine_empty_output_is_still_attributable(self):
        from actions import model_lifecycle

        # finish_reason `stop` with no content is a real defect, not our budget.
        def fake_post(url, **kwargs):
            return FakeResponse({"choices": [{"finish_reason": "stop", "message": {"content": ""}}]})

        with mock.patch.object(
            model_lifecycle, "ensure_model_loaded", return_value={"ok": True, "instance_id": "x"}
        ):
            result = model_lifecycle.probe_model(
                "qwen/qwen3-4b-2507",
                cfg=self.cfg,
                post=fake_post,
                get=lambda *a, **k: FakeResponse(models_payload()),
                now=1000.0,
            )

        self.assertEqual(result["outcome"], "empty_output")
        health = model_lifecycle.model_health("qwen/qwen3-4b-2507", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["consecutive_failures"], 1)

    def test_inventory_failure_does_not_break_the_probe(self):
        from actions import model_lifecycle

        def exploding_get(*a, **k):
            raise RuntimeError("native api unavailable")

        with mock.patch.object(
            model_lifecycle, "ensure_model_loaded", return_value={"ok": True, "instance_id": "x"}
        ):
            result = model_lifecycle.probe_model(
                "qwen/qwen3.5-9b",
                cfg=self.cfg,
                post=lambda *a, **k: FakeResponse(
                    {"choices": [{"finish_reason": "stop", "message": {"content": "ready"}}]}
                ),
                get=exploding_get,
                now=1000.0,
            )

        self.assertTrue(result["ok"])


class ProbeOperationTests(unittest.TestCase):
    """On-demand probe reachable through the model_lifecycle action facade."""

    def setUp(self):
        self.db_path = str(Path(tempfile.gettempdir()) / f"jarvis-test-op-{uuid.uuid4().hex}.sqlite")
        self.params_config = {
            "model_runtime_db_path": self.db_path,
            "model_health_enabled": True,
            "model_health_probe_enabled": True,
        }
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(self.db_path + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    def test_probe_operation_is_dispatched(self):
        from actions import model_lifecycle

        with mock.patch.object(
            model_lifecycle, "probe_model", return_value={"ok": True, "outcome": "ok"}
        ) as probe:
            payload = json.loads(
                model_lifecycle.model_lifecycle(
                    {
                        "operation": "probe",
                        "model": "marco-deepresearch-8b",
                        "route": "research",
                        "_config": dict(self.params_config),
                    }
                )
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(probe.call_args.args[0], "marco-deepresearch-8b")
        self.assertEqual(probe.call_args.kwargs["route"], "research")

    def test_probe_operation_requires_a_model(self):
        from actions import model_lifecycle

        payload = json.loads(
            model_lifecycle.model_lifecycle(
                {"operation": "probe", "_config": dict(self.params_config)}
            )
        )
        self.assertFalse(payload["ok"])
        self.assertIn("model", payload["error"].lower())

    def test_health_operation_reports_the_store(self):
        from actions import model_lifecycle

        cfg = model_lifecycle.resolve_config(dict(self.params_config))
        model_lifecycle.record_model_outcome("marco-deepresearch-8b", outcome="ok", cfg=cfg)

        payload = json.loads(
            model_lifecycle.model_lifecycle(
                {"operation": "model_health", "_config": dict(self.params_config)}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual([item["model"] for item in payload["models"]], ["marco-deepresearch-8b"])

    def test_probe_declares_itself_in_the_tool_schema(self):
        import main

        declaration = next(
            item for item in main.TOOL_DECLARATIONS if item["name"] == "model_lifecycle"
        )
        operations = declaration["parameters"]["properties"]["operation"]["description"]
        self.assertIn("probe", operations)
        self.assertIn("model_health", operations)


class ProbeLeaseWaitTests(unittest.TestCase):
    """A probe must never block a busy machine while waiting for the lease."""

    def setUp(self):
        from actions import model_lifecycle

        self.cfg = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(
                    Path(tempfile.gettempdir()) / f"jarvis-test-wait-{uuid.uuid4().hex}.sqlite"
                ),
                "model_health_enabled": True,
                "model_health_probe_enabled": True,
            }
        )
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(self.cfg["lease_db_path"]) + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    def test_probe_passes_its_wait_budget_to_the_lease(self):
        from actions import model_lifecycle

        with mock.patch.object(
            model_lifecycle,
            "acquire_generation_lease",
            return_value={"ok": False, "error": "busy"},
        ) as acquire:
            result = model_lifecycle.probe_model(
                "marco-deepresearch-8b", cfg=self.cfg, wait_seconds=0, now=1000.0
            )

        self.assertEqual(acquire.call_args.kwargs["wait_seconds"], 0)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "lease_unavailable")

    def test_unavailable_lease_records_inconclusive_not_a_failure(self):
        from actions import model_lifecycle

        with mock.patch.object(
            model_lifecycle,
            "acquire_generation_lease",
            return_value={"ok": False, "error": "busy"},
        ):
            model_lifecycle.probe_model(
                "marco-deepresearch-8b", cfg=self.cfg, wait_seconds=0, now=1000.0
            )

        health = model_lifecycle.model_health("marco-deepresearch-8b", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["consecutive_failures"], 0)


class ModelHealthSurfaceTests(unittest.TestCase):
    """Task A6: cooldown state is visible in status and in the process trace."""

    def setUp(self):
        from actions import model_lifecycle

        self.cfg = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(
                    Path(tempfile.gettempdir()) / f"jarvis-test-surface-{uuid.uuid4().hex}.sqlite"
                ),
                "model_health_enabled": True,
                "model_health_failure_threshold": 2,
                "model_health_cooldown_seconds": [300],
            }
        )
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(self.cfg["lease_db_path"]) + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    def test_status_reports_health_summary(self):
        from actions import model_lifecycle

        for _ in range(2):
            model_lifecycle.record_model_outcome(
                "qwen/qwen3.5-9b", outcome="timeout", cfg=self.cfg
            )

        def fake_get(url, **kwargs):
            return FakeResponse(models_payload())

        status = model_lifecycle.status(self.cfg, get=fake_get)
        self.assertIn("health", status)
        self.assertEqual(status["health"]["cooling_down_count"], 1)
        cooling = [item for item in status["health"]["models"] if item["state"] == "cooling_down"]
        self.assertEqual(cooling[0]["model"], "qwen/qwen3.5-9b")

    def test_entering_cooldown_emits_a_process_event(self):
        from actions import model_lifecycle
        from core import process_events

        events = []
        with mock.patch.object(process_events.PROCESS_EVENTS, "emit", side_effect=lambda **kw: events.append(kw)):
            for _ in range(2):
                model_lifecycle.record_model_outcome(
                    "qwen/qwen3.5-9b", outcome="timeout", cfg=self.cfg, error="slow generation"
                )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["category"], "model")
        self.assertIn("qwen/qwen3.5-9b", event["summary"])
        self.assertIn(event["severity"], {"warning", "error"})

    def test_no_event_when_no_cooldown_opens(self):
        from actions import model_lifecycle
        from core import process_events

        events = []
        with mock.patch.object(process_events.PROCESS_EVENTS, "emit", side_effect=lambda **kw: events.append(kw)):
            model_lifecycle.record_model_outcome("qwen/qwen3.5-9b", outcome="ok", cfg=self.cfg)
            model_lifecycle.record_model_outcome("qwen/qwen3.5-9b", outcome="timeout", cfg=self.cfg)

        self.assertEqual(events, [])

    def test_event_emission_failure_does_not_break_recording(self):
        from actions import model_lifecycle
        from core import process_events

        with mock.patch.object(
            process_events.PROCESS_EVENTS, "emit", side_effect=RuntimeError("hub is full")
        ):
            for _ in range(2):
                model_lifecycle.record_model_outcome(
                    "qwen/qwen3.5-9b", outcome="timeout", cfg=self.cfg
                )

        health = model_lifecycle.model_health("qwen/qwen3.5-9b", cfg=self.cfg)
        self.assertEqual(health["state"], "cooling_down")

    def test_no_event_is_emitted_when_health_is_disabled(self):
        from actions import model_lifecycle
        from core import process_events

        disabled = model_lifecycle.resolve_config(
            {"model_runtime_db_path": str(self.cfg["lease_db_path"]), "model_health_enabled": False}
        )
        events = []
        with mock.patch.object(process_events.PROCESS_EVENTS, "emit", side_effect=lambda **kw: events.append(kw)):
            for _ in range(3):
                model_lifecycle.record_model_outcome("qwen/qwen3.5-9b", outcome="timeout", cfg=disabled)

        self.assertEqual(events, [])


class ModelProbeTests(unittest.TestCase):
    """Task A4: bounded active probe for a model with no recent sample."""

    def setUp(self):
        from actions import model_lifecycle

        self.cfg = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(
                    Path(tempfile.gettempdir()) / f"jarvis-test-probe-{uuid.uuid4().hex}.sqlite"
                ),
                "model_health_enabled": True,
                "model_health_probe_enabled": True,
                "model_health_probe_timeout_seconds": 30,
                "model_health_probe_max_tokens": 32,
                "model_health_sample_ttl_seconds": 3600,
            }
        )
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(self.cfg["lease_db_path"]) + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _ready(**overrides):
        return mock.patch.object(
            __import__("actions.model_lifecycle", fromlist=["model_lifecycle"]),
            "ensure_model_loaded",
            return_value={"ok": True, "instance_id": "probe-instance", **overrides},
        )

    def test_probe_is_skipped_when_probing_is_disabled(self):
        from actions import model_lifecycle

        cfg = model_lifecycle.resolve_config(
            {
                "model_runtime_db_path": str(self.cfg["lease_db_path"]),
                "model_health_enabled": True,
                "model_health_probe_enabled": False,
            }
        )
        posts = []

        result = model_lifecycle.probe_model(
            "marco-deepresearch-8b",
            cfg=cfg,
            post=lambda *a, **k: posts.append(k) or FakeResponse({}),
            now=1000.0,
        )
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "probe_disabled")
        self.assertEqual(posts, [])

    def test_probe_is_skipped_when_a_recent_sample_exists(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome(
            "marco-deepresearch-8b", outcome="ok", cfg=self.cfg, now=1000.0
        )
        posts = []

        result = model_lifecycle.probe_model(
            "marco-deepresearch-8b",
            cfg=self.cfg,
            post=lambda *a, **k: posts.append(k) or FakeResponse({}),
            now=1100.0,
        )
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "recent_sample")
        self.assertEqual(posts, [])

    def test_probe_runs_for_an_unknown_model_and_records_ok(self):
        from actions import model_lifecycle

        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["timeout"] = kwargs.get("timeout")
            return FakeResponse({"choices": [{"message": {"content": "ready"}}]})

        with self._ready():
            result = model_lifecycle.probe_model(
                "marco-deepresearch-8b", cfg=self.cfg, post=fake_post, now=1000.0
            )

        self.assertTrue(result["ok"])
        self.assertFalse(result.get("skipped"))
        self.assertEqual(result["outcome"], "ok")
        self.assertTrue(result["sentinel_matched"])
        self.assertEqual(captured["timeout"], 30)
        self.assertEqual(captured["json"]["max_tokens"], 32)
        self.assertIn("/chat/completions", captured["url"])

        health = model_lifecycle.model_health("marco-deepresearch-8b", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["last_outcome"], "ok")
        self.assertEqual(health["last_source"], "probe")

    def test_probe_runs_again_once_the_sample_is_stale(self):
        from actions import model_lifecycle

        model_lifecycle.record_model_outcome(
            "marco-deepresearch-8b", outcome="ok", cfg=self.cfg, now=1000.0
        )

        def fake_post(url, **kwargs):
            return FakeResponse({"choices": [{"message": {"content": "ready"}}]})

        with self._ready():
            result = model_lifecycle.probe_model(
                "marco-deepresearch-8b", cfg=self.cfg, post=fake_post, now=1000.0 + 3601
            )
        self.assertFalse(result.get("skipped"))

    def test_probe_empty_response_is_attributable(self):
        from actions import model_lifecycle

        def fake_post(url, **kwargs):
            return FakeResponse({"choices": [{"message": {"content": ""}}]})

        with self._ready():
            result = model_lifecycle.probe_model(
                "qwen/qwen3.5-9b", cfg=self.cfg, post=fake_post, now=1000.0
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["outcome"], "empty_output")
        health = model_lifecycle.model_health("qwen/qwen3.5-9b", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["consecutive_failures"], 1)

    def test_probe_timeout_is_attributable(self):
        from actions import model_lifecycle

        def fake_post(url, **kwargs):
            raise requests.exceptions.Timeout("probe exceeded its budget")

        with self._ready():
            result = model_lifecycle.probe_model(
                "qwen/qwen3.5-9b", cfg=self.cfg, post=fake_post, now=1000.0
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["outcome"], "timeout")

    def test_probe_load_failure_is_attributable(self):
        from actions import model_lifecycle

        with mock.patch.object(
            model_lifecycle, "ensure_model_loaded", return_value={"ok": False, "error": "no room"}
        ):
            result = model_lifecycle.probe_model(
                "qwen/qwen3.5-9b",
                cfg=self.cfg,
                post=lambda *a, **k: FakeResponse({}),
                now=1000.0,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["outcome"], "load_failed")

    def test_probe_missing_sentinel_is_not_treated_as_a_failure(self):
        from actions import model_lifecycle

        # A verbose but working model must not be blacklisted for adding preamble.
        def fake_post(url, **kwargs):
            return FakeResponse(
                {"choices": [{"message": {"content": "Certainly! Here is my answer."}}]}
            )

        with self._ready():
            result = model_lifecycle.probe_model(
                "google/gemma-4-e4b", cfg=self.cfg, post=fake_post, now=1000.0
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["outcome"], "ok")
        self.assertFalse(result["sentinel_matched"])
        health = model_lifecycle.model_health("google/gemma-4-e4b", cfg=self.cfg, now=1000.0)
        self.assertEqual(health["consecutive_failures"], 0)

    def test_probe_does_not_leak_a_generation_lease(self):
        from actions import model_lifecycle

        def fake_post(url, **kwargs):
            raise requests.exceptions.Timeout("probe exceeded its budget")

        with self._ready():
            model_lifecycle.probe_model(
                "qwen/qwen3.5-9b", cfg=self.cfg, post=fake_post, now=1000.0
            )

        self.assertEqual(
            model_lifecycle.persistent_generation_snapshot(self.cfg)["leases"], []
        )

    def test_probe_holds_the_generation_lease_while_running(self):
        from actions import model_lifecycle

        observed = {}

        def fake_post(url, **kwargs):
            observed["leases"] = model_lifecycle.persistent_generation_snapshot(self.cfg)["leases"]
            return FakeResponse({"choices": [{"message": {"content": "ready"}}]})

        with self._ready():
            model_lifecycle.probe_model(
                "qwen/qwen3.5-9b", cfg=self.cfg, post=fake_post, now=1000.0
            )

        # A probe must not bypass the one-generation-at-a-time guarantee.
        self.assertEqual(len(observed["leases"]), 1)


if __name__ == "__main__":
    unittest.main()
