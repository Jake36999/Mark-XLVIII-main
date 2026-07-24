from datetime import datetime
import unittest

from jarvis_ui_components.models import CommandAction, NoteItem, coerce_many


class ModelTests(unittest.TestCase):
    def test_mapping_ignores_unknown_fields(self) -> None:
        note = NoteItem.from_mapping(
            {
                "id": "one",
                "title": "One",
                "updated": "2026-07-22T10:00:00",
                "unknown_backend_field": True,
            }
        )
        self.assertEqual(note.id, "one")
        self.assertEqual(note.updated_at(), datetime(2026, 7, 22, 10, 0, 0))

    def test_coerce_many_accepts_models_and_mappings(self) -> None:
        existing = NoteItem("one", "One")
        values = coerce_many(NoteItem, [existing, {"id": "two", "title": "Two"}])
        self.assertEqual([item.id for item in values], ["one", "two"])

    def test_command_search_text_includes_keywords(self) -> None:
        action = CommandAction(
            "vault.search",
            "Search memory",
            "Hybrid vault lookup",
            "Knowledge",
            ["rag", "notes"],
        )
        text = action.searchable_text()
        self.assertIn("hybrid", text)
        self.assertIn("rag", text)


if __name__ == "__main__":
    unittest.main()
