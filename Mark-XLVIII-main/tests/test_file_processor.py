import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from actions import file_processor as fp
from actions import document_workflow as dw


class FakeModel:
    def __init__(self, text="local analysis"):
        self.text = text
        self.prompts = []

    def generate_content(self, contents):
        self.prompts.append(contents)
        return SimpleNamespace(text=self.text)


class FileProcessorModelRoutingTests(unittest.TestCase):
    def test_there_is_no_gemini_path_left_to_take(self):
        """These tests used to patch `_get_api_key` to explode if it was ever
        read. It and `_gemini_client()` were deleted on 2026-07-30 -- the client
        had zero callers -- so the property is now structural rather than
        enforced by a mock that could quietly stop matching."""
        self.assertFalse(hasattr(fp, "_get_api_key"))
        self.assertFalse(hasattr(fp, "_gemini_client"))
        self.assertNotIn("genai", Path(fp.__file__).read_text(encoding="utf-8"))

    def test_text_summary_uses_model_router_without_gemini_key(self):
        model = FakeModel("local text summary")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("# Notes\n\nJARVIS uses local models for file analysis.", encoding="utf-8")

            with mock.patch("actions.file_processor.get_model_wrapper", return_value=model) as get_wrapper:
                result = fp.file_processor({"file_path": str(path), "action": "summarize", "save": False})

        self.assertEqual(result, "local text summary")
        get_wrapper.assert_called_once_with(role="worker", system=fp.ANALYSIS_SYSTEM_PROMPT)
        self.assertIn("Summarize this document", model.prompts[0])

    def test_json_analysis_uses_model_router_without_gemini_key(self):
        model = FakeModel("local json analysis")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            path.write_text('{"project": "mark", "memory": "vault-first"}', encoding="utf-8")

            with mock.patch("actions.file_processor.get_model_wrapper", return_value=model) as get_wrapper:
                result = fp.file_processor({"file_path": str(path), "action": "analyze", "save": False})

        self.assertEqual(result, "local json analysis")
        get_wrapper.assert_called_once_with(role="worker", system=fp.ANALYSIS_SYSTEM_PROMPT)
        self.assertIn("JSON data", model.prompts[0])

    def test_code_review_uses_model_router_without_gemini_key(self):
        model = FakeModel("local code review")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.py"
            path.write_text("print('hello')\n", encoding="utf-8")

            with mock.patch("actions.file_processor.get_model_wrapper", return_value=model) as get_wrapper:
                result = fp.file_processor({"file_path": str(path), "action": "review", "save": False})

        self.assertEqual(result, "local code review")
        get_wrapper.assert_called_once_with(role="worker", system=fp.ANALYSIS_SYSTEM_PROMPT)
        self.assertIn("Review this py code", model.prompts[0])

    def test_large_document_chunk_map_reduce_resumes_completed_maps(self):
        model = FakeModel("cited analysis")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.md"
            path.write_text(("Evidence paragraph with useful context. " * 400), encoding="utf-8")
            params = {"chunk_chars": 2000, "overlap_chars": 100, "save_to_vault": False, "resume": True}
            with mock.patch("actions.document_workflow.get_model_wrapper", return_value=model), \
                 mock.patch("actions.document_workflow._checkpoint_path", return_value=Path(tmp) / "job.json"):
                first = dw.analyze_path(path, instruction="Find the evidence.", params=params)
                first_call_count = len(model.prompts)
                second = dw.analyze_path(path, instruction="Find the evidence.", params=params)

        self.assertTrue(first["ok"])
        self.assertGreater(first["chunks"], 1)
        self.assertEqual(first["resumed_chunks"], 0)
        self.assertEqual(second["resumed_chunks"], second["chunks"])
        self.assertEqual(len(model.prompts), first_call_count + 1)

    def test_folder_analysis_is_recursive_and_bounded(self):
        model = FakeModel("folder synthesis")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            (root / "src").mkdir(parents=True)
            (root / "src" / "one.py").write_text("print('one')", encoding="utf-8")
            (root / "README.md").write_text("# Project", encoding="utf-8")
            with mock.patch("actions.document_workflow.get_model_wrapper", return_value=model), \
                 mock.patch("actions.document_workflow._checkpoint_path", return_value=Path(tmp) / "folder-job.json"):
                result = dw.analyze_path(root, params={"save_to_vault": False, "max_files": 10})

        self.assertTrue(result["ok"])
        self.assertEqual(result["files_considered"], 2)
        self.assertGreaterEqual(result["segments"], 2)


if __name__ == "__main__":
    unittest.main()
