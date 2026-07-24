import unittest

from core import approval_response as ar


def _body_with(section: str) -> str:
    return f"# Some Plan\n\nIntro text.\n\n{section}\n\n## Trailing Section\n\nMore text.\n"


class RenderTemplateTests(unittest.TestCase):
    def test_template_is_parseable_as_pending_when_untouched(self):
        body = _body_with(ar.render_approval_template())
        result = ar.parse_approval_response(body)
        self.assertEqual(result["decision"], "pending")
        self.assertEqual(result["checked_options"], [])


class ParseApprovalResponseTests(unittest.TestCase):
    def test_approve_checked(self):
        section = ar.render_approval_template().replace(
            "- [ ] **Approve**", "- [x] **Approve**"
        )
        result = ar.parse_approval_response(_body_with(section))
        self.assertEqual(result["decision"], "approve")

    def test_uppercase_x_is_accepted(self):
        section = ar.render_approval_template().replace(
            "- [ ] **Deny**", "- [X] **Deny**"
        )
        result = ar.parse_approval_response(_body_with(section))
        self.assertEqual(result["decision"], "deny")

    def test_correct_checked_with_correction_text(self):
        section = ar.render_approval_template().replace(
            "- [ ] **Correct**", "- [x] **Correct**"
        ).replace(
            "> [!note] Correction details (only read if **Correct** is checked)\n> Describe what should change.",
            "> [!note] Correction details (only read if **Correct** is checked)\n"
            "> Split the implementation node into two smaller steps.\n"
            "> Also add a research node for the token store.",
        )
        result = ar.parse_approval_response(_body_with(section))
        self.assertEqual(result["decision"], "correct")
        self.assertIn("Split the implementation node into two smaller steps.", result["correction"])
        self.assertIn("Also add a research node for the token store.", result["correction"])

    def test_deny_checked_with_reason(self):
        section = ar.render_approval_template().replace(
            "- [ ] **Deny**", "- [x] **Deny**"
        ).replace(
            "> [!note] Reason for denial (only read if **Deny** is checked)\n> Explain why this plan should not run.",
            "> [!note] Reason for denial (only read if **Deny** is checked)\n> This touches production credentials.",
        )
        result = ar.parse_approval_response(_body_with(section))
        self.assertEqual(result["decision"], "deny")
        self.assertIn("This touches production credentials.", result["denial_reason"])

    def test_multiple_checked_boxes_is_ambiguous_not_a_guess(self):
        section = (
            ar.render_approval_template()
            .replace("- [ ] **Approve**", "- [x] **Approve**")
            .replace("- [ ] **Deny**", "- [x] **Deny**")
        )
        result = ar.parse_approval_response(_body_with(section))
        self.assertEqual(result["decision"], "ambiguous")
        self.assertEqual(result["checked_options"], ["Approve", "Deny"])

    def test_missing_section_is_pending(self):
        result = ar.parse_approval_response("# No approval section here.\n\nJust prose.\n")
        self.assertEqual(result["decision"], "pending")

    def test_correction_text_from_a_different_option_is_not_bled_into_denial(self):
        section = ar.render_approval_template().replace(
            "- [ ] **Correct**", "- [x] **Correct**"
        ).replace(
            "> Describe what should change.", "> Add a verification node after implementation."
        )
        result = ar.parse_approval_response(_body_with(section))
        self.assertIn("Add a verification node after implementation.", result["correction"])
        self.assertNotIn("Add a verification node after implementation.", result["denial_reason"])
        self.assertEqual(result["denial_reason"], "Explain why this plan should not run.")


if __name__ == "__main__":
    unittest.main()
