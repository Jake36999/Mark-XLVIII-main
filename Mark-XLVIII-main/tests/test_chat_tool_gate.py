"""Tests for the plain-chat tool-confirmation gate added to main.py:
- Tier 1: a requires_approval tool pauses instead of executing, and only
  executes on a real, next-turn affirmative reply, using the frozen args
  captured at ask-time.
- Tier 2: dev_agent never executes directly from chat; it's redirected to a
  reviewable Canvas plan.
- Regression: the ~11 deterministic workflow-bootstrap calls that call
  _execute_router_tool_call directly (not through the gated model-tool-call
  loop) remain unaffected by the new gate.
"""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
from core.model_router import ToolCall, ToolModelResponse


def _new_jarvis() -> "main.JarvisLive":
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.ui = mock.Mock()
    jarvis.ui.muted = False
    jarvis.speak = mock.Mock()
    jarvis._pending_plan_run_id = ""
    jarvis._active_plan_run_id = ""
    jarvis._pending_tool_confirmation = None
    jarvis._phone_active = False
    return jarvis


class TierOnePauseAndResumeTests(unittest.TestCase):
    def test_requires_approval_tool_pauses_and_does_not_execute(self):
        jarvis = _new_jarvis()
        routed = ToolModelResponse(
            text="",
            tool_calls=[ToolCall(id="c1", name="file_controller", arguments={"operation": "delete", "path": "x.txt"})],
        )
        with mock.patch("main.call_with_tools", return_value=routed), \
             mock.patch("main.file_controller") as fake_file_controller:
            jarvis._handle_router_text_command("delete x.txt", turn_id=None)

        fake_file_controller.assert_not_called()
        self.assertIsNotNone(jarvis._pending_tool_confirmation)
        self.assertEqual(jarvis._pending_tool_confirmation["tool_name"], "file_controller")
        self.assertEqual(jarvis._pending_tool_confirmation["arguments"], {"operation": "delete", "path": "x.txt"})
        reply = jarvis.speak.call_args.args[0]
        self.assertIn("file_controller", reply)

    def test_affirmative_reply_executes_with_frozen_args(self):
        jarvis = _new_jarvis()
        jarvis._pending_tool_confirmation = {
            "tool_name": "file_controller",
            "arguments": {"operation": "delete", "path": "x.txt"},
            "call_id": "c1",
            "created_turn_id": None,
            "created_at": time.monotonic(),
            "expires_at": time.monotonic() + 120.0,
        }
        with mock.patch("main.file_controller", return_value="deleted") as fake_file_controller, \
             mock.patch("main.call_text", return_value="Done, x.txt was deleted."), \
             mock.patch("main.call_with_tools") as fake_call_with_tools:
            jarvis._handle_router_text_command("yes", turn_id=None)

        fake_file_controller.assert_called_once()
        _, kwargs = fake_file_controller.call_args
        self.assertEqual(kwargs["parameters"], {"operation": "delete", "path": "x.txt"})
        fake_call_with_tools.assert_not_called()
        self.assertIsNone(jarvis._pending_tool_confirmation)

    def test_non_affirmative_reply_discards_pending_and_routes_normally(self):
        jarvis = _new_jarvis()
        jarvis._pending_tool_confirmation = {
            "tool_name": "file_controller",
            "arguments": {"operation": "delete", "path": "x.txt"},
            "call_id": "c1",
            "created_turn_id": None,
            "created_at": time.monotonic(),
            "expires_at": time.monotonic() + 120.0,
        }
        with mock.patch("main.file_controller") as fake_file_controller, \
             mock.patch("main.call_with_tools", return_value=ToolModelResponse(text="Sure, what's up?", tool_calls=[])):
            jarvis._handle_router_text_command("actually what's the weather", turn_id=None)

        fake_file_controller.assert_not_called()
        self.assertIsNone(jarvis._pending_tool_confirmation)

    def test_expired_pending_confirmation_not_honored(self):
        jarvis = _new_jarvis()
        jarvis._pending_tool_confirmation = {
            "tool_name": "file_controller",
            "arguments": {"operation": "delete", "path": "x.txt"},
            "call_id": "c1",
            "created_turn_id": None,
            "created_at": time.monotonic() - 300,
            "expires_at": time.monotonic() - 180,
        }
        with mock.patch("main.file_controller") as fake_file_controller, \
             mock.patch("main.call_with_tools", return_value=ToolModelResponse(text="", tool_calls=[])):
            jarvis._handle_router_text_command("yes", turn_id=None)

        fake_file_controller.assert_not_called()
        self.assertIsNone(jarvis._pending_tool_confirmation)


class TierTwoDevAgentRedirectTests(unittest.TestCase):
    def test_dev_agent_never_executes_directly_from_chat(self):
        jarvis = _new_jarvis()
        routed = ToolModelResponse(
            text="",
            tool_calls=[ToolCall(id="c1", name="dev_agent", arguments={"instruction": "add a caching layer"})],
        )
        fake_decomposition = {"ok": True, "canvas_path": "fake.canvas", "node_count": 3}
        fake_proposal = {"ok": True, "note_path": "fake-approval.md"}
        with mock.patch("main.call_with_tools", return_value=routed), \
             mock.patch("main.dev_agent") as fake_dev_agent, \
             mock.patch("actions.canvas_plan.decompose_goal_to_canvas", return_value=fake_decomposition) as fake_decompose, \
             mock.patch("actions.canvas_plan.propose_canvas_plan", return_value=fake_proposal) as fake_propose:
            jarvis._handle_router_text_command("plan out a caching layer for graphify_query", turn_id=None)

        fake_dev_agent.assert_not_called()
        fake_decompose.assert_called_once()
        fake_propose.assert_called_once()
        self.assertIsNone(jarvis._pending_tool_confirmation)
        reply = jarvis.speak.call_args.args[0]
        self.assertIn("fake.canvas", reply)
        self.assertIn("fake-approval.md", reply)


class DeterministicBootstrapUnaffectedTests(unittest.TestCase):
    """_execute_router_tool_call is also called directly by ~11 deterministic,
    phrase-triggered workflow bootstraps -- these must keep executing without
    pausing for confirmation, since the gate belongs only in the model-driven
    routed.tool_calls loop, not in this shared helper."""

    def test_jarvis_memory_create_todo_template_executes_directly(self):
        jarvis = _new_jarvis()
        with mock.patch("main.jarvis_memory", return_value='{"ok": true}') as fake_jarvis_memory:
            result = jarvis._execute_router_tool_call(
                "c1", "jarvis_memory", {"operation": "create_todo_template"}
            )
        fake_jarvis_memory.assert_called_once()
        self.assertIn("ok", result)

    def test_plan_workflow_start_plan_executes_directly(self):
        jarvis = _new_jarvis()
        with mock.patch("main.plan_workflow", return_value='{"ok": true}') as fake_plan_workflow:
            result = jarvis._execute_router_tool_call("c1", "plan_workflow", {"operation": "start_plan"})
        fake_plan_workflow.assert_called_once()
        self.assertIn("ok", result)


if __name__ == "__main__":
    unittest.main()
