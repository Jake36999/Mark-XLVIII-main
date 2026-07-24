import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import jarvis_memory as memory
from actions.vault_watch import VaultWatcher


class VaultWatcherTests(unittest.TestCase):
    def test_scan_once_updates_incremental_index_without_starting_observer(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = memory.resolve_config({
                "jarvis_notes_root": tmp,
                "remember_enabled": False,
                "rag_embedding_provider": "disabled",
            })
            memory.create_note(note_type="memory", title="Watched", content="change", cfg=cfg, sync=False)
            watcher = VaultWatcher(cfg)

            result = watcher.scan_once()

            self.assertTrue(result["ok"])
            self.assertEqual(result["reindex"]["indexed_notes"], 1)
            self.assertFalse(watcher.status()["running"])

    def test_scan_once_checks_tts_read_triggers_on_non_startup_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = memory.resolve_config({
                "jarvis_notes_root": tmp,
                "remember_enabled": False,
                "rag_embedding_provider": "disabled",
            })
            note_path = memory.create_note(
                note_type="memory", title="Read Aloud Me", content="change", cfg=cfg, sync=False
            )["path"]
            watcher = VaultWatcher(cfg)
            watcher._startup_pending = False
            watcher.mark_event("modified", src_path=note_path)

            with mock.patch("actions.tts_read_trigger.check_tts_read_triggers", return_value=[]) as checker:
                result = watcher.scan_once()

            self.assertTrue(result["ok"])
            checker.assert_called_once()
            (called_paths,), _kwargs = checker.call_args
            self.assertIn(note_path, called_paths)

    def test_scan_once_skips_tts_read_triggers_on_startup_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = memory.resolve_config({
                "jarvis_notes_root": tmp,
                "remember_enabled": False,
                "rag_embedding_provider": "disabled",
            })
            memory.create_note(note_type="memory", title="Watched", content="change", cfg=cfg, sync=False)
            watcher = VaultWatcher(cfg)
            watcher._startup_pending = True

            with mock.patch("actions.tts_read_trigger.check_tts_read_triggers") as checker:
                result = watcher.scan_once()

            self.assertTrue(result["ok"])
            checker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
