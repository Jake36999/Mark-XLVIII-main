import unittest
import json
import threading
import tempfile
from datetime import datetime
from types import SimpleNamespace
from unittest import mock
from pathlib import Path


class RouterModeConfigTests(unittest.TestCase):
    def test_assistant_mode_defaults_to_router(self):
        import main

        self.assertEqual(main._assistant_mode({}), "router")

    def test_gemini_live_is_disabled_unless_explicitly_enabled(self):
        import main

        self.assertFalse(main._gemini_live_enabled({}))
        self.assertFalse(main._gemini_live_enabled({"assistant_mode": "router"}))
        self.assertFalse(
            main._gemini_live_enabled(
                {"assistant_mode": "gemini_live", "voice_provider": "gemini", "gemini_api_key": "key"}
            )
        )

    def test_google_billing_error_is_non_retryable(self):
        import main

        self.assertTrue(
            main._is_nonretryable_gemini_error(
                "Your prepayment credits are depleted. Please manage billing."
            )
        )
        self.assertTrue(main._is_nonretryable_gemini_error("429 RESOURCE_EXHAUSTED"))


class RouterModeSetupConfigTests(unittest.TestCase):
    def test_ui_config_ready_accepts_openai_without_gemini(self):
        from ui import _is_config_ready

        self.assertFalse(_is_config_ready({"os_system": "windows", "openai_api_key": "sk-test"}))
        self.assertTrue(
            _is_config_ready(
                {
                    "os_system": "windows",
                    "assistant_mode": "router",
                    "planner_provider": "lmstudio",
                    "lmstudio_url": "http://localhost:1234/v1",
                }
            )
        )
        self.assertFalse(_is_config_ready({"planner_provider": "lmstudio"}))

    def test_setup_merge_enables_router_mode_when_openai_key_is_added(self):
        from ui import _merge_setup_config

        cfg = _merge_setup_config({}, "", "windows", "sk-test")

        self.assertEqual(cfg["assistant_mode"], "router")
        self.assertEqual(cfg["voice_provider"], "disabled")
        self.assertEqual(cfg["planner_provider"], "lmstudio")
        self.assertNotIn("openai_api_key", cfg)

    def test_setup_merge_supports_local_mode_without_cloud_keys(self):
        from ui import _merge_setup_config, _is_config_ready

        cfg = _merge_setup_config({}, "", "windows", "")

        self.assertEqual(cfg["assistant_mode"], "router")
        self.assertEqual(cfg["planner_provider"], "lmstudio")
        self.assertEqual(cfg["worker_provider"], "lmstudio")
        self.assertTrue(_is_config_ready(cfg))


class DependencyScriptTests(unittest.TestCase):
    def test_dependency_check_script_lists_required_runtime_imports(self):
        script = Path("scripts/check-mark-dependencies.ps1")

        self.assertTrue(script.exists())
        text = script.read_text(encoding="utf-8")
        for module in ("PyQt6", "requests", "google.genai", "sounddevice", "fastapi", "uvicorn"):
            self.assertIn(module, text)


class RouterToolCallingTests(unittest.TestCase):
    def test_router_tool_schema_uses_openai_compatible_function_tools(self):
        import main

        tools = main._router_tool_schema("scout this registered project")
        project_tool = next(item for item in tools if item["function"]["name"] == "project_operator")

        self.assertEqual(project_tool["type"], "function")
        self.assertEqual(project_tool["function"]["parameters"]["type"], "object")
        self.assertEqual(
            project_tool["function"]["parameters"]["properties"]["operation"]["type"],
            "string",
        )

    def test_router_tool_schema_filters_by_prompt(self):
        import main

        tools = main._router_tool_schema("check system status")

        self.assertEqual([tool["function"]["name"] for tool in tools], ["system_status"])

    def test_router_tool_schema_routes_memory_prompts_to_jarvis_memory(self):
        import main

        tools = main._router_tool_schema("search your memory for the local model plan")
        names = [tool["function"]["name"] for tool in tools]

        self.assertIn("jarvis_memory", names)

    def test_router_tool_schema_routes_relationship_questions_to_graphify_query(self):
        import main

        for prompt in (
            "what calls select_reading_set",
            "what does ToolDispatcher depend on",
            "show me the codebase knowledge graph",
            "what is the shortest path between ToolDispatcher and capability_registry",
        ):
            names = [tool["function"]["name"] for tool in main._router_tool_schema(prompt)]
            self.assertIn("graphify_query", names, msg=f"prompt={prompt!r} names={names}")

    def test_router_tool_schema_offers_graphify_query_alongside_project_operator(self):
        import main

        names = [tool["function"]["name"] for tool in main._router_tool_schema("explain the codebase structure")]

        self.assertIn("project_operator", names)
        self.assertIn("graphify_query", names)

    def test_router_tool_schema_routes_vault_markdown_and_json_memory(self):
        import main

        vault_tools = [
            tool["function"]["name"]
            for tool in main._router_tool_schema("create a markdown note in your vault")
        ]
        json_tools = [
            tool["function"]["name"]
            for tool in main._router_tool_schema("save this as short-term JSON memory")
        ]

        self.assertIn("jarvis_memory", vault_tools)
        self.assertIn("save_memory", json_tools)
        self.assertIn("jarvis_memory", json_tools)

    def test_router_tool_schema_routes_document_folder_and_deep_research_workflows(self):
        import main

        document_tools = [
            tool["function"]["name"]
            for tool in main._router_tool_schema("analyze this large document")
        ]
        folder_tools = [
            tool["function"]["name"]
            for tool in main._router_tool_schema("analyze this large folder")
        ]
        research_tools = [
            tool["function"]["name"]
            for tool in main._router_tool_schema("generate a deep research report on local RAG")
        ]

        self.assertIn("file_processor", document_tools)
        self.assertIn("file_controller", folder_tools)
        self.assertIn("project_operator", folder_tools)
        self.assertIn("jarvis_memory", research_tools)
        self.assertIn("web_search", research_tools)

    def test_router_tool_schema_hard_routes_current_news_reports(self):
        import main

        tools = main._router_tool_schema("could you generate a .md report of today's AI news for Obsidian")
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["capability_registry", "web_search", "jarvis_memory"])

    def test_router_tool_schema_hard_routes_learn_topic_workflow(self):
        import main

        text = "hey, could you learn about wifi sensing datasets so I can query you about them later"
        tools = main._router_tool_schema(text)
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["capability_registry", "web_search", "jarvis_memory"])
        self.assertEqual(main._extract_learn_topic(text), "wifi sensing datasets")

    def test_router_tool_schema_hard_routes_todo_template_workflow(self):
        import main

        tools = main._router_tool_schema("just place a blank to do list template in the obsidian vault using .md formatting")
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["jarvis_memory"])

    def test_router_tool_schema_routes_create_plan_to_plan_workflow(self):
        import main

        tools = main._router_tool_schema("create plan: improve workflow execution with subagents")
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["plan_workflow"])

    def test_deep_research_task_is_a_reviewable_plan_request(self):
        import main

        text = (
            "conduct a deep research task and gather resources for using wifi for a sensing pipeline "
            "and how others are doing it, with or without a camera"
        )

        self.assertTrue(main._is_create_plan_prompt(text))
        self.assertEqual([tool["function"]["name"] for tool in main._router_tool_schema(text)], ["plan_workflow"])
        self.assertTrue(main._extract_plan_prompt(text).startswith("gather resources for using wifi"))

    def test_cancel_planning_is_hard_routed_to_plan_workflow(self):
        import main

        self.assertTrue(main._is_cancel_planning_prompt("cancel planning"))
        self.assertEqual(
            [tool["function"]["name"] for tool in main._router_tool_schema("cancel planning")],
            ["plan_workflow"],
        )

    def test_router_tool_schema_routes_start_plan_to_plan_workflow(self):
        import main

        tools = main._router_tool_schema("start plan: latest")
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["plan_workflow"])

    def test_router_tool_schema_routes_revise_plan_to_plan_workflow(self):
        import main

        tools = main._router_tool_schema("revise plan: make the first milestone smaller")
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["plan_workflow"])

    def test_router_tool_schema_routes_natural_plan_update_to_plan_workflow(self):
        import main

        text = "kay, i need you to update the plan to conduct online research for what datasets are available for wifi sensing"
        tools = main._router_tool_schema(text)
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["plan_workflow"])
        self.assertEqual(
            main._extract_plan_revision(text),
            "conduct online research for what datasets are available for wifi sensing",
        )

    def test_router_tool_schema_routes_capability_questions_to_registry(self):
        import main

        tools = main._router_tool_schema("what tools do you have")
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["capability_registry"])

    def test_router_tool_schema_routes_speech_questions_to_registry(self):
        import main

        tools = main._router_tool_schema("does your text to speech work")
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(names, ["capability_registry"])

    def test_router_tool_schema_keeps_action_tools_for_web_news_and_reminders(self):
        import main

        news_tools = [tool["function"]["name"] for tool in main._router_tool_schema("can you check the news")]
        reminder_tools = [tool["function"]["name"] for tool in main._router_tool_schema("set a reminder")]
        web_tools = [tool["function"]["name"] for tool in main._router_tool_schema("search the web")]

        # "can you check the news" used to also offer capability_registry,
        # because the routing table matched the bare politeness marker
        # "can you ". That collision is what sent "can you extract the methods
        # from this pdf" to the capability manifest -- whose contents are
        # literally JARVIS's own backend orchestration methods. The marker is
        # gone, so a clear action prompt now yields just its action tool, which
        # is what the other two assertions here already expected.
        self.assertEqual(news_tools, ["web_search"])
        self.assertEqual(reminder_tools, ["reminder"])
        self.assertEqual(web_tools, ["web_search"])

    def test_router_prompts_name_jarvis_and_make_gemini_optional(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)

        with mock.patch("main.load_memory", return_value={}), \
             mock.patch("main.format_memory_for_prompt", return_value=""), \
             mock.patch("main._load_system_prompt", return_value="core prompt"):
            system = jarvis._router_system_prompt()

        self.assertIn("You are JARVIS", system)
        self.assertIn("MARK XLVIII is the shell/platform name", system)
        self.assertIn("Always answer in English", system)
        self.assertIn("local STT/TTS", system)
        self.assertIn("Gemini Live is optional", system)
        self.assertIn("ISO date", system)
        self.assertIn("JARVIS's tool router", jarvis._router_tool_system_prompt())
        self.assertIn("Markdown/JSON memory", jarvis._router_tool_system_prompt())
        self.assertIn("CURRENT DATE AND TIME", jarvis._router_tool_system_prompt())

    def test_core_prompt_disables_automatic_language_switch_memory(self):
        prompt = Path("core/prompt.txt").read_text(encoding="utf-8")

        self.assertIn("Always answer and speak in English", prompt)
        self.assertIn("LANGUAGE LOCK", prompt)
        self.assertNotIn("LANGUAGE DETECTION", prompt)
        self.assertNotIn("Respond in user's language", prompt)

    def test_router_mode_executes_tool_calls_and_summarizes_result(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.ui.muted = False
        jarvis._router_system_prompt = mock.Mock(return_value="system")
        jarvis._execute_router_tool_call = mock.Mock(return_value='{"ok": true, "projects": []}')
        jarvis.speak = mock.Mock()

        routed = SimpleNamespace(
            text="",
            tool_calls=[
                SimpleNamespace(
                    id="call_1",
                    name="project_operator",
                    arguments={"operation": "list"},
                )
            ],
        )

        with mock.patch("main.call_with_tools", return_value=routed) as call_with_tools, \
             mock.patch("main.call_text", return_value="I found the registered projects."):
            jarvis._handle_router_text_command("list my projects")

        call_with_tools.assert_called_once()
        jarvis._execute_router_tool_call.assert_called_once_with(
            "call_1",
            "project_operator",
            {"operation": "list"},
            # A model-selected call is authorized by classify_effect having
            # cleared it, and must say so -- see _TOOL_AUTHORIZATION_BASES.
            authorized_by="effect_classified",
        )
        jarvis.ui.write_log.assert_any_call("TOOL: project_operator")
        jarvis.ui.write_log.assert_any_call("JARVIS: I found the registered projects.")
        jarvis.speak.assert_called_once_with("I found the registered projects.")

    def test_router_turn_injects_and_acknowledges_relevant_external_vault_change(self):
        import main
        from core import vault_activity

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "Alpha.md"
            note.write_text("---\nid: alpha\ntitle: Alpha\n---\n\n# Alpha\nOld value\n", encoding="utf-8")
            vault_activity.baseline_vault(root)
            note.write_text(note.read_text(encoding="utf-8").replace("Old value", "New value"), encoding="utf-8")
            vault_activity.process_event_batch(root, [{"event_type": "modified", "src_path": str(note)}])

            jarvis = main.JarvisLive.__new__(main.JarvisLive)
            jarvis.ui = mock.Mock()
            jarvis._router_system_prompt = mock.Mock(return_value="system")
            jarvis.speak = mock.Mock()
            routed = SimpleNamespace(text="The Alpha note changed to New value.", tool_calls=[])
            cfg = {
                "jarvis_notes_root": str(root),
                "vault_turn_awareness_enabled": True,
                "vault_turn_change_limit": 8,
                "vault_turn_change_max_chars": 1800,
            }

            with mock.patch("main._load_runtime_config", return_value=cfg), mock.patch(
                "main.call_with_tools", return_value=routed
            ) as call_with_tools:
                jarvis._handle_router_text_command("what changed in Alpha?", turn_id=7)

            model_prompt = call_with_tools.call_args.args[0]
            self.assertIn("HOST VAULT CHANGE CONTEXT", model_prompt)
            self.assertIn("New value", model_prompt)
            self.assertEqual(vault_activity.pending_change_count(root), 0)

    def test_current_news_report_workflow_executes_search_before_memory(self):
        import main

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 7, 20, 12, 0)

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        calls = []

        def fake_execute(call_id, name, args, *, authorized_by=""):
            calls.append((name, args))
            if name == "capability_registry":
                return json.dumps({"ok": True, "workflow_id": "current_news_report"})
            if name == "web_search":
                self.assertEqual(args["mode"], "news")
                self.assertEqual(args["date_from"], "2026-07-20")
                self.assertTrue(args["require_citations"])
                return json.dumps(
                    {
                        "ok": True,
                        "query": "AI news",
                        "mode": "news",
                        "retrieved_at": "2026-07-20T12:00:00Z",
                        "results": [
                            {
                                "title": "AI Lab Ships Safer Tool Use Model",
                                "snippet": "Grounded cited source.",
                                "url": "https://example.com/ai-tool-use",
                                "source": "Example News",
                            }
                        ],
                    }
                )
            if name == "jarvis_memory":
                self.assertEqual(args["operation"], "create_report_from_search")
                self.assertEqual(args["search_payload"]["results"][0]["url"], "https://example.com/ai-tool-use")
                return json.dumps(
                    {
                        "ok": True,
                        "title": "AI News Briefing - 2026-07-20",
                        "path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Reports\\ai.md",
                        "source_count": 1,
                    }
                )
            raise AssertionError(name)

        jarvis._execute_router_tool_call = mock.Mock(side_effect=fake_execute)

        with mock.patch("main.datetime", FixedDateTime):
            reply = jarvis._handle_current_news_report_workflow(
                "please generate a markdown report of today's AI news for Obsidian"
            )

        self.assertIn("saved AI News Briefing - 2026-07-20", reply)
        self.assertEqual([name for name, _ in calls], ["capability_registry", "web_search", "jarvis_memory"])
        jarvis.ui.write_log.assert_any_call("TOOL: capability_registry")
        jarvis.ui.write_log.assert_any_call("TOOL: web_search")
        jarvis.ui.write_log.assert_any_call("TOOL: jarvis_memory")

    def test_learn_topic_workflow_executes_search_before_memory(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        calls = []

        def fake_execute(call_id, name, args, *, authorized_by=""):
            calls.append((name, args))
            if name == "capability_registry":
                return json.dumps({"ok": True, "workflow_id": "learn_topic_memory"})
            if name == "web_search":
                self.assertEqual(args["mode"], "research")
                self.assertEqual(args["query"], "wifi sensing datasets")
                self.assertTrue(args["require_citations"])
                return json.dumps(
                    {
                        "ok": True,
                        "query": "wifi sensing datasets",
                        "mode": "research",
                        "retrieved_at": "2026-07-21T09:00:00Z",
                        "results": [
                            {
                                "title": "WiFi CSI Dataset Collection",
                                "snippet": "Channel state information datasets for WiFi sensing.",
                                "url": "https://example.com/wifi-csi-datasets",
                                "source": "Example Research",
                            },
                            {
                                "title": "Intel 5300 CSI Dataset Notes",
                                "snippet": "Dataset notes for Intel 5300 receiver workflows.",
                                "url": "https://example.com/intel-5300",
                                "source": "Example Lab",
                            },
                        ],
                    }
                )
            if name == "jarvis_memory":
                self.assertEqual(args["operation"], "learn_topic")
                self.assertEqual(args["topic"], "wifi sensing datasets")
                self.assertEqual(args["search_payload"]["results"][0]["url"], "https://example.com/wifi-csi-datasets")
                return json.dumps(
                    {
                        "ok": True,
                        "topic": "wifi sensing datasets",
                        "report_path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Deep Research\\wifi.md",
                        "memory_path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Memories\\learned_topics\\wifi.md",
                        "source_count": 2,
                        "key_points": [
                            "1. WiFi CSI Dataset Collection: Channel state information datasets [1]",
                        ],
                    }
                )
            raise AssertionError(name)

        jarvis._execute_router_tool_call = mock.Mock(side_effect=fake_execute)

        reply = jarvis._handle_learn_topic_workflow(
            "hey, could you learn about wifi sensing datasets so I can query you about them later"
        )

        self.assertIn("I have learned about wifi sensing datasets", reply)
        self.assertIn("RAG memory note", reply)
        self.assertEqual([name for name, _ in calls], ["capability_registry", "web_search", "jarvis_memory"])
        jarvis.ui.write_log.assert_any_call("TOOL: capability_registry")
        jarvis.ui.write_log.assert_any_call("TOOL: web_search")
        jarvis.ui.write_log.assert_any_call("TOOL: jarvis_memory")

    def test_todo_template_workflow_calls_memory_directly(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Templates\\to-do-list-template.md",
                    "template_kind": "todo_list",
                    "reindex": {"ok": True},
                }
            )
        )

        reply = jarvis._handle_todo_template_workflow(
            "just place a blank to do list template in the obsidian vault using .md formatting"
        )

        self.assertIn("blank Markdown to-do list template", reply)
        jarvis._execute_router_tool_call.assert_called_once()
        _, tool_name, args = jarvis._execute_router_tool_call.call_args.args
        self.assertEqual(tool_name, "jarvis_memory")
        self.assertEqual(args["operation"], "create_todo_template")
        self.assertTrue(args["reindex"])
        jarvis.ui.write_log.assert_any_call("TOOL: jarvis_memory")

    def test_stale_router_turn_is_suppressed(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.speak = mock.Mock()
        jarvis._router_turn_lock = threading.Lock()
        jarvis._router_generation_lock = threading.Lock()
        jarvis._router_turn_seq = 2
        jarvis._router_latest_turn_id = 2

        with mock.patch("main.call_with_tools") as call_with_tools:
            jarvis._handle_router_text_command("yesterday list", turn_id=1, source="voice")

        call_with_tools.assert_not_called()
        jarvis.speak.assert_not_called()
        jarvis.ui.write_log.assert_any_call("SYS: Skipped stale voice turn.")

    def test_create_plan_workflow_calls_plan_tool_directly(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Plans\\plan.md",
                    "metadata": {"title": "Plan - Improve Workflow Execution"},
                }
            )
        )

        reply = jarvis._handle_create_plan_workflow("create plan: improve workflow execution with subagents")

        self.assertIn("Plan created and saved", reply)
        jarvis._execute_router_tool_call.assert_called_once()
        _, tool_name, args = jarvis._execute_router_tool_call.call_args.args
        self.assertEqual(tool_name, "plan_workflow")
        self.assertEqual(args["operation"], "create_plan")
        self.assertEqual(args["prompt"], "improve workflow execution with subagents")
        self.assertTrue(args["internet"])
        jarvis.ui.write_log.assert_any_call("TOOL: plan_workflow")
        jarvis.ui.set_planning_mode.assert_called_once_with(True, prompt_submitted=True)

    def test_cancel_planning_exits_mode_without_deleting_the_plan_note(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._pending_plan_run_id = ""
        jarvis._active_plan_run_id = ""
        jarvis._planning_mode_active = True

        reply = jarvis._handle_cancel_planning_workflow("cancel planning")

        self.assertIn("Planning mode cancelled", reply)
        self.assertIn("remains in the vault", reply)
        self.assertFalse(jarvis._planning_mode_active)
        jarvis.ui.set_planning_mode.assert_called_once_with(False)

    def test_start_plan_workflow_calls_plan_tool_directly(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Plans\\plan.md",
                    "execution_summary_path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Summaries\\run.md",
                    "run_id": "plan-run-20260721120000-demo",
                    "packets": [
                        {"id": "P01", "task": "Execute first milestone", "worker": "JARVIS router"},
                    ],
                }
            )
        )

        reply = jarvis._handle_start_plan_workflow("start plan: latest")

        self.assertIn("Plan started", reply)
        self.assertIn("Execution run note", reply)
        jarvis._execute_router_tool_call.assert_called_once()
        _, tool_name, args = jarvis._execute_router_tool_call.call_args.args
        self.assertEqual(tool_name, "plan_workflow")
        self.assertEqual(args["operation"], "start_plan")
        self.assertEqual(args["path"], "latest")
        self.assertEqual(args["agent_count"], 1)
        jarvis.ui.write_log.assert_any_call("TOOL: plan_workflow")

    def test_revise_plan_workflow_calls_plan_tool_directly(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Plans\\plan.md",
                    "status": "revision_requested",
                }
            )
        )

        reply = jarvis._handle_revise_plan_workflow("revise plan: make the first milestone smaller")

        self.assertIn("Plan revision recorded", reply)
        jarvis._execute_router_tool_call.assert_called_once()
        _, tool_name, args = jarvis._execute_router_tool_call.call_args.args
        self.assertEqual(tool_name, "plan_workflow")
        self.assertEqual(args["operation"], "revise_plan")
        self.assertEqual(args["path"], "latest")
        self.assertEqual(args["revision"], "make the first milestone smaller")
        jarvis.ui.write_log.assert_any_call("TOOL: plan_workflow")

    def test_natural_update_plan_workflow_calls_plan_tool_directly(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "path": "F:\\Mark-XLVIII-main\\Jarvis_notes\\Plans\\plan.md",
                    "status": "revision_requested",
                }
            )
        )

        reply = jarvis._handle_revise_plan_workflow(
            "kay, i need you to update the plan to conduct online research for what datasets are available for wifi sensing"
        )

        self.assertIn("Plan revision recorded", reply)
        jarvis._execute_router_tool_call.assert_called_once()
        _, tool_name, args = jarvis._execute_router_tool_call.call_args.args
        self.assertEqual(tool_name, "plan_workflow")
        self.assertEqual(args["operation"], "revise_plan")
        self.assertEqual(args["path"], "latest")
        self.assertEqual(
            args["revision"],
            "conduct online research for what datasets are available for wifi sensing",
        )
        jarvis.ui.write_log.assert_any_call("TOOL: plan_workflow")


class ToolSummaryGroundingTests(unittest.TestCase):
    """Regression coverage for a live-tested finding: a chat request to run a
    specific test file got routed to project_operator (an unrelated project's
    generic status), and the summary step then fabricated a 'test suite passed,
    proceeding with feature closure' narrative from that status. The prompt must
    name exactly which tools ran and explicitly forbid claiming a test/build/gate
    outcome that isn't actually present in the tool result."""

    def test_summary_prompt_lists_the_tools_actually_called(self):
        import main

        prompt = main._build_tool_summary_prompt(
            "Run the tests and confirm this feature is done.",
            [{"tool": "project_operator", "arguments": {}, "result": '{"ok": true}'}],
        )

        self.assertIn("Tools actually called this turn: project_operator", prompt)

    def test_summary_prompt_forbids_unfounded_test_or_gate_claims(self):
        import main

        prompt = main._build_tool_summary_prompt("Run the tests.", [])

        self.assertIn("Tools actually called this turn: none", prompt)
        self.assertIn("Never state", prompt)
        self.assertIn("test suite", prompt.lower())

    def test_summary_prompt_dedupes_repeated_tool_names(self):
        import main

        prompt = main._build_tool_summary_prompt(
            "Do a thing twice.",
            [
                {"tool": "project_operator", "arguments": {}, "result": "{}"},
                {"tool": "project_operator", "arguments": {}, "result": "{}"},
            ],
        )

        self.assertIn("Tools actually called this turn: project_operator", prompt)
        self.assertNotIn("project_operator, project_operator", prompt)


class ToolReceiptTests(unittest.TestCase):
    """WS2 (2026-07-24 planning roadmap, D4): a deterministic, unfabricatable
    record of what a tool call actually returned, used both for the process
    trace and as evidence for the anti-fabrication check below."""

    def test_json_result_extracts_ok_returncode_and_error(self):
        import main

        result = '{"ok": false, "returncode": 1, "error": "boom", "extra": "ignored-shape"}'
        receipt = main._tool_receipt("code_helper", {"operation": "run"}, result)

        self.assertEqual(receipt["tool"], "code_helper")
        self.assertEqual(receipt["operation"], "run")
        self.assertEqual(receipt["ok"], False)
        self.assertEqual(receipt["returncode"], 1)
        self.assertEqual(receipt["error"], "boom")

    def test_non_json_result_falls_back_to_a_snippet(self):
        import main

        receipt = main._tool_receipt("weather_report", {}, "Sunny, 21C")

        self.assertNotIn("ok", receipt)
        self.assertEqual(receipt["result_snippet"], "Sunny, 21C")


class UnverifiedCompletionNoticeTests(unittest.TestCase):
    """WS2 hard anti-fabrication check: the live-tested failure was JARVIS
    claiming 'test suite passed... proceeding with feature closure' from a
    project_operator call that never ran a test. A completion-style claim
    with no supporting receipt must get a deterministic caveat appended."""

    def test_unsupported_test_pass_claim_gets_a_notice(self):
        import main

        reply = (
            "The test suite has been checked for status. Result: Operation status "
            "confirmed as successful (ok: true). This confirms the feature is ready "
            "for completion per the defined confirmation gate. Proceeding with "
            "feature closure."
        )
        receipts = [{"tool": "project_operator", "ok": True, "result_snippet": '{"ok": true, "projects": []}'}]

        notice = main._unverified_completion_notice(reply, receipts)

        self.assertIsNotNone(notice)
        self.assertIn("unverified", notice.lower())

    def test_test_pass_claim_backed_by_a_real_receipt_gets_no_notice(self):
        import main

        reply = "All tests passed -- 17 passed in 0.35s."
        receipts = [{"tool": "code_helper", "result_snippet": "17 passed in 0.35s"}]

        self.assertIsNone(main._unverified_completion_notice(reply, receipts))

    def test_plain_reply_with_no_completion_claim_gets_no_notice(self):
        import main

        self.assertIsNone(main._unverified_completion_notice("Here are your registered projects.", []))

    def test_honest_negated_claim_is_not_flagged(self):
        """Regression: a live re-run surfaced this exact false positive -- a
        correctly-grounded reply that says a test outcome could NOT be
        confirmed was itself getting flagged as the unsupported claim."""
        import main

        reply = (
            "The requested tests (test_tts_read_trigger.py) were not run, and no test "
            "results are available in the provided tool output. The project_operator "
            "tool returned a status summary but did not execute or report on the test "
            "suite. Therefore, the vault-watcher TTS read-trigger tests cannot be "
            "confirmed as passing."
        )
        receipt = {"tool": "project_operator", "ok": True, "result_snippet": '{"ok": true}'}

        self.assertIsNone(main._unverified_completion_notice(reply, [receipt]))


class RouterModeAntiFabricationIntegrationTests(unittest.TestCase):
    """Reproduces the exact live-tested fabrication scenario end to end
    through _handle_router_text_command, with the model calls mocked."""

    def test_fabricated_test_pass_claim_gets_flagged_in_the_final_reply(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.ui.muted = False
        jarvis._router_system_prompt = mock.Mock(return_value="system")
        jarvis.speak = mock.Mock()
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "projects": [{"project_id": "quantule_mapper", "display_name": "Quantule Mapper"}],
                }
            )
        )

        routed = SimpleNamespace(
            text="",
            tool_calls=[SimpleNamespace(id="call_1", name="project_operator", arguments={"operation": "status"})],
        )
        fabricated_reply = (
            "The vault-watcher's TTS read-trigger test suite has been checked for status. "
            "Result: Operation status confirmed as successful (ok: true). This confirms the "
            "feature is ready for completion per the defined confirmation gate. Proceeding "
            "with feature closure."
        )

        with mock.patch("main.call_with_tools", return_value=routed), mock.patch(
            "main.call_text", return_value=fabricated_reply
        ):
            jarvis._handle_router_text_command("Run the test suite and confirm tests/test_tts_read_trigger.py passes.")

        final_reply = jarvis.speak.call_args.args[0]
        self.assertIn(fabricated_reply, final_reply)
        self.assertIn("unverified", final_reply.lower())

    def test_a_real_pytest_pass_receipt_does_not_get_flagged(self):
        import main

        # code_helper's "run" operation is one of the tools the chat
        # confirmation gate now pauses (requires_approval per
        # core.tool_dispatcher.classify_effect) -- so this now takes two
        # turns: the first pauses for confirmation, the second (an
        # affirmative reply) actually executes and produces the grounded
        # reply this test is really checking for.
        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.ui.muted = False
        jarvis._router_system_prompt = mock.Mock(return_value="system")
        jarvis.speak = mock.Mock()
        jarvis._pending_tool_confirmation = None
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps({"ok": True, "returncode": 0, "stdout": "17 passed in 0.35s\n"})
        )

        routed = SimpleNamespace(
            text="",
            tool_calls=[SimpleNamespace(id="call_1", name="code_helper", arguments={"operation": "run"})],
        )
        real_reply = "All 17 tests passed."

        with mock.patch("main.call_with_tools", return_value=routed), mock.patch(
            "main.call_text", return_value=real_reply
        ):
            jarvis._handle_router_text_command("Run tests/test_tts_read_trigger.py.")

        jarvis._execute_router_tool_call.assert_not_called()
        self.assertIsNotNone(jarvis._pending_tool_confirmation)

        with mock.patch("main.call_with_tools") as fake_call_with_tools, mock.patch(
            "main.call_text", return_value=real_reply
        ):
            jarvis._handle_router_text_command("yes")

        fake_call_with_tools.assert_not_called()
        jarvis._execute_router_tool_call.assert_called_once()
        final_reply = jarvis.speak.call_args.args[0]
        self.assertEqual(final_reply, real_reply)
        self.assertNotIn("unverified", final_reply.lower())


class RepositoryLearningRouterTests(unittest.TestCase):
    def test_repository_learning_routes_before_generic_topic_learning(self):
        import main

        self.assertTrue(main._is_learn_project_prompt("learn about this project"))
        self.assertEqual(main._router_tool_names_for_text("please read the files in this directory"), ["project_operator"])

    def test_project_learning_handler_calls_read_only_operator(self):
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis._execute_router_tool_call = mock.Mock(
            return_value=json.dumps(
                {
                    "ok": True,
                    "status": "complete",
                    "project_root": "F:\\Mark-XLVIII-main",
                    "inventory_file_count": 120,
                    "files_read_count": 24,
                    "brief_path": "F:\\vault\\Project Brief.md",
                    "memory_path": "F:\\vault\\Project Memory.md",
                    "diagnostics": [],
                }
            )
        )

        reply = jarvis._handle_learn_project_workflow("learn about this project")

        self.assertIn("read-only repository learning", reply)
        self.assertIn("Project Brief.md", reply)
        _, tool_name, args = jarvis._execute_router_tool_call.call_args.args
        self.assertEqual(tool_name, "project_operator")
        self.assertEqual(args["operation"], "learn_project")
        self.assertEqual(args["project_id"], "mark_platform")


if __name__ == "__main__":
    unittest.main()
