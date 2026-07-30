"""Every declared capability must actually be reachable.

A capability is declared in up to four places, and they have to agree:

  `main.TOOL_DECLARATIONS`   what the model is told it can call
  `main._execute_tool`       what can actually be dispatched from chat
  `CAPABILITY_POLICY`        risk level, confirmation, permission boundary
  `core/tool_dispatcher`     what the MCP path can reach

A name present in one and missing from another is a broken join, and a broken
join is invisible: the model is told the tool exists, calls it, and gets
"Unknown tool" back as if it had asked for something imaginary.

This is not hypothetical. `canvas_plan` -- Canvas Mode 2, the reasoning-backed
planning engine with its own handbook note and 160 tests -- was declared with a
full description of propose/evaluate_approval/execute, wired for MCP, and had
**no branch in `_execute_tool`**. Every call from chat fell through to
"Unknown tool: canvas_plan" from the day it was added until 2026-07-30.

It hid because the visible half still worked: `_redirect_dev_agent_to_canvas`
calls decompose and propose directly, so a canvas and an approval note still
appeared. What could not run was everything *after* the human decides. The
engine could produce plans and never execute one.
"""
import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
from actions.capability_registry import CAPABILITY_POLICY


def _dispatchable_tool_names() -> set[str]:
    """Names `_execute_tool` compares against, read from the AST.

    Deliberately structural rather than calling the tools: invoking them to find
    out whether they dispatch would run real side effects.
    """
    tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    execute_tool = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_execute_tool"
    )
    names: set[str] = set()
    for node in ast.walk(execute_tool):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "name":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    names.add(comparator.value)
                elif isinstance(comparator, (ast.Tuple, ast.List, ast.Set)):
                    names.update(
                        elt.value for elt in comparator.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    )
    return names


class DeclaredToolsAreReachableTests(unittest.TestCase):
    def test_every_declared_tool_can_be_dispatched(self):
        declared = {tool["name"] for tool in main.TOOL_DECLARATIONS}
        undispatchable = sorted(declared - _dispatchable_tool_names())
        self.assertEqual(
            undispatchable, [],
            "these tools are offered to the model but `_execute_tool` has no branch for them, "
            f"so every call returns 'Unknown tool': {undispatchable}",
        )

    def test_every_declared_tool_is_governed(self):
        """A tool with no policy entry has no risk level, no confirmation
        requirement and no permission boundary."""
        declared = {tool["name"] for tool in main.TOOL_DECLARATIONS}
        ungoverned = sorted(declared - set(CAPABILITY_POLICY))
        self.assertEqual(ungoverned, [], f"declared but absent from CAPABILITY_POLICY: {ungoverned}")

    def test_no_dispatch_branch_exists_for_a_tool_nobody_declared(self):
        """The reverse leak: reachable only if something other than the model
        names it, which means it is not covered by the declaration review."""
        declared = {tool["name"] for tool in main.TOOL_DECLARATIONS}
        orphans = sorted(_dispatchable_tool_names() - declared - {"close_camera"})
        self.assertEqual(orphans, [], f"dispatchable but never declared: {orphans}")

    def test_registry_help_entries_are_either_tools_or_known_non_tools(self):
        """`CAPABILITY_HELP` is what JARVIS describes when asked what it can do.
        Two entries are legitimately not callable -- `speech` happens as part of
        every spoken turn, `operational_ui` is keyboard-driven -- but anything
        else described and not dispatchable is a promise the user cannot cash.

        Found live: the User Guide listed `speech` in its tool table with a risk
        level, so asking for it returned "Unknown tool: speech"."""
        from actions.capability_registry import CAPABILITY_HELP

        NOT_CALLABLE = {"speech", "operational_ui"}
        declared = {tool["name"] for tool in main.TOOL_DECLARATIONS}
        undeliverable = sorted(set(CAPABILITY_HELP) - declared - NOT_CALLABLE)
        self.assertEqual(
            undeliverable, [],
            f"described in the capability registry but not callable: {undeliverable}",
        )

    def test_the_known_non_tools_really_are_absent_from_the_tool_list(self):
        """Guards the exception itself: if `speech` ever becomes a real tool,
        this fails and the allowance above must be removed rather than left to
        silently excuse a live tool."""
        declared = {tool["name"] for tool in main.TOOL_DECLARATIONS}
        for name in ("speech", "operational_ui"):
            with self.subTest(name=name):
                self.assertNotIn(name, declared)

    def test_governed_names_are_either_declared_tools_or_ui_capabilities(self):
        """`CAPABILITY_POLICY` also covers things the user operates directly --
        `operational_ui` is the Ctrl+K palette and the Process Trace panel, which
        the registry describes but the model cannot call. Those are legitimate;
        anything else in policy and not declared is a gap."""
        UI_ONLY = {"operational_ui"}
        declared = {tool["name"] for tool in main.TOOL_DECLARATIONS}
        unexplained = sorted(set(CAPABILITY_POLICY) - declared - UI_ONLY)
        self.assertEqual(
            unexplained, [],
            "in CAPABILITY_POLICY but neither a declared tool nor a known UI capability: "
            f"{unexplained}",
        )


class ChatAndMcpAgreeTests(unittest.TestCase):
    """Both entry points must reach the same set of tools. `canvas_plan` was
    wired for MCP and missing from chat; the earlier `dev_agent` confirmation
    gate had the same shape. A tool reachable from one path only is a tool whose
    behaviour depends on how it was invoked."""

    def test_every_mcp_reachable_tool_is_also_reachable_from_chat(self):
        from core.tool_dispatcher import HEADLESS_TOOLS

        missing = sorted(set(HEADLESS_TOOLS) - _dispatchable_tool_names())
        self.assertEqual(
            missing, [],
            f"reachable over MCP but not from chat: {missing}",
        )


class DocumentedTriggerPhrasesReachTheirHandlerTests(unittest.TestCase):
    """The Command Palette promises specific phrases. A promise the predicate
    does not accept is a capability the user cannot reach the documented way."""

    def test_the_documented_create_plan_phrasing_is_accepted(self):
        """Documented as "create plan...", but the predicate required
        "create plan:" or "create a plan to/for", so the documented form fell
        through to model routing."""
        for phrase in (
            "create plan to ship the caching layer",
            "create plan: ship the caching layer",
            "create a plan to ship the caching layer",
            "make a plan for the caching layer",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(main._is_create_plan_prompt(phrase))

    def test_talking_about_planning_does_not_start_a_plan(self):
        """Anchored at the start on purpose. This session fixed several
        substring collisions ("repo" inside weather_report, "ram" inside
        program), so a mid-sentence match is not acceptable here."""
        for phrase in (
            "what does the create plan workflow do",
            "tell me about create plan",
            "recreate plan output",
        ):
            with self.subTest(phrase=phrase):
                self.assertFalse(main._is_create_plan_prompt(phrase))

    def test_the_other_documented_workflow_triggers_still_match(self):
        checks = [
            (main._is_start_plan_prompt, "start plan"),
            (main._is_cancel_planning_prompt, "cancel planning"),
            (main._is_revise_plan_prompt, "revise the plan"),
            (main._is_learn_topic_prompt, "learn about wifi sensing"),
            (main._is_learn_project_prompt, "learn this project"),
            (main._is_todo_template_prompt, "create a blank to-do list template"),
            (main._is_current_news_report_prompt, "today's AI news report"),
            (main._is_capability_overview_prompt, "what tools do you have available"),
        ]
        for predicate, phrase in checks:
            with self.subTest(phrase=phrase):
                self.assertTrue(predicate(phrase), f"{predicate.__name__} no longer matches its documented phrase")


class CanvasModeTwoIsReachableTests(unittest.TestCase):
    """Named explicitly rather than left to the category test, because the whole
    approval half of Mode 2 was unreachable and nothing noticed."""

    def test_canvas_plan_is_dispatchable(self):
        self.assertIn("canvas_plan", _dispatchable_tool_names())

    def test_the_operations_after_a_human_decides_are_the_ones_that_were_lost(self):
        """propose worked via the dev_agent redirect. evaluate_approval,
        verify_approval and execute did not exist from chat at all."""
        from actions import canvas_plan

        for operation in ("evaluate_approval", "verify_approval", "execute"):
            with self.subTest(operation=operation):
                self.assertTrue(hasattr(canvas_plan, "canvas_plan"))
                declaration = next(t for t in main.TOOL_DECLARATIONS if t["name"] == "canvas_plan")
                self.assertIn(operation, str(declaration["parameters"]))


if __name__ == "__main__":
    unittest.main()
