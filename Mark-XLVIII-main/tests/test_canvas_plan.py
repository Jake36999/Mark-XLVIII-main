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


if __name__ == "__main__":
    unittest.main()
