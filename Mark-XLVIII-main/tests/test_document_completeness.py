import tempfile
import unittest
from pathlib import Path

from core.document_completeness import check_document_completeness


class CheckDocumentCompletenessTests(unittest.TestCase):
    def test_ok_when_most_topics_are_covered(self):
        requirements = (
            "The script's overall purpose.\n"
            "Detailed entries for each function and class.\n"
            "The real dependency graph between components."
        )
        content = (
            "# Specification\n\n"
            "## Purpose\nThis script packages notebooks for distribution.\n\n"
            "## Functions and classes\nEach function and class is documented below with signatures.\n\n"
            "## Dependency graph\nThe dependency graph between components is shown here.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "spec.md"
            note.write_text(content, encoding="utf-8")
            result = check_document_completeness(str(note), requirements)

        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["topics"]), 3)
        self.assertTrue(all(t["covered"] for t in result["topics"]))

    def test_not_ok_when_most_topics_are_missing(self):
        requirements = (
            "The script's overall purpose.\n"
            "Detailed entries for each function and class.\n"
            "The real dependency graph between components.\n"
            "Any inferred assumptions or edge cases."
        )
        content = "# Notes\n\nThis is a short placeholder note with nothing substantive in it.\n"
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "spec.md"
            note.write_text(content, encoding="utf-8")
            result = check_document_completeness(str(note), requirements)

        self.assertFalse(result["ok"], result)
        self.assertIn("Missing or thin", result["summary"])

    def test_one_weak_topic_does_not_sink_an_otherwise_complete_document(self):
        # pass_ratio (70%) means one under-covered topic among several
        # strong ones must not fail the whole document -- a stray filler
        # sentence in raw prose requirements shouldn't be an unmeetable bar.
        requirements = (
            "The script's overall purpose.\n"
            "Detailed entries for each function and class.\n"
            "The real dependency graph between components.\n"
            "Any other relevant zzznonexistentqqq topic."
        )
        content = (
            "This script's overall purpose is packaging.\n"
            "Detailed entries for each function and class follow below.\n"
            "The real dependency graph between components is included.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "spec.md"
            note.write_text(content, encoding="utf-8")
            result = check_document_completeness(str(note), requirements)

        self.assertTrue(result["ok"], result)
        covered = [t for t in result["topics"] if t["covered"]]
        self.assertEqual(len(covered), 3)

    def test_returns_an_error_for_an_unreadable_file(self):
        missing = str(Path(tempfile.gettempdir()) / "definitely_missing_spec_xyz.md")
        result = check_document_completeness(missing, "The script's overall purpose.")
        self.assertFalse(result["ok"])
        self.assertIn("Could not read", result["error"])

    def test_no_structured_requirements_falls_back_to_non_empty_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "spec.md"
            note.write_text("Some content here.", encoding="utf-8")
            ok_result = check_document_completeness(str(note), "")

            empty_note = Path(tmp) / "empty.md"
            empty_note.write_text("", encoding="utf-8")
            empty_result = check_document_completeness(str(empty_note), "")

        self.assertTrue(ok_result["ok"])
        self.assertFalse(empty_result["ok"])


if __name__ == "__main__":
    unittest.main()
