import unittest

from actions.plan_workflow import (
    TaskMethodContext,
    TaskMethodRegistry,
    TaskMethodSpec,
    _DEFAULT_TASK_METHODS,
    _fallback_model_reasoning_step,
    default_task_method_registry,
)


def _ctx(task: str, **overrides) -> TaskMethodContext:
    lowered = task.lower()
    fields = {
        "plan_id": "plan-test",
        "step_id": "p01",
        "task": task,
        "clean_task": task,
        "lowered": lowered,
        "prompt": "a test prompt",
        "output_root": None,
        "source_path": None,
        "project_id": None,
        "multi_agent": False,
        "dependencies": [],
        "previous": "",
        "steps_so_far": [],
    }
    fields.update(overrides)
    return TaskMethodContext(**fields)


class TaskMethodRegistryTests(unittest.TestCase):
    def test_registry_is_inspectable(self):
        """The whole point: every recognized task shape is now listable by name,
        instead of only discoverable by reading a 200-line elif chain."""
        candidates = _DEFAULT_TASK_METHODS.candidates()
        method_ids = [spec.method_id for spec in candidates]

        self.assertEqual(len(method_ids), len(set(method_ids)), "method ids must be unique")
        self.assertIn("build_python_job_runner", method_ids)
        self.assertIn("web_research", method_ids)
        for spec in candidates:
            self.assertTrue(spec.description, f"{spec.method_id} has no description")

    def test_registering_duplicate_method_id_is_rejected(self):
        registry = TaskMethodRegistry()
        spec = TaskMethodSpec(
            method_id="dup",
            description="first",
            matches=lambda ctx: False,
            build=lambda ctx: {},
        )
        registry.register(spec)
        with self.assertRaises(Exception):
            registry.register(spec)

    def test_registering_method_without_description_is_rejected(self):
        registry = TaskMethodRegistry()
        with self.assertRaises(Exception):
            registry.register(TaskMethodSpec(
                method_id="no_description",
                description="",
                matches=lambda ctx: True,
                build=lambda ctx: {},
            ))

    def test_select_returns_first_matching_method_in_priority_order(self):
        ctx = _ctx("Build the modular Python job runner under /tmp/x")
        spec = _DEFAULT_TASK_METHODS.select(ctx)

        self.assertIsNotNone(spec)
        self.assertEqual(spec.method_id, "build_python_job_runner")

    def test_web_keyword_method_only_matches_after_more_specific_prefixes_miss(self):
        # "record research artifacts" must resolve to record_artifact, not web_research,
        # even though it contains the substring "research" -- registration order encodes
        # that specific-prefix methods outrank the generic keyword method.
        ctx = _ctx("Record research artifacts for the completed step")
        spec = _DEFAULT_TASK_METHODS.select(ctx)

        self.assertIsNotNone(spec)
        self.assertEqual(spec.method_id, "record_artifact")

    def test_unrecognized_task_shape_matches_no_method(self):
        ctx = _ctx("Draft a haiku about the deployment window")
        spec = _DEFAULT_TASK_METHODS.select(ctx)

        self.assertIsNone(spec)

    def test_fallback_produces_model_reasoning_step_with_defaults(self):
        ctx = _ctx("Draft a haiku about the deployment window")
        built = _fallback_model_reasoning_step(ctx)

        self.assertEqual(built["step_type"], "model_reasoning")
        self.assertEqual(built["target"], "local_worker")
        self.assertEqual(built["orchestrator"], "cognitive")
        self.assertEqual(built["risk_tier"], "T1")
        self.assertNotIn("evidence", built["inputs"])

    def test_fallback_binds_evidence_from_dependency_steps(self):
        ctx = _ctx(
            "Draft a haiku about the deployment window",
            dependencies=["p01"],
            steps_so_far=[{"step_id": "p01", "target": "web_search", "inputs": {}}],
        )
        built = _fallback_model_reasoning_step(ctx)

        self.assertEqual(built["inputs"]["evidence"], [{"bind": {"from_step": "p01", "path": "result.results"}}])

    def test_delegate_development_falls_back_to_gate_without_a_registered_project(self):
        ctx = _ctx("Delegate the approved development objective to build the feature", project_id=None)
        spec = _DEFAULT_TASK_METHODS.select(ctx)
        built = spec.build(ctx)

        self.assertEqual(built["step_type"], "gate")
        self.assertEqual(built["target"], "registered_project_required")

    def test_delegate_development_requires_confirmation_with_a_registered_project(self):
        ctx = _ctx("Delegate the approved development objective to build the feature", project_id="mark_platform")
        spec = _DEFAULT_TASK_METHODS.select(ctx)
        built = spec.build(ctx)

        self.assertEqual(built["target"], "project_operator")
        self.assertTrue(built["requires_confirmation"])
        self.assertEqual(built["risk_tier"], "T3")
        self.assertFalse(built["retry_safe"])

    def test_a_fresh_registry_starts_empty(self):
        """default_task_method_registry() builds a new instance each call --
        confirms the module-level cache isn't hiding shared mutable state."""
        registry = default_task_method_registry()
        self.assertEqual(len(registry.candidates()), len(_DEFAULT_TASK_METHODS.candidates()))
        self.assertIsNot(registry, _DEFAULT_TASK_METHODS)


if __name__ == "__main__":
    unittest.main()
