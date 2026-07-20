import json
import unittest

from actions.capability_registry import build_registry, capability_registry


class CapabilityRegistryTests(unittest.TestCase):
    def declarations(self):
        return [
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

    def test_search_finds_model_lifecycle_help(self):
        payload = json.loads(
            capability_registry(
                {"operation": "search", "query": "what lm studio models are loaded"},
                declarations=self.declarations(),
            )
        )

        self.assertEqual(payload["results"][0]["name"], "model_lifecycle")

    def test_tools_call_is_metadata_only(self):
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
        self.assertEqual(payload["call_policy"], "metadata_only")
        self.assertIn("does not execute", payload["message"])


if __name__ == "__main__":
    unittest.main()
