import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import canvas_plan
from actions import jarvis_canvas as canvas
from actions.dual_orchestrator import DIALECT, validate_workflow


def _node(node_id: str, text: str, *, role: str = "", x: int = 0, y: int = 0) -> dict:
    node = {"id": node_id, "type": "text", "text": text, "x": x, "y": y, "width": 400, "height": 180}
    if role:
        node["jarvisRole"] = role
    return node


def _edge(edge_id: str, src: str, dst: str) -> dict:
    return {"id": edge_id, "fromNode": src, "toNode": dst, "fromSide": "right", "toSide": "left"}


class CompileCanvasTests(unittest.TestCase):
    def test_linear_chain_compiles_to_ordered_dependent_steps(self):
        payload = {
            "nodes": [
                _node("a", "role: research\nInvestigate the auth module.", role="research"),
                _node("b", "Run the test suite.", role="verification"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="demo_plan", name="Demo Plan")

        self.assertEqual(workflow["schema_version"], DIALECT)
        step_ids = [step["step_id"] for step in workflow["steps"]]
        self.assertEqual(len(step_ids), 2)
        # b depends on a
        by_id = {step["step_id"]: step for step in workflow["steps"]}
        b_step = next(s for s in workflow["steps"] if "verification" in s["step_type"] or s["step_type"] == "command")
        # the research node is upstream of the verification node
        research_id = next(sid for sid, s in by_id.items() if s["step_type"] == "model_reasoning")
        self.assertIn(research_id, b_step["depends_on"])

    def test_compiled_workflow_passes_orchestrator_validation(self):
        payload = {
            "nodes": [
                _node("root", "The goal.", role="plan"),
                _node("r", "Research the options.", role="research"),
                _node("impl", "Apply the change.", role="implementation"),
                _node("rev", "Review the diff.", role="review"),
                _node("ver", "Run pytest.", role="verification"),
            ],
            "edges": [
                _edge("e1", "root", "r"),
                _edge("e2", "r", "impl"),
                _edge("e3", "impl", "rev"),
                _edge("e4", "rev", "ver"),
            ],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="full_plan", name="Full Plan")
        # must survive the real schema + semantic validator unchanged
        validated = validate_workflow(workflow)
        self.assertEqual(len(validated["steps"]), 5)

    def test_branch_and_merge_dependencies(self):
        # a -> b, a -> c, b -> d, c -> d  (diamond)
        payload = {
            "nodes": [
                _node("a", "Scope.", role="research"),
                _node("b", "Branch one.", role="research"),
                _node("c", "Branch two.", role="research"),
                _node("d", "Merge findings.", role="review"),
            ],
            "edges": [
                _edge("e1", "a", "b"),
                _edge("e2", "a", "c"),
                _edge("e3", "b", "d"),
                _edge("e4", "c", "d"),
            ],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="diamond", name="Diamond")
        by_id = {step["step_id"]: step for step in workflow["steps"]}
        d_step = by_id[canvas_plan.node_step_id("d")]
        self.assertEqual(
            sorted(d_step["depends_on"]),
            sorted([canvas_plan.node_step_id("b"), canvas_plan.node_step_id("c")]),
        )

    def test_review_step_evidence_is_bound_to_upstream_results(self):
        # T5: a review node must critique its upstream's real output, not
        # dispatch with only the human's review instruction and no evidence.
        payload = {
            "nodes": [
                _node("r", "Research.", role="research"),
                _node("rev", "Review the findings.", role="review"),
            ],
            "edges": [_edge("e1", "r", "rev")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="revcheck", name="RevCheck")
        rev_step = next(s for s in workflow["steps"] if s["step_type"] == "review")
        r_step_id = canvas_plan.node_step_id("r")
        self.assertEqual(
            rev_step["inputs"]["evidence"],
            [{"bind": {"from_step": r_step_id, "path": "result.summary"}}],
        )

    def test_review_step_with_no_upstream_gets_no_evidence_binding(self):
        payload = {"nodes": [_node("rev", "Review something.", role="review")], "edges": []}
        workflow = canvas_plan.compile_canvas(payload, workflow_id="lonely_review", name="Lonely")
        rev_step = workflow["steps"][0]
        self.assertNotIn("evidence", rev_step["inputs"])

    def test_cycle_is_refused_with_visible_diagnostic(self):
        payload = {
            "nodes": [
                _node("a", "A", role="research"),
                _node("b", "B", role="research"),
            ],
            "edges": [_edge("e1", "a", "b"), _edge("e2", "b", "a")],
        }
        with self.assertRaises(canvas_plan.CanvasCompileError) as ctx:
            canvas_plan.compile_canvas(payload, workflow_id="cyclic", name="Cyclic")
        self.assertIn("cycle", str(ctx.exception).lower())

    def test_implementation_node_runs_in_openclaw_resource_class_and_is_gated(self):
        from actions.dual_orchestrator import _resource_class

        payload = {
            "nodes": [_node("impl", "Write the file.", role="implementation")],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="impl_only", name="Impl")
        step = workflow["steps"][0]
        # must land in the sandboxed OpenClaw resource class, not a bare command
        self.assertEqual(_resource_class(step), "openclaw")
        self.assertEqual(step["target"], "project_operator")
        self.assertEqual(step["inputs"].get("operation"), "delegate_openclaw")
        self.assertTrue(step.get("requires_confirmation"))
        self.assertIn(step["side_effects"], {"external_write", "local_write", "destructive"})
        self.assertIn(step["risk_tier"], {"T3", "T4", "T5"})

    def test_preview_plan_builds_review_manifest_and_flags_side_effects(self):
        payload = {
            "nodes": [
                _node("r", "Research.", role="research"),
                _node("impl", "Apply change.", role="implementation"),
                _node("ver", "Run tests.", role="verification"),
            ],
            "edges": [_edge("e1", "r", "impl"), _edge("e2", "impl", "ver")],
        }
        preview = canvas_plan.preview_plan(payload, workflow_id="prev", name="Prev")

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["step_count"], 3)
        # research precedes implementation precedes verification
        self.assertEqual(
            preview["order"],
            [canvas_plan.node_step_id("r"), canvas_plan.node_step_id("impl"), canvas_plan.node_step_id("ver")],
        )
        # the OpenClaw implementation step is surfaced as side-effecting for review
        flagged = {row["step_id"] for row in preview["side_effecting"]}
        self.assertIn(canvas_plan.node_step_id("impl"), flagged)
        impl_row = next(r for r in preview["side_effecting"] if r["step_id"] == canvas_plan.node_step_id("impl"))
        self.assertEqual(impl_row["resource_class"], "openclaw")
        self.assertTrue(impl_row["requires_confirmation"])

    def test_absent_role_defaults_to_least_privileged_research(self):
        # A node with no declared role must NEVER become a side-effectful step.
        payload = {"nodes": [{"id": "x", "type": "text", "text": "do a thing", "x": 0, "y": 0, "width": 400, "height": 180}], "edges": []}
        workflow = canvas_plan.compile_canvas(payload, workflow_id="bare", name="Bare")
        step = workflow["steps"][0]
        self.assertEqual(step["step_type"], "model_reasoning")
        self.assertEqual(step["side_effects"], "none")
        self.assertFalse(step.get("requires_confirmation", False))

    def test_role_parsed_from_text_directive_when_no_property(self):
        payload = {
            "nodes": [{"id": "n", "type": "text", "text": "type: verification\nrun the checks", "x": 0, "y": 0, "width": 400, "height": 180}],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="fromtext", name="FromText")
        self.assertEqual(workflow["steps"][0]["step_type"], "command")

    def test_instruction_text_strips_the_role_directive_line(self):
        payload = {"nodes": [_node("a", "role: research\nActual instruction body.", role="research")], "edges": []}
        workflow = canvas_plan.compile_canvas(payload, workflow_id="strip", name="Strip")
        desc = workflow["steps"][0]["description"]
        self.assertIn("Actual instruction body.", desc)
        self.assertNotIn("role: research", desc)

    def test_empty_canvas_is_refused(self):
        with self.assertRaises(canvas_plan.CanvasCompileError):
            canvas_plan.compile_canvas({"nodes": [], "edges": []}, workflow_id="empty", name="Empty")


class NoteRoleAndBranchCompileTests(unittest.TestCase):
    """WS4c: pass-forward notes are canvas-only, never a compiled step, and a
    real step's depends_on resolves through them to the real upstream node."""

    def test_note_is_excluded_and_downstream_depends_on_resolves_through_it(self):
        payload = {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("n", "role: note\nTask C completed, runtime shape changed.", role="note"),
                _node("r", "role: review\nReconsider the plan.", role="review"),
            ],
            "edges": [_edge("e1", "a", "n"), _edge("e2", "n", "r")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="notes", name="Notes")

        step_ids = {step["step_id"] for step in workflow["steps"]}
        self.assertEqual(len(workflow["steps"]), 2)  # the note never becomes a step
        self.assertNotIn(canvas_plan.node_step_id("n"), step_ids)

        review_step = next(s for s in workflow["steps"] if s["step_type"] == "review")
        research_step_id = canvas_plan.node_step_id("a")
        self.assertEqual(review_step["depends_on"], [research_step_id])

        # the compiled workflow must still pass the real orchestrator validator
        validate_workflow(workflow)

    def test_note_chain_resolves_through_multiple_notes(self):
        payload = {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("n1", "role: note\nFirst fact.", role="note"),
                _node("n2", "role: note\nSecond fact, derived from the first.", role="note"),
                _node("r", "role: review\nReconsider.", role="review"),
            ],
            "edges": [_edge("e1", "a", "n1"), _edge("e2", "n1", "n2"), _edge("e3", "n2", "r")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="notechain", name="NoteChain")

        self.assertEqual(len(workflow["steps"]), 2)
        review_step = next(s for s in workflow["steps"] if s["step_type"] == "review")
        self.assertEqual(review_step["depends_on"], [canvas_plan.node_step_id("a")])

    def test_note_with_no_downstream_consumer_still_compiles(self):
        payload = {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("n", "role: note\nAn observation nobody reacts to.", role="note"),
            ],
            "edges": [_edge("e1", "a", "n")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="danglingnote", name="DanglingNote")
        self.assertEqual(len(workflow["steps"]), 1)
        validate_workflow(workflow)

    def test_note_role_resolves_from_hashtag_and_alias(self):
        payload = {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                {"id": "n", "type": "text", "text": "#note\nAn aside.", "x": 0, "y": 0, "width": 400, "height": 180},
                _node("b", "role: annotation\nAlso an aside.", role="annotation"),
            ],
            "edges": [_edge("e1", "a", "n"), _edge("e2", "n", "b")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="notealias", name="NoteAlias")
        # both "n" (hashtag) and "b" (alias) resolve to role "note" -- neither compiles
        self.assertEqual(len(workflow["steps"]), 1)

    def test_workflow_role_compiles_identically_to_plan(self):
        # 2026-07-25 terminology workflow: "workflow" is the preferred spelling
        # for the canvas anchor, aliased onto the exact same "plan" role/step.
        payload = {
            "nodes": [
                _node("root", "role: workflow\nShip the thing.", role="workflow"),
                _node("a", "role: research\nInvestigate.", role="research"),
            ],
            "edges": [_edge("e1", "root", "a")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="workflowalias", name="WorkflowAlias")
        anchor_steps = [s for s in workflow["steps"] if s["step_type"] == "gate" and s["target"] == "plan_milestone"]
        self.assertEqual(len(anchor_steps), 1)

    def test_mode_directive_on_the_anchor_node_reaches_workflow_variables(self):
        payload = {
            "nodes": [
                _node("root", "role: workflow\nmode: development\nShip the thing.", role="workflow"),
                _node("a", "role: research\nInvestigate.", role="research"),
            ],
            "edges": [_edge("e1", "root", "a")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="modetest", name="ModeTest")
        self.assertEqual(workflow["variables"]["mode"], "development")

    def test_missing_mode_directive_leaves_variables_unchanged(self):
        payload = {
            "nodes": [
                _node("root", "role: workflow\nShip the thing.", role="workflow"),
                _node("a", "role: research\nInvestigate.", role="research"),
            ],
            "edges": [_edge("e1", "root", "a")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="nomode", name="NoMode")
        self.assertNotIn("mode", workflow["variables"])


class DecomposeValidationBranchTests(unittest.TestCase):
    """WS4c: minimal, format-only validation of the optional `branch` field
    in a raw (not-yet-assembled) model decomposition response."""

    def _payload_with_branch(self, branch) -> dict:
        node = {"id": "a", "role": "research", "prose": "Do a thing.", "depends_on": ["root"]}
        if branch is not None:
            node["directives"] = {"branch": branch}
        return {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Goal.", "depends_on": []},
                node,
            ],
        }

    def test_valid_branch_value_is_accepted(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_branch("A"))
        self.assertEqual(problems, [])

    def test_missing_branch_is_fine(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_branch(None))
        self.assertEqual(problems, [])

    def test_empty_branch_value_is_rejected(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_branch("   "))
        self.assertTrue(any("invalid branch value" in p for p in problems))

    def test_overlong_branch_value_is_rejected(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_branch("x" * 41))
        self.assertTrue(any("invalid branch value" in p for p in problems))


class DecomposeValidationDeliverablesTests(unittest.TestCase):
    """WS4d: minimal, format-only validation of the optional `deliverables`
    field in a raw (not-yet-assembled) model decomposition response."""

    def _payload_with_deliverables(self, deliverables) -> dict:
        node = {"id": "a", "role": "implementation", "prose": "Build it.", "depends_on": ["root"]}
        if deliverables is not None:
            node["deliverables"] = deliverables
        return {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Goal.", "depends_on": []},
                node,
            ],
        }

    def test_valid_deliverables_are_accepted(self):
        problems = canvas_plan._validate_decomposition(
            self._payload_with_deliverables(["The script exists at scripts/foo.py.", "It prints a summary."])
        )
        self.assertEqual(problems, [])

    def test_missing_deliverables_is_fine(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_deliverables(None))
        self.assertEqual(problems, [])

    def test_non_list_deliverables_is_rejected(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_deliverables("just a string"))
        self.assertTrue(any("invalid deliverables list" in p for p in problems))

    def test_too_many_deliverables_is_rejected(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_deliverables([f"item {i}" for i in range(6)]))
        self.assertTrue(any("invalid deliverables list" in p for p in problems))

    def test_empty_deliverable_entry_is_rejected(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_deliverables(["Real one.", "   "]))
        self.assertTrue(any("malformed deliverable entry" in p for p in problems))

    def test_overlong_deliverable_entry_is_rejected(self):
        problems = canvas_plan._validate_decomposition(self._payload_with_deliverables(["x" * 201]))
        self.assertTrue(any("malformed deliverable entry" in p for p in problems))


class NodeDirectiveParsingTests(unittest.TestCase):
    """WS1 (2026-07-24 planning roadmap, D1): a node's leading `key: value`
    lines are directives; everything after is the agent's actual prompt."""

    def test_parses_multiple_directives_in_any_order(self):
        text = (
            "scope: tests/test_vault_watch.py\n"
            "role: verification\n"
            "recommended model: developer (openclaw)\n"
            "Just that one file, not the whole suite."
        )
        directives, remaining = canvas_plan._parse_node_directives(text)
        self.assertEqual(
            directives,
            {
                "scope": "tests/test_vault_watch.py",
                "role": "verification",
                "recommended_model": "developer (openclaw)",
            },
        )
        self.assertEqual(remaining, "Just that one file, not the whole suite.")

    def test_test_and_type_are_aliases_of_scope_and_role(self):
        directives, _ = canvas_plan._parse_node_directives("type: implementation\ntest: tests/test_foo.py\nDo it.")
        self.assertEqual(directives["role"], "implementation")
        self.assertEqual(directives["scope"], "tests/test_foo.py")

    def test_task_is_an_alias_of_branch(self):
        # 2026-07-25 terminology workflow: "task" is the preferred spelling for
        # a WS4c macro-pillar tag, but resolves to the same "branch" key so
        # compile_canvas's existing branch-aware layout needs no changes.
        directives, _ = canvas_plan._parse_node_directives("role: research\ntask: A\nInvestigate.")
        self.assertEqual(directives["branch"], "A")
        self.assertNotIn("task", directives)

    def test_mode_directive_is_parsed(self):
        directives, _ = canvas_plan._parse_node_directives("role: workflow\nmode: development\nBuild it.")
        self.assertEqual(directives["mode"], "development")

    def test_stops_at_the_first_non_directive_line(self):
        text = "role: research\nThis is prose, project: not a directive here.\nMore prose."
        directives, remaining = canvas_plan._parse_node_directives(text)
        self.assertEqual(directives, {"role": "research"})
        self.assertIn("project: not a directive here.", remaining)

    def test_plain_prose_with_no_directives_is_untouched(self):
        directives, remaining = canvas_plan._parse_node_directives("Run the test suite and report back.")
        self.assertEqual(directives, {})
        self.assertEqual(remaining, "Run the test suite and report back.")

    def test_empty_directive_value_is_dropped(self):
        directives, _ = canvas_plan._parse_node_directives("project:\nrole: implementation\nDo it.")
        self.assertNotIn("project", directives)
        self.assertEqual(directives["role"], "implementation")


class CompileCanvasDirectiveWiringTests(unittest.TestCase):
    """WS1: directives must reach the compiled step's inputs, not just get
    parsed -- this is what actually fixes the confirmed live-test bugs."""

    def test_verification_scope_directive_becomes_args(self):
        payload = {
            "nodes": [_node("v", "role: verification\nscope: tests/test_vault_watch.py\nJust this file.", role="verification")],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="scope_test")
        self.assertEqual(workflow["steps"][0]["inputs"]["args"], ["tests/test_vault_watch.py"])

    def test_verification_scope_directive_supports_multiple_comma_separated_paths(self):
        payload = {
            "nodes": [
                _node(
                    "v",
                    "role: verification\nscope: tests/test_a.py, tests/test_b.py\nRun both.",
                    role="verification",
                )
            ],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="multi_scope")
        self.assertEqual(workflow["steps"][0]["inputs"]["args"], ["tests/test_a.py", "tests/test_b.py"])

    def test_verification_without_scope_gets_no_args(self):
        payload = {"nodes": [_node("v", "role: verification\nRun everything.", role="verification")], "edges": []}
        workflow = canvas_plan.compile_canvas(payload, workflow_id="no_scope")
        self.assertNotIn("args", workflow["steps"][0]["inputs"])

    def test_implementation_node_level_project_directive_sets_project_id(self):
        payload = {
            "nodes": [
                _node("i", "role: implementation\nproject: mark_platform\nWrite a script.", role="implementation")
            ],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="node_project")
        self.assertEqual(workflow["steps"][0]["inputs"]["project_id"], "mark_platform")

    def test_implementation_intent_always_forwards_the_stripped_prose(self):
        payload = {
            "nodes": [
                _node(
                    "i",
                    "role: implementation\nproject: mark_platform\nWrite a hello world script.",
                    role="implementation",
                )
            ],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="intent_test")
        self.assertEqual(workflow["steps"][0]["inputs"]["intent"], "Write a hello world script.")

    def test_implementation_without_project_directive_gets_no_project_id(self):
        """Confirms the live-tested gap: no directive, no canvas-level default
        -- inputs.project_id is simply absent, matching today's safe no-op
        rather than guessing a target."""
        payload = {"nodes": [_node("i", "role: implementation\nDo it.", role="implementation")], "edges": []}
        workflow = canvas_plan.compile_canvas(payload, workflow_id="no_project")
        self.assertNotIn("project_id", workflow["steps"][0]["inputs"])

    def test_canvas_level_project_from_plan_root_is_inherited(self):
        payload = {
            "nodes": [
                _node("root", "role: plan\nproject: mark_platform\nOverall goal.", role="plan"),
                _node("i", "role: implementation\nDo the thing.", role="implementation"),
            ],
            "edges": [_edge("e1", "root", "i")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="canvas_project")
        impl_step = next(s for s in workflow["steps"] if s["inputs"]["canvas_role"] == "implementation")
        self.assertEqual(impl_step["inputs"]["project_id"], "mark_platform")

    def test_node_level_project_overrides_canvas_level(self):
        payload = {
            "nodes": [
                _node("root", "role: plan\nproject: mark_platform\nOverall goal.", role="plan"),
                _node(
                    "i",
                    "role: implementation\nproject: knowledge_compiler_engine\nDo the thing.",
                    role="implementation",
                ),
            ],
            "edges": [_edge("e1", "root", "i")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="override_project")
        impl_step = next(s for s in workflow["steps"] if s["inputs"]["canvas_role"] == "implementation")
        self.assertEqual(impl_step["inputs"]["project_id"], "knowledge_compiler_engine")

    def test_unregistered_node_level_project_is_refused_at_compile_time(self):
        payload = {
            "nodes": [
                _node("i", "role: implementation\nproject: totally_fake_project\nDo it.", role="implementation")
            ],
            "edges": [],
        }
        with self.assertRaises(canvas_plan.CanvasCompileError):
            canvas_plan.compile_canvas(payload, workflow_id="bad_project")

    def test_unregistered_canvas_level_project_is_refused_at_compile_time(self):
        payload = {
            "nodes": [_node("root", "role: plan\nproject: totally_fake_project\nGoal.", role="plan")],
            "edges": [],
        }
        with self.assertRaises(canvas_plan.CanvasCompileError):
            canvas_plan.compile_canvas(payload, workflow_id="bad_canvas_project")

    def test_file_directive_reaches_inputs(self):
        payload = {
            "nodes": [_node("r", "role: reference\nfile: scratch/notes.md\nSee this file.", role="reference")],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="file_test")
        self.assertEqual(workflow["steps"][0]["inputs"]["file"], "scratch/notes.md")

    def test_recommended_model_directive_is_threaded_through_but_inert(self):
        payload = {
            "nodes": [
                _node(
                    "i",
                    "role: implementation\nproject: mark_platform\nrecommended model: developer (openclaw)\nDo it.",
                    role="implementation",
                )
            ],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="recommended_model_test")
        self.assertEqual(workflow["steps"][0]["inputs"]["recommended_model"], "developer (openclaw)")
        # Inert: it doesn't change the role, target, or any other compiled field.
        self.assertEqual(workflow["steps"][0]["target"], "project_operator")


class ContextPreambleTests(unittest.TestCase):
    """WS4d: deterministic, compile-time-only context inheritance -- no
    model call, assembled purely from prose already on the canvas."""

    def _step(self, workflow: dict, node_id: str) -> dict:
        return next(s for s in workflow["steps"] if s["step_id"] == canvas_plan.node_step_id(node_id))

    def test_single_node_plan_gets_no_preamble(self):
        payload = {"nodes": [_node("root", "role: plan\nShip it.", role="plan")], "edges": []}
        workflow = canvas_plan.compile_canvas(payload, workflow_id="solo")
        # the plan node itself is never a _CONTEXT_PREAMBLE_ROLES role, so
        # nothing to check on inputs.prompt/intent -- just confirm no crash
        # and no context_injected marker anywhere.
        self.assertNotIn("context_injected", workflow["steps"][0]["inputs"])

    def test_single_branch_research_gets_system_goal_only(self):
        payload = {
            "nodes": [
                _node("root", "role: plan\nShip the login page.", role="plan"),
                _node("r", "role: research\nInvestigate options.", role="research"),
            ],
            "edges": [_edge("e1", "root", "r")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="single_branch")
        r_step = self._step(workflow, "r")
        self.assertTrue(r_step["inputs"]["context_injected"])
        self.assertIn("System goal: Ship the login page.", r_step["inputs"]["prompt"])
        self.assertIn("Investigate options.", r_step["inputs"]["prompt"])
        # no branch/sibling lines for a single-branch plan
        self.assertNotIn("component", r_step["inputs"]["prompt"])

    def test_multi_branch_node_gets_own_and_sibling_branch_lines(self):
        payload = {
            "nodes": [
                _node("root", "role: plan\nShip the notification feature.", role="plan"),
                _node("a_root", "role: implementation\nbranch: A\nBuild the detector.", role="implementation"),
                _node(
                    "a_sub",
                    "role: research\nbranch: A\nInvestigate process-trace events.",
                    role="research",
                ),
                _node("b_root", "role: implementation\nbranch: B\nBuild the TTS delivery.", role="implementation"),
            ],
            "edges": [_edge("e1", "a_sub", "a_root"), _edge("e2", "root", "a_sub"), _edge("e3", "root", "b_root")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="multi_branch")
        a_sub_step = self._step(workflow, "a_sub")
        prompt = a_sub_step["inputs"]["prompt"]
        self.assertIn("System goal: Ship the notification feature.", prompt)
        self.assertIn("component A: Build the detector.", prompt)
        self.assertIn("component B: Build the TTS delivery.", prompt)

    def test_branch_root_does_not_reference_itself(self):
        payload = {
            "nodes": [
                _node("root", "role: plan\nShip it.", role="plan"),
                _node("a_root", "role: implementation\nbranch: A\nBuild the thing.", role="implementation"),
            ],
            "edges": [_edge("e1", "root", "a_root")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="root_self")
        a_root_step = self._step(workflow, "a_root")
        intent = a_root_step["inputs"]["intent"]
        # a_root IS branch A's root -- must not describe itself as "part of component A: Build the thing."
        self.assertNotIn("This step is part of component A", intent)
        self.assertIn("System goal: Ship it.", intent)

    def test_preamble_fields_are_truncated_to_budget(self):
        long_goal = "x" * 500
        payload = {
            "nodes": [
                _node("root", f"role: plan\n{long_goal}", role="plan"),
                _node("r", "role: research\nDo it.", role="research"),
            ],
            "edges": [_edge("e1", "root", "r")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="truncate")
        prompt = self._step(workflow, "r")["inputs"]["prompt"]
        system_line = next(line for line in prompt.splitlines() if line.startswith("System goal:"))
        self.assertLessEqual(len(system_line), len("System goal: ") + canvas_plan._PREAMBLE_FIELD_BUDGET)

    def test_verification_and_reference_roles_get_no_preamble(self):
        payload = {
            "nodes": [
                _node("root", "role: plan\nShip it.", role="plan"),
                _node("v", "role: verification\nRun tests.", role="verification"),
                _node("f", "role: reference\nSee the docs.", role="reference"),
            ],
            "edges": [_edge("e1", "root", "v"), _edge("e2", "root", "f")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="no_preamble_roles")
        self.assertNotIn("context_injected", self._step(workflow, "v")["inputs"])
        self.assertNotIn("context_injected", self._step(workflow, "f")["inputs"])

    def test_evidence_extends_to_research_and_implementation_for_reliable_dependencies(self):
        payload = {
            "nodes": [
                _node("r", "role: research\nInvestigate.", role="research"),
                _node("i", "role: implementation\nBuild it.", role="implementation"),
            ],
            "edges": [_edge("e1", "r", "i")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="evidence_extend")
        i_step = self._step(workflow, "i")
        r_step_id = canvas_plan.node_step_id("r")
        self.assertEqual(
            i_step["inputs"]["evidence"],
            [{"bind": {"from_step": r_step_id, "path": "result.summary"}}],
        )

    def test_evidence_is_not_bound_to_unreliably_shaped_dependency(self):
        # a review depending on a verification (command-shaped result, no
        # reliable `summary` key) must not get a binding that would just
        # silently resolve to None at runtime.
        payload = {
            "nodes": [
                _node("v", "role: verification\nRun tests.", role="verification"),
                _node("rev", "role: review\nReview the results.", role="review"),
            ],
            "edges": [_edge("e1", "v", "rev")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="unreliable_evidence")
        rev_step = self._step(workflow, "rev")
        self.assertNotIn("evidence", rev_step["inputs"])

    def test_resolved_target_summary_shows_context_indicator(self):
        payload = {
            "nodes": [
                _node("root", "role: plan\nShip the login page.", role="plan"),
                _node("r", "role: research\nInvestigate options.", role="research"),
            ],
            "edges": [_edge("e1", "root", "r")],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="preview_indicator")
        r_step = self._step(workflow, "r")
        self.assertIn("+ context", canvas_plan._resolved_target_summary(r_step))
        root_step = self._step(workflow, "root")
        self.assertNotIn("+ context", canvas_plan._resolved_target_summary(root_step))


class PreviewResolvedTargetTests(unittest.TestCase):
    """WS1: the approval preview must show what will actually run, not just
    the node's prose -- the exact gap the implementation-node live test
    found (preview implied a write that could never happen)."""

    def _manifest_item(self, **inputs) -> dict:
        return {"inputs": inputs}

    def test_verification_with_scope_shows_it(self):
        item = self._manifest_item(canvas_role="verification", args=["tests/test_foo.py"])
        self.assertIn("scope: tests/test_foo.py", canvas_plan._resolved_target_summary(item))

    def test_verification_without_scope_warns_full_suite(self):
        item = self._manifest_item(canvas_role="verification")
        summary = canvas_plan._resolved_target_summary(item)
        self.assertIn("no scope", summary.lower())
        self.assertIn("entire suite", summary.lower())

    def test_implementation_with_project_shows_it(self):
        item = self._manifest_item(canvas_role="implementation", project_id="mark_platform")
        self.assertIn("project: mark_platform", canvas_plan._resolved_target_summary(item))

    def test_implementation_without_project_warns_no_write(self):
        item = self._manifest_item(canvas_role="implementation")
        summary = canvas_plan._resolved_target_summary(item)
        self.assertIn("no project target", summary.lower())
        self.assertIn("will not write", summary.lower())

    def test_recommended_model_is_surfaced_when_present(self):
        item = self._manifest_item(
            canvas_role="implementation", project_id="mark_platform", recommended_model="developer (openclaw)"
        )
        self.assertIn("recommended model: developer (openclaw)", canvas_plan._resolved_target_summary(item))

    def test_other_roles_render_an_em_dash(self):
        item = self._manifest_item(canvas_role="research")
        self.assertEqual(canvas_plan._resolved_target_summary(item), "—")


def _cfg(root: Path) -> dict:
    return {"jarvis_notes_root": str(root), "jarvis_canvas_folder": "Canvases/JARVIS"}


class SyncStepStatusTests(unittest.TestCase):
    """T2: push a run's per-step state back onto the source canvas's node cards."""

    def _plan_payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("b", "role: implementation\nApply.", role="implementation"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def test_updates_matching_nodes_writes_once_and_colors_by_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._plan_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")
            a_step = canvas_plan.node_step_id("a")
            b_step = canvas_plan.node_step_id("b")
            run_status = {
                "run": {"run_id": "run-1"},
                "items": [
                    {"item_id": a_step, "state": "ACCEPTED", "attempt": 1},
                    {"item_id": b_step, "state": "REPAIR", "attempt": 1},
                ],
            }

            result = canvas_plan.sync_step_status(path, workflow, run_status, cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["updated"], 2)
            reloaded = canvas.load_canvas(path)
            by_id = {n["id"]: n for n in reloaded["nodes"]}
            self.assertEqual(by_id["a"]["jarvis"]["step_state"], "ACCEPTED")
            self.assertEqual(by_id["b"]["jarvis"]["step_state"], "REPAIR")
            # different states get visibly different colors
            self.assertNotEqual(by_id["a"].get("color"), by_id["b"].get("color"))
            # human-authored instruction text is untouched
            self.assertIn("Investigate.", by_id["a"]["text"])
            self.assertIn("Apply.", by_id["b"]["text"])

    def test_identical_state_on_second_call_makes_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._plan_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")
            run_status = {
                "run": {"run_id": "run-1"},
                "items": [{"item_id": canvas_plan.node_step_id("a"), "state": "ACCEPTED", "attempt": 1}],
            }

            first = canvas_plan.sync_step_status(path, workflow, run_status, cfg=cfg)
            revision_after_first = first["revision"]
            second = canvas_plan.sync_step_status(path, workflow, run_status, cfg=cfg)

            self.assertEqual(second["updated"], 0)
            self.assertEqual(second["revision"], revision_after_first)
            self.assertFalse(second.get("archived_snapshot"))
            receipt = second["receipts"][0]
            self.assertFalse(receipt["applied"])
            self.assertEqual(receipt["reason"], "unchanged")

    def test_unknown_workflow_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._plan_payload())

            result = canvas_plan.sync_step_status(
                path, {"workflow_id": "not_compiled_from_canvas"}, {"items": []}, cfg=cfg
            )

            self.assertFalse(result["ok"])
            self.assertIn("node mapping", result["error"])

    def test_steps_not_present_in_canvas_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._plan_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")
            run_status = {"run": {"run_id": "run-1"}, "items": [{"item_id": "ghost_step", "state": "ACCEPTED"}]}

            result = canvas_plan.sync_step_status(path, workflow, run_status, cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["updated"], 0)


class ForwardScoutTests(unittest.TestCase):
    """T3's novel mechanic: a completed node teaches its successors."""

    def _linear_payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nOriginal human prompt for A.", role="research"),
                _node("b", "role: implementation\nOriginal human prompt for B.", role="implementation"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def test_appends_context_below_marker_without_touching_authored_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            result = canvas_plan.forward_scout(path, workflow, "a", result_summary="Found 3 auth entry points.", cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["updated"], 1)
            reloaded = canvas.load_canvas(path)
            b_text = next(n["text"] for n in reloaded["nodes"] if n["id"] == "b")
            self.assertIn("Original human prompt for B.", b_text)
            self.assertIn("Found 3 auth entry points.", b_text)
            a_text = next(n["text"] for n in reloaded["nodes"] if n["id"] == "a")
            self.assertEqual(a_text, "role: research\nOriginal human prompt for A.")

    def test_identical_summary_on_second_call_makes_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            canvas_plan.forward_scout(path, workflow, "a", result_summary="Same finding.", cfg=cfg)
            revision_after_first = canvas.content_revision(path)
            second = canvas_plan.forward_scout(path, workflow, "a", result_summary="Same finding.", cfg=cfg)

            self.assertEqual(second["updated"], 0)
            self.assertEqual(canvas.content_revision(path), revision_after_first)
            self.assertFalse(second.get("archived_snapshot"))

    def test_changed_summary_replaces_block_without_duplicating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            canvas_plan.forward_scout(path, workflow, "a", result_summary="First finding.", cfg=cfg)
            canvas_plan.forward_scout(path, workflow, "a", result_summary="Revised finding.", cfg=cfg)

            b_text = next(n["text"] for n in canvas.load_canvas(path)["nodes"] if n["id"] == "b")
            self.assertNotIn("First finding.", b_text)
            self.assertIn("Revised finding.", b_text)
            self.assertEqual(b_text.count("Original human prompt for B."), 1)

    def test_multiple_upstream_nodes_accumulate_distinct_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = {
                "nodes": [
                    _node("a", "role: research\nResearch A.", role="research"),
                    _node("c", "role: research\nResearch C.", role="research"),
                    _node("b", "role: implementation\nApply.", role="implementation"),
                ],
                "edges": [_edge("e1", "a", "b"), _edge("e2", "c", "b")],
            }
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            canvas_plan.forward_scout(path, workflow, "a", result_summary="From A.", cfg=cfg)
            canvas_plan.forward_scout(path, workflow, "c", result_summary="From C.", cfg=cfg)

            b_text = next(n["text"] for n in canvas.load_canvas(path)["nodes"] if n["id"] == "b")
            self.assertIn("From A.", b_text)
            self.assertIn("From C.", b_text)

    def test_terminal_node_with_no_downstream_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            result = canvas_plan.forward_scout(path, workflow, "b", result_summary="Done.", cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["updated"], 0)

    def test_node_outside_workflow_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)

            result = canvas_plan.forward_scout(path, {"variables": {}}, "a", result_summary="x", cfg=cfg)

            self.assertFalse(result["ok"])


class NodeCompletionSopTests(unittest.TestCase):
    """T3: documentation pass + forward-scout + optional handoff, run together."""

    def _linear_payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: implementation\nDo the work.", role="implementation"),
                _node("b", "role: verification\nCheck it.", role="verification"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def test_documentation_pass_writes_a_vault_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            result = canvas_plan.record_node_documentation(path, workflow, "a", result_summary="Wrote the patch.", cfg=cfg)

            self.assertTrue(result["ok"])
            note_path = Path(result["note_path"])
            self.assertTrue(note_path.exists())
            self.assertIn("Wrote the patch.", note_path.read_text(encoding="utf-8"))

    def test_handoff_note_includes_all_named_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            result = canvas_plan.record_node_handoff(
                path, workflow, "a",
                usage="Import `foo` and call `bar()`.",
                api_surface="`bar(x: int) -> int`",
                tests_run="pytest tests/test_foo.py",
                telemetry="p50 12ms",
                unresolved_gaps="No retry on timeout.",
                cfg=cfg,
            )

            self.assertTrue(result["ok"])
            text = Path(result["note_path"]).read_text(encoding="utf-8")
            for expected in ("Import `foo`", "bar(x: int)", "test_foo.py", "p50 12ms", "No retry on timeout."):
                self.assertIn(expected, text)

    def test_run_node_completion_sop_runs_doc_then_scout_then_optional_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            result = canvas_plan.run_node_completion_sop(
                path, workflow, "a",
                result_summary="Patched the module.",
                handoff={"usage": "u", "api_surface": "a", "tests_run": "t", "telemetry": "te", "unresolved_gaps": "g"},
                cfg=cfg,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["documentation"]["ok"])
            self.assertTrue(result["forward_scout"]["ok"])
            self.assertIsNotNone(result["handoff"])
            self.assertTrue(result["handoff"]["ok"])
            b_text = next(n["text"] for n in canvas.load_canvas(path)["nodes"] if n["id"] == "b")
            self.assertIn("Patched the module.", b_text)

    def test_handoff_is_skipped_when_not_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._linear_payload()
            canvas.write_canvas(path, payload)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            result = canvas_plan.run_node_completion_sop(path, workflow, "a", result_summary="Done.", cfg=cfg)

            self.assertIsNone(result["handoff"])


class PlanFingerprintTests(unittest.TestCase):
    """T4: the fingerprint must ignore everything JARVIS's own write-backs touch."""

    def _payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("b", "role: implementation\nApply.", role="implementation"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def test_color_and_jarvis_metadata_do_not_affect_fingerprint(self):
        payload = self._payload()
        before = canvas_plan.plan_fingerprint(payload)
        payload["nodes"][0]["color"] = "5"
        payload["nodes"][0]["jarvis"] = {"kind": "plan_step", "step_state": "ACCEPTED"}
        after = canvas_plan.plan_fingerprint(payload)
        self.assertEqual(before, after)

    def test_forward_scout_appended_text_does_not_affect_fingerprint(self):
        payload = self._payload()
        before = canvas_plan.plan_fingerprint(payload)
        payload["nodes"][1]["text"] = (
            payload["nodes"][1]["text"] + f"\n\n{canvas_plan._SCOUT_MARKER}\n> **Context from `a`:** Found 3 endpoints."
        )
        after = canvas_plan.plan_fingerprint(payload)
        self.assertEqual(before, after)

    def test_role_change_changes_fingerprint(self):
        payload = self._payload()
        before = canvas_plan.plan_fingerprint(payload)
        payload["nodes"][0]["jarvisRole"] = "verification"
        after = canvas_plan.plan_fingerprint(payload)
        self.assertNotEqual(before, after)

    def test_authored_instruction_change_changes_fingerprint(self):
        payload = self._payload()
        before = canvas_plan.plan_fingerprint(payload)
        payload["nodes"][0]["text"] = "role: research\nInvestigate something completely different."
        after = canvas_plan.plan_fingerprint(payload)
        self.assertNotEqual(before, after)

    def test_edge_change_changes_fingerprint(self):
        payload = self._payload()
        before = canvas_plan.plan_fingerprint(payload)
        payload["edges"] = []
        after = canvas_plan.plan_fingerprint(payload)
        self.assertNotEqual(before, after)

    def test_directive_only_edit_changes_fingerprint(self):
        """D2 (2026-07-24 roadmap): editing a directive (e.g. `recommended
        model:`) must re-trigger approval even if the prose is untouched --
        'left unedited = accepted, edited = re-assessed' only holds if the
        fingerprint actually sees the edit."""
        payload = {
            "nodes": [_node("a", "role: implementation\nApply.", role="implementation")],
            "edges": [],
        }
        before = canvas_plan.plan_fingerprint(payload)
        payload["nodes"][0]["text"] = "role: implementation\nrecommended model: developer (openclaw)\nApply."
        after = canvas_plan.plan_fingerprint(payload)
        self.assertNotEqual(before, after)


class ProposeCanvasPlanTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("b", "role: implementation\nApply.", role="implementation"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def test_first_proposal_creates_pending_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._payload())

            result = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertTrue(result["changed"])
            self.assertEqual(result["plan_version"], 1)
            note_path = Path(result["note_path"])
            self.assertTrue(note_path.exists())
            from actions import jarvis_memory as memory

            metadata, body, _ = memory.read_note(note_path)
            self.assertEqual(metadata["approval_state"], "pending_review")
            from core import approval_response

            self.assertEqual(approval_response.parse_approval_response(body)["decision"], "pending")

    def test_reproposing_unchanged_canvas_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._payload())

            first = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)
            second = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)

            self.assertFalse(second["changed"])
            self.assertEqual(second["plan_version"], 1)
            self.assertEqual(second["plan_fingerprint_hash"], first["plan_fingerprint_hash"])

    def test_own_writeback_from_sync_step_status_does_not_trigger_reproposal(self):
        # This is the exact failure mode being guarded against: JARVIS's own
        # status write-back must never look like a human plan edit.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._payload()
            canvas.write_canvas(path, payload)
            first = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)
            workflow = canvas_plan.compile_canvas(payload, workflow_id="demo", name="Demo")

            run_status = {
                "run": {"run_id": "run-1"},
                "items": [{"item_id": canvas_plan.node_step_id("a"), "state": "ACCEPTED", "attempt": 1}],
            }
            canvas_plan.sync_step_status(path, workflow, run_status, cfg=cfg)
            canvas_plan.forward_scout(path, workflow, "a", result_summary="Found something.", cfg=cfg)

            second = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)

            self.assertFalse(second["changed"])
            self.assertEqual(second["plan_fingerprint_hash"], first["plan_fingerprint_hash"])

    def test_genuine_human_edit_bumps_version_and_resets_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._payload()
            canvas.write_canvas(path, payload)
            first = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)

            payload["nodes"][0]["text"] = "role: research\nInvestigate the payments module instead."
            canvas.write_canvas(path, payload)

            second = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)

            self.assertTrue(second["changed"])
            self.assertEqual(second["plan_version"], 2)
            self.assertNotEqual(second["plan_fingerprint_hash"], first["plan_fingerprint_hash"])


def _check_option(note_path: Path, option: str, *, fill: str = "") -> None:
    """Test helper simulating a human checking a box (and filling a callout)."""
    from actions import jarvis_memory as memory
    from core import approval_response as approval

    metadata, body, _ = memory.read_note(note_path)
    body = body.replace(f"- [ ] **{option}**", f"- [x] **{option}**")
    if fill:
        if option == "Correct":
            body = body.replace(
                "> [!note] Correction details (only read if **Correct** is checked)\n> Describe what should change.",
                f"> [!note] Correction details (only read if **Correct** is checked)\n> {fill}",
            )
        elif option == "Deny":
            body = body.replace(
                "> [!note] Reason for denial (only read if **Deny** is checked)\n> Explain why this plan should not run.",
                f"> [!note] Reason for denial (only read if **Deny** is checked)\n> {fill}",
            )
    note_path.write_text(f"{memory.render_frontmatter(metadata)}\n\n{body}", encoding="utf-8")


class EvaluateCanvasApprovalTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("b", "role: implementation\nApply.", role="implementation"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def _propose(self, root: Path, cfg: dict) -> tuple[Path, dict]:
        path = root / "Canvases" / "JARVIS" / "plan.canvas"
        canvas.write_canvas(path, self._payload())
        proposal = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)
        return path, proposal

    def test_pending_decision_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            _canvas_path, proposal = self._propose(root, cfg)

            result = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "pending")

    def test_approve_signs_an_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            _canvas_path, proposal = self._propose(root, cfg)
            _check_option(Path(proposal["note_path"]), "Approve")

            result = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "approved")
            self.assertTrue(Path(result["approval_path"]).is_file())
            from actions import jarvis_memory as memory

            metadata, _body, _ = memory.read_note(Path(proposal["note_path"]))
            self.assertEqual(metadata["approval_state"], "approved")

    def test_reevaluating_an_approved_note_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            _canvas_path, proposal = self._propose(root, cfg)
            _check_option(Path(proposal["note_path"]), "Approve")

            first = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)
            second = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            self.assertTrue(second["ok"])
            self.assertTrue(second.get("already"))
            self.assertEqual(second["approval_path"], first["approval_path"])

    def test_deny_records_reason_and_mints_no_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            _canvas_path, proposal = self._propose(root, cfg)
            _check_option(Path(proposal["note_path"]), "Deny", fill="This touches production credentials.")

            result = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "denied")
            self.assertIn("production credentials", result["reason"])
            from actions import jarvis_memory as memory

            metadata, _body, _ = memory.read_note(Path(proposal["note_path"]))
            self.assertEqual(metadata["approval_state"], "denied")
            self.assertFalse(str(metadata.get("approval_path") or ""))

    def test_correct_records_correction_and_mints_no_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            _canvas_path, proposal = self._propose(root, cfg)
            _check_option(Path(proposal["note_path"]), "Correct", fill="Add a verification node after implementation.")

            result = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "revision_requested")
            self.assertIn("verification node", result["correction"])

    def test_ambiguous_double_checked_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            _canvas_path, proposal = self._propose(root, cfg)
            note_path = Path(proposal["note_path"])
            _check_option(note_path, "Approve")
            _check_option(note_path, "Deny")

            result = canvas_plan.evaluate_canvas_approval(note_path, cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "ambiguous")

    def test_canvas_drift_blocks_approval_even_when_approve_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            canvas_path, proposal = self._propose(root, cfg)
            _check_option(Path(proposal["note_path"]), "Approve")

            # a human edits the canvas's authored content after the note was proposed
            payload = canvas.load_canvas(canvas_path)
            payload["nodes"][0]["text"] = "role: research\nInvestigate something entirely different."
            canvas.write_canvas(canvas_path, payload, expected_revision=canvas.content_revision(canvas_path))

            result = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "drift")

    def test_own_writebacks_do_not_block_a_legitimate_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            canvas_path, proposal = self._propose(root, cfg)
            workflow = canvas_plan.compile_canvas(canvas.load_canvas(canvas_path), workflow_id="demo", name="Demo")
            run_status = {
                "run": {"run_id": "run-1"},
                "items": [{"item_id": canvas_plan.node_step_id("a"), "state": "ACCEPTED", "attempt": 1}],
            }
            canvas_plan.sync_step_status(canvas_path, workflow, run_status, cfg=cfg)
            canvas_plan.forward_scout(canvas_path, workflow, "a", result_summary="Found it.", cfg=cfg)
            _check_option(Path(proposal["note_path"]), "Approve")

            result = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "approved")


class VerifyCanvasPlanApprovalTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("b", "role: implementation\nApply.", role="implementation"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def test_unapproved_plan_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._payload())
            proposal = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)

            result = canvas_plan.verify_canvas_plan_approval(proposal["note_path"], cfg=cfg)

            self.assertFalse(result["ok"])

    def test_approved_undrifted_plan_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._payload())
            proposal = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)
            _check_option(Path(proposal["note_path"]), "Approve")
            canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            result = canvas_plan.verify_canvas_plan_approval(proposal["note_path"], cfg=cfg)

            self.assertTrue(result["ok"])
            self.assertTrue(result["workflow_hash"])
            self.assertTrue(result["approved_action_ids"])

    def test_drift_after_approval_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            payload = self._payload()
            canvas.write_canvas(path, payload)
            proposal = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)
            _check_option(Path(proposal["note_path"]), "Approve")
            canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            payload["nodes"][0]["text"] = "role: research\nSomething else entirely."
            canvas.write_canvas(path, payload, expected_revision=canvas.content_revision(path))

            result = canvas_plan.verify_canvas_plan_approval(proposal["note_path"], cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "drift")

    def test_tampered_envelope_fails_signature_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._payload())
            proposal = canvas_plan.propose_canvas_plan(path, workflow_id="demo", name="Demo", cfg=cfg)
            _check_option(Path(proposal["note_path"]), "Approve")
            approved = canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)

            envelope_path = Path(approved["approval_path"])
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            envelope["approved_action_ids"] = ["tampered_step"]
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

            result = canvas_plan.verify_canvas_plan_approval(proposal["note_path"], cfg=cfg)

            self.assertFalse(result["ok"])


class BuildCanvasDualReviewerTests(unittest.TestCase):
    """T5: the review node's dual critic -- model pass (existing) + user gate (new)."""

    def _payload(self) -> dict:
        return {
            "nodes": [
                _node("r", "Research.", role="research"),
                _node("rev", "Review the findings.", role="review"),
                _node("impl", "Apply the change.", role="implementation"),
            ],
            "edges": [_edge("e1", "r", "rev"), _edge("e2", "rev", "impl")],
        }

    def _reviewer(self, root: Path, cfg: dict):
        from actions.dual_orchestrator import compile_workflow

        workflow = canvas_plan.compile_canvas(self._payload(), workflow_id="gate", name="Gate")
        # The reviewer contract receives manifest items (an "id" key), not raw
        # workflow steps (a "step_id" key) -- match what `_execute_item` really passes.
        manifest = compile_workflow(workflow, preview=True)
        rev_item = next(item for item in manifest["items"] if item["step_type"] == "review")
        reviewer = canvas_plan.build_canvas_dual_reviewer(workflow, cfg=cfg)
        return reviewer, rev_item, workflow

    def test_non_review_item_delegates_to_default_model_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, _rev_step, _workflow = self._reviewer(root, cfg)
            other_item = {
                "id": "some_other_step",
                "step_type": "model_reasoning",
                "description": "Do research.",
                "acceptance_criteria": {"required": True},
            }
            with mock.patch(
                "core.model_router.call_text",
                return_value='{"verdict": "ACCEPT", "defects": []}',
            ):
                verdict, defects = reviewer(other_item, {"text": "some result"}, [])
            self.assertEqual(verdict, "ACCEPT")

    def test_review_item_first_pass_writes_note_and_escalates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, rev_step, _workflow = self._reviewer(root, cfg)

            verdict, defects = reviewer(rev_step, {"text": "The upstream research looks solid."}, [])

            self.assertEqual(verdict, "ESCALATE")
            self.assertIn("awaiting_user_review", defects)
            note_path = canvas_plan._canvas_review_note_path(root, "gate", rev_step["id"])
            self.assertTrue(note_path.exists())
            self.assertIn("The upstream research looks solid.", note_path.read_text(encoding="utf-8"))

    def test_review_item_second_call_still_pending_escalates_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, rev_step, _workflow = self._reviewer(root, cfg)
            reviewer(rev_step, {"text": "critique"}, [])

            verdict, defects = reviewer(rev_step, {"text": "critique"}, [])

            self.assertEqual(verdict, "ESCALATE")
            self.assertIn("awaiting_user_review:pending", defects)

    def test_review_item_approved_by_human_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, rev_step, _workflow = self._reviewer(root, cfg)
            reviewer(rev_step, {"text": "critique"}, [])
            note_path = canvas_plan._canvas_review_note_path(root, "gate", rev_step["id"])
            _check_option(note_path, "Approve")

            verdict, defects = reviewer(rev_step, {"text": "critique"}, [])

            self.assertEqual(verdict, "ACCEPT")
            from actions import jarvis_memory as memory

            metadata, _body, _ = memory.read_note(note_path)
            self.assertEqual(metadata["review_state"], "approved")

    def test_review_item_denied_by_human_rejects_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, rev_step, _workflow = self._reviewer(root, cfg)
            reviewer(rev_step, {"text": "critique"}, [])
            note_path = canvas_plan._canvas_review_note_path(root, "gate", rev_step["id"])
            _check_option(note_path, "Deny", fill="The upstream research is factually wrong.")

            verdict, defects = reviewer(rev_step, {"text": "critique"}, [])

            self.assertEqual(verdict, "REJECT_REPLAN")
            self.assertTrue(any("factually wrong" in defect for defect in defects))

    def test_review_item_correction_requested_rejects_with_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, rev_step, _workflow = self._reviewer(root, cfg)
            reviewer(rev_step, {"text": "critique"}, [])
            note_path = canvas_plan._canvas_review_note_path(root, "gate", rev_step["id"])
            _check_option(note_path, "Correct", fill="Research the payments module too.")

            verdict, defects = reviewer(rev_step, {"text": "critique"}, [])

            self.assertEqual(verdict, "REJECT_REPLAN")
            self.assertTrue(any("payments module" in defect for defect in defects))

    def test_review_item_ambiguous_double_check_escalates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, rev_step, _workflow = self._reviewer(root, cfg)
            reviewer(rev_step, {"text": "critique"}, [])
            note_path = canvas_plan._canvas_review_note_path(root, "gate", rev_step["id"])
            _check_option(note_path, "Approve")
            _check_option(note_path, "Deny")

            verdict, defects = reviewer(rev_step, {"text": "critique"}, [])

            self.assertEqual(verdict, "ESCALATE")
            self.assertIn("awaiting_user_review:ambiguous", defects)

    def test_replay_of_already_resolved_review_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            reviewer, rev_step, _workflow = self._reviewer(root, cfg)
            reviewer(rev_step, {"text": "critique"}, [])
            note_path = canvas_plan._canvas_review_note_path(root, "gate", rev_step["id"])
            _check_option(note_path, "Approve")
            reviewer(rev_step, {"text": "critique"}, [])  # resolves to approved

            verdict, defects = reviewer(rev_step, {"text": "critique"}, [])  # replay

            self.assertEqual(verdict, "ACCEPT")


class ExecuteCanvasPlanTests(unittest.TestCase):
    """End-to-end: T1 compile -> T4 approve -> execution driver -> T5 gate ->
    resume -> T2 status write-back -> T3 completion SOP, all wired together."""

    def _payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nInvestigate the auth module.", role="research"),
                _node("rev", "role: review\nReview the findings.", role="review"),
                _node("b", "role: research\nFollow up on what the review approved.", role="research"),
            ],
            "edges": [_edge("e1", "a", "rev"), _edge("e2", "rev", "b")],
        }

    def _approved_note(self, root: Path, cfg: dict) -> tuple[Path, str]:
        path = root / "Canvases" / "JARVIS" / "plan.canvas"
        canvas.write_canvas(path, self._payload())
        proposal = canvas_plan.propose_canvas_plan(path, workflow_id="drive", name="Drive", cfg=cfg)
        _check_option(Path(proposal["note_path"]), "Approve")
        canvas_plan.evaluate_canvas_approval(proposal["note_path"], cfg=cfg)
        return path, proposal["note_path"]

    def test_refuses_to_run_an_unapproved_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._payload())
            proposal = canvas_plan.propose_canvas_plan(path, workflow_id="drive", name="Drive", cfg=cfg)

            result = canvas_plan.execute_canvas_plan(proposal["note_path"], cfg=cfg)

            self.assertFalse(result["ok"])

    def test_runs_to_review_gate_then_resumes_after_human_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            canvas_path, note_path = self._approved_note(root, cfg)

            with mock.patch("core.model_router.call_text", return_value='{"verdict": "ACCEPT", "defects": []}'):
                first = canvas_plan.execute_canvas_plan(note_path, cfg=cfg)

            self.assertTrue(first["ok"])
            self.assertEqual(first["execution_state"], "escalated")
            states = {item["item_id"]: item["state"] for item in first["run_status"]["items"]}
            self.assertEqual(sorted(states.values()), sorted(["ACCEPTED", "ESCALATE", "PENDING"]))

            # T2: the canvas node itself reflects the run's real per-step states
            reloaded = canvas.load_canvas(canvas_path)
            by_id = {n["id"]: n for n in reloaded["nodes"]}
            self.assertEqual(by_id["a"]["jarvis"]["step_state"], "ACCEPTED")
            self.assertEqual(by_id["rev"]["jarvis"]["step_state"], "ESCALATE")

            # T3: research(a)'s completion SOP already taught the review node
            self.assertIn(canvas_plan._SCOUT_MARKER, by_id["rev"]["text"])

            # approve the T5 review-gate note the reviewer callback wrote
            review_step_id = next(item_id for item_id, state in states.items() if state == "ESCALATE")
            notes_root = canvas.resolve_config(cfg)["notes_root"]
            review_note_path = canvas_plan._canvas_review_note_path(notes_root, "drive", review_step_id)
            self.assertTrue(review_note_path.exists())
            self.assertIn("Model Critique", review_note_path.read_text(encoding="utf-8"))
            _check_option(review_note_path, "Approve")

            with mock.patch("core.model_router.call_text", return_value='{"verdict": "ACCEPT", "defects": []}'):
                second = canvas_plan.execute_canvas_plan(note_path, cfg=cfg)

            self.assertTrue(second["ok"])
            self.assertEqual(second["execution_state"], "completed")
            self.assertTrue(all(item["state"] == "ACCEPTED" for item in second["run_status"]["items"]))

    def test_completion_sop_is_not_refiled_on_resume(self):
        # a resumed call must not re-run the completion SOP for a node whose
        # step already accepted on an earlier call -- only "a" is accepted on
        # the first call (1 documentation note); the resume then accepts "rev"
        # and "b" too, so exactly 2 more should appear, never a 4th for "a".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            _canvas_path, note_path = self._approved_note(root, cfg)
            notes_root = canvas.resolve_config(cfg)["notes_root"]

            def doc_note_count() -> int:
                return len(list((notes_root / "Logs").glob("*documentation*")))

            with mock.patch("core.model_router.call_text", return_value='{"verdict": "ACCEPT", "defects": []}'):
                first = canvas_plan.execute_canvas_plan(note_path, cfg=cfg)
            self.assertEqual(doc_note_count(), 1)

            states = {item["item_id"]: item["state"] for item in first["run_status"]["items"]}
            review_step_id = next(item_id for item_id, state in states.items() if state == "ESCALATE")
            review_note_path = canvas_plan._canvas_review_note_path(notes_root, "drive", review_step_id)
            _check_option(review_note_path, "Approve")

            with mock.patch("core.model_router.call_text", return_value='{"verdict": "ACCEPT", "defects": []}'):
                canvas_plan.execute_canvas_plan(note_path, cfg=cfg)

            self.assertEqual(doc_note_count(), 3)


class CanvasPlanDispatcherTests(unittest.TestCase):
    """The tool-dispatcher entry point: pure routing onto the tested functions."""

    def _payload(self) -> dict:
        return {
            "nodes": [
                _node("a", "role: research\nInvestigate.", role="research"),
                _node("b", "role: implementation\nApply.", role="implementation"),
            ],
            "edges": [_edge("e1", "a", "b")],
        }

    def test_health(self):
        payload = json.loads(canvas_plan.canvas_plan({"operation": "health"}))
        self.assertTrue(payload["ok"])

    def test_unknown_operation_is_refused(self):
        payload = json.loads(canvas_plan.canvas_plan({"operation": "not_a_real_operation"}))
        self.assertFalse(payload["ok"])
        self.assertIn("Unknown canvas_plan operation", payload["error"])

    def test_propose_and_evaluate_approval_through_the_dispatcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "plan.canvas"
            canvas.write_canvas(path, self._payload())

            proposed = json.loads(
                canvas_plan.canvas_plan(
                    {"operation": "propose", "canvas_path": str(path), "workflow_id": "dispatch", "name": "Dispatch", "_config": cfg}
                )
            )
            self.assertTrue(proposed["ok"])
            note_path = proposed["note_path"]
            _check_option(Path(note_path), "Approve")

            evaluated = json.loads(
                canvas_plan.canvas_plan({"operation": "evaluate_approval", "note_path": note_path, "_config": cfg})
            )
            self.assertTrue(evaluated["ok"])
            self.assertEqual(evaluated["status"], "approved")

            verified = json.loads(
                canvas_plan.canvas_plan({"operation": "verify_approval", "note_path": note_path, "_config": cfg})
            )
            self.assertTrue(verified["ok"])

    def test_missing_note_path_is_a_clean_error_not_a_crash(self):
        payload = json.loads(canvas_plan.canvas_plan({"operation": "evaluate_approval", "_config": {}}))
        self.assertFalse(payload["ok"])


class CanvasExecutionReceiptTests(unittest.TestCase):
    """WS2 (2026-07-24 planning roadmap, D4): a per-item pass/fail record for
    the process trace, built from each item's already-written result file."""

    def test_reads_ok_returncode_and_output_tail_from_result_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "01-v1.json"
            result_path.write_text(
                json.dumps({"result": {"ok": True, "returncode": 0, "stdout": "....\n17 passed in 0.35s\n"}}),
                encoding="utf-8",
            )
            result = {
                "run_id": "run-1",
                "execution_state": "completed",
                "run_status": {"items": [{"item_id": "v1", "state": "ACCEPTED", "result_path": str(result_path)}]},
            }
            receipt = canvas_plan._canvas_execution_receipt(result)

        self.assertEqual(receipt["run_id"], "run-1")
        item = receipt["items"][0]
        self.assertEqual(item["state"], "ACCEPTED")
        self.assertEqual(item["ok"], True)
        self.assertEqual(item["returncode"], 0)
        self.assertEqual(item["output_tail"], "17 passed in 0.35s")

    def test_missing_result_file_does_not_crash(self):
        result = {
            "run_id": "run-2",
            "execution_state": "blocked",
            "run_status": {"items": [{"item_id": "v1", "state": "REJECT_REPLAN", "error": "boom", "result_path": "does/not/exist.json"}]},
        }
        receipt = canvas_plan._canvas_execution_receipt(result)
        item = receipt["items"][0]
        self.assertEqual(item["state"], "REJECT_REPLAN")
        self.assertEqual(item["error"], "boom")
        self.assertNotIn("ok", item)

    def test_dispatcher_attaches_the_receipt_as_detail_on_execute(self):
        fake_result = {
            "ok": True,
            "run_id": "run-3",
            "execution_state": "completed",
            "run_status": {"items": [{"item_id": "v1", "state": "ACCEPTED", "result_path": ""}]},
        }
        with mock.patch("actions.canvas_plan.execute_canvas_plan", return_value=fake_result), mock.patch(
            "core.process_events.emit_process_event"
        ) as emit:
            canvas_plan.canvas_plan({"operation": "execute", "note_path": "some/note.md"})

        completion_call = emit.call_args_list[-1]
        self.assertEqual(completion_call.kwargs["detail"]["run_id"], "run-3")

    def test_dispatcher_attaches_no_detail_for_non_execute_operations(self):
        with mock.patch("core.process_events.emit_process_event") as emit:
            canvas_plan.canvas_plan({"operation": "health"})

        completion_call = emit.call_args_list[-1]
        self.assertIsNone(completion_call.kwargs["detail"])


class DecomposeGoalToCanvasTests(unittest.TestCase):
    """WS4a: turning a plain goal into a real, drawn canvas."""

    def _good_payload(self) -> dict:
        return {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Ship the thing.", "depends_on": []},
                {
                    "id": "look_around",
                    "role": "research",
                    "directives": {"recommended_model": "research"},
                    "prose": "Find the existing auth module.",
                    "depends_on": ["root"],
                },
                {
                    "id": "make_change",
                    "role": "implementation",
                    "directives": {"project": "demo_project", "file": "auth.py"},
                    "prose": "Apply the fix.",
                    "depends_on": ["look_around"],
                },
                {
                    "id": "check_it",
                    "role": "verification",
                    "directives": {"scope": "tests/test_auth.py"},
                    "prose": "Run the auth tests.",
                    "depends_on": ["make_change"],
                },
            ],
            "rationale": "Research first, then change, then verify.",
        }

    def test_well_formed_response_assembles_a_valid_canvas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._good_payload())) as call_text:
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["node_count"], 4)
            self.assertEqual(result["rationale"], "Research first, then change, then verify.")
            call_text.assert_called_once()
            self.assertEqual(call_text.call_args.kwargs["role"], "planner")

            canvas_path = Path(result["canvas_path"])
            self.assertTrue(canvas_path.exists())
            self.assertTrue(canvas_path.is_relative_to(root))
            # a caller-less default name must still land under the canvas
            # folder, not directly in the vault root
            self.assertTrue(canvas_path.is_relative_to(root / "Canvases" / "JARVIS"))

            document = canvas.load_canvas(canvas_path)
            self.assertEqual(len(document["nodes"]), 4)
            self.assertEqual(len(document["edges"]), 3)

            by_id = {node["id"]: node for node in document["nodes"]}
            self.assertIn("root", by_id)
            self.assertIn("role: implementation", by_id["make_change"]["text"])
            self.assertIn("project: demo_project", by_id["make_change"]["text"])
            self.assertIn("file: auth.py", by_id["make_change"]["text"])
            self.assertIn("scope: tests/test_auth.py", by_id["check_it"]["text"])
            self.assertIn("Run the auth tests.", by_id["check_it"]["text"])

            # layout_document must actually run: a linear dependency chain should
            # land each node in its own layer, strictly increasing in y, not all
            # four stacked on the (0, 0) placeholder.
            ys = [by_id[nid]["y"] for nid in ("root", "look_around", "make_change", "check_it")]
            self.assertEqual(ys, sorted(ys))
            self.assertEqual(len(set(ys)), 4)

            edge_pairs = {(edge["fromNode"], edge["toNode"]) for edge in document["edges"]}
            self.assertEqual(edge_pairs, {("root", "look_around"), ("look_around", "make_change"), ("make_change", "check_it")})

    def test_user_workflow_mode_is_written_onto_the_plan_node_and_returned(self):
        # A minimal payload for the compile step specifically -- _good_payload()'s
        # implementation node references an unregistered "demo_project", which
        # compile_canvas validates and would fail on for a reason unrelated to
        # what this test actually checks (the mode directive's own plumbing).
        minimal_payload = {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Ship the thing.", "depends_on": []},
                {"id": "look_around", "role": "research", "prose": "Find it.", "depends_on": ["root"]},
            ],
            "rationale": "Minimal.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch("core.model_router.call_text", return_value=json.dumps(minimal_payload)):
                result = canvas_plan.decompose_goal_to_canvas(
                    "Fix the login bug", cfg=cfg, user_workflow_mode="development"
                )

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["mode"], "development")

            document = canvas.load_canvas(Path(result["canvas_path"]))
            by_id = {node["id"]: node for node in document["nodes"]}
            self.assertIn("mode: development", by_id["root"]["text"])
            # only the plan/anchor node gets it, not every node
            self.assertNotIn("mode:", by_id["look_around"]["text"])

            workflow = canvas_plan.compile_canvas(document, workflow_id="modewired", name="ModeWired")
            self.assertEqual(workflow["variables"]["mode"], "development")

    def test_omitted_user_workflow_mode_leaves_the_plan_node_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._good_payload())):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

            self.assertEqual(result["mode"], "")
            document = canvas.load_canvas(Path(result["canvas_path"]))
            by_id = {node["id"]: node for node in document["nodes"]}
            self.assertNotIn("mode:", by_id["root"]["text"])

    def test_project_hint_is_forwarded_into_the_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._good_payload())) as call_text:
                canvas_plan.decompose_goal_to_canvas("Fix the login bug", project_hint="demo_project", cfg=cfg)

            prompt_arg = call_text.call_args.args[0]
            self.assertIn("demo_project", prompt_arg)

    def test_empty_goal_is_rejected_without_calling_the_model(self):
        with mock.patch("core.model_router.call_text") as call_text:
            result = canvas_plan.decompose_goal_to_canvas("   ")

        self.assertFalse(result["ok"])
        call_text.assert_not_called()

    def test_non_json_response_is_rejected_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch("core.model_router.call_text", return_value="Sure, here's a plan: step one, step two."):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertIn("not parseable JSON", result["error"])
            self.assertEqual(result["raw_text"], "Sure, here's a plan: step one, step two.")
            self.assertFalse((root / "Canvases").exists())

    def test_missing_plan_node_is_rejected(self):
        payload = self._good_payload()
        for node in payload["nodes"]:
            if node["role"] == "plan":
                node["role"] = "research"
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("Expected exactly one node with role 'plan'", result["error"])

    def test_unrecognised_role_is_rejected(self):
        payload = self._good_payload()
        payload["nodes"][1]["role"] = "not_a_real_role"
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("unrecognised role", result["error"])

    def test_orphan_non_plan_node_is_rejected(self):
        # Caught live: the model left a research node with no depends_on,
        # leaving the plan node disconnected from the rest of the graph.
        payload = self._good_payload()
        payload["nodes"][1]["depends_on"] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("has no depends_on", result["error"])
        self.assertFalse((root / "Canvases").exists())

    def test_retry_succeeds_after_a_failed_first_attempt(self):
        broken = self._good_payload()
        broken["nodes"][1]["depends_on"] = []
        fixed = self._good_payload()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch(
                "core.model_router.call_text", side_effect=[json.dumps(broken), json.dumps(fixed)]
            ) as call_text:
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["attempts"], 2)
            self.assertEqual(call_text.call_count, 2)
            # the second attempt's prompt must carry the first attempt's
            # validation failure back to the model
            second_prompt = call_text.call_args_list[1].args[0]
            self.assertIn("A prior attempt was rejected", second_prompt)
            self.assertIn("has no depends_on", second_prompt)

    def test_retry_gives_up_after_max_attempts_and_reports_the_final_failure(self):
        broken = self._good_payload()
        broken["nodes"][1]["depends_on"] = []
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(broken)) as call_text:
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg, max_attempts=2)

            self.assertFalse(result["ok"])
            self.assertEqual(result["attempts"], 2)
            self.assertEqual(call_text.call_count, 2)
            self.assertIn("has no depends_on", result["error"])

    def test_first_attempt_success_makes_only_one_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch(
                "core.model_router.call_text", return_value=json.dumps(self._good_payload())
            ) as call_text:
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["attempts"], 1)
            call_text.assert_called_once()

    def test_dependency_cycle_is_not_retried(self):
        # A cycle is a different failure class than the validation problems
        # the retry loop targets -- deliberately a one-shot failure.
        payload = {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Anchor.", "depends_on": []},
                {"id": "a", "role": "research", "prose": "Step A.", "depends_on": ["root", "b"]},
                {"id": "b", "role": "implementation", "prose": "Step B.", "depends_on": ["a"]},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)) as call_text:
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertIn("cycle", result["error"])
            call_text.assert_called_once()

    def test_dangling_depends_on_is_rejected(self):
        payload = self._good_payload()
        payload["nodes"][1]["depends_on"] = ["some_node_that_does_not_exist"]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("depends_on unknown id", result["error"])

    def test_dependency_cycle_is_rejected(self):
        payload = {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Anchor.", "depends_on": []},
                {"id": "a", "role": "research", "prose": "Step A.", "depends_on": ["root", "b"]},
                {"id": "b", "role": "implementation", "prose": "Step B.", "depends_on": ["a"]},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("cycle", result["error"])
        self.assertFalse((root / "Canvases").exists())

    def test_duplicate_slugified_ids_are_disambiguated_and_edges_still_resolve(self):
        # Two raw ids that collide once slugified ("Step 1!" and "Step 1?" both
        # become "step_1") must not silently merge into one node, and any
        # depends_on referencing either original id must still land on the
        # correct (disambiguated) node -- this is the exact bug caught and
        # fixed mid-implementation.
        payload = {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Anchor.", "depends_on": []},
                {"id": "Step 1!", "role": "research", "prose": "First.", "depends_on": ["root"]},
                {"id": "Step 1?", "role": "implementation", "prose": "Second.", "depends_on": ["Step 1!"]},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)):
                result = canvas_plan.decompose_goal_to_canvas("Fix the login bug", cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["node_count"], 3)
            document = canvas.load_canvas(Path(result["canvas_path"]))
            self.assertEqual(len(document["nodes"]), 3)
            node_ids = {node["id"] for node in document["nodes"]}
            self.assertEqual(len(node_ids), 3)
            self.assertEqual(len(document["edges"]), 2)

    def test_canvas_name_override_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._good_payload())):
                result = canvas_plan.decompose_goal_to_canvas(
                    "Fix the login bug", canvas_name="Canvases/JARVIS/custom_name.canvas", cfg=cfg
                )

            self.assertTrue(result["ok"], result)
            self.assertTrue(Path(result["canvas_path"]).name, "custom_name.canvas")


class DecomposeBranchAndNoteTests(unittest.TestCase):
    """WS4c: a multi-branch decomposition round-trips through
    decompose_goal_to_canvas -- branch mirrored to a top-level key, note
    nodes excluded only at compile time (still present in the canvas)."""

    def _branched_payload(self) -> dict:
        return {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Ship a login page with OAuth.", "depends_on": []},
                {
                    "id": "b_login_ui",
                    "role": "research",
                    "directives": {"branch": "B"},
                    "prose": "Design the login page UI.",
                    "depends_on": ["root"],
                },
                {
                    "id": "a_oauth_flow",
                    "role": "research",
                    "directives": {"branch": "A"},
                    "prose": "Investigate the OAuth provider's flow.",
                    "depends_on": ["b_login_ui"],
                },
                {
                    "id": "a_oauth_note",
                    "role": "note",
                    "directives": {"branch": "A"},
                    "prose": "The provider requires a callback URL registered up front.",
                    "depends_on": ["a_oauth_flow"],
                },
                {
                    "id": "b_review_callback",
                    "role": "review",
                    "directives": {"branch": "B"},
                    "prose": "Reconsider the login UI given the callback URL requirement.",
                    "depends_on": ["a_oauth_note"],
                },
            ],
            "rationale": "Two branches: OAuth investigation (A) feeds a note back to the login UI branch (B).",
        }

    def test_branch_directive_is_mirrored_to_a_top_level_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._branched_payload())):
                result = canvas_plan.decompose_goal_to_canvas("Ship a login page with OAuth", cfg=cfg)

            self.assertTrue(result["ok"], result)
            document = canvas.load_canvas(Path(result["canvas_path"]))
            by_id = {node["id"]: node for node in document["nodes"]}
            self.assertEqual(by_id["a_oauth_flow"]["branch"], "A")
            self.assertEqual(by_id["b_login_ui"]["branch"], "B")
            self.assertIn("branch: A", by_id["a_oauth_flow"]["text"])

            # a note node still exists as a real canvas node (readable by a
            # human/critique-model) even though compile_canvas will exclude
            # it from the executed steps
            note_node = by_id["a_oauth_note"]
            self.assertIn("role: note", note_node["text"])

            # the canvas as a whole must still compile cleanly, with the
            # review's depends_on resolving through the note
            workflow = canvas_plan.compile_canvas(document, workflow_id="branched", name="Branched")
            review_step = next(s for s in workflow["steps"] if s["step_type"] == "review")
            oauth_step_id = canvas_plan.node_step_id("a_oauth_flow")
            self.assertEqual(review_step["depends_on"], [oauth_step_id])

    def test_two_branches_land_in_distinct_columns_after_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._branched_payload())):
                result = canvas_plan.decompose_goal_to_canvas("Ship a login page with OAuth", cfg=cfg)

            document = canvas.load_canvas(Path(result["canvas_path"]))
            by_id = {node["id"]: node for node in document["nodes"]}
            a_x = by_id["a_oauth_flow"]["x"]
            b_x = by_id["b_login_ui"]["x"]
            self.assertNotEqual(a_x, b_x)


class DecomposeDeliverablesTests(unittest.TestCase):
    """WS4d: deliverables round-trip through decompose_goal_to_canvas into
    real acceptance_criteria, and are surfaced to the critique pass."""

    def _payload_with_deliverables(self) -> dict:
        return {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Ship the report script.", "depends_on": []},
                {
                    "id": "build_script",
                    "role": "implementation",
                    "prose": "Write the report-generating script.",
                    "depends_on": ["root"],
                    "deliverables": ["A script exists at scripts/report.py.", "Running it prints a summary table."],
                },
            ],
        }

    def test_deliverables_are_mirrored_and_rendered_in_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._payload_with_deliverables())):
                result = canvas_plan.decompose_goal_to_canvas("Ship the report script", cfg=cfg)

            self.assertTrue(result["ok"], result)
            document = canvas.load_canvas(Path(result["canvas_path"]))
            by_id = {node["id"]: node for node in document["nodes"]}
            build_node = by_id["build_script"]
            self.assertEqual(
                build_node["deliverables"],
                ["A script exists at scripts/report.py.", "Running it prints a summary table."],
            )
            self.assertIn("Deliverables:", build_node["text"])
            self.assertIn("A script exists at scripts/report.py.", build_node["text"])

    def test_deliverables_compile_into_real_acceptance_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._payload_with_deliverables())):
                result = canvas_plan.decompose_goal_to_canvas("Ship the report script", cfg=cfg)

            document = canvas.load_canvas(Path(result["canvas_path"]))
            workflow = canvas_plan.compile_canvas(document, workflow_id="deliverables_test")
            build_step = next(s for s in workflow["steps"] if s["step_type"] == "tool")
            self.assertEqual(
                build_step["acceptance_criteria"]["deliverables"],
                ["A script exists at scripts/report.py.", "Running it prints a summary table."],
            )

    def test_deliverables_surface_in_critique_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(self._payload_with_deliverables())):
                result = canvas_plan.decompose_goal_to_canvas("Ship the report script", cfg=cfg)

            document = canvas.load_canvas(Path(result["canvas_path"]))
            summary = canvas_plan._plan_summary_for_critique(document)
            build_entry = next(item for item in summary if item["id"] == "build_script")
            self.assertEqual(
                build_entry["deliverables"],
                ["A script exists at scripts/report.py.", "Running it prints a summary table."],
            )

    def test_node_without_deliverables_gets_bare_acceptance_criteria(self):
        payload = {
            "nodes": [_node("a", "role: research\nInvestigate.", role="research")],
            "edges": [],
        }
        workflow = canvas_plan.compile_canvas(payload, workflow_id="no_deliverables")
        self.assertEqual(workflow["steps"][0]["acceptance_criteria"], {"required": True})

    def test_bare_string_deliverable_is_coerced_not_rejected(self):
        # Caught live: the model reliably writes a single deliverable as a
        # bare string despite the schema showing an array. Coerce rather
        # than fail the whole decomposition over one forgivable format slip.
        payload = {
            "nodes": [
                {"id": "root", "role": "plan", "prose": "Ship it.", "depends_on": []},
                {
                    "id": "build",
                    "role": "implementation",
                    "prose": "Build it.",
                    "depends_on": ["root"],
                    "deliverables": "config loaded into memory as Python dict.",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(Path(tmp))
            with mock.patch("core.model_router.call_text", return_value=json.dumps(payload)):
                result = canvas_plan.decompose_goal_to_canvas("Ship it", cfg=cfg)

            self.assertTrue(result["ok"], result)
            document = canvas.load_canvas(Path(result["canvas_path"]))
            by_id = {node["id"]: node for node in document["nodes"]}
            self.assertEqual(by_id["build"]["deliverables"], ["config loaded into memory as Python dict."])


def _critique_json(verdict: str, *, missing_steps=None, concerns=None, rationale: str = "") -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "missing_steps": missing_steps or [],
            "concerns": concerns or [],
            "rationale": rationale or f"Verdict is {verdict}.",
        }
    )


class CritiqueCanvasPlanTests(unittest.TestCase):
    """WS4b: the plan-level critique pass (extends T5's per-node review)."""

    def _write_plan_canvas(self, root: Path) -> Path:
        path = root / "Canvases" / "JARVIS" / "plan.canvas"
        payload = {
            "nodes": [
                _node("root", "role: plan\nShip the thing.", role="plan"),
                _node("a", "role: research\nInvestigate.", role="research"),
            ],
            "edges": [_edge("e1", "root", "a")],
        }
        canvas.write_canvas(path, payload)
        return path

    def test_well_formed_critique_is_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            canvas_path = self._write_plan_canvas(root)
            response = _critique_json(
                "caution", concerns=["No rollback step if the change fails."], rationale="Usable but risky."
            )
            with mock.patch("core.model_router.call_text", return_value=response) as call_text:
                result = canvas_plan.critique_canvas_plan(canvas_path, goal="Ship the thing", cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["verdict"], "caution")
            self.assertEqual(result["concerns"], ["No rollback step if the change fails."])
            self.assertEqual(result["rationale"], "Usable but risky.")
            self.assertEqual(call_text.call_args.kwargs["role"], "planner")
            # the critic sees the plan's actual structure, not just the goal text
            prompt_arg = call_text.call_args.args[0]
            self.assertIn('"role": "research"', prompt_arg.replace("'", '"'))

    def test_non_json_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            canvas_path = self._write_plan_canvas(root)
            with mock.patch("core.model_router.call_text", return_value="Looks fine to me!"):
                result = canvas_plan.critique_canvas_plan(canvas_path, cfg=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("not parseable JSON", result["error"])

    def test_unrecognised_verdict_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            canvas_path = self._write_plan_canvas(root)
            with mock.patch("core.model_router.call_text", return_value=_critique_json("maybe")):
                result = canvas_plan.critique_canvas_plan(canvas_path, cfg=cfg)

        self.assertFalse(result["ok"])
        self.assertIn("unrecognised verdict", result["error"])

    def test_verification_before_implementation_escalates_even_if_the_model_approves(self):
        # Caught live: the model itself rubber-stamped a plan where the
        # verification node ran before the implementation node it was meant
        # to verify even existed. Deterministic backstop must catch this
        # regardless of what the model says.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "bad_order.canvas"
            payload = {
                "nodes": [
                    _node("root", "role: plan\nShip it.", role="plan"),
                    _node("verify", "role: verification\nRun the tests.", role="verification"),
                    _node("build", "role: implementation\nBuild it.", role="implementation"),
                ],
                "edges": [_edge("e1", "root", "verify"), _edge("e2", "verify", "build")],
            }
            canvas.write_canvas(path, payload)
            with mock.patch(
                "core.model_router.call_text",
                return_value=_critique_json("approve", rationale="Looks fine."),
            ):
                result = canvas_plan.critique_canvas_plan(path, cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["verdict"], "re_review")
            self.assertTrue(any("does not depend" in c for c in result["concerns"]))

    def test_correctly_ordered_verification_does_not_trigger_the_backstop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "good_order.canvas"
            payload = {
                "nodes": [
                    _node("root", "role: plan\nShip it.", role="plan"),
                    _node("build", "role: implementation\nBuild it.", role="implementation"),
                    _node("verify", "role: verification\nRun the tests.", role="verification"),
                ],
                "edges": [_edge("e1", "root", "build"), _edge("e2", "build", "verify")],
            }
            canvas.write_canvas(path, payload)
            with mock.patch(
                "core.model_router.call_text",
                return_value=_critique_json("approve", rationale="Looks fine."),
            ):
                result = canvas_plan.critique_canvas_plan(path, cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["verdict"], "approve")
            self.assertEqual(result["concerns"], [])

    def test_empty_canvas_is_rejected_without_calling_the_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            path = root / "Canvases" / "JARVIS" / "empty.canvas"
            canvas.write_canvas(path, {"nodes": [], "edges": []})
            with mock.patch("core.model_router.call_text") as call_text:
                result = canvas_plan.critique_canvas_plan(path, cfg=cfg)

        self.assertFalse(result["ok"])
        call_text.assert_not_called()


class CritiqueAndProposePlanTests(unittest.TestCase):
    """WS4b: D5's weighted refine loop -- decompose -> critique -> (re_review
    loops, caution/reject pull a human in) -> propose."""

    def _decompose_json(self, *, second_node_id: str = "a") -> str:
        return json.dumps(
            {
                "nodes": [
                    {"id": "root", "role": "plan", "prose": "Ship it.", "depends_on": []},
                    {"id": second_node_id, "role": "research", "prose": "Look into it.", "depends_on": ["root"]},
                ],
                "rationale": "Simple two-step plan.",
            }
        )

    def test_approve_verdict_proposes_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch(
                "core.model_router.call_text",
                side_effect=[self._decompose_json(), _critique_json("approve", rationale="Looks complete.")],
            ):
                result = canvas_plan.critique_and_propose_plan("Ship the thing", workflow_id="demo", cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertTrue(result["proposed"])
            self.assertEqual(result["verdict"], "approve")
            self.assertTrue(Path(result["note_path"]).exists())
            self.assertTrue(Path(result["critique_note_path"]).exists())
            critique_text = Path(result["critique_note_path"]).read_text(encoding="utf-8")
            self.assertIn("Looks complete.", critique_text)
            # D5: the critique is a linked Obsidian note connected to the plan --
            # always, not only when there's something to warn about.
            approval_text = Path(result["note_path"]).read_text(encoding="utf-8")
            critique_stem = Path(result["critique_note_path"]).stem
            self.assertIn(f"[[{critique_stem}]]", approval_text)
            self.assertNotIn("Plan critique flagged a concern", approval_text)

    def test_caution_verdict_proposes_with_a_warning_callout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch(
                "core.model_router.call_text",
                side_effect=[
                    self._decompose_json(),
                    _critique_json("caution", rationale="No rollback plan.", concerns=["No rollback plan."]),
                ],
            ):
                result = canvas_plan.critique_and_propose_plan("Ship the thing", workflow_id="demo", cfg=cfg)

            self.assertTrue(result["proposed"])
            self.assertEqual(result["verdict"], "caution")
            approval_text = Path(result["note_path"]).read_text(encoding="utf-8")
            self.assertIn("Plan critique flagged a concern", approval_text)
            self.assertIn("No rollback plan.", approval_text)
            critique_stem = Path(result["critique_note_path"]).stem
            self.assertIn(f"[[{critique_stem}]]", approval_text)

    def test_reject_verdict_does_not_propose(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch(
                "core.model_router.call_text",
                side_effect=[self._decompose_json(), _critique_json("reject", rationale="Goal is unclear.")],
            ):
                result = canvas_plan.critique_and_propose_plan("Ship the thing", workflow_id="demo", cfg=cfg)

            self.assertTrue(result["ok"], result)
            self.assertFalse(result["proposed"])
            self.assertEqual(result["verdict"], "reject")
            self.assertTrue(Path(result["critique_note_path"]).exists())
            # the critique note itself lives in Plans/, but no approval note
            # should have been created -- reject must not call propose
            self.assertFalse((root / "Plans" / "canvas-approval-demo.md").exists())

    def test_re_review_loops_back_and_then_approves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            responses = [
                self._decompose_json(second_node_id="a"),
                _critique_json("re_review", missing_steps=["add a verification step"], rationale="Missing verification."),
                self._decompose_json(second_node_id="b"),
                _critique_json("approve", rationale="Now complete."),
            ]
            with mock.patch("core.model_router.call_text", side_effect=responses) as call_text:
                result = canvas_plan.critique_and_propose_plan(
                    "Ship the thing", workflow_id="demo", max_rewrites=2, cfg=cfg
                )

            self.assertTrue(result["proposed"])
            self.assertEqual(result["verdict"], "approve")
            # both critique revisions should exist as separate linked notes
            self.assertTrue((root / "Plans" / "canvas-critique-demo-r1.md").exists())
            self.assertTrue((root / "Plans" / "canvas-critique-demo-r2.md").exists())
            # the rewrite's decompose call must have seen the critique's own feedback
            second_decompose_prompt = call_text.call_args_list[2].args[0]
            self.assertIn("add a verification step", second_decompose_prompt)

    def test_re_review_exhausting_rewrite_budget_is_treated_as_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            responses = [
                self._decompose_json(second_node_id="a"),
                _critique_json("re_review", missing_steps=["still missing something"]),
                self._decompose_json(second_node_id="b"),
                _critique_json("re_review", missing_steps=["still missing something"]),
            ]
            with mock.patch("core.model_router.call_text", side_effect=responses):
                result = canvas_plan.critique_and_propose_plan(
                    "Ship the thing", workflow_id="demo", max_rewrites=1, cfg=cfg
                )

            self.assertTrue(result["ok"], result)
            self.assertFalse(result["proposed"])
            self.assertEqual(result["verdict"], "re_review")
            self.assertTrue((root / "Plans" / "canvas-critique-demo-r1.md").exists())
            self.assertTrue((root / "Plans" / "canvas-critique-demo-r2.md").exists())
            self.assertFalse((root / "Plans" / "canvas-approval-demo.md").exists())

    def test_critique_failure_short_circuits_without_proposing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = _cfg(root)
            with mock.patch(
                "core.model_router.call_text", side_effect=[self._decompose_json(), "not json at all"]
            ):
                result = canvas_plan.critique_and_propose_plan("Ship the thing", workflow_id="demo", cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertIn("canvas_path", result)
            self.assertFalse((root / "Plans").exists())


if __name__ == "__main__":
    unittest.main()
