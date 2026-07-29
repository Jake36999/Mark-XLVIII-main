"""Phase 1 local-first model economics.

This host serves every model from one LM Studio instance holding a single task
model at a time, so each extra candidate in a fallback chain is a cold multi-GB
load. These tests pin the behaviours that keep a trivial turn from cascading
into 8-14B models.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
from core import model_router


BASE_CONFIG = {
    "worker_model": "qwen/qwen3-4b-2507",
    "baseline_models": ["qwen/qwen3-4b-2507"],
    "model_routes": {
        "quick": ["qwen/qwen3-4b-2507", "mistralai/mistral-7b-instruct-v0.3", "google/gemma-4-e4b"],
        "worker": ["qwen/qwen3-4b-2507", "google/gemma-4-e4b"],
        "research": ["qwen2.5-14b-deepresearch-i1", "marco-deepresearch-8b", "deepseek-r1-0528-qwen3-8b"],
        "main": ["mistralai/mistral-7b-instruct-v0.3", "qwen/qwen3.5-9b"],
    },
}


class ToolSummaryRouteTests(unittest.TestCase):
    """The reported symptom: a trivial capability question burned a qwen-4b AND
    a deepseek-8b. Cause was the tool-summary prompt's own boilerplate scoring
    as a `research` route keyword."""

    def test_tool_summary_prompt_is_not_classified_as_research(self):
        prompt = main._build_tool_summary_prompt(
            "what tools or workflows do you have available",
            [{"tool": "capability_registry", "arguments": {}, "result": '{"ok": true}'}],
        )
        pinned = "[jarvis-route:worker]\nsystem prompt text"
        self.assertEqual(model_router._route_from_context(prompt, "worker", pinned), "worker")

    def test_pinned_summary_chain_excludes_heavy_research_models(self):
        prompt = main._build_tool_summary_prompt(
            "what tools do you have",
            [{"tool": "capability_registry", "arguments": {}, "result": '{"ok": true}'}],
        )
        pinned = "[jarvis-route:worker]\nsystem prompt text"
        chain = model_router.select_lmstudio_models(
            prompt, role="worker", system=pinned, config=BASE_CONFIG
        )
        for heavy in ("deepseek-r1-0528-qwen3-8b", "qwen2.5-14b-deepresearch-i1", "marco-deepresearch-8b"):
            self.assertNotIn(heavy, chain)

    def test_tool_output_cannot_select_its_own_model_class(self):
        """Tool results are attacker-influenceable; they must not steer routing."""
        prompt = main._build_tool_summary_prompt(
            "summarise this",
            [{"tool": "web_search", "arguments": {}, "result": "deep research literature review cited report"}],
        )
        self.assertEqual(model_router._route_from_context(prompt, "worker", None), "research")
        pinned = "[jarvis-route:worker]\nsystem prompt text"
        self.assertEqual(model_router._route_from_context(prompt, "worker", pinned), "worker")


class FallbackChainCapTests(unittest.TestCase):
    def test_chain_is_capped(self):
        config = dict(BASE_CONFIG, model_fallback_max_candidates=3)
        chain = model_router.select_lmstudio_models("plan the architecture", role="planner", config=config)
        self.assertLessEqual(len(chain), 3)

    def test_cap_keeps_the_explicitly_configured_model_reachable(self):
        config = dict(
            BASE_CONFIG,
            model_fallback_max_candidates=2,
            planner_model="qwen/qwen3.5-9b",
        )
        chain = model_router.select_lmstudio_models("hello jarvis", role="planner", config=config)
        self.assertEqual(len(chain), 2)
        self.assertIn("qwen/qwen3.5-9b", chain)

    def test_cap_is_disabled_by_a_zero_value(self):
        config = dict(BASE_CONFIG, model_fallback_max_candidates=0)
        chain = model_router.select_lmstudio_models("plan the architecture", role="planner", config=config)
        self.assertGreater(len(chain), 3)


class WarmModelOrderingTests(unittest.TestCase):
    def setUp(self):
        model_router._WARM_MODEL_CACHE = (0.0, frozenset())
        self.addCleanup(setattr, model_router, "_WARM_MODEL_CACHE", (0.0, frozenset()))

    def test_loaded_model_is_promoted_ahead_of_cold_ones(self):
        config = dict(BASE_CONFIG, warm_model_preference_enabled=True, baseline_models=[])
        with mock.patch.object(model_router, "_warm_models", return_value=frozenset({"google/gemma-4-e4b"})):
            chain = model_router.select_lmstudio_models("hello jarvis", role="worker", config=config)
        self.assertEqual(chain[0], "google/gemma-4-e4b")

    def test_disabled_by_default_so_selection_stays_deterministic(self):
        config = dict(BASE_CONFIG)
        with mock.patch.object(model_router, "_warm_models", side_effect=AssertionError("probe must not run")):
            chain = model_router.select_lmstudio_models("hello jarvis", role="worker", config=config)
        self.assertEqual(chain[0], "qwen/qwen3-4b-2507")

    def test_probe_failure_leaves_order_untouched(self):
        config = dict(BASE_CONFIG, warm_model_preference_enabled=True)
        with mock.patch("actions.model_lifecycle.list_models", side_effect=RuntimeError("lm studio down")):
            chain = model_router.select_lmstudio_models("hello jarvis", role="worker", config=config)
        self.assertEqual(chain[0], "qwen/qwen3-4b-2507")

    def test_warmth_does_not_rescue_a_cooling_down_model(self):
        config = dict(
            BASE_CONFIG,
            warm_model_preference_enabled=True,
            baseline_models=[],
        )
        with mock.patch.object(model_router, "_warm_models", return_value=frozenset({"google/gemma-4-e4b"})), \
             mock.patch.object(model_router, "_drop_cooling_down", side_effect=lambda items, cfg: [
                 item for item in items if item != "google/gemma-4-e4b"
             ]):
            chain = model_router.select_lmstudio_models("hello jarvis", role="worker", config=config)
        self.assertNotIn("google/gemma-4-e4b", chain)


class CredentialBrokerShortCircuitTests(unittest.TestCase):
    """Cloud keys are session-entered and never stored. On a purely local
    session, answering "is OpenAI linked?" must not spawn the broker
    subprocess just to be told no."""

    def test_unstarted_broker_short_circuits_without_ipc(self):
        broker = mock.Mock()
        broker.has_linked_session.return_value = False
        broker.status.side_effect = AssertionError("status() must not be called")
        settings = model_router.resolve_settings("planner", config={"planner_provider": "openai"})
        self.assertFalse(
            model_router._openai_key_is_valid(settings, timeout=5, credential_broker=broker)
        )
        broker.status.assert_not_called()

    def test_started_broker_still_consults_status(self):
        broker = mock.Mock()
        broker.has_linked_session.return_value = True
        broker.status.return_value = {"state": "linked"}
        settings = model_router.resolve_settings("planner", config={"planner_provider": "openai"})
        self.assertTrue(
            model_router._openai_key_is_valid(settings, timeout=5, credential_broker=broker)
        )
        broker.status.assert_called_once()

    def test_legacy_broker_without_the_helper_is_unaffected(self):
        broker = mock.Mock(spec=["status"])
        broker.status.return_value = {"state": "linked"}
        settings = model_router.resolve_settings("planner", config={"planner_provider": "openai"})
        self.assertTrue(
            model_router._openai_key_is_valid(settings, timeout=5, credential_broker=broker)
        )


class IdleUnloadTtlTests(unittest.TestCase):
    """TTS released idle task models before every spoken reply, and its only
    guard was "is a request in flight right now" -- which is always false by
    then. A model used seconds ago was evicted, then cold-loaded next turn."""

    def _listed(self):
        return {
            "ok": True,
            "loaded": [
                {"instance_id": "mistralai/mistral-7b-instruct-v0.3",
                 "model_key": "mistralai/mistral-7b-instruct-v0.3", "baseline": False},
                {"instance_id": "qwen/qwen3-4b-2507", "model_key": "qwen/qwen3-4b-2507", "baseline": True},
            ],
            "policy": {},
        }

    def _run(self, recent, *, force=False):
        from actions import model_lifecycle

        post = mock.Mock()
        post.return_value = mock.Mock(raise_for_status=mock.Mock())
        with mock.patch.object(model_lifecycle, "active_snapshot", return_value={"active_count": 0}), \
             mock.patch.object(model_lifecycle, "list_models", return_value=self._listed()), \
             mock.patch.object(model_lifecycle, "recently_used_models", return_value=recent):
            result = model_lifecycle.unload_non_baseline(timeout=5, post=post, force=force)
        return result, post

    def test_recently_used_task_model_is_kept(self):
        result, post = self._run({"mistralai/mistral-7b-instruct-v0.3"})
        self.assertEqual(result["unloaded"], [])
        post.assert_not_called()
        kept = {item["model_key"] for item in result["kept"]}
        self.assertIn("mistralai/mistral-7b-instruct-v0.3", kept)

    def test_idle_task_model_is_still_unloaded(self):
        result, post = self._run(set())
        unloaded = {item["model_key"] for item in result["unloaded"]}
        self.assertIn("mistralai/mistral-7b-instruct-v0.3", unloaded)
        post.assert_called_once()

    def test_force_bypasses_the_ttl_guard(self):
        result, post = self._run({"mistralai/mistral-7b-instruct-v0.3"}, force=True)
        unloaded = {item["model_key"] for item in result["unloaded"]}
        self.assertIn("mistralai/mistral-7b-instruct-v0.3", unloaded)

    def test_baseline_is_never_unloaded(self):
        result, _ = self._run(set())
        unloaded = {item["model_key"] for item in result["unloaded"]}
        self.assertNotIn("qwen/qwen3-4b-2507", unloaded)

    def test_lease_lookup_failure_fails_open(self):
        from actions import model_lifecycle

        with mock.patch.object(model_lifecycle, "_lease_connect", side_effect=RuntimeError("db locked")):
            self.assertEqual(model_lifecycle.recently_used_models({"task_model_ttl_seconds": 300}), set())


class ContextBudgetTests(unittest.TestCase):
    """Chunk to the model that will actually run the work, not to the context
    the model advertises."""

    def test_effective_window_prefers_the_configured_load_profile(self):
        from actions import model_registry

        profile = model_registry.effective_profile("qwen/qwen3-4b-2507")
        self.assertEqual(profile["declared_context_window"], 32768)
        self.assertEqual(profile["effective_context_window"], 4096)

    def test_budget_is_derived_from_the_effective_window(self):
        from actions import model_registry

        small = model_registry.char_budget_for("qwen/qwen3-4b-2507")
        large = model_registry.char_budget_for("qwen/qwen3.5-9b")
        self.assertLess(small, large)
        self.assertLess(small, 32768 * 3.2)

    def test_unknown_model_still_returns_a_usable_budget(self):
        from actions import model_registry

        self.assertGreaterEqual(model_registry.char_budget_for("not-a-real-model"), 1_000)

    def test_oversized_tool_result_cannot_overflow_the_worker_context(self):
        from actions import model_registry

        huge = [{"tool": "jarvis_memory", "arguments": {}, "result": "X" * 60_000}]
        prompt = main._build_tool_summary_prompt("summarise my notes", huge)
        budget = model_registry.char_budget_for("qwen/qwen3-4b-2507", reserve_tokens=900)
        self.assertLessEqual(len(prompt), budget)

    def test_budget_lookup_failure_falls_back_to_a_safe_limit(self):
        with mock.patch("actions.model_registry.char_budget_for", side_effect=RuntimeError("no config")):
            self.assertEqual(main._tool_summary_evidence_limit("hi"), 8_000)


class CapabilityOverviewFastPathTests(unittest.TestCase):
    def test_capability_questions_are_recognised(self):
        for text in [
            "what tools or workflows do you have available",
            "what tools do you have",
            "what can you do",
            "list your tools",
            "what are your capabilities?",
        ]:
            with self.subTest(text=text):
                self.assertTrue(main._is_capability_overview_prompt(text))

    def test_artifact_questions_are_not_hijacked(self):
        """The reported PDF failure: 'can you extract the methods from this pdf'
        previously reached capability_registry, whose manifest literally lists
        the backend orchestration methods."""
        for text in [
            "can you extract the methods from this pdf",
            "extract the methods",
            "what are the methods in this paper",
            "summarize this file",
            "use your tools to summarize the attached pdf",
        ]:
            with self.subTest(text=text):
                self.assertFalse(main._is_capability_overview_prompt(text))

    def test_overview_answers_with_zero_model_calls(self):
        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.ui.muted = False
        jarvis.speak = mock.Mock()
        jarvis._pending_plan_run_id = ""
        jarvis._active_plan_run_id = ""
        jarvis._pending_tool_confirmation = None
        jarvis._phone_active = False

        with mock.patch("main.call_with_tools", side_effect=AssertionError("planner model called")), \
             mock.patch("main.call_text", side_effect=AssertionError("worker model called")):
            jarvis._handle_router_text_command("what tools or workflows do you have available")

        reply = jarvis.speak.call_args.args[0]
        self.assertIn("tools", reply.lower())
        # Also spoken aloud, so the full ~9k-character manifest is not acceptable.
        self.assertLess(len(reply), 3000)


if __name__ == "__main__":
    unittest.main()
