import tempfile
import unittest
from pathlib import Path

from core.session_key_store import (
    forget_session_key, load_session_key, save_session_key, saved_providers,
)


class SessionKeyStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "session_keys.env"

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trips_a_saved_key(self):
        save_session_key("deepinfra", "abc123", path=self.path)

        self.assertEqual(load_session_key("deepinfra", path=self.path), "abc123")

    def test_missing_provider_returns_none_not_an_error(self):
        self.assertIsNone(load_session_key("openai", path=self.path))

    def test_saving_one_provider_does_not_touch_another(self):
        save_session_key("openai", "openai-key", path=self.path)
        save_session_key("anthropic", "anthropic-key", path=self.path)

        self.assertEqual(load_session_key("openai", path=self.path), "openai-key")
        self.assertEqual(load_session_key("anthropic", path=self.path), "anthropic-key")

    def test_re_saving_the_same_provider_overwrites_not_appends(self):
        """The whole point of the feature: 'the key most recently saved',
        not a growing history of every key ever pasted."""
        save_session_key("openai", "first-key", path=self.path)
        save_session_key("openai", "second-key", path=self.path)

        self.assertEqual(load_session_key("openai", path=self.path), "second-key")
        raw = self.path.read_text(encoding="utf-8")
        self.assertEqual(raw.count("OPENAI_API_KEY="), 1)

    def test_empty_key_is_refused(self):
        with self.assertRaises(ValueError):
            save_session_key("openai", "   ", path=self.path)

    def test_forget_removes_only_that_provider(self):
        save_session_key("openai", "openai-key", path=self.path)
        save_session_key("deepinfra", "di-key", path=self.path)

        forget_session_key("openai", path=self.path)

        self.assertIsNone(load_session_key("openai", path=self.path))
        self.assertEqual(load_session_key("deepinfra", path=self.path), "di-key")

    def test_forgetting_a_provider_with_nothing_saved_is_a_no_op(self):
        forget_session_key("openai", path=self.path)  # must not raise
        self.assertFalse(self.path.exists())

    def test_saved_providers_lists_lowercase_names(self):
        save_session_key("openai", "k1", path=self.path)
        save_session_key("deepinfra", "k2", path=self.path)

        self.assertEqual(saved_providers(path=self.path), ["deepinfra", "openai"])

    def test_no_file_yet_reports_no_saved_providers(self):
        self.assertEqual(saved_providers(path=self.path), [])


if __name__ == "__main__":
    unittest.main()
