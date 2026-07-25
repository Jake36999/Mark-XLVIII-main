import json
import tempfile
import unittest
import re
from pathlib import Path
from unittest.mock import patch


class ProjectOperatorRegistryTests(unittest.TestCase):
    def test_registry_contains_initial_projects(self):
        from actions import project_operator

        registry = project_operator.load_registry()

        self.assertEqual(
            {
                "quantule_mapper",
                "knowledge_compiler_engine",
                "mark_platform",
                "network_management",
                "archive",
            },
            set(registry["projects"].keys()),
        )

    def test_archive_entry_grants_no_safe_operations_by_default(self):
        # Workflow 2: the archive is registered only so graphify_query can
        # resolve project_id="archive" -- it must not accidentally pick up any
        # project_operator capability. classify_operation's own fallthrough for
        # anything not in safe_operations is "confirm", so an empty
        # safe_operations list means every operation requires confirmation.
        from actions import project_operator

        registry = project_operator.load_registry()
        decision = project_operator.classify_operation(registry, project_id="archive", operation="status")

        self.assertEqual("confirm", decision["action"])
        self.assertTrue(decision["requires_confirmation"])

    def test_safe_status_operation_is_allowed_without_confirmation(self):
        from actions import project_operator

        registry = project_operator.load_registry()

        decision = project_operator.classify_operation(
            registry,
            project_id="network_management",
            operation="status",
            command="powershell -NoProfile -ExecutionPolicy Bypass -File Verify-RfBackend.ps1",
        )

        self.assertEqual("allow", decision["action"])
        self.assertFalse(decision["requires_confirmation"])

    def test_heavy_operation_requires_confirmation(self):
        from actions import project_operator

        registry = project_operator.load_registry()

        decision = project_operator.classify_operation(
            registry,
            project_id="knowledge_compiler_engine",
            operation="heavy_training",
            command="docker compose up worker-theorist worker-coding",
        )

        self.assertEqual("confirm", decision["action"])
        self.assertTrue(decision["requires_confirmation"])

    def test_destructive_command_is_blocked_without_confirmation_record(self):
        from actions import project_operator

        registry = project_operator.load_registry()

        decision = project_operator.classify_operation(
            registry,
            project_id="quantule_mapper",
            operation="cleanup",
            command="Remove-Item -Recurse -Force simulation_data",
        )

        self.assertEqual("block", decision["action"])
        self.assertTrue(decision["requires_confirmation"])

    def test_delegate_openclaw_is_registered_as_safe(self):
        from actions import project_operator

        registry = project_operator.load_registry()

        decision = project_operator.classify_operation(
            registry,
            project_id="mark_platform",
            operation="delegate_openclaw",
        )

        self.assertEqual("allow", decision["action"])
        self.assertFalse(decision["requires_confirmation"])

    def test_learn_project_is_registered_as_read_only_safe(self):
        from actions import project_operator

        registry = project_operator.load_registry()
        decision = project_operator.classify_operation(registry, "mark_platform", "learn_project")

        self.assertEqual("allow", decision["action"])
        self.assertFalse(decision["requires_confirmation"])


class ProjectOperatorBridgeTests(unittest.TestCase):
    def test_build_jsonrpc_request_uses_tools_call_shape(self):
        from actions import project_operator

        request = project_operator.build_jsonrpc_request(
            "mcp_scout_workspace",
            {"project_id": "network_management", "absolute_path": "F:\\network_management"},
            request_id=42,
        )

        self.assertEqual("2.0", request["jsonrpc"])
        self.assertEqual(42, request["id"])
        self.assertEqual("tools.call", request["method"])
        self.assertEqual("mcp_scout_workspace", request["params"]["toolName"])
        self.assertEqual("network_management", request["params"]["args"]["project_id"])

    def test_bridge_unavailable_returns_setup_guidance(self):
        from actions import project_operator

        with patch("actions.project_operator.socket.create_connection", side_effect=OSError("no daemon")):
            result = project_operator.call_aletheia_tool(
                {"host": "127.0.0.1", "port": 8765, "timeout_seconds": 1},
                "mcp_scout_workspace",
                {"project_id": "network_management", "absolute_path": "F:\\network_management"},
            )

        self.assertFalse(result["ok"])
        self.assertEqual("bridge_unavailable", result["error"]["code"])
        self.assertIn("start-aletheia-operator.ps1", result["summary"])

    def test_scout_operation_maps_to_aletheia_scout_tool(self):
        from actions import project_operator

        calls = []

        def fake_call(bridge, tool_name, args):
            calls.append((bridge, tool_name, args))
            return {"ok": True, "summary": "scouted", "result": {"file_count": 10}}

        with patch("actions.project_operator.call_aletheia_tool", side_effect=fake_call):
            result_text = project_operator.project_operator(
                {"project_id": "network_management", "operation": "scout"}
            )

        self.assertIn('"ok": true', result_text.lower())
        self.assertEqual("mcp_scout_workspace", calls[0][1])
        self.assertEqual("network_management", calls[0][2]["project_id"])
        self.assertEqual("F:\\network_management", calls[0][2]["absolute_path"])

    def test_bridge_result_is_compacted_before_returning_to_mark(self):
        from actions import project_operator

        huge_tree = "x" * 20000

        with patch(
            "actions.project_operator.call_aletheia_tool",
            return_value={
                "ok": True,
                "summary": "scouted",
                "result": {
                    "tree": huge_tree,
                    "file_count": 500,
                    "skipped_count": 1000,
                    "files": [{"path": f"file_{index}.py"} for index in range(100)],
                },
            },
        ):
            result_text = project_operator.project_operator(
                {"project_id": "network_management", "operation": "scout"}
            )

        self.assertLess(len(result_text), 6000)
        self.assertIn("files_omitted", result_text)

    def test_explicit_directory_learning_does_not_require_project_registration(self):
        from actions import project_operator

        with tempfile.TemporaryDirectory() as tmp, patch(
            "actions.project_learning.learn_repository",
            return_value={
                "ok": True,
                "status": "complete",
                "brief_path": "brief.md",
                "memory_path": "memory.md",
                "snapshot_path": "snapshot.json",
            },
        ) as learn:
            payload = json.loads(
                project_operator.project_operator(
                    {"operation": "learn_project", "path": tmp, "intent": "read this directory"}
                )
            )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["policy"]["reason"].startswith("Explicit directory learning"))
        self.assertEqual(Path(learn.call_args.args[0]), Path(tmp).resolve())


class FakeCompleted:
    def __init__(self, returncode=0, stdout="spawned", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class OpenClawDelegationTests(unittest.TestCase):
    def test_openclaw_command_uses_subprocess_backend_and_no_keepalive(self):
        from actions import project_operator

        command = project_operator.build_openclaw_spawn_command(
            project={"root": "F:\\network_management"},
            team="mark-network-management",
            agent_name="openclaw-network",
            task="Prepare handoff",
            workspace=False,
        )

        self.assertIn("spawn", command)
        self.assertIn("subprocess", command)
        subprocess_index = command.index("subprocess")
        self.assertEqual(command[subprocess_index + 1:subprocess_index + 3], ["openclaw", "agent"])
        self.assertIn("--no-keepalive", command)
        self.assertIn("--no-workspace", command)

    def test_delegate_openclaw_defaults_to_one_agent(self):
        from actions import project_operator

        registry = project_operator.load_registry()
        project = registry["projects"]["mark_platform"]
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return FakeCompleted()

        with patch("actions.jarvis_memory.create_note", return_value={"ok": True, "path": "handoff.md"}), patch(
            "actions.project_operator.model_lifecycle_service.register_external_activity",
            return_value="guard",
        ):
            result = project_operator.delegate_openclaw(
                "mark_platform",
                project,
                {"intent": "prepare continuity notes"},
                run=fake_run,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["agents"], 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("--no-keepalive", calls[0][0])
        self.assertEqual(
            calls[0][0][calls[0][0].index("--openclaw-agent") + 1],
            "jarvis-worker",
        )
        self.assertEqual(result["handoff_note"]["path"], "handoff.md")

    def test_delegate_openclaw_blocks_multiple_agents_without_explicit_parallel_intent(self):
        from actions import project_operator

        registry = project_operator.load_registry()
        project = registry["projects"]["mark_platform"]

        result = project_operator.delegate_openclaw(
            "mark_platform",
            project,
            {"intent": "prepare continuity notes", "agents": 3},
            run=lambda *args, **kwargs: self.fail("spawn should not run"),
        )

        self.assertFalse(result["ok"])
        self.assertIn("Multiple OpenClaw agents require explicit", result["policy"]["reason"])

    def test_delegate_openclaw_allows_three_agents_for_explicit_parallel_task(self):
        from actions import project_operator

        registry = project_operator.load_registry()
        project = registry["projects"]["mark_platform"]
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return FakeCompleted()

        with patch("actions.jarvis_memory.create_note", return_value={"ok": True, "path": "handoff.md"}), patch(
            "actions.project_operator.model_lifecycle_service.register_external_activity",
            return_value="guard",
        ):
            result = project_operator.delegate_openclaw(
                "mark_platform",
                project,
                {"intent": "parallel multi-file coding handoff", "agents": 3},
                run=fake_run,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["agents"], 3)
        self.assertEqual(len(calls), 3)


class MarkToolWiringTests(unittest.TestCase):
    def test_main_declares_and_dispatches_project_operator(self):
        main_text = Path("main.py").read_text(encoding="utf-8")

        self.assertRegex(main_text, re.compile(r"from actions\.project_operator\s+import project_operator"))
        self.assertIn('"name": "project_operator"', main_text)
        self.assertIn('elif name == "project_operator":', main_text)

    def test_main_declares_and_dispatches_model_lifecycle(self):
        main_text = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("from actions.model_lifecycle", main_text)
        self.assertIn('"name": "model_lifecycle"', main_text)
        self.assertIn('elif name == "model_lifecycle":', main_text)


class StartupScriptTests(unittest.TestCase):
    def test_operator_startup_scripts_exist_and_register_allowed_roots(self):
        scripts = [
            Path("scripts/operator-env.ps1"),
            Path("scripts/start-aletheia-operator.ps1"),
            Path("scripts/start-mark-operator.ps1"),
        ]

        for script in scripts:
            self.assertTrue(script.exists(), f"Missing startup script: {script}")

        env_text = Path("scripts/operator-env.ps1").read_text(encoding="utf-8")
        for root in (
            "F:\\quantule_mapper",
            "F:\\knowledge_compiler_engine (DAG Engine)",
            "F:\\Mark-XLVIII-main",
            "F:\\network_management",
        ):
            self.assertIn(root, env_text)
        self.assertIn("ALETHEIA_ALLOWED_ROOTS", env_text)


if __name__ == "__main__":
    unittest.main()
