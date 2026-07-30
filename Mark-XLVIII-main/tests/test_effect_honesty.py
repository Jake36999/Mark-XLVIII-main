"""One test per site that once claimed success it had not earned.

The 2026-07 cycle produced seven defects that shared no subsystem and one
mistake: a success signal returned at the moment work was *dispatched* rather
than when it was *done*. Each was repaired individually. These are the tests
that would have caught them, written the way that generalises -- **force the
effect to not happen, then assert the return value does not claim it did.**

Read as a set, they define the convention in `core/effect_outcome.py` more
concretely than prose can: a return value describes what the caller may rely on
having happened.
"""
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.effect_outcome import (
    ASSERTS_COMPLETION,
    COMPLETED,
    EFFECT_STATES,
    EffectStateError,
    FAILED,
    PARTIAL,
    REQUESTED,
    SKIPPED,
    UNKNOWN,
    asserts_completion,
    canonical_state,
    outcome,
)


class TheVocabularyItselfTests(unittest.TestCase):
    def test_only_completed_entitles_a_caller_to_assume_the_effect_happened(self):
        self.assertEqual(ASSERTS_COMPLETION, {COMPLETED})
        for state in (PARTIAL, REQUESTED, SKIPPED, FAILED, UNKNOWN):
            with self.subTest(state=state):
                self.assertFalse(asserts_completion(state))

    def test_ok_is_derived_so_it_cannot_contradict_the_state(self):
        """Every original defect was a success flag that had drifted from what
        actually happened. Deriving it removes the possibility."""
        self.assertTrue(outcome(COMPLETED)["ok"])
        for state in (PARTIAL, REQUESTED, SKIPPED, FAILED, UNKNOWN):
            with self.subTest(state=state):
                self.assertFalse(outcome(state)["ok"])

    def test_a_typo_fails_loudly_rather_than_reading_as_success(self):
        with self.assertRaises(EffectStateError):
            outcome("complete")  # the real string that shipped on every plan

    def test_requested_is_available_and_distinct_from_both_success_and_failure(self):
        """The state this system kept failing to express. A bare boolean has no
        room for it, which is why bare booleans caused the defects."""
        self.assertIn(REQUESTED, EFFECT_STATES)
        self.assertNotEqual(REQUESTED, COMPLETED)
        self.assertNotEqual(REQUESTED, FAILED)


class CancellingARunningTaskTests(unittest.TestCase):
    """`Future.cancel()` returns False once a task is running, and nothing stops.
    A bare boolean let a client believe a model call or delegation had been
    cancelled while it kept going."""

    def test_a_running_task_reports_requested_not_completed(self):
        from core.mcp_server import MCPTaskStore

        store = MCPTaskStore(max_workers=1)
        started, release = threading.Event(), threading.Event()

        def slow():
            started.set()
            release.wait(3)

        record = store.submit(slow)
        started.wait(2)
        result = store.cancel(record.task_id)
        release.set()

        self.assertFalse(result["cancelled"])
        self.assertEqual(canonical_state("mcp_task_cancel", result["status"]), REQUESTED)

    def test_a_queued_task_genuinely_cancelled_reports_completed(self):
        from core.mcp_server import MCPTaskStore

        store = MCPTaskStore(max_workers=1)
        release = threading.Event()
        store.submit(lambda: release.wait(3))
        queued = store.submit(lambda: "never runs")
        result = store.cancel(queued.task_id)
        release.set()

        self.assertTrue(result["cancelled"])
        self.assertEqual(canonical_state("mcp_task_cancel", result["status"]), COMPLETED)

    def test_an_absent_task_is_unknown_rather_than_either_answer(self):
        from core.mcp_server import MCPTaskStore

        result = MCPTaskStore(max_workers=1).cancel("no-such-task")
        self.assertEqual(canonical_state("mcp_task_cancel", result["status"]), UNKNOWN)


class PlanEvidenceTests(unittest.TestCase):
    """`research_state` was the literal string "complete" on every plan, so a
    well-sourced plan and one built from nothing were indistinguishable to a
    reader or a downstream workflow deciding whether to act."""

    def test_a_failed_web_backend_is_not_reported_as_complete(self):
        from actions.plan_workflow import _research_state

        evidence = _research_state({"ok": False, "message": "backend exploded"}, [], internet=True)
        self.assertEqual(canonical_state("plan_research", evidence["research_state"]), FAILED)
        self.assertIn("backend exploded", evidence["web_error"])

    def test_a_search_that_returns_nothing_is_not_reported_as_complete(self):
        from actions.plan_workflow import _research_state

        evidence = _research_state({"ok": True, "results": []}, [], internet=True)
        self.assertNotIn(
            canonical_state("plan_research", evidence["research_state"]), ASSERTS_COMPLETION
        )

    def test_being_offline_is_skipped_not_failed_and_not_complete(self):
        """Nothing went wrong; nothing was attempted. Conflating that with
        failure is its own dishonesty."""
        from actions.plan_workflow import _research_state

        evidence = _research_state({}, [], internet=False)
        self.assertEqual(canonical_state("plan_research", evidence["research_state"]), SKIPPED)

    def test_real_sources_do_still_report_complete(self):
        """The guard must not be so eager that a genuinely good plan is
        downgraded -- that would make the signal useless in the other direction."""
        from actions.plan_workflow import _research_state

        evidence = _research_state(
            {"ok": True, "results": [{"url": "https://example.org/a"}]}, [], internet=True
        )
        self.assertEqual(canonical_state("plan_research", evidence["research_state"]), COMPLETED)

    def test_the_state_is_visible_to_a_reader_not_only_to_code(self):
        from actions.plan_workflow import _research_state, _research_state_notice

        notice = _research_state_notice(_research_state({"ok": False, "message": "down"}, [], internet=True))
        self.assertIn("failed", notice)


class VisionAnswerTests(unittest.TestCase):
    """The original returned "[VISION_ACTIVE] ... the actual image arrives in the
    next message". It never arrived, and the reply was generated from no visual
    input at all."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"

    def test_a_failing_vision_model_does_not_produce_an_answer(self):
        from actions import vision_pipeline

        with mock.patch.object(vision_pipeline, "call_vision", side_effect=RuntimeError("model not loaded")):
            result = vision_pipeline.describe_image(self.PNG, "image/png", "what is this?", angle="camera")

        self.assertFalse(result["ok"])
        self.assertEqual(result["answer"], "")
        self.assertIn("model not loaded", result["error"])

    def test_the_reported_path_is_the_one_actually_taken(self):
        """`angle` is what was asked for; `path` is what ran. They diverge
        whenever OCR reads too little, and reporting the request instead of the
        outcome is exactly the original mistake."""
        from actions import vision_pipeline

        with mock.patch.object(vision_pipeline, "call_vision", side_effect=["", "A paused video."]):
            result = vision_pipeline.describe_image(self.PNG, "image/png", "what's on screen?", angle="screen")

        self.assertEqual(result["angle"], "screen")
        self.assertEqual(canonical_state("vision_answer", result["path"]), COMPLETED)
        self.assertEqual(result["path"], "vision_scene_fallback")

    def test_a_transcript_without_an_answer_is_partial_not_complete(self):
        from actions import vision_pipeline

        transcript = "\n".join(f"line {n} of the build log" for n in range(20))
        with mock.patch.object(vision_pipeline, "call_vision", return_value=transcript), \
             mock.patch.object(vision_pipeline, "call_text", return_value=""):
            result = vision_pipeline.describe_image(self.PNG, "image/png", "what happened?", angle="screen")

        self.assertEqual(canonical_state("vision_answer", result["path"]), PARTIAL)

    def test_a_capture_that_never_happened_is_never_described(self):
        from actions import vision_pipeline

        with mock.patch.object(vision_pipeline, "call_vision") as model:
            result = vision_pipeline.describe_image(b"", "image/png", "what is this?")
        model.assert_not_called()
        self.assertFalse(result["ok"])


class CaptureEntryPointTests(unittest.TestCase):
    """`screen_process()` returned True the moment bytes were queued -- success
    for work that had not happened, and after Live was switched off, for work
    that never happened at all."""

    def test_it_returns_an_answer_rather_than_a_boolean(self):
        from actions import screen_processor

        with mock.patch.object(screen_processor, "_capture_screen", return_value=(b"img", "image/png")), \
             mock.patch("actions.vision_pipeline.describe_image",
                        return_value={"ok": True, "answer": "A code editor.", "path": "ocr_then_text", "error": ""}):
            result = screen_processor.screen_process({"angle": "screen", "text": "what's on screen?"})

        self.assertEqual(result, "A code editor.")

    def test_a_failed_read_is_falsy_rather_than_a_confident_true(self):
        from actions import screen_processor

        with mock.patch.object(screen_processor, "_capture_screen", return_value=(b"img", "image/png")), \
             mock.patch("actions.vision_pipeline.describe_image",
                        return_value={"ok": False, "answer": "", "path": "", "error": "no vision model"}):
            result = screen_processor.screen_process({"angle": "screen", "text": "what's on screen?"})

        self.assertEqual(result, "")
        self.assertFalse(result)

    def test_a_capture_failure_is_not_reported_as_an_answer(self):
        from actions import screen_processor

        with mock.patch.object(screen_processor, "_capture_screen", side_effect=RuntimeError("no display")):
            self.assertEqual(screen_processor.screen_process({"angle": "screen", "text": "x"}), "")


class ConfiguredVersusEffectiveTests(unittest.TestCase):
    """Reporting the value you were handed is not reporting the value you
    produced. The resolver appended speech models to `baseline_models`, so it
    reported a baseline it had silently changed -- overriding a recorded owner
    decision and making the task-model TTL unreachable for speech."""

    def test_speech_models_are_not_added_behind_the_configured_baseline(self):
        from actions.model_lifecycle import _resolved_config

        resolved = _resolved_config(
            {
                "baseline_models": ["qwen/qwen3-4b-2507"],
                "tts_model": "orpeus_text_to_speech",
                "voice_engine": "orpheus",
            }
        )
        self.assertNotIn("orpeus_text_to_speech", resolved["baseline_models"])

    def test_what_the_resolver_reports_is_what_it_produced(self):
        """The property the config audit exists to check, asserted directly."""
        from actions.model_lifecycle import _resolved_config

        declared = ["qwen/qwen3-4b-2507"]
        resolved = _resolved_config({"baseline_models": list(declared), "worker_model": "qwen/qwen3-4b-2507"})
        self.assertEqual(sorted(set(resolved["baseline_models"])), sorted(set(declared)))

    def test_the_audit_that_catches_this_class_reports_no_contradictions(self):
        from scripts.config_audit import _findings

        contradictions = [
            f for f in _findings() if not f["ok"] and f.get("severity", "error") == "error"
        ]
        self.assertEqual(contradictions, [], f"declared and effective configuration disagree: {contradictions}")


class WorkThatWouldSilentlyDoNothingTests(unittest.TestCase):
    """A Canvas implementation node with no project target compiled cleanly, was
    approved by a human, and then delegated nothing -- `project_operator` treats
    a missing project id as `operation=list` and returns ok:true."""

    def test_compiling_fails_rather_than_producing_a_step_that_cannot_act(self):
        from actions import canvas_plan

        payload = {
            "nodes": [
                {"id": "a", "type": "text", "text": "role: plan\nShip the caching layer.",
                 "x": 0, "y": 0, "width": 300, "height": 120},
                {"id": "b", "type": "text", "text": "role: implementation\nAdd the cache.",
                 "x": 0, "y": 200, "width": 300, "height": 120},
            ],
            "edges": [{"id": "e1", "fromNode": "a", "toNode": "b"}],
        }
        with self.assertRaises(canvas_plan.CanvasCompileError) as caught:
            canvas_plan.compile_canvas(payload, workflow_id="p", name="P")
        self.assertIn("project", str(caught.exception).lower())

    def test_the_failure_names_the_node_so_it_can_be_fixed(self):
        """A compile error that does not say which node is barely better than
        the silent no-op it replaced."""
        from actions import canvas_plan

        payload = {
            "nodes": [
                {"id": "plan-1", "type": "text", "text": "role: plan\nShip it.",
                 "x": 0, "y": 0, "width": 300, "height": 120},
                {"id": "impl-7", "type": "text", "text": "role: implementation\nAdd the cache.",
                 "x": 0, "y": 200, "width": 300, "height": 120},
            ],
            "edges": [{"id": "e1", "fromNode": "plan-1", "toNode": "impl-7"}],
        }
        with self.assertRaises(canvas_plan.CanvasCompileError) as caught:
            canvas_plan.compile_canvas(payload, workflow_id="p", name="P")
        self.assertIn("impl-7", str(caught.exception))


class ToolDispatchTests(unittest.TestCase):
    """The authorization basis is the same shape of problem one level up: a call
    site that inherits permission it never stated is claiming something it has
    not established."""

    def test_an_unknown_basis_fails_closed_rather_than_open(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.speak = mock.Mock()
        with mock.patch.object(main.JarvisLive, "_execute_tool", new=mock.AsyncMock()) as execute:
            payload = json.loads(
                jarvis._execute_router_tool_call("c", "jarvis_memory", {}, authorized_by="invented")
            )
        self.assertFalse(payload["ok"])
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
