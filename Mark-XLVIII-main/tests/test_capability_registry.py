import json
import unittest
from unittest import mock

from actions.capability_registry import build_registry, capability_registry


class CapabilityRegistryTests(unittest.TestCase):
    def declarations(self):
        return [
            {
                "name": "capability_registry",
                "description": "Describes tools and workflows.",
                "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING"}}},
            },
            {
                "name": "web_search",
                "description": "Searches the web and news.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING"},
                        "mode": {"type": "STRING"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "reminder",
                "description": "Sets a timed reminder.",
                "parameters": {"type": "OBJECT", "properties": {"message": {"type": "STRING"}}},
            },
            {
                "name": "model_lifecycle",
                "description": "Reports and cleans up LM Studio loaded models.",
                "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING"}}},
            },
            {
                "name": "jarvis_memory",
                "description": "Writes vault notes and queries local RAG.",
                "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING"}}},
            },
            {
                "name": "plan_workflow",
                "description": "Creates long-form plans and execution summaries.",
                "parameters": {"type": "OBJECT", "properties": {"operation": {"type": "STRING"}}},
            },
            {
                "name": "save_memory",
                "description": "Writes compact JSON memory.",
                "parameters": {"type": "OBJECT", "properties": {"value": {"type": "STRING"}}},
            },
            {
                "name": "file_processor",
                "description": "Analyzes uploaded files.",
                "parameters": {"type": "OBJECT", "properties": {"file_path": {"type": "STRING"}}},
            },
            {
                "name": "file_controller",
                "description": "Reads and writes local files.",
                "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING"}}},
            },
        ]

    def test_registry_identity_and_voice_do_not_require_gemini(self):
        registry = build_registry(self.declarations(), config={"stt_engine": "vosk", "tts_engine": "windows"})

        self.assertEqual(registry["identity"]["assistant_name"], "JARVIS")
        self.assertEqual(registry["identity"]["platform_name"], "MARK XLVIII")
        self.assertFalse(registry["voice"]["gemini_live_required"])
        self.assertEqual(registry["voice"]["stt_engine"], "vosk")
        self.assertEqual(registry["voice"]["tts_engine"], "windows")

    def test_help_merges_deep_help_with_tool_schema(self):
        payload = json.loads(
            capability_registry(
                {"operation": "help", "tool_name": "web_search"},
                declarations=self.declarations(),
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["identity"]["assistant_name"], "JARVIS")
        self.assertEqual(payload["tool"]["name"], "web_search")
        self.assertIn("news", payload["tool"]["categories"])
        self.assertIn("query", payload["tool"]["schema"]["properties"])
        self.assertIn("current information", payload["details"])

    def test_search_finds_speech_and_reminder_capabilities(self):
        speech = json.loads(
            capability_registry(
                {"operation": "search", "query": "does text to speech work"},
                declarations=self.declarations(),
            )
        )
        reminders = json.loads(
            capability_registry(
                {"operation": "search", "query": "can you set reminders"},
                declarations=self.declarations(),
            )
        )

        self.assertEqual(speech["results"][0]["name"], "speech")
        self.assertEqual(reminders["results"][0]["name"], "reminder")

    def test_manifest_supports_mcp_style_tools_list(self):
        manifest = json.loads(
            capability_registry(
                {"operation": "manifest"},
                declarations=self.declarations(),
            )
        )
        listed = json.loads(
            capability_registry(
                {"operation": "mcp", "method": "tools/list"},
                declarations=self.declarations(),
            )
        )

        self.assertTrue(manifest["ok"])
        self.assertIn("tools/list", manifest["manifest"]["methods"])
        self.assertTrue(listed["ok"])
        self.assertTrue(any(tool["name"] == "web_search" for tool in listed["tools"]))

    def test_manifest_includes_workflow_records_and_methods(self):
        manifest = json.loads(
            capability_registry(
                {"operation": "manifest"},
                declarations=self.declarations(),
            )
        )

        workflow_names = {workflow["name"] for workflow in manifest["manifest"]["workflows"]}

        self.assertIn("workflows/list", manifest["manifest"]["methods"])
        self.assertIn("workflows/plan", manifest["manifest"]["methods"])
        self.assertIn("vault_markdown_note", workflow_names)
        self.assertIn("short_term_json_memory", workflow_names)
        self.assertIn("deep_research_report", workflow_names)
        self.assertIn("learn_topic_memory", workflow_names)
        self.assertIn("todo_list_template", workflow_names)
        self.assertIn("current_news_report", workflow_names)
        self.assertIn("long_form_plan_execution", workflow_names)
        self.assertIn("canvas_plan_review_cycle", workflow_names)
        self.assertIn("registered_project_handoff", workflow_names)
        self.assertIn("repository_learning", workflow_names)
        self.assertIn("browser_task_automation", workflow_names)
        self.assertIn("local_file_management", workflow_names)
        self.assertIn("scheduled_reminder", workflow_names)
        self.assertIn("skill_learning_gate", workflow_names)
        self.assertIn("task_tracking_review", workflow_names)

    def test_repository_learning_workflow_describes_read_only_vault_artifacts(self):
        payload = json.loads(
            capability_registry(
                {
                    "operation": "mcp",
                    "method": "workflows/get",
                    "params": {"name": "repository_learning"},
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(payload["ok"])
        workflow = payload["workflow"]
        self.assertIn("read-only", workflow["safety"].lower())
        self.assertTrue(any("Project Brief.md" in artifact for artifact in workflow["artifacts"]))
        self.assertIn("project_operator", workflow["invokes"])

    def test_canvas_plan_workflow_describes_approval_gated_execution(self):
        payload = json.loads(
            capability_registry(
                {
                    "operation": "mcp",
                    "method": "workflows/get",
                    "params": {"name": "canvas_plan_review_cycle"},
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(payload["ok"])
        workflow = payload["workflow"]
        self.assertIn("canvas_plan", workflow["invokes"])
        step_ids = {step["id"] for step in workflow["steps"]}
        self.assertIn("propose", step_ids)
        self.assertIn("await_decision", step_ids)
        self.assertIn("execute", step_ids)
        self.assertTrue(workflow["requires_confirmation"])

    def test_canvas_plan_capability_help_and_policy_are_registered(self):
        registry = build_registry(self.declarations())
        tool = next(item for item in registry["tools"] if item["name"] == "canvas_plan")

        self.assertIn("Mode 2", tool["title"])
        self.assertEqual(tool["risk_level"], "high")
        self.assertTrue(tool["requires_confirmation"])
        self.assertIn("OpenClaw", tool["permission_boundary"])

    def test_mcp_style_workflow_get_and_search(self):
        fetched = json.loads(
            capability_registry(
                {
                    "operation": "mcp",
                    "method": "workflows/get",
                    "params": {"name": "deep_research_report"},
                },
                declarations=self.declarations(),
            )
        )
        searched = json.loads(
            capability_registry(
                {
                    "operation": "mcp",
                    "method": "workflows/search",
                    "params": {"query": "markdown vault note"},
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(fetched["ok"])
        self.assertEqual(fetched["workflow"]["kind"], "workflow")
        self.assertIn("web_search", fetched["workflow"]["invokes"])
        self.assertTrue(any(workflow["name"] == "vault_markdown_note" for workflow in searched["workflows"]))

    def test_help_describes_json_memory_and_file_processing(self):
        memory = json.loads(
            capability_registry(
                {"operation": "help", "tool_name": "save_memory"},
                declarations=self.declarations(),
            )
        )
        files = json.loads(
            capability_registry(
                {"operation": "help", "tool_name": "file_processor"},
                declarations=self.declarations(),
            )
        )

        self.assertTrue(memory["ok"])
        self.assertIn("long_term.json", memory["details"])
        self.assertTrue(files["ok"])
        self.assertIn("model router", files["details"])

    def test_help_describes_topic_learning_memory(self):
        memory = json.loads(
            capability_registry(
                {"operation": "help", "tool_name": "jarvis_memory"},
                declarations=self.declarations(),
            )
        )
        workflow = json.loads(
            capability_registry(
                {
                    "operation": "mcp",
                    "method": "workflows/get",
                    "params": {"name": "learn_topic_memory"},
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(memory["ok"])
        self.assertIn("learn_topic", memory["details"])
        self.assertIn("create_todo_template", memory["details"])
        self.assertTrue(workflow["ok"])
        self.assertEqual(workflow["workflow"]["workflow_id"], "learn_topic_memory")
        self.assertIn("Jarvis_notes/Memories/learned_topics/*.md", workflow["workflow"]["artifacts"])

    def test_search_finds_model_lifecycle_help(self):
        payload = json.loads(
            capability_registry(
                {"operation": "search", "query": "what lm studio models are loaded"},
                declarations=self.declarations(),
            )
        )

        self.assertEqual(payload["results"][0]["name"], "model_lifecycle")

    def test_tools_call_uses_guarded_dispatcher(self):
        with mock.patch("core.tool_dispatcher.get_tool_dispatcher") as dispatcher:
            dispatcher.return_value.call.return_value = {
                "ok": True,
                "tool": "web_search",
                "result": {"results": [{"title": "Current result"}]},
                "policy": {"effect": "read", "requires_approval": False},
            }
            payload = json.loads(
                capability_registry(
                    {
                        "operation": "mcp",
                        "method": "tools/call",
                        "params": {"name": "web_search", "arguments": {"query": "latest news"}},
                    },
                    declarations=self.declarations(),
                )
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool"], "web_search")
        self.assertEqual(payload["policy"]["effect"], "read")

    def test_workflow_records_include_rich_planning_metadata(self):
        payload = json.loads(
            capability_registry(
                {
                    "operation": "mcp",
                    "method": "workflows/get",
                    "params": {"name": "current_news_report"},
                },
                declarations=self.declarations(),
            )
        )

        workflow = payload["workflow"]
        self.assertTrue(payload["ok"])
        self.assertEqual(workflow["workflow_id"], "current_news_report")
        self.assertEqual(workflow["risk_level"], "low")
        self.assertFalse(workflow["requires_confirmation"])
        self.assertIn("web_search", workflow["invokes"])
        self.assertIn("jarvis_memory", workflow["invokes"])
        self.assertTrue(all(isinstance(step, dict) for step in workflow["steps"]))
        self.assertTrue(any(step["operation"] == "create_report_from_search" for step in workflow["steps"]))
        self.assertIn("Jarvis_notes/Reports/*.md", workflow["artifacts"])
        self.assertIn("no_cited_sources", workflow["block_statuses"])

    def test_workflows_plan_matches_current_news_report(self):
        payload = json.loads(
            capability_registry(
                {
                    "operation": "plan",
                    "query": "generate me a markdown report of today's AI news for Obsidian",
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["workflow_id"], "current_news_report")
        self.assertIn("web_search", payload["invokes"])
        self.assertIn("jarvis_memory", payload["invokes"])
        self.assertFalse(payload["requires_confirmation"])
        self.assertIn("Jarvis_notes/Reports/*.md", payload["expected_artifacts"])

    def test_plan_workflow_help_and_plan_match(self):
        help_payload = json.loads(
            capability_registry(
                {"operation": "help", "tool_name": "plan_workflow"},
                declarations=self.declarations(),
            )
        )
        plan_payload = json.loads(
            capability_registry(
                {
                    "operation": "plan",
                    "query": "create a plan for improving subagent execution",
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(help_payload["ok"])
        self.assertEqual(help_payload["tool"]["name"], "plan_workflow")
        self.assertIn("pending_review", help_payload["details"])
        self.assertIn("Start Plan", help_payload["details"])
        self.assertTrue(plan_payload["ok"])
        self.assertEqual(plan_payload["workflow_id"], "long_form_plan_execution")
        self.assertIn("plan_workflow", plan_payload["invokes"])
        self.assertTrue(any(step.get("operation") == "start_plan" for step in plan_payload["steps"]))

    def test_workflows_plan_matches_learn_topic_memory(self):
        payload = json.loads(
            capability_registry(
                {
                    "operation": "plan",
                    "query": "could you learn about wifi sensing datasets so I can query you later",
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["workflow_id"], "learn_topic_memory")
        self.assertIn("web_search", payload["invokes"])
        self.assertIn("jarvis_memory", payload["invokes"])
        self.assertIn("Jarvis_notes/Memories/learned_topics/*.md", payload["expected_artifacts"])

    def test_workflows_plan_matches_todo_list_template(self):
        payload = json.loads(
            capability_registry(
                {
                    "operation": "plan",
                    "query": "place a blank to do list template in the obsidian vault using md formatting",
                },
                declarations=self.declarations(),
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["workflow_id"], "todo_list_template")
        self.assertEqual(payload["invokes"], ["jarvis_memory"])
        self.assertIn("Jarvis_notes/Templates/to-do-list-template.md", payload["expected_artifacts"])

    def test_progressive_disclosure_exposes_cards_manifests_and_schema_on_demand(self):
        cards = json.loads(
            capability_registry(
                {"operation": "mcp", "method": "cards/list", "params": {"query": "web news"}},
                declarations=self.declarations(),
            )
        )
        selected = json.loads(
            capability_registry(
                {"operation": "mcp", "method": "capabilities/select", "params": {"query": "search current AI news"}},
                declarations=self.declarations(),
            )
        )
        manifest = json.loads(
            capability_registry(
                {"operation": "mcp", "method": "manifests/get", "params": {"name": "web_search"}},
                declarations=self.declarations(),
            )
        )
        schema = json.loads(
            capability_registry(
                {"operation": "mcp", "method": "schemas/get", "params": {"name": "web_search"}},
                declarations=self.declarations(),
            )
        )

        self.assertTrue(cards["cards"])
        self.assertNotIn("schema", cards["cards"][0])
        self.assertIn(selected["selected"]["id"], {"web_search", "current_news_report"})
        self.assertEqual(manifest["manifest"]["id"], "web_search")
        self.assertIn("properties", schema["schema"])


if __name__ == "__main__":
    unittest.main()
