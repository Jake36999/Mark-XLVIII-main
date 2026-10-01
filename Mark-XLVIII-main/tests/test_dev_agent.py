import unittest
from unittest import mock

from actions import dev_agent


class EstimateScopeTests(unittest.TestCase):
    """estimate_scope() is the signal main.py's dynamic router (2026-09-25)
    uses to decide whether a dev_agent request is small enough to skip the
    Canvas-review gate -- it must stop at planning and never write anything.
    """

    def test_single_file_no_dependencies_is_small(self):
        plan = {"project_name": "x", "files": [{"path": "a.py", "description": "d"}], "dependencies": []}
        with mock.patch.object(dev_agent, "_plan_project", return_value=plan):
            scope = dev_agent.estimate_scope("write a quick script")

        self.assertTrue(scope["ok"])
        self.assertTrue(scope["is_small"])
        self.assertEqual(1, scope["file_count"])
        self.assertEqual(0, scope["dependency_count"])

    def test_multiple_files_is_not_small(self):
        plan = {
            "project_name": "x",
            "files": [{"path": "a.py"}, {"path": "b.py"}],
            "dependencies": [],
        }
        with mock.patch.object(dev_agent, "_plan_project", return_value=plan):
            scope = dev_agent.estimate_scope("build a small app")

        self.assertTrue(scope["ok"])
        self.assertFalse(scope["is_small"])
        self.assertEqual(2, scope["file_count"])

    def test_single_file_with_a_dependency_is_not_small(self):
        # code_helper's write action has no dependency-install step, so a
        # single file that still needs a pip install cannot take the fast
        # path -- it must fall through to the reviewable Canvas plan.
        plan = {"project_name": "x", "files": [{"path": "a.py"}], "dependencies": ["requests"]}
        with mock.patch.object(dev_agent, "_plan_project", return_value=plan):
            scope = dev_agent.estimate_scope("write a script that hits an API")

        self.assertTrue(scope["ok"])
        self.assertFalse(scope["is_small"])

    def test_rate_limit_during_planning_reports_not_ok_not_small(self):
        with mock.patch.object(dev_agent, "_plan_project", side_effect=dev_agent.RateLimitError("busy")):
            scope = dev_agent.estimate_scope("write a quick script")

        self.assertFalse(scope["ok"])
        self.assertNotIn("is_small", scope)

    def test_planner_returning_bad_json_reports_not_ok(self):
        with mock.patch.object(dev_agent, "_plan_project", side_effect=ValueError("bad json")):
            scope = dev_agent.estimate_scope("write a quick script")

        self.assertFalse(scope["ok"])

    def test_estimate_scope_never_writes_a_file(self):
        plan = {"project_name": "x", "files": [{"path": "a.py"}], "dependencies": []}
        with mock.patch.object(dev_agent, "_plan_project", return_value=plan), mock.patch.object(
            dev_agent, "_write_file"
        ) as write_file:
            dev_agent.estimate_scope("write a quick script")

        write_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
