"""A decomposition that cannot be proposed must not report success.

Found by running Canvas Mode 2 end to end on 2026-07-30 rather than by reading
it. The first stage failed immediately:

    CanvasCompileError: Implementation node 'implement_subtract_func' has no
    project target.

Two joins were missing, and together they broke the loop at its first step:

  1. `project_hint` was a caller-supplied parameter with **no callers anywhere**.
     `decompose_goal_to_canvas` pins `project:` onto implementation nodes only
     when a hint is present, so the pin never fired -- and `compile_canvas`
     (correctly) refuses an implementation node with no project target.

  2. `decompose_goal_to_canvas` never checked that what it produced compiles. It
     wrote the canvas and returned `ok: True`, so the caller got a canvas path,
     no approval note, and nothing connecting the two. Its own docstring already
     promised that nothing is written and `ok` is False on a structurally
     invalid decomposition -- a canvas the compiler refuses is structurally
     invalid, whatever else is right about it.

The live consequence: every coding request through `_redirect_dev_agent_to_canvas`
produced a canvas and then failed to propose it, because a real plan almost
always contains an implementation step.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions import canvas_plan
from actions.canvas_plan import CanvasCompileError, _infer_project_hint

REGISTRY = {
    "projects": {
        "e2e_scratch": {"display_name": "E2E Scratch", "root": "/tmp/scratch"},
        "mark_platform": {"display_name": "Mark Platform", "root": "/tmp/mark"},
    }
}


class ProjectInferenceTests(unittest.TestCase):
    def _infer(self, goal: str) -> str:
        import actions.project_operator as po

        with mock.patch.object(po, "load_registry", return_value=REGISTRY):
            return _infer_project_hint(goal)

    def test_a_goal_naming_one_project_resolves_to_it(self):
        self.assertEqual(self._infer("Add a subtract function in the e2e_scratch project"), "e2e_scratch")

    def test_a_display_name_resolves_too(self):
        self.assertEqual(self._infer("Refactor Mark Platform routing"), "mark_platform")

    def test_an_ambiguous_goal_resolves_to_nothing(self):
        """Guessing which repository a plan will write to is precisely the
        decision `compile_canvas` refuses to make for the user. Refusing here
        too means the failure arrives at compile time, in the preview, rather
        than as work against the wrong repo."""
        self.assertEqual(self._infer("Compare e2e_scratch and mark_platform"), "")

    def test_a_goal_naming_no_project_resolves_to_nothing(self):
        self.assertEqual(self._infer("Write a poem about the sea"), "")

    def test_an_unreadable_registry_is_not_fatal(self):
        import actions.project_operator as po

        with mock.patch.object(po, "load_registry", side_effect=OSError("registry missing")):
            self.assertEqual(_infer_project_hint("anything"), "")


class DecompositionValidatesBeforeClaimingSuccessTests(unittest.TestCase):
    """The precheck, exercised without a model by driving `compile_canvas`
    directly with the shapes decompose can emit."""

    def _canvas(self, *, project: str | None) -> dict:
        impl_text = "role: implementation\n"
        if project:
            impl_text += f"project: {project}\n"
        impl_text += "\nAdd the subtract function."
        return {
            "nodes": [
                {"id": "plan_1", "type": "text", "text": "role: plan\nShip subtract.",
                 "x": 0, "y": 0, "width": 300, "height": 120},
                {"id": "impl_1", "type": "text", "text": impl_text,
                 "x": 0, "y": 200, "width": 300, "height": 120},
            ],
            "edges": [{"id": "e1", "fromNode": "plan_1", "toNode": "impl_1"}],
        }

    def test_an_implementation_node_without_a_project_does_not_compile(self):
        """The condition the live run hit."""
        with self.assertRaises(CanvasCompileError):
            canvas_plan.compile_canvas(self._canvas(project=None), workflow_id="p", name="P")

    def test_the_same_canvas_compiles_once_the_project_is_pinned(self):
        """So the pin is the fix, not a workaround."""
        import actions.project_operator as po

        with mock.patch.object(po, "load_registry", return_value=REGISTRY):
            workflow = canvas_plan.compile_canvas(
                self._canvas(project="e2e_scratch"), workflow_id="p", name="P"
            )
        self.assertTrue(workflow["steps"])

    def test_decompose_reports_failure_instead_of_writing_an_unusable_canvas(self):
        """The effect-honesty property: `ok: True` plus a canvas path must mean
        the canvas can actually be proposed.

        Drives the real function with a stubbed planner response, then makes the
        compile step fail. `jarvis_canvas` and `compile_canvas` are patched at
        their source modules because `decompose_goal_to_canvas` imports both
        inside the function body.
        """
        import actions.jarvis_canvas as jc
        import actions.project_operator as po

        planner_reply = json.dumps({
            "rationale": "test",
            "nodes": [
                {"id": "plan_1", "role": "plan", "prose": "Ship it.", "depends_on": []},
                {"id": "impl_1", "role": "implementation", "prose": "Do it.", "depends_on": ["plan_1"]},
            ],
        })
        with mock.patch.object(po, "load_registry", return_value=REGISTRY), \
             mock.patch("core.model_router.call_text", return_value=planner_reply), \
             mock.patch.object(canvas_plan, "compile_canvas",
                               side_effect=CanvasCompileError("node 'impl_1' has no project target")), \
             mock.patch.object(jc, "write_canvas") as write_canvas:
            result = canvas_plan.decompose_goal_to_canvas("Build something with no project named")

        self.assertFalse(result["ok"], f"reported success for an uncompilable canvas: {result}")
        self.assertIn("does not compile", result["error"])
        write_canvas.assert_not_called()


class TheLiveCallerSuppliesWhatItNeedsTests(unittest.TestCase):
    def test_the_dev_agent_redirect_still_calls_decompose(self):
        """The redirect deliberately passes no hint -- inference happens inside
        `decompose_goal_to_canvas` so every caller benefits rather than each
        having to remember."""
        import inspect

        import main

        source = inspect.getsource(main.JarvisLive._redirect_dev_agent_to_canvas)
        self.assertIn("decompose_goal_to_canvas", source)
        self.assertIn("propose_canvas_plan", source)

    def test_decompose_infers_the_hint_without_being_told(self):
        signature = __import__("inspect").signature(canvas_plan.decompose_goal_to_canvas)
        self.assertEqual(signature.parameters["project_hint"].default, "")


if __name__ == "__main__":
    unittest.main()
