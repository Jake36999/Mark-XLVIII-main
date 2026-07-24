import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import plan_workflow as pw
from actions import jarvis_memory as jm


def _check_option(note_path: Path, option: str, *, fill: str = "") -> None:
    """Simulate a human checking a box (and filling a callout) in a note."""
    metadata, body, _ = jm.read_note(note_path)
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
    note_path.write_text(f"{jm.render_frontmatter(metadata)}\n\n{body}", encoding="utf-8")


class PlanWorkflowTests(unittest.TestCase):
    def cfg(self, root: Path) -> dict:
        resolved = jm.resolve_config(
            {
                "jarvis_notes_root": str(root),
                "remember_enabled": False,
                "remember_project_id": "jarvis_notes",
                "remember_project_name": "Jarvis Notes",
            }
        )
        # Test isolation: START PLAN/approve gate on a healthy worker via a live
        # model probe. These tests exercise plan mechanics, not model availability,
        # so bypass the gate. NOTE: jm.resolve_config returns a curated dict and
        # drops unknown keys, so these control-plane flags must be set on the
        # resolved dict directly, not passed as overrides.
        resolved["enforce_model_quality_floor"] = False
        resolved["model_health_enabled"] = False
        resolved["model_health_probe_enabled"] = False
        return resolved

    def web_payload(self):
        return {
            "ok": True,
            "retrieved_at": "2026-07-21T10:00:00Z",
            "results": [
                {
                    "title": "Planning Systems Need Review Gates",
                    "snippet": "Review gates reduce accidental execution risk.",
                    "url": "https://example.com/planning-gates",
                    "source": "Example Research",
                    "published_at": "2026-07-21",
                    "retrieved_at": "2026-07-21T10:00:00Z",
                    "backend": "test",
                }
            ],
        }

    def test_create_plan_writes_research_backed_vault_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                result = pw.create_plan(
                    "Improve JARVIS long form plans and gated execution",
                    cfg=cfg,
                    internet=True,
                    max_web_results=3,
                )

            path = Path(result["path"])
            metadata, body, _ = jm.read_note(path)

            self.assertTrue(result["ok"])
            self.assertTrue(path.exists())
            self.assertIn("Plans", path.parts)
            self.assertEqual(metadata["type"], "plan")
            self.assertEqual(metadata["approval_state"], "pending_review")
            self.assertEqual(metadata["workflow_id"], pw.PLAN_WORKFLOW_ID)
            self.assertIn("## Research Notes", body)
            self.assertIn("https://example.com/planning-gates", body)
            self.assertIn("## Subagent Delegation", body)
            self.assertIn("## Approval Gates", body)
            self.assertTrue(result["reindex"]["ok"])
            self.assertIn("## Approval Decision", body)
            self.assertIn("- [ ] **Approve**", body)
            self.assertIn("- [ ] **Correct**", body)
            self.assertIn("- [ ] **Deny**", body)

    def test_evaluate_plan_approval_pending_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Evaluate approval pending case", cfg=cfg)

            result = pw.evaluate_plan_approval(created["path"], cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "pending")

    def test_evaluate_plan_approval_ambiguous_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Evaluate approval ambiguous case", cfg=cfg)
            note_path = Path(created["path"])
            _check_option(note_path, "Approve")
            _check_option(note_path, "Deny")

            result = pw.evaluate_plan_approval(created["path"], cfg=cfg)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "ambiguous")

    def test_evaluate_plan_approval_approve_delegates_to_approve_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Evaluate approval approve case", cfg=cfg)
            _check_option(Path(created["path"]), "Approve")

            result = pw.evaluate_plan_approval(created["path"], cfg=cfg)
            metadata, _body, _ = jm.read_note(Path(created["path"]))

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "approved")
            self.assertEqual(metadata["approval_state"], "approved")
            self.assertEqual(metadata["execution_state"], "ready")

    def test_evaluate_plan_approval_correct_delegates_to_revise_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Evaluate approval correction case", cfg=cfg)
            _check_option(Path(created["path"]), "Correct", fill="Split the first milestone into two steps.")

            result = pw.evaluate_plan_approval(created["path"], cfg=cfg)
            metadata, body, _ = jm.read_note(Path(created["path"]))

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "revision_requested")
            self.assertEqual(metadata["approval_state"], "revision_requested")
            self.assertIn("Split the first milestone into two steps.", body)
            # revise_plan resets the decision to blank for the new plan_version
            self.assertIn("- [ ] **Approve**", body)

    def test_evaluate_plan_approval_deny_records_reason_without_approving(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Evaluate approval deny case", cfg=cfg)
            _check_option(Path(created["path"]), "Deny", fill="This touches production credentials.")

            result = pw.evaluate_plan_approval(created["path"], cfg=cfg)
            metadata, _body, _ = jm.read_note(Path(created["path"]))

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "denied")
            self.assertIn("production credentials", result["reason"])
            self.assertEqual(metadata["approval_state"], "denied")
            self.assertNotEqual(metadata["approval_state"], "approved")

    def test_plan_workflow_dispatcher_evaluates_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Dispatcher evaluate approval case", cfg=cfg)
            _check_option(Path(created["path"]), "Approve")

            payload = json.loads(
                pw.plan_workflow({"operation": "evaluate_approval", "path": created["path"], "_config": cfg})
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "approved")

    def test_revise_and_approve_plan_update_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Build a planning workflow", cfg=cfg)

            revised = pw.revise_plan(created["path"], "Make the first milestone smaller.", cfg=cfg)
            approved = pw.approve_plan(created["path"], cfg=cfg)
            metadata, body, _ = jm.read_note(Path(created["path"]))

            self.assertTrue(revised["ok"])
            self.assertTrue(approved["ok"])
            self.assertEqual(metadata["approval_state"], "approved")
            self.assertEqual(metadata["execution_state"], "ready")
            self.assertIn("Make the first milestone smaller.", body)

    def test_start_plan_creates_execution_run_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Build a start-plan execution gate", cfg=cfg)

            started = pw.start_plan(created["path"], cfg=cfg, agent_count=1, max_packets=5)
            plan_metadata, _, _ = jm.read_note(Path(created["path"]))
            run_path = Path(started["execution_summary_path"])
            run_metadata, run_body, _ = jm.read_note(run_path)

            self.assertTrue(started["ok"])
            self.assertTrue(run_path.exists())
            self.assertEqual(plan_metadata["approval_state"], "approved")
            self.assertEqual(plan_metadata["execution_state"], "queued")
            self.assertEqual(run_metadata["type"], "execution_summary")
            self.assertEqual(run_metadata["execution_state"], "queued")
            self.assertEqual(run_metadata["plan_path"], created["path"])
            self.assertIn("## System Prompt Injection", run_body)
            self.assertIn("## Sequenced Work Packets", run_body)
            self.assertIn("## Agent Delegation", run_body)
            self.assertIn("## Synthesis Protocol", run_body)
            self.assertTrue(started["packets"])
            self.assertTrue(started["run_id"])
            bundle_path = Path(started["bundle_path"])
            self.assertTrue((bundle_path / "workflow.yaml").exists())
            self.assertTrue((bundle_path / "work-items.json").exists())
            self.assertTrue((bundle_path / "approval.json").exists())

    def test_plan_workflow_dispatcher_starts_latest_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                pw.create_plan("Start the newest available plan", cfg=cfg)

            payload = json.loads(
                pw.plan_workflow(
                    {
                        "operation": "start_plan",
                        "path": "latest",
                        "_config": cfg,
                    }
                )
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["execution_state"], "queued")
            self.assertIn("execution_summary_path", payload)

    def test_plan_workflow_dispatcher_revises_latest_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                created = pw.create_plan("Revise the newest available plan", cfg=cfg)

            payload = json.loads(
                pw.plan_workflow(
                    {
                        "operation": "revise_plan",
                        "path": "latest",
                        "revision": "Add a smaller first step.",
                        "_config": cfg,
                    }
                )
            )
            metadata, body, _ = jm.read_note(Path(created["path"]))

            self.assertTrue(payload["ok"])
            self.assertEqual(metadata["approval_state"], "revision_requested")
            self.assertIn("Add a smaller first step.", body)

    def test_plan_workflow_dispatcher_creates_summary_and_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            summary = json.loads(
                pw.plan_workflow(
                    {
                        "operation": "create_summary",
                        "title": "Plan Execution Summary",
                        "outcome": "Milestones completed.",
                        "_config": cfg,
                    }
                )
            )
            blocker = json.loads(
                pw.plan_workflow(
                    {
                        "operation": "create_blocker",
                        "title": "Needs Design Choice",
                        "blocker": "User needs to pick storage policy.",
                        "_config": cfg,
                    }
                )
            )

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["metadata"]["type"], "execution_summary")
            self.assertTrue(blocker["ok"])
            self.assertEqual(blocker["metadata"]["type"], "blocker")
            self.assertEqual(blocker["metadata"]["status"], "blocked")

    def test_list_templates_exposes_plan_document_types(self):
        payload = json.loads(pw.plan_workflow({"operation": "list_templates"}))

        self.assertTrue(payload["ok"])
        self.assertIn("plan", payload["templates"])
        self.assertIn("execution_run", payload["templates"])
        self.assertIn("execution_summary", payload["templates"])
        self.assertIn("blocker", payload["templates"])
        self.assertIn("decision_record", payload["templates"])

    def test_specialized_job_runner_plan_compiles_to_registered_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "job_runner_demo"
            prompt = (
                f"Plan and build an isolated modular Python job-runner demo under {output_root}. "
                "Use a replaceable task module and telemetry adapter."
            )

            tasks = pw._steps_from_prompt(prompt)
            workflow = pw._workflow_from_tasks("plan-job-runner", 1, tasks, prompt)
            targets = [step["target"] for step in workflow["steps"]]

            self.assertEqual(
                targets,
                ["approval_gate", "build_python_job_runner", "validate_python_project", "vault_create_note"],
            )
            self.assertEqual(workflow["steps"][1]["inputs"]["output_root"], str(output_root))

    def test_executable_task_extraction_does_not_include_status_or_user_control_rows(self):
        body = """## Workflow Plan

1. Build the approved artifact.
2. Validate the approved artifact.

## Milestones

| Milestone | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Research and context | JARVIS/User | Not started | |

## Next Actions

- [ ] User reviews this plan in Obsidian.
- [ ] User approves execution.
"""

        self.assertEqual(
            pw._extract_plan_tasks(body),
            ["Build the approved artifact", "Validate the approved artifact"],
        )

    def test_section_extraction_keeps_nested_obsidian_headings(self):
        body = """## Scope

### In scope

- Visible approved constraint.

### Out of scope

- Another approved constraint.

## Milestones

- Later section.
"""

        scope = pw._extract_section(body, "Scope")

        self.assertIn("### In scope", scope)
        self.assertIn("### Out of scope", scope)
        self.assertNotIn("Later section", scope)

    def test_specialized_documentation_plan_binds_validation_to_created_artifacts(self):
        prompt = (
            "Review the Markdown vault and create an Evaluation MOC, Workflow Architecture Report, "
            "and Knowledge Gaps and Next Actions Report."
        )

        tasks = pw._steps_from_prompt(prompt)
        workflow = pw._workflow_from_tasks("plan-docs", 1, tasks, prompt)
        validation = workflow["steps"][2]

        self.assertEqual(workflow["steps"][1]["target"], "create_vault_documentation_set")
        self.assertEqual(validation["target"], "validate_vault_artifacts")
        self.assertEqual(
            validation["inputs"]["artifacts"]["bind"],
            {"from_step": "p02", "path": "result.artifacts"},
        )

    def test_user_edit_pauses_stale_run_and_survives_versioned_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            prompt = (
                "Review the Markdown vault and create an Evaluation MOC, Workflow Architecture Report, "
                "and Knowledge Gaps and Next Actions Report."
            )
            with mock.patch("actions.plan_workflow.structured_web_search", return_value=self.web_payload()):
                plan = pw.create_plan(prompt, cfg=cfg, internet=False)
            started = pw.start_plan(plan["path"], cfg=cfg)
            path = Path(plan["path"])
            original = path.read_text(encoding="utf-8")
            user_marker = "- Preserve this user-authored evaluation constraint."
            path.write_text(
                original.replace("### Out of scope", f"{user_marker}\n\n### Out of scope"),
                encoding="utf-8",
            )

            paused = pw.execute_plan_run(started["run_id"], cfg=cfg)
            revised = pw.revise_plan(str(path), "Retain the user-authored constraint and rebind approval.", cfg=cfg)
            resumed = pw.start_plan(str(path), cfg=cfg)
            metadata, body, _ = jm.read_note(path)

            self.assertEqual(paused["status"], "PAUSED_HASH_DRIFT")
            self.assertTrue(revised["ok"])
            self.assertTrue(resumed["ok"])
            self.assertNotEqual(started["run_id"], resumed["run_id"])
            self.assertEqual(metadata["plan_version"], 2)
            self.assertEqual(metadata["execution_state"], "queued")
            self.assertIn(user_marker, body)

    def test_local_only_coding_plan_preflights_and_completes_without_remember_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = jm.resolve_config(
                {
                    "jarvis_notes_root": str(root),
                    "remember_enabled": False,
                }
            )
            output_root = root / "Artifacts" / "job_runner_demo"
            prompt = (
                f"Plan and build an isolated modular Python job-runner demo under {output_root}. "
                "Use a replaceable task module and telemetry adapter."
            )
            created = pw.create_plan(prompt, cfg=cfg, internet=False)
            started = pw.start_plan(created["path"], cfg=cfg)
            executed = pw.execute_plan_run(started["run_id"], cfg=cfg)

            self.assertTrue(created["ok"])
            self.assertTrue(started["ok"])
            self.assertTrue(executed["ok"])
            self.assertEqual(executed["run"]["status"], "COMPLETED")
            self.assertTrue((output_root / "job_runner.py").is_file())
            self.assertTrue((output_root / "tests" / "test_job_runner.py").is_file())
            self.assertFalse(list((root / "Blockers").glob("*.md")) if (root / "Blockers").exists() else [])

    def test_coding_hook_preflight_rejects_output_outside_registered_roots(self):
        from actions.dual_orchestrator import WorkflowRuntime, compile_workflow

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            output_root = Path(outside) / "job_runner_demo"
            prompt = (
                f"Plan and build an isolated modular Python job-runner demo under {output_root}. "
                "Use a replaceable task module and telemetry adapter."
            )
            tasks = pw._steps_from_prompt(prompt)
            workflow = pw._workflow_from_tasks("plan-job-runner", 1, tasks, prompt)
            runtime = WorkflowRuntime(root)

            with self.assertRaisesRegex(ValueError, "outside registered workflow roots"):
                compile_workflow(
                    workflow,
                    tool_names={"web_search", "jarvis_memory", "project_operator", "capability_registry"},
                    hook_registry=runtime.hooks,
                    command_registry=runtime.commands,
                )

    def test_online_resource_plan_compiles_to_cited_research_steps(self):
        prompt = "search online and find potential resources for analysing Intel 5300 CSI packets"

        tasks = pw._steps_from_prompt(prompt)
        workflow = pw._workflow_from_tasks("plan-csi", 1, tasks, prompt)

        self.assertIn("Collect cited web sources", tasks[0])
        self.assertEqual(workflow["steps"][0]["target"], "web_search")
        self.assertTrue(workflow["steps"][0]["inputs"]["require_citations"])
        self.assertEqual(workflow["steps"][1]["target"], "jarvis_memory")
        self.assertEqual(workflow["steps"][-1]["target"], "vault_create_note")

    def test_repository_learning_plan_uses_read_only_project_operation_not_openclaw(self):
        prompt = "learn about this project and read the files in this directory"

        tasks = pw._steps_from_prompt(prompt)
        workflow = pw._workflow_from_tasks("plan-learn-project", 1, tasks, prompt)

        first = workflow["steps"][0]
        self.assertEqual(first["target"], "project_operator")
        self.assertEqual(first["inputs"]["operation"], "learn_project")
        self.assertEqual(first["inputs"]["project_id"], "mark_platform")
        self.assertFalse(any(step.get("inputs", {}).get("operation") == "delegate_openclaw" for step in workflow["steps"]))


if __name__ == "__main__":
    unittest.main()


class WorkflowIdDerivationTests(unittest.TestCase):
    """Plan ids routinely start with a date; the schema requires a leading letter."""

    def test_date_leading_plan_id_becomes_schema_valid(self):
        import re

        from actions.plan_workflow import _workflow_id_from_plan

        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for plan_id in (
            "2026-07-22-plan-review-the-vault",
            "2026_07_22_plan",
            "9lives",
            "___",
            "",
            "Plan With Caps And Spaces",
        ):
            with self.subTest(plan_id=plan_id):
                self.assertRegex(_workflow_id_from_plan(plan_id), pattern)

    def test_letter_leading_ids_are_unchanged(self):
        from actions.plan_workflow import _workflow_id_from_plan

        self.assertEqual(_workflow_id_from_plan("plan-review-vault"), "plan_review_vault")

    def test_result_respects_the_length_bound(self):
        from actions.plan_workflow import _workflow_id_from_plan

        self.assertLessEqual(len(_workflow_id_from_plan("2026-" + "x" * 200)), 60)


class BundleGuardTests(unittest.TestCase):
    """An empty run_bundle must produce the intended message, not a crash."""

    def test_empty_bundle_value_is_reported_not_dereferenced(self):
        from actions import plan_workflow as pw

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "Plans" / "p.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "---\nid: p\ntitle: P\ntype: plan\nrun_bundle: ''\n---\n\n## Executable Work Items\n",
                encoding="utf-8",
            )
            result = pw._validate_plan_bundle(path, self_cfg := pw.resolve_memory_config())
            del self_cfg

        self.assertFalse(result["ok"])
        self.assertIn("run bundle is missing", result["error"].lower())
