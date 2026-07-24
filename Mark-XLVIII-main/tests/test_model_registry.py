import unittest
from unittest import mock


def lmstudio_models_payload():
    """Mirrors the live shape recorded by scripts/probe-lmstudio-model-fields.py."""
    return {
        "ok": True,
        "models": [
            {
                "type": "llm",
                "publisher": "ATH-MaaS",
                "key": "marco-deepresearch-8b",
                "display_name": "Marco DeepResearch 8B",
                "architecture": "qwen3",
                "quantization": {"name": "Q4_K_S", "bits_per_weight": 4},
                "size_bytes": 4802012608,
                "params_string": "8B",
                "max_context_length": 131072,
                "format": "gguf",
                "capabilities": {"vision": False, "trained_for_tool_use": True},
                "loaded_instances": [],
            },
            {
                "type": "llm",
                "publisher": "local",
                "key": "unlimited-ocr",
                "display_name": "Unlimited OCR",
                "architecture": "qwen2",
                "quantization": {"name": "Q4_K_M", "bits_per_weight": 4},
                "size_bytes": 2621440000,
                "params_string": "3B",
                "max_context_length": 32768,
                "format": "gguf",
                "capabilities": {"vision": True, "trained_for_tool_use": False},
                "loaded_instances": [],
            },
            {
                "type": "llm",
                "publisher": "qwen",
                "key": "qwen/qwen3-4b-2507",
                "display_name": "Qwen3 4B 2507",
                "architecture": "qwen3",
                "quantization": {"name": "Q4_K_M", "bits_per_weight": 4},
                "size_bytes": 2497459753,
                "params_string": "4B",
                "max_context_length": 262144,
                "format": "gguf",
                "capabilities": {"vision": False, "trained_for_tool_use": True},
                "loaded_instances": [
                    {"id": "qwen/qwen3-4b-2507", "config": {"context_length": 4096, "parallel": 4}}
                ],
            },
        ],
    }


def isolated_config(**overrides):
    """Never read the live health store from a unit test.

    registry_status() with no config resolves the real runtime.json, which points
    at the machine's real model-runtime database. Recorded health from live use
    then changes which model wins the sort and makes these tests non-deterministic.
    """
    import tempfile
    import uuid
    from pathlib import Path

    config = {
        "model_runtime_db_path": str(
            Path(tempfile.gettempdir()) / f"jarvis-test-registry-{uuid.uuid4().hex}.sqlite"
        ),
        "model_health_enabled": False,
        "model_health_probe_enabled": False,
    }
    config.update(overrides)
    return config


def registry_status_with(payload=None, cloud_state="unlinked", config=None):
    from actions import model_registry

    with mock.patch.object(
        model_registry.model_lifecycle, "list_models", return_value=payload or lmstudio_models_payload()
    ), mock.patch.object(model_registry, "get_session_broker") as broker:
        broker.return_value.status.return_value = {"state": cloud_state, "reason": ""}
        return model_registry.registry_status(config if config is not None else isolated_config())


def record_for(status, model_key):
    for record in status["models"]:
        if record.get("model") == model_key:
            return record
    raise AssertionError(f"{model_key!r} not present in registry status")


class ProfileResolutionTests(unittest.TestCase):
    """Task B1: profile lookup must not resolve a model onto a different model's profile."""

    def test_substring_key_does_not_inherit_longer_profile(self):
        from actions.model_registry import _profile_for

        # `qwen3-8b` is installed on the host and its key is a strict substring of
        # `deepseek-r1-0528-qwen3-8b`. Bidirectional substring matching resolved it
        # onto DeepSeek's profile, inheriting tool_use=False while LM Studio reports
        # the model as tool-capable.
        profile = _profile_for("qwen3-8b")
        self.assertNotEqual(profile["profile_id"], "deepseek-r1-0528-qwen3-8b")

    def test_exact_key_match_wins(self):
        from actions.model_registry import MODEL_PROFILES, _profile_for

        for key in MODEL_PROFILES:
            if key == "openai":
                continue
            with self.subTest(model=key):
                self.assertEqual(_profile_for(key)["profile_id"], key)

    def test_variant_suffix_resolves_to_base_profile(self):
        from actions.model_registry import _profile_for

        # LM Studio reports variant-qualified keys such as `<model>@q4_k_m`.
        self.assertEqual(
            _profile_for("qwen/qwen3-4b-2507@q4_k_m")["profile_id"],
            "qwen/qwen3-4b-2507",
        )

    def test_unknown_model_returns_uncalibrated_default(self):
        from actions.model_registry import _profile_for

        profile = _profile_for("unlimited-ocr")
        self.assertEqual(profile["profile_id"], "unlimited-ocr")
        self.assertEqual(profile["roles"], ["worker"])
        self.assertIn("has not been calibrated", " ".join(profile["known_failures"]))

    def test_longer_key_does_not_resolve_to_shorter_profile(self):
        from actions.model_registry import _profile_for

        # The inverse direction of the same defect.
        profile = _profile_for("marco-deepresearch-8b-experimental-fork")
        self.assertEqual(profile["profile_id"], "marco-deepresearch-8b-experimental-fork")

    def test_openai_profile_is_never_returned_for_a_local_model(self):
        from actions.model_registry import _profile_for

        self.assertNotEqual(_profile_for("openai-ish-local-model")["profile_id"], "openai")


class ReportedCapabilityTests(unittest.TestCase):
    """Task B2: LM Studio's reported facts outrank the hand-declared table."""

    def test_reported_context_outranks_declared_context(self):
        status = registry_status_with()
        record = record_for(status, "marco-deepresearch-8b")
        # MODEL_PROFILES declares 32768; LM Studio reports 131072.
        self.assertEqual(record["context_window"], 131072)

    def test_reported_tool_use_outranks_declared_tool_use(self):
        from actions.model_registry import MODEL_PROFILES

        self.assertFalse(MODEL_PROFILES["marco-deepresearch-8b"]["tool_use"])
        record = record_for(registry_status_with(), "marco-deepresearch-8b")
        self.assertTrue(record["tool_use"])

    def test_vision_capability_comes_from_lmstudio(self):
        status = registry_status_with()
        self.assertTrue(record_for(status, "unlimited-ocr")["vision"])
        self.assertFalse(record_for(status, "marco-deepresearch-8b")["vision"])

    def test_uncalibrated_model_is_not_failed_on_a_fabricated_context(self):
        from actions.model_registry import meets_floor

        record = record_for(registry_status_with(), "unlimited-ocr")
        # The uncalibrated default declares 8192, which fails the 16000 research floor.
        # The real ceiling is 32768, so context must no longer be a failure reason.
        self.assertEqual(record["context_window"], 32768)
        _, reasons = meets_floor(record, "research")
        self.assertNotIn("context_window_below_floor", reasons)
        # It must still fail on the one field LM Studio cannot report.
        self.assertIn("structured_output_below_floor", reasons)

    def test_structured_output_remains_declared(self):
        record = record_for(registry_status_with(), "marco-deepresearch-8b")
        self.assertEqual(record["structured_output"], "medium")

    def test_field_provenance_is_recorded(self):
        record = record_for(registry_status_with(), "marco-deepresearch-8b")
        self.assertIn("context_window", record["reported_fields"])
        self.assertIn("tool_use", record["reported_fields"])
        self.assertIn("structured_output", record["declared_fields"])

    def test_missing_capability_block_falls_back_to_declared(self):
        payload = {
            "ok": True,
            "models": [
                {
                    "type": "llm",
                    "key": "qwen/qwen3.5-9b",
                    "display_name": "Qwen3.5 9B",
                    "loaded_instances": [],
                }
            ],
        }
        record = record_for(registry_status_with(payload), "qwen/qwen3.5-9b")
        self.assertEqual(record["context_window"], 32768)
        self.assertTrue(record["tool_use"])
        self.assertEqual(record["reported_fields"], [])

    def test_measured_size_is_surfaced_for_admission(self):
        record = record_for(registry_status_with(), "qwen/qwen3-4b-2507")
        self.assertEqual(record["size_bytes"], 2497459753)
        self.assertEqual(record["loaded_instances"], 1)

    def test_selection_still_returns_a_worker_for_plan_start(self):
        from actions import model_registry

        # plan_workflow gates START PLAN on this call; it must keep resolving.
        with mock.patch.object(
            model_registry.model_lifecycle, "list_models", return_value=lmstudio_models_payload()
        ), mock.patch.object(model_registry, "get_session_broker") as broker:
            broker.return_value.status.return_value = {"state": "unlinked", "reason": ""}
            decision = model_registry.select_for_role("worker", isolated_config())
        self.assertTrue(decision["ok"])
        self.assertEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")


class HealthGatedSelectionTests(unittest.TestCase):
    """Task A5: a cooling-down model is not selectable."""

    def setUp(self):
        import tempfile
        import uuid
        from pathlib import Path

        from actions import model_lifecycle

        self.db_path = str(Path(tempfile.gettempdir()) / f"jarvis-test-gate-{uuid.uuid4().hex}.sqlite")
        self.config = {
            "model_runtime_db_path": self.db_path,
            "model_health_enabled": True,
            "model_health_failure_threshold": 2,
            "model_health_cooldown_seconds": [300],
        }
        self.lifecycle_cfg = model_lifecycle.resolve_config(dict(self.config))
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        from pathlib import Path

        for suffix in ("", "-wal", "-shm"):
            try:
                Path(self.db_path + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    def _cool_down(self, model):
        from actions import model_lifecycle

        for _ in range(2):
            model_lifecycle.record_model_outcome(model, outcome="timeout", cfg=self.lifecycle_cfg)

    def _status(self):
        from actions import model_registry

        with mock.patch.object(
            model_registry.model_lifecycle, "list_models", return_value=lmstudio_models_payload()
        ), mock.patch.object(model_registry, "get_session_broker") as broker:
            broker.return_value.status.return_value = {"state": "unlinked", "reason": ""}
            return model_registry.registry_status(dict(self.config))

    def test_status_reports_health_cooldown_and_last_error(self):
        self._cool_down("marco-deepresearch-8b")
        record = record_for(self._status(), "marco-deepresearch-8b")
        self.assertEqual(record["health"], "cooling_down")
        self.assertIsNotNone(record["cooldown_until"])
        self.assertFalse(record["available"])
        self.assertTrue(record["installed"])

    def test_healthy_model_stays_available(self):
        record = record_for(self._status(), "qwen/qwen3-4b-2507")
        self.assertTrue(record["available"])
        self.assertEqual(record["health"], "unknown")

    def test_selection_skips_a_cooling_down_model(self):
        from actions import model_registry

        self._cool_down("qwen/qwen3-4b-2507")
        decision = model_registry.select_for_role("worker", dict(self.config), status_payload=self._status())
        self.assertTrue(decision["ok"])
        self.assertNotEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")

    def test_all_candidates_cooling_down_fails_explicitly(self):
        from actions import model_registry

        for model in ("qwen/qwen3-4b-2507", "marco-deepresearch-8b", "unlimited-ocr"):
            self._cool_down(model)

        decision = model_registry.select_for_role("worker", dict(self.config), status_payload=self._status())
        self.assertFalse(decision["ok"])
        # A workflow must pause on an explicit reason, not silently drop below the floor.
        self.assertIn("cooling down", decision["error"].lower())

    def test_behaviour_is_unchanged_when_health_is_disabled(self):
        from actions import model_registry

        self._cool_down("qwen/qwen3-4b-2507")
        disabled = dict(self.config)
        disabled["model_health_enabled"] = False

        with mock.patch.object(
            model_registry.model_lifecycle, "list_models", return_value=lmstudio_models_payload()
        ), mock.patch.object(model_registry, "get_session_broker") as broker:
            broker.return_value.status.return_value = {"state": "unlinked", "reason": ""}
            status = model_registry.registry_status(disabled)

        record = record_for(status, "qwen/qwen3-4b-2507")
        self.assertTrue(record["available"])
        decision = model_registry.select_for_role("worker", disabled, status_payload=status)
        self.assertEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")


class ColdSelectionProbeTests(unittest.TestCase):
    """Prove a never-measured specialist responds before a workflow commits to it."""

    def setUp(self):
        import tempfile
        import uuid
        from pathlib import Path

        self.db_path = str(Path(tempfile.gettempdir()) / f"jarvis-test-cold-{uuid.uuid4().hex}.sqlite")
        self.config = {
            "model_runtime_db_path": self.db_path,
            "model_health_enabled": True,
            "model_health_probe_enabled": True,
        }
        self.probed = []
        self.addCleanup(self._remove_db)

    def _remove_db(self):
        from pathlib import Path

        for suffix in ("", "-wal", "-shm"):
            try:
                Path(self.db_path + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    def _status(self, health_by_model=None):
        status = registry_status_with()
        for record in status["models"]:
            if record["provider"] != "lmstudio":
                continue
            state = (health_by_model or {}).get(record["model"], "unknown")
            record["health"] = state
            # Mirror what registry_status derives from the health store.
            record["available"] = state != "cooling_down"
        return status

    def _probe(self, result_by_model):
        def fake_probe(model, **kwargs):
            self.probed.append(model)
            return result_by_model.get(model, {"ok": True, "outcome": "ok"})

        return fake_probe

    def test_probing_is_off_unless_requested(self):
        from actions import model_registry

        model_registry.select_for_role(
            "worker", dict(self.config), status_payload=self._status(), probe_fn=self._probe({})
        )
        self.assertEqual(self.probed, [])

    def test_cold_candidate_is_probed_before_selection(self):
        from actions import model_registry

        decision = model_registry.select_for_role(
            "worker",
            dict(self.config),
            status_payload=self._status(),
            probe=True,
            probe_fn=self._probe({}),
        )
        self.assertTrue(decision["ok"])
        self.assertEqual(self.probed, [decision["selected"]["model"]])
        self.assertTrue(decision["probed"])

    def test_measured_candidate_is_not_probed(self):
        from actions import model_registry

        status = self._status({"qwen/qwen3-4b-2507": "healthy"})
        decision = model_registry.select_for_role(
            "worker", dict(self.config), status_payload=status, probe=True, probe_fn=self._probe({})
        )
        self.assertEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")
        self.assertEqual(self.probed, [])

    def test_failed_probe_moves_to_the_next_candidate(self):
        from actions import model_registry

        status = self._status()
        decision = model_registry.select_for_role(
            "worker",
            dict(self.config),
            status_payload=status,
            probe=True,
            probe_fn=self._probe(
                {"qwen/qwen3-4b-2507": {"ok": False, "outcome": "timeout", "error": "no response"}}
            ),
        )
        self.assertTrue(decision["ok"])
        self.assertNotEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")
        self.assertIn("qwen/qwen3-4b-2507", decision["probe_failures"])

    def test_probe_count_is_bounded(self):
        from actions import model_registry

        decision = model_registry.select_for_role(
            "worker",
            dict(self.config),
            status_payload=self._status(),
            probe=True,
            probe_fn=self._probe(
                {
                    "qwen/qwen3-4b-2507": {"ok": False, "outcome": "timeout"},
                    "marco-deepresearch-8b": {"ok": False, "outcome": "timeout"},
                    "unlimited-ocr": {"ok": False, "outcome": "timeout"},
                }
            ),
        )
        # Never probe the whole inventory looking for a winner.
        self.assertLessEqual(len(self.probed), model_registry.MAX_COLD_PROBES)
        self.assertEqual(decision["probed"], self.probed)

    def test_busy_lease_does_not_block_selection(self):
        from actions import model_registry

        decision = model_registry.select_for_role(
            "worker",
            dict(self.config),
            status_payload=self._status(),
            probe=True,
            probe_fn=self._probe(
                {
                    "qwen/qwen3-4b-2507": {
                        "ok": False,
                        "skipped": True,
                        "reason": "lease_unavailable",
                    }
                }
            ),
        )
        # A skipped probe is not a failure; the candidate still wins.
        self.assertEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")
        self.assertEqual(decision["probe_failures"], [])

    def test_probe_machinery_failure_does_not_block_selection(self):
        from actions import model_registry

        def exploding_probe(model, **kwargs):
            raise RuntimeError("probe subsystem is broken")

        decision = model_registry.select_for_role(
            "worker",
            dict(self.config),
            status_payload=self._status(),
            probe=True,
            probe_fn=exploding_probe,
        )
        self.assertTrue(decision["ok"])

    def test_failing_candidate_is_reprobed_not_trusted(self):
        from actions import model_registry

        # One probe failure is below the cooldown threshold, so the model stays
        # `available`. When it is the only candidate left it must still be
        # re-probed rather than trusted — otherwise a workflow is handed the
        # model that just failed.
        status = self._status(
            {
                "qwen/qwen3-4b-2507": "failing",
                "marco-deepresearch-8b": "cooling_down",
                "unlimited-ocr": "cooling_down",
            }
        )
        decision = model_registry.select_for_role(
            "worker", dict(self.config), status_payload=status, probe=True, probe_fn=self._probe({})
        )
        self.assertEqual(self.probed, ["qwen/qwen3-4b-2507"])
        self.assertEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")

    def test_degraded_candidate_is_accepted_without_reprobing(self):
        from actions import model_registry

        # `degraded` means slow but working; it has a usable measurement.
        status = self._status({"qwen/qwen3-4b-2507": "degraded"})
        decision = model_registry.select_for_role(
            "worker", dict(self.config), status_payload=status, probe=True, probe_fn=self._probe({})
        )
        self.assertEqual(decision["selected"]["model"], "qwen/qwen3-4b-2507")
        self.assertEqual(self.probed, [])

    def test_healthy_candidate_outranks_a_failing_peer(self):
        from actions import model_registry

        status = self._status(
            {"qwen/qwen3-4b-2507": "failing", "marco-deepresearch-8b": "healthy"}
        )
        decision = model_registry.select_for_role(
            "worker", dict(self.config), status_payload=status, probe=True, probe_fn=self._probe({})
        )
        self.assertEqual(decision["selected"]["model"], "marco-deepresearch-8b")
        self.assertEqual(self.probed, [])

    def test_probing_is_inert_when_the_probe_flag_is_off(self):
        from actions import model_registry

        disabled = dict(self.config)
        disabled["model_health_probe_enabled"] = False
        model_registry.select_for_role(
            "worker", disabled, status_payload=self._status(), probe=True, probe_fn=self._probe({})
        )
        self.assertEqual(self.probed, [])


class RouteInventoryTests(unittest.TestCase):
    """Task B3: a configured model that is not installed must not be advertised."""

    def test_absent_route_model_is_reported_missing(self):
        from actions.model_registry import route_inventory_diagnostics

        result = route_inventory_diagnostics(
            {"model_routes": {"vision": ["unlimited-ocr", "not-installed-30b"]}},
            status_payload=registry_status_with(),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            [(item["route"], item["model"]) for item in result["missing"]],
            [("vision", "not-installed-30b")],
        )

    def test_installed_route_models_are_not_reported_missing(self):
        from actions.model_registry import route_inventory_diagnostics

        result = route_inventory_diagnostics(
            {"model_routes": {"worker": ["qwen/qwen3-4b-2507", "unlimited-ocr"]}},
            status_payload=registry_status_with(),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])

    def test_diagnostics_are_skipped_when_lmstudio_is_unreachable(self):
        from actions.model_registry import route_inventory_diagnostics

        # An unreachable backend must not be reported as "every model is missing".
        result = route_inventory_diagnostics(
            {"model_routes": {"vision": ["anything"]}},
            status_payload={"models": [], "lmstudio_health": "unavailable"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["reason"], "lmstudio_unavailable")

    def test_shipped_config_does_not_route_to_the_uninstalled_30b(self):
        import json
        from pathlib import Path

        # `qwen3-vl-30b-a3b-instruct` is not installed on this host. RAL-final
        # listed resolving or removing it as prioritised next step #5; advertising
        # an absent model as a vision fallback makes capability health dishonest.
        config = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "runtime.json").read_text(encoding="utf-8")
        )
        routed = {
            model
            for models in (config.get("model_routes") or {}).values()
            for model in models
        }
        self.assertNotIn("qwen3-vl-30b-a3b-instruct", routed)


if __name__ == "__main__":
    unittest.main()
