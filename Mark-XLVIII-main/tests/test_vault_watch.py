import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
