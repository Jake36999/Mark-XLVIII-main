import unittest


class SetupConfigMergeTests(unittest.TestCase):
    def test_setup_merge_updates_both_keys_and_preserves_provider_settings(self):
        from ui import _merge_setup_config

        existing = {
            "gemini_api_key": "old-gemini",
            "openai_api_key": "old-openai",
            "planner_provider": "openai",
            "planner_model": "gpt-5.4",
            "worker_provider": "lmstudio",
            "worker_model": "google/gemma-4-e4b",
            "lmstudio_url": "http://localhost:1234/v1",
        }

        merged = _merge_setup_config(existing, "new-gemini", "windows", "new-openai")

        self.assertEqual(merged["gemini_api_key"], "new-gemini")
        self.assertEqual(merged["openai_api_key"], "new-openai")
        self.assertEqual(merged["os_system"], "windows")
        self.assertEqual(merged["planner_provider"], "openai")
        self.assertEqual(merged["worker_model"], "google/gemma-4-e4b")

    def test_setup_merge_keeps_existing_keys_when_fields_are_blank(self):
        from ui import _merge_setup_config

        existing = {
            "gemini_api_key": "keep-gemini",
            "openai_api_key": "keep-openai",
            "os_system": "linux",
            "planner_model": "gpt-5.4",
        }

        merged = _merge_setup_config(existing, "", "windows", "")

        self.assertEqual(merged["gemini_api_key"], "keep-gemini")
        self.assertEqual(merged["openai_api_key"], "keep-openai")
        self.assertEqual(merged["os_system"], "windows")
        self.assertEqual(merged["planner_model"], "gpt-5.4")

    def test_setup_merge_sets_provider_defaults_when_openai_key_is_added(self):
        from ui import _merge_setup_config

        merged = _merge_setup_config(
            {"gemini_api_key": "gemini"},
            "gemini",
            "windows",
            "openai",
        )

        self.assertEqual(merged["planner_provider"], "openai")
        self.assertEqual(merged["openai_url"], "https://api.openai.com/v1")
        self.assertEqual(merged["worker_provider"], "lmstudio")
        self.assertEqual(merged["lmstudio_url"], "http://localhost:1234/v1")

    def test_setup_merge_prefers_openai_when_new_openai_key_is_entered(self):
        from ui import _merge_setup_config

        merged = _merge_setup_config(
            {
                "planner_provider": "lmstudio",
                "planner_model": "qwen/qwen3.5-9b",
                "worker_provider": "lmstudio",
            },
            "",
            "windows",
            "new-openai-key",
        )

        self.assertEqual(merged["openai_api_key"], "new-openai-key")
        self.assertEqual(merged["planner_provider"], "openai")


if __name__ == "__main__":
    unittest.main()
