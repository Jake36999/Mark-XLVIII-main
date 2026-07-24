import unittest
from pathlib import Path


class SetupConfigMergeTests(unittest.TestCase):
    def test_planning_button_has_explicit_cancel_mode(self):
        source = Path("ui.py").read_text(encoding="utf-8")

        self.assertIn('self._plan_btn.setText("CANCEL PLANNING")', source)
        self.assertIn('msg = "cancel planning"', source)
        self.assertIn("_planning_sig = pyqtSignal(bool, bool)", source)

    def test_setup_merge_discards_keys_and_preserves_provider_settings(self):
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

        self.assertNotIn("gemini_api_key", merged)
        self.assertNotIn("openai_api_key", merged)
        self.assertEqual(merged["os_system"], "windows")
        self.assertEqual(merged["planner_provider"], "openai")
        self.assertEqual(merged["worker_model"], "google/gemma-4-e4b")

    def test_setup_merge_removes_existing_keys_when_fields_are_blank(self):
        from ui import _merge_setup_config

        existing = {
            "gemini_api_key": "keep-gemini",
            "openai_api_key": "keep-openai",
            "os_system": "linux",
            "planner_model": "gpt-5.4",
        }

        merged = _merge_setup_config(existing, "", "windows", "")

        self.assertNotIn("gemini_api_key", merged)
        self.assertNotIn("openai_api_key", merged)
        self.assertEqual(merged["os_system"], "windows")
        self.assertEqual(merged["planner_model"], "gpt-5.4")

    def test_setup_merge_uses_local_defaults_even_when_cloud_keys_are_submitted(self):
        from ui import _merge_setup_config

        merged = _merge_setup_config(
            {"gemini_api_key": "gemini"},
            "gemini",
            "windows",
            "openai",
        )

        self.assertNotIn("openai_api_key", merged)
        self.assertNotIn("gemini_api_key", merged)
        self.assertEqual(merged["planner_provider"], "lmstudio")
        self.assertEqual(merged["openai_url"], "https://api.openai.com/v1")
        self.assertEqual(merged["worker_provider"], "lmstudio")
        self.assertEqual(merged["lmstudio_url"], "http://localhost:1234/v1")

    def test_setup_merge_does_not_change_provider_from_temporary_key_input(self):
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

        self.assertNotIn("openai_api_key", merged)
        self.assertEqual(merged["planner_provider"], "lmstudio")


if __name__ == "__main__":
    unittest.main()
