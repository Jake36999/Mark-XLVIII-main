import unittest
from unittest import mock

from core.tool_dispatcher import DispatchContext, ToolDispatcher, classify_effect


class ToolDispatcherTests(unittest.TestCase):
    def declarations(self):
        return [
            {
                "name": "web_search",
                "description": "read",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "reminder",
                "description": "write",
                "parameters": {"type": "object", "properties": {"operation": {"type": "string"}}},
            },
        ]

    def test_schema_validation_runs_before_dispatch(self):
        dispatcher = ToolDispatcher(self.declarations())

        result = dispatcher.call("web_search", {})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_arguments")

    def test_read_call_executes_but_write_requires_frozen_workflow_authorization(self):
        dispatcher = ToolDispatcher(self.declarations())
        with mock.patch("core.tool_dispatcher._handler", return_value=lambda args: {"ok": True, "query": args["query"]}):
            read = dispatcher.call("web_search", {"query": "AI"})
            write = dispatcher.call("reminder", {"operation": "create"}, context=DispatchContext(user_confirmed=True))

        self.assertTrue(read["ok"])
        self.assertEqual(read["result"]["query"], "AI")
        self.assertFalse(write["ok"])
        self.assertEqual(write["error"]["code"], "approval_required")

    def test_effect_classification_tracks_state_and_artifact_writes(self):
        self.assertEqual(
            classify_effect("jarvis_memory", {"operation": "run_task_review"})["effect"],
            "read",
        )
        self.assertEqual(
            classify_effect(
                "jarvis_memory",
                {"operation": "run_task_review", "scheduled": True},
            )["effect"],
            "write",
        )
        self.assertEqual(
            classify_effect(
                "file_processor",
                {"operation": "analyze_large", "save_to_vault": False},
            )["effect"],
            "read",
        )
        self.assertEqual(
            classify_effect("file_processor", {"operation": "analyze_large"})["effect"],
            "write",
        )

    def test_canvas_plan_effect_classification(self):
        # health and verify_approval are pure reads; propose/evaluate_approval/
        # execute all write (a note, an approval envelope, or the run itself)
        # and must default to requiring approval like any other write.
        self.assertEqual(classify_effect("canvas_plan", {"operation": "health"})["effect"], "read")
        self.assertEqual(classify_effect("canvas_plan", {"operation": "verify_approval"})["effect"], "read")
        for operation in ("propose", "evaluate_approval", "execute"):
            result = classify_effect("canvas_plan", {"operation": operation})
            self.assertEqual(result["effect"], "write")
            self.assertTrue(result["requires_approval"])

    def test_canvas_plan_is_registered_and_routes_through_the_handler(self):
        from core import tool_dispatcher as td

        self.assertIn("canvas_plan", td.HEADLESS_TOOLS)
        with mock.patch("actions.canvas_plan.canvas_plan", return_value='{"ok": true, "operation": "health"}') as fake:
            handler = td._handler("canvas_plan")
            self.assertIsNotNone(handler)
            result = handler({"operation": "health"})
        fake.assert_called_once_with({"operation": "health"})
        self.assertEqual(result, '{"ok": true, "operation": "health"}')


if __name__ == "__main__":
    unittest.main()
