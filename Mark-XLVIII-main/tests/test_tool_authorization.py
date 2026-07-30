"""Explicit tool authorization, and honest task cancellation.

Both close findings from the 2026-07-30 external review.
"""
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
from core.mcp_server import MCPTaskStore
from core.tool_dispatcher import DispatchContext


def _jarvis():
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.ui = mock.Mock()
    jarvis.ui.muted = False
    jarvis.speak = mock.Mock()
    return jarvis


class AuthorizationBasisTests(unittest.TestCase):
    """`_execute_router_tool_call` used to pass `pre_approved=True`
    unconditionally. True of every caller at the time, but it made the
    authorization implicit -- a call site added later would silently inherit a
    bypass of the strongest guard, which is the same shape as the defect that
    started this work."""

    def setUp(self):
        self.jarvis = _jarvis()
        response = type("R", (), {"response": {"result": "ran"}})()
        patcher = mock.patch.object(main.JarvisLive, "_execute_tool", new=mock.AsyncMock(return_value=response))
        self.execute = patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_basis_in_the_table_is_usable(self):
        from main import _TOOL_AUTHORIZATION_BASES

        self.assertEqual(
            set(_TOOL_AUTHORIZATION_BASES),
            {"effect_classified", "user_confirmed", "deterministic_workflow"},
        )

    def test_a_permitted_shortcut_tool_runs(self):
        result = self.jarvis._execute_router_tool_call(
            "c", "jarvis_memory", {}, authorized_by="deterministic_workflow"
        )
        self.assertEqual(result, "ran")

    def test_individually_checked_bases_are_not_tool_restricted(self):
        """effect_classified and user_confirmed vet one specific call, so the
        tool identity is already accounted for."""
        for basis in ("effect_classified", "user_confirmed"):
            with self.subTest(basis=basis):
                self.assertEqual(
                    self.jarvis._execute_router_tool_call("c", "send_message", {}, authorized_by=basis),
                    "ran",
                )

    def test_a_shortcut_cannot_reach_a_high_risk_tool(self):
        """The teeth: a deterministic shortcut is authorized by a matched literal
        phrase, which justifies the tools those handlers use -- not one added
        later."""
        for tool in ("send_message", "dev_agent", "file_controller", "shutdown_jarvis"):
            with self.subTest(tool=tool):
                payload = json.loads(
                    self.jarvis._execute_router_tool_call("c", tool, {}, authorized_by="deterministic_workflow")
                )
                self.assertFalse(payload["ok"])
                self.assertIn("not permitted", payload["error"])
        self.execute.assert_not_called()

    def test_an_unknown_basis_fails_closed(self):
        payload = json.loads(
            self.jarvis._execute_router_tool_call("c", "jarvis_memory", {}, authorized_by="made_up")
        )
        self.assertFalse(payload["ok"])
        self.assertIn("Unknown tool authorization basis", payload["error"])
        self.execute.assert_not_called()

    def test_the_basis_is_a_required_keyword(self):
        """A new call site must state its authorization rather than inherit one."""
        with self.assertRaises(TypeError):
            self.jarvis._execute_router_tool_call("c", "jarvis_memory", {})

    def test_every_call_site_declares_a_basis(self):
        import re

        source = Path(main.__file__).read_text(encoding="utf-8")
        calls = re.findall(r"_execute_router_tool_call\((?:[^()]|\([^()]*\))*\)", source, re.S)
        missing = [call for call in calls if "authorized_by" not in call and "def " not in call]
        self.assertEqual(missing, [], f"call sites without an authorization basis: {missing}")


class HonestCancellationTests(unittest.TestCase):
    """`Future.cancel()` only succeeds while a task is queued. Once running it
    returns False and nothing stops -- so a bare boolean let a client believe a
    model call or delegation had been cancelled while it kept going."""

    def test_unknown_task_is_reported_as_unknown(self):
        store = MCPTaskStore(max_workers=1)
        self.assertEqual(store.cancel("nope")["status"], "unknown")

    def test_a_queued_task_is_genuinely_cancelled(self):
        store = MCPTaskStore(max_workers=1)
        release = threading.Event()
        store.submit(lambda: release.wait(3))
        queued = store.submit(lambda: "never runs")
        outcome = store.cancel(queued.task_id)
        release.set()
        self.assertTrue(outcome["cancelled"])
        self.assertEqual(outcome["status"], "cancelled")

    def test_a_running_task_is_not_claimed_as_cancelled(self):
        store = MCPTaskStore(max_workers=1)
        started = threading.Event()
        release = threading.Event()

        def slow():
            started.set()
            release.wait(3)
            return "done"

        record = store.submit(slow)
        started.wait(2)
        outcome = store.cancel(record.task_id)
        release.set()
        self.assertFalse(outcome["cancelled"])
        self.assertEqual(outcome["status"], "cancellation_requested")
        self.assertTrue(outcome["cooperative"])

    def test_a_cooperative_tool_sees_the_flag_and_stops(self):
        store = MCPTaskStore(max_workers=1)
        started = threading.Event()
        observed = {}

        def cooperative(context):
            started.set()
            for _ in range(100):
                if context.cancelled:
                    observed["stopped_early"] = True
                    return {"ok": True, "cancelled": True}
                time.sleep(0.01)
            observed["stopped_early"] = False
            return {"ok": True}

        event = threading.Event()
        record = store.submit(
            cooperative, DispatchContext(source="mcp", cancel_event=event), cancel_event=event
        )
        started.wait(2)
        store.cancel(record.task_id)
        record.future.result(timeout=5)
        self.assertTrue(observed["stopped_early"])

    def test_a_context_without_a_token_is_never_cancelled(self):
        self.assertFalse(DispatchContext(source="router").cancelled)


if __name__ == "__main__":
    unittest.main()
