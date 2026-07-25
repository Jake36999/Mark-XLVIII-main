import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.chat_confirmation import describe_pending_action, is_affirmative_reply


class IsAffirmativeReplyTests(unittest.TestCase):
    def test_matches_plain_affirmatives(self):
        for text in ["yes", "Yes.", "yeah", "yep", "confirm", "confirmed", "go ahead",
                     "do it", "proceed", "sure", "ok", "okay", "affirmative", "correct",
                     "that's right", "please proceed", "please do"]:
            with self.subTest(text=text):
                self.assertTrue(is_affirmative_reply(text))

    def test_matches_with_sir(self):
        self.assertTrue(is_affirmative_reply("yes, sir"))
        self.assertTrue(is_affirmative_reply("sir, go ahead"))

    def test_rejects_qualified_affirmatives(self):
        for text in ["yes but also do the other thing", "yes and also delete everything",
                     "sure, but check with me first"]:
            with self.subTest(text=text):
                self.assertFalse(is_affirmative_reply(text))

    def test_rejects_negatives_and_unrelated_text(self):
        for text in ["no", "cancel", "", "   ", "what's the weather", "stop"]:
            with self.subTest(text=text):
                self.assertFalse(is_affirmative_reply(text))

    def test_case_insensitive(self):
        self.assertTrue(is_affirmative_reply("YES"))
        self.assertTrue(is_affirmative_reply("Go Ahead"))


class DescribePendingActionTests(unittest.TestCase):
    def test_includes_tool_name_and_permission_boundary(self):
        description = describe_pending_action(
            "file_controller",
            {"operation": "delete", "path": "x.txt"},
            {"effect": "destructive", "requires_approval": True, "operation": "delete"},
        )
        self.assertIn("file_controller", description)
        self.assertIn("delete", description)
        self.assertIn("confirmation", description.lower())

    def test_handles_unknown_tool_gracefully(self):
        description = describe_pending_action(
            "not_a_real_tool", {}, {"effect": "write", "requires_approval": True, "operation": ""}
        )
        self.assertIn("not_a_real_tool", description)
        self.assertTrue(description.strip())


if __name__ == "__main__":
    unittest.main()
