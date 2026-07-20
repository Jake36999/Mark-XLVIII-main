import unittest
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
        self.assertTrue(
            main._gemini_live_enabled(
                {
                    "assistant_mode": "gemini_live",
                    "voice_provider": "gemini",
                    "gemini_api_key": "key",
                }
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

        self.assertTrue(_is_config_ready({"os_system": "windows", "openai_api_key": "sk-test"}))
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
        self.assertEqual(cfg["planner_provider"], "openai")

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

        tools = main._router_tool_schema()
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

        self.assertIn("capability_registry", news_tools)
        self.assertIn("web_search", news_tools)
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
        self.assertIn("local STT/TTS", system)
        self.assertIn("Gemini Live is optional", system)
        self.assertIn("JARVIS's tool router", jarvis._router_tool_system_prompt())

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
        )
        jarvis.ui.write_log.assert_any_call("TOOL: project_operator")
        jarvis.ui.write_log.assert_any_call("JARVIS: I found the registered projects.")
        jarvis.speak.assert_called_once_with("I found the registered projects.")


if __name__ == "__main__":
    unittest.main()
