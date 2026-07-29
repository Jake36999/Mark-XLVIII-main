"""Phase 2 file pipeline.

Reported failure: a PDF was uploaded, the user asked to "extract the methods",
and JARVIS answered with the methods used to orchestrate its own backend.
Three independent causes, each pinned below.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
from core.tool_dispatcher import classify_effect


def _jarvis():
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.ui = mock.Mock()
    jarvis.ui.muted = False
    jarvis.ui.current_file = None
    jarvis.speak = mock.Mock()
    jarvis._pending_plan_run_id = ""
    jarvis._active_plan_run_id = ""
    jarvis._pending_tool_confirmation = None
    jarvis._active_upload = None
    jarvis._phone_active = False
    return jarvis


class RouterKeywordCollisionTests(unittest.TestCase):
    """Same family as the already-fixed "repo" matching inside
    "weather_report": bare single words were matched as substrings."""

    def test_ram_does_not_match_inside_other_words(self):
        self.assertTrue(main._rule_token_matches("ram", "how much ram is free"))
        for text in ("show me the program diagram", "the framework parameters"):
            with self.subTest(text=text):
                self.assertFalse(main._rule_token_matches("ram", text))

    def test_read_does_not_match_inside_other_words(self):
        self.assertTrue(main._rule_token_matches("read", "read the config"))
        for text in ("what have you already done", "spawn a thread"):
            with self.subTest(text=text):
                self.assertFalse(main._rule_token_matches("read", text))

    def test_multiword_phrases_still_match_as_substrings(self):
        self.assertTrue(main._rule_token_matches("deep research", "run a deep research pass"))

    def test_dot_prefixed_extensions_still_match(self):
        self.assertTrue(main._rule_token_matches(".json", "open data.json"))


class FileQuestionRoutingTests(unittest.TestCase):
    def test_the_reported_prompt_no_longer_reaches_capability_registry(self):
        """capability_registry's manifest literally lists the backend
        orchestration methods, so routing a document question there is what
        produced the wrong answer."""
        names = main._router_tool_names_for_text("can you extract the methods from this pdf")
        self.assertIn("file_processor", names)
        self.assertNotIn("capability_registry", names)

    def test_phrasings_without_a_format_word_still_route_to_the_file_tool(self):
        for text in ("extract the methods", "what are the methods in this paper"):
            with self.subTest(text=text):
                self.assertIn("file_processor", main._router_tool_names_for_text(text))

    def test_an_active_upload_biases_a_bare_request_to_the_file(self):
        self.assertIn("file_processor", main._router_tool_names_for_text("summarise this", has_upload=True))

    def test_capability_questions_are_unaffected(self):
        names = main._router_tool_names_for_text("what tools or workflows do you have available")
        self.assertEqual(names, ["capability_registry"])

    def test_the_model_is_never_handed_an_empty_tool_list(self):
        """tools=[] leaves the model unable to act, so it answers from the
        system prompt -- which mostly describes JARVIS's own tooling."""
        for text in ("xyzzy", "", "asdfgh qwerty", "????"):
            with self.subTest(text=text):
                self.assertTrue(main._router_tool_names_for_text(text))
                self.assertTrue(main._router_tool_schema(text))


class UploadContinuityTests(unittest.TestCase):
    """Router turns are stateless, so the uploaded path used to die with the
    announcement turn -- the turn that actually asked about the file had no
    idea a file existed."""

    ANNOUNCE = "[FILE_UPLOADED] path=C:/tmp/paper.pdf | name=paper.pdf | type=pdf | size=1.1 KB | tell the user"

    def test_announcement_is_remembered(self):
        jarvis = _jarvis()
        jarvis._record_upload_announcement(self.ANNOUNCE)
        self.assertEqual(jarvis._active_upload["name"], "paper.pdf")
        self.assertEqual(jarvis._active_upload_path(), "C:/tmp/paper.pdf")

    def test_context_note_names_the_file_without_leaking_contents(self):
        jarvis = _jarvis()
        jarvis._record_upload_announcement(self.ANNOUNCE)
        note = jarvis._upload_context_note()
        self.assertIn("paper.pdf", note)
        self.assertIn("C:/tmp/paper.pdf", note)

    def test_no_upload_means_no_note(self):
        self.assertEqual(_jarvis()._upload_context_note(), "")

    def test_missing_path_is_backfilled_for_file_tools(self):
        jarvis = _jarvis()
        jarvis._record_upload_announcement(self.ANNOUNCE)
        resolved = jarvis._with_upload_path("file_processor", {"action": "extract_text"})
        self.assertEqual(resolved["file_path"], "C:/tmp/paper.pdf")

    def test_an_explicit_path_is_never_overridden(self):
        jarvis = _jarvis()
        jarvis._record_upload_announcement(self.ANNOUNCE)
        resolved = jarvis._with_upload_path("file_processor", {"file_path": "C:/other.pdf"})
        self.assertEqual(resolved["file_path"], "C:/other.pdf")

    def test_unrelated_tools_are_untouched(self):
        jarvis = _jarvis()
        jarvis._record_upload_announcement(self.ANNOUNCE)
        self.assertEqual(jarvis._with_upload_path("web_search", {"query": "x"}), {"query": "x"})


class FileProcessorClassificationTests(unittest.TestCase):
    """The gate must describe what the tool really does, and must not demand a
    confirmation for reading a file the user just handed over."""

    def test_omitted_action_is_read_not_a_generic_write(self):
        decision = classify_effect("file_processor", {"action": "", "file_path": "/x.pdf"})
        self.assertEqual(decision["effect"], "read")
        self.assertFalse(decision["requires_approval"])

    def test_summarize_and_analyze_are_read_when_not_saving(self):
        for action in ("summarize", "analyze"):
            with self.subTest(action=action):
                decision = classify_effect("file_processor", {"action": action, "file_path": "/x.pdf"})
                self.assertFalse(decision["requires_approval"])

    def test_explicitly_saving_requires_approval(self):
        decision = classify_effect("file_processor", {"action": "summarize", "file_path": "/x.pdf", "save": True})
        self.assertTrue(decision["requires_approval"])

    def test_folder_analysis_still_requires_approval(self):
        decision = classify_effect("file_processor", {"action": "analyze_folder", "file_path": "/dir"})
        self.assertTrue(decision["requires_approval"])


class FileProcessorInstructionTests(unittest.TestCase):
    def test_unrecognised_action_still_sends_a_real_instruction(self):
        """`instruction = action` ran *after* action was reassigned to
        "custom", and prompt_map had already been built from the original
        (empty) instruction -- so the model got raw file content with no
        instruction at all and free-associated. A direct fabrication vector."""
        import tempfile

        from actions import file_processor as fp

        captured = {}

        class _Model:
            def generate_content(self, prompt):
                captured["prompt"] = prompt
                return mock.Mock(text="ok")

        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "doc.txt"
            doc.write_text("SECRET_CONTENT", encoding="utf-8")
            with mock.patch.object(fp, "_analysis_client", return_value=_Model()):
                fp._process_text_doc(doc, "txt", "extract_the_methods", {"instruction": ""})
        prompt = captured["prompt"]
        self.assertIn("SECRET_CONTENT", prompt)
        self.assertNotEqual(prompt.strip(), "SECRET_CONTENT")
        self.assertIn("extract_the_methods", prompt)
        self.assertIn("do not invent", prompt.lower())


class ExtractReturnsContentTests(unittest.TestCase):
    def test_bounded_extract_returns_short_text_verbatim(self):
        from actions import file_processor as fp

        self.assertEqual(fp._bounded_extract("hello"), "hello")

    def test_bounded_extract_truncates_and_says_so(self):
        from actions import file_processor as fp

        out = fp._bounded_extract("x" * 50_000)
        self.assertLess(len(out), 50_000)
        self.assertIn("truncated", out)


if __name__ == "__main__":
    unittest.main()
