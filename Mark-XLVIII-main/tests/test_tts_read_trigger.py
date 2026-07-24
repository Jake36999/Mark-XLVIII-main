import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import tts_read_trigger as trigger


class TriggerDetectionTests(unittest.TestCase):
    def test_checked_marker_is_detected(self):
        text = "- [x] Read this aloud [tts:read]\n"
        self.assertTrue(trigger.is_triggered(text))
        self.assertTrue(trigger.has_trigger(text))

    def test_unchecked_marker_is_not_triggered_but_is_present(self):
        text = "- [ ] Read this aloud [tts:read]\n"
        self.assertFalse(trigger.is_triggered(text))
        self.assertTrue(trigger.has_trigger(text))

    def test_unrelated_checked_checkbox_is_not_triggered(self):
        text = "- [x] Buy milk [task:groceries-1]\n"
        self.assertFalse(trigger.is_triggered(text))
        self.assertFalse(trigger.has_trigger(text))

    def test_case_insensitive_marker_and_checkbox(self):
        text = "- [X] Read aloud [TTS:READ]\n"
        self.assertTrue(trigger.is_triggered(text))

    def test_reset_trigger_unchecks_only_the_marked_line(self):
        text = "- [x] Buy milk [task:groceries-1]\n- [x] Read aloud [tts:read]\n"
        reset = trigger.reset_trigger(text)
        self.assertIn("- [x] Buy milk [task:groceries-1]", reset)
        self.assertIn("- [ ] Read aloud [tts:read]", reset)
        self.assertFalse(trigger.is_triggered(reset))


class TextForSpeechTests(unittest.TestCase):
    def test_strips_frontmatter(self):
        text = "---\ntitle: \"Test\"\n---\n\nHello there.\n"
        self.assertEqual(trigger.text_for_speech(text), "Hello there.")

    def test_strips_code_fences_and_inline_code(self):
        text = "Before.\n```python\nprint('secret')\n```\nAfter `inline` code.\n"
        result = trigger.text_for_speech(text)
        self.assertNotIn("print(", result)
        self.assertIn("Before.", result)
        self.assertIn("After inline code.", result)

    def test_strips_checkbox_and_trigger_marker(self):
        text = "- [x] Read this aloud [tts:read]\nActual content.\n"
        result = trigger.text_for_speech(text)
        self.assertNotIn("[tts:read]", result)
        self.assertNotIn("[x]", result)
        self.assertIn("Actual content.", result)

    def test_strips_headings_callouts_and_blockquotes(self):
        text = "## Section\n\n> [!info] Note\n> Some detail.\n\n> Plain quote.\n"
        result = trigger.text_for_speech(text)
        self.assertNotIn("##", result)
        self.assertNotIn("[!info]", result)
        self.assertIn("Section", result)
        self.assertIn("Some detail.", result)
        self.assertIn("Plain quote.", result)

    def test_resolves_wikilinks_to_display_text(self):
        text = "See [[Some Note]] and [[Other Note|a friendlier name]].\n"
        result = trigger.text_for_speech(text)
        self.assertIn("Some Note", result)
        self.assertIn("a friendlier name", result)
        self.assertNotIn("[[", result)


class CheckTtsReadTriggersTests(unittest.TestCase):
    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def test_checked_trigger_speaks_and_resets_the_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            self._write(note, "- [x] Read this aloud [tts:read]\nHello world.\n")
            fake_reader = mock.Mock()

            with mock.patch("actions.tts_read_trigger._get_reader", return_value=fake_reader), \
                 mock.patch("core.runtime_config.load_runtime_config", return_value={}), \
                 mock.patch("threading.Thread") as thread_cls:
                triggered = trigger.check_tts_read_triggers([str(note)])

            self.assertEqual(triggered, [str(note)])
            thread_cls.assert_called_once()
            _args, kwargs = thread_cls.call_args
            self.assertEqual(kwargs["target"], fake_reader.speak)
            self.assertIn("Hello world.", kwargs["args"][0])
            reset_text = note.read_text(encoding="utf-8")
            self.assertIn("- [ ] Read this aloud [tts:read]", reset_text)

    def test_unchecked_trigger_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            self._write(note, "- [ ] Read this aloud [tts:read]\nHello world.\n")

            with mock.patch("core.runtime_config.load_runtime_config", return_value={}), \
                 mock.patch("threading.Thread") as thread_cls:
                triggered = trigger.check_tts_read_triggers([str(note)])

            self.assertEqual(triggered, [])
            thread_cls.assert_not_called()

    def test_note_without_trigger_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            original = "# Just a normal note\n\n- [x] A regular task [task:1]\n"
            self._write(note, original)

            with mock.patch("core.runtime_config.load_runtime_config", return_value={}):
                triggered = trigger.check_tts_read_triggers([str(note)])

            self.assertEqual(triggered, [])
            self.assertEqual(note.read_text(encoding="utf-8"), original)

    def test_non_markdown_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.canvas"
            self._write(note, "- [x] Read this aloud [tts:read]\n")

            with mock.patch("core.runtime_config.load_runtime_config", return_value={}):
                triggered = trigger.check_tts_read_triggers([str(note)])

            self.assertEqual(triggered, [])

    def test_disabled_via_config_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            self._write(note, "- [x] Read this aloud [tts:read]\nHello world.\n")

            with mock.patch(
                "core.runtime_config.load_runtime_config",
                return_value={"tts_read_trigger_enabled": False},
            ), mock.patch("threading.Thread") as thread_cls:
                triggered = trigger.check_tts_read_triggers([str(note)])

            self.assertEqual(triggered, [])
            thread_cls.assert_not_called()
            # untouched -- still checked, since the feature is disabled
            self.assertIn("[x] Read this aloud", note.read_text(encoding="utf-8"))

    def test_revision_conflict_is_handled_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            self._write(note, "- [x] Read this aloud [tts:read]\nHello world.\n")

            with mock.patch("core.runtime_config.load_runtime_config", return_value={}), \
                 mock.patch(
                     "actions.jarvis_memory.atomic_write",
                     side_effect=RuntimeError("Revision conflict"),
                 ), mock.patch("threading.Thread") as thread_cls:
                triggered = trigger.check_tts_read_triggers([str(note)])

            self.assertEqual(triggered, [])
            thread_cls.assert_not_called()

    def test_missing_file_is_skipped_without_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            ghost = Path(tmp) / "ghost.md"
            with mock.patch("core.runtime_config.load_runtime_config", return_value={}):
                triggered = trigger.check_tts_read_triggers([str(ghost)])
            self.assertEqual(triggered, [])


if __name__ == "__main__":
    unittest.main()
