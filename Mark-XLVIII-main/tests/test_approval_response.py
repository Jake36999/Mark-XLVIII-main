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


class ButtonDecisionTests(unittest.TestCase):
    """The Buttons community plugin cannot tick an existing checkbox -- in
    0.9.x `replace` means the button replacing itself, and text actions only
    prepend/append. So a click appends `Decision: <label>` and the parser
    treats that as equivalent evidence to a ticked box.

    The plugin is optional: the line is plain enough to type by hand, and a
    vault without Buttons keeps using the checkboxes unchanged.
    """

    def _clicked(self, *labels: str, section: str | None = None) -> str:
        """Append the lines a click writes, *inside* the approval section.

        Appending after `_body_with` would land the line beyond the trailing
        `##` header and outside the parsed section -- which is correct
        behaviour, just not what these cases are exercising.
        """
        recorded = "".join(f"\nDecision: {label}\n" for label in labels)
        return _body_with((section or ar.render_approval_template()) + recorded)

    def test_template_ships_a_button_per_option(self):
        template = ar.render_approval_template()
        self.assertEqual(template.count("```button"), 3)
        for label in ("Approve", "Correct", "Deny"):
            self.assertIn(f"action Decision: {label}", template)

    def test_the_buttons_own_action_lines_are_not_read_as_a_decision(self):
        """`action Decision: Approve` sits inside every rendered button block.
        A fresh, untouched template must still be pending -- the parser's
        anchored pattern is what prevents the template approving itself."""
        self.assertEqual(
            ar.parse_approval_response(_body_with(ar.render_approval_template()))["decision"],
            "pending",
        )

    def test_a_click_records_a_decision(self):
        for label, expected in [("Approve", "approve"), ("Correct", "correct"), ("Deny", "deny")]:
            with self.subTest(label=label):
                result = ar.parse_approval_response(self._clicked(label))
                self.assertEqual(result["decision"], expected)
                self.assertEqual(result["clicked_options"], [label])

    def test_double_clicking_the_same_button_is_still_one_decision(self):
        body = self._clicked("Approve", "Approve")
        self.assertEqual(ar.parse_approval_response(body)["decision"], "approve")

    def test_two_different_buttons_are_ambiguous(self):
        body = self._clicked("Approve", "Deny")
        self.assertEqual(ar.parse_approval_response(body)["decision"], "ambiguous")

    def test_a_decision_recorded_outside_the_section_is_ignored(self):
        """Scoping matters: only lines inside the Approval Decision section
        count, so stray text elsewhere in a plan note cannot approve it."""
        body = _body_with(ar.render_approval_template()) + "\nDecision: Approve\n"
        self.assertEqual(ar.parse_approval_response(body)["decision"], "pending")

    def test_a_click_agreeing_with_a_ticked_box_is_honoured(self):
        section = ar.render_approval_template().replace("- [ ] **Approve**", "- [x] **Approve**")
        self.assertEqual(
            ar.parse_approval_response(self._clicked("Approve", section=section))["decision"], "approve"
        )

    def test_a_click_contradicting_a_ticked_box_fails_closed(self):
        section = ar.render_approval_template().replace("- [ ] **Approve**", "- [x] **Approve**")
        self.assertEqual(
            ar.parse_approval_response(self._clicked("Deny", section=section))["decision"], "ambiguous"
        )

    def test_a_hand_typed_line_works_without_the_plugin(self):
        self.assertEqual(ar.parse_approval_response(self._clicked("approve"))["decision"], "approve")

    def test_prose_mentioning_a_decision_is_not_a_decision(self):
        body = _body_with(ar.render_approval_template() + "\nI think Decision approve is right, maybe.\n")
        self.assertEqual(ar.parse_approval_response(body)["decision"], "pending")


if __name__ == "__main__":
    unittest.main()
