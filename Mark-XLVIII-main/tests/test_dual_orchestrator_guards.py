"""The guards that stand between an approval and real state changes.

`dual_orchestrator` is the component that executes approved work against the
user's files, repositories and delegated processes. The 2026-07-30 assessment
found it the least densely tested thing in the repository relative to its
risk -- 1,762 lines against 19 tests, while `canvas_plan`, which produces
*proposals a human then reviews*, had 160.

The existing suite covers schema validation, idempotency, concurrency and the
escalate/retry cycle. What it did not cover is everything that stops a run from
executing something the human did not approve, or executing it twice:

  * envelope integrity -- the whole approval model rests on one HMAC
  * on-disk drift -- the bundle is plain files and can change after approval
  * crash recovery -- what happens to an item that was RUNNING when the process died
  * cancellation
  * compensation
  * binding resolution between steps

Every test here runs against a real SQLite runtime in a temporary directory.
None of them reach the network, a model, or anything outside the temp vault.
"""
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from actions import dual_orchestrator as do
from tests.test_dual_orchestrator import RuntimeHarness, workflow


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _query(db_path: Path, sql: str, *params):
    """Read the runtime's own tables, closing the handle afterwards.

    `with sqlite3.connect(...)` commits but does **not** close, and on Windows
    the still-open handle makes `TemporaryDirectory` cleanup fail with a
    confusing NotADirectoryError on the .sqlite file.
    """
    with closing(sqlite3.connect(db_path)) as connection:
        return connection.execute(sql, params).fetchall()


def _write(db_path: Path, sql: str, *params) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(sql, params)
        connection.commit()


class ApprovalEnvelopeIntegrityTests(RuntimeHarness):
    """One HMAC is the difference between "the human approved this" and "someone
    edited a JSON file". Every field is signed, so every field must be checked."""

    def test_a_valid_envelope_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = do.build_approval_envelope(
                vault_root=root, plan_id="p", plan_version=1,
                approval_projection_hash="proj", workflow_hash="wf",
                manifest_hash="mf", approved_action_ids=["a"],
            )
            self.assertTrue(do.verify_approval_envelope(root, envelope))

    def test_editing_any_signed_field_invalidates_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = do.build_approval_envelope(
                vault_root=root, plan_id="p", plan_version=1,
                approval_projection_hash="proj", workflow_hash="wf",
                manifest_hash="mf", approved_action_ids=["a"],
            )
            for field, tampered in [
                ("plan_id", "other-plan"),
                ("plan_version", 2),
                ("approval_projection_hash", "different"),
                ("workflow_hash", "different"),
                ("manifest_hash", "different"),
                ("approved_action_ids", ["a", "b"]),
                ("approved_at", "2020-01-01T00:00:00Z"),
            ]:
                with self.subTest(field=field):
                    self.assertFalse(do.verify_approval_envelope(root, {**envelope, field: tampered}))

    def test_adding_an_action_that_was_never_approved_invalidates_it(self):
        """The attack this is really for: approve one harmless action, then add
        a destructive one to the list before execution."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = do.build_approval_envelope(
                vault_root=root, plan_id="p", plan_version=1,
                approval_projection_hash="proj", workflow_hash="wf",
                manifest_hash="mf", approved_action_ids=["read_something"],
            )
            envelope["approved_action_ids"] = ["read_something", "delete_everything"]
            self.assertFalse(do.verify_approval_envelope(root, envelope))

    def test_a_missing_or_empty_signature_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = do.build_approval_envelope(
                vault_root=root, plan_id="p", plan_version=1,
                approval_projection_hash="proj", workflow_hash="wf",
                manifest_hash="mf", approved_action_ids=["a"],
            )
            self.assertFalse(do.verify_approval_envelope(root, {k: v for k, v in envelope.items() if k != "signature"}))
            self.assertFalse(do.verify_approval_envelope(root, {**envelope, "signature": ""}))

    def test_an_envelope_signed_by_another_vault_is_rejected(self):
        """Keys are per-vault. An approval carried over from somewhere else is
        not an approval here."""
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            envelope = do.build_approval_envelope(
                vault_root=Path(tmp_a), plan_id="p", plan_version=1,
                approval_projection_hash="proj", workflow_hash="wf",
                manifest_hash="mf", approved_action_ids=["a"],
            )
            self.assertFalse(do.verify_approval_envelope(Path(tmp_b), envelope))

    def test_the_signing_key_is_stable_within_a_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(do.approval_signing_key(root), do.approval_signing_key(root))

    def test_the_signing_key_is_not_stored_in_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = do.approval_signing_key(root)
            on_disk = (root / ".jarvis" / "approval-signing-key.bin").read_bytes()
            self.assertNotIn(secret, on_disk)


class ExecutionRefusesTamperedBundlesTests(RuntimeHarness):
    """The bundle is three plain files on disk. Approval happens at one moment;
    execution happens later. Anything that changed in between must stop the run
    rather than execute the changed version."""

    def _prepare(self, root, handler=lambda payload: {"ok": True}):
        hooks = self.hook_registry(handler)
        raw = workflow()
        manifest = do.compile_workflow(raw, hook_registry=hooks)
        bundle = self.write_bundle(root, raw, manifest)
        runtime = do.WorkflowRuntime(root, hook_registry=hooks)
        self.register(runtime, bundle, manifest)
        return runtime, bundle, hooks

    def test_a_forged_signature_stops_execution_before_any_work(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, bundle, _ = self._prepare(root, lambda payload: calls.append(1) or {"ok": True})
            envelope = json.loads((bundle / "approval.json").read_text(encoding="utf-8"))
            envelope["signature"] = "0" * 64
            (bundle / "approval.json").write_text(json.dumps(envelope), encoding="utf-8")
            runtime.approve_run("run-test")

            result = runtime.execute_run("run-test")

        self.assertFalse(result["ok"])
        self.assertIn("signature", result["error"].lower())
        self.assertEqual(calls, [], "work ran despite an invalid approval signature")

    def test_editing_the_workflow_after_approval_is_hash_drift(self):
        """The signature would still verify -- it covers the recorded hash, not
        the file. This is the check that notices the file itself changed."""
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, bundle, _ = self._prepare(root, lambda payload: calls.append(1) or {"ok": True})
            raw = yaml.safe_load((bundle / "workflow.yaml").read_text(encoding="utf-8"))
            raw["steps"][0]["description"] = "Something the human never read"
            (bundle / "workflow.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
            runtime.approve_run("run-test")

            result = runtime.execute_run("run-test")

        self.assertEqual(result["status"], "PAUSED_HASH_DRIFT")
        self.assertEqual(calls, [], "an edited workflow was executed")

    def test_editing_the_manifest_after_approval_is_caught(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, bundle, _ = self._prepare(root, lambda payload: calls.append(1) or {"ok": True})
            manifest = json.loads((bundle / "work-items.json").read_text(encoding="utf-8"))
            manifest["items"][0]["inputs"] = {"injected": "value"}
            (bundle / "work-items.json").write_text(json.dumps(manifest), encoding="utf-8")
            runtime.approve_run("run-test")

            result = runtime.execute_run("run-test")

        self.assertFalse(result["ok"])
        self.assertIn("DRIFT", result["status"])
        self.assertEqual(calls, [], "an edited manifest was executed")

    def test_a_run_that_was_never_approved_does_not_execute(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, _, _ = self._prepare(root, lambda payload: calls.append(1) or {"ok": True})

            result = runtime.execute_run("run-test")  # no approve_run

        self.assertEqual(result["status"], "PAUSED_NOT_APPROVED")
        self.assertEqual(calls, [], "an unapproved run executed")

    def test_an_unknown_run_is_reported_rather_than_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = do.WorkflowRuntime(Path(tmp), hook_registry=self.hook_registry(lambda p: {"ok": True}))
            self.assertFalse(runtime.execute_run("no-such-run").get("ok"))


class CrashRecoveryTests(RuntimeHarness):
    """An item can be RUNNING when the process dies. What happens next is the
    difference between a safe resume and doing the same side effect twice."""

    def _prepare(self, root, *, retry_safe=True):
        hooks = self.hook_registry(lambda payload: {"ok": True})
        raw = workflow(retry_safe=retry_safe)
        manifest = do.compile_workflow(raw, hook_registry=hooks)
        bundle = self.write_bundle(root, raw, manifest)
        runtime = do.WorkflowRuntime(root, hook_registry=hooks)
        self.register(runtime, bundle, manifest)
        runtime.approve_run("run-test")
        return runtime, manifest

    def _mark_running(self, runtime, item_id, *, expires_at, owner="dead-worker"):
        _write(
            runtime.db_path,
            "UPDATE workflow_items SET state='RUNNING', lease_owner=?, lease_expires_at=? "
            "WHERE run_id='run-test' AND item_id=?",
            owner, expires_at, item_id,
        )

    def _state(self, runtime, item_id):
        rows = _query(
            runtime.db_path,
            "SELECT state FROM workflow_items WHERE run_id='run-test' AND item_id=?", item_id,
        )
        return rows[0][0]

    def test_a_live_lease_means_another_worker_owns_it(self):
        """Two processes must not run the same item. A lease that has not
        expired belongs to someone else."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime, manifest = self._prepare(Path(tmp))
            item_id = manifest["items"][0]["id"]
            self._mark_running(runtime, item_id, expires_at=_iso(datetime.now(timezone.utc) + timedelta(minutes=5)))

            result = runtime.execute_run("run-test")

        self.assertEqual(result["status"], "RUN_ALREADY_ACTIVE")
        self.assertEqual(result["lease_owner"], "dead-worker")

    def test_an_expired_lease_on_retry_safe_work_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, manifest = self._prepare(Path(tmp), retry_safe=True)
            item_id = manifest["items"][0]["id"]
            self._mark_running(runtime, item_id, expires_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=5)))

            runtime._recover_stale_items("run-test", manifest)

            self.assertEqual(self._state(runtime, item_id), "REPAIR")

    def test_an_expired_lease_on_non_retry_safe_work_is_never_silently_retried(self):
        """The whole point of `retry_safe: false`. The outcome is genuinely
        unknown -- the step may have completed its side effect before the crash
        -- so it must stop for a human rather than run again."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime, manifest = self._prepare(Path(tmp), retry_safe=False)
            item_id = manifest["items"][0]["id"]
            self._mark_running(runtime, item_id, expires_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=5)))

            runtime._recover_stale_items("run-test", manifest)

            self.assertEqual(self._state(runtime, item_id), "UNKNOWN_OUTCOME")

    def test_a_running_item_missing_from_the_manifest_pauses_the_run(self):
        """The manifest changed under a live item. Nothing sensible can be
        concluded about it, so stop."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime, manifest = self._prepare(Path(tmp))
            self._mark_running(runtime, manifest["items"][0]["id"],
                               expires_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=5)))
            emptied = {**manifest, "items": []}

            recovery = runtime._recover_stale_items("run-test", emptied)

        self.assertEqual(recovery["status"], "PAUSED_ITEM_DRIFT")


class CancellationTests(RuntimeHarness):
    def test_cancelling_stops_pending_work_from_starting(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hooks = self.hook_registry(lambda payload: calls.append(1) or {"ok": True})
            raw = workflow()
            manifest = do.compile_workflow(raw, hook_registry=hooks)
            bundle = self.write_bundle(root, raw, manifest)
            runtime = do.WorkflowRuntime(root, hook_registry=hooks)
            self.register(runtime, bundle, manifest)
            runtime.approve_run("run-test")

            runtime.request_cancel("run-test", reason="user_interrupt")
            result = runtime.execute_run("run-test")

        self.assertEqual(calls, [], "cancelled work still executed")
        self.assertNotEqual(result.get("run", {}).get("status"), "COMPLETED")

    def test_cancelling_marks_pending_items_cancelled_rather_than_leaving_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hooks = self.hook_registry(lambda payload: {"ok": True})
            raw = workflow()
            manifest = do.compile_workflow(raw, hook_registry=hooks)
            bundle = self.write_bundle(root, raw, manifest)
            runtime = do.WorkflowRuntime(root, hook_registry=hooks)
            self.register(runtime, bundle, manifest)

            runtime.request_cancel("run-test")
            states = [row[0] for row in _query(
                runtime.db_path, "SELECT state FROM workflow_items WHERE run_id='run-test'"
            )]
        self.assertEqual(set(states), {"CANCELLED"})

    def test_a_cancel_is_recorded_as_an_event_with_its_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hooks = self.hook_registry(lambda payload: {"ok": True})
            raw = workflow()
            manifest = do.compile_workflow(raw, hook_registry=hooks)
            bundle = self.write_bundle(root, raw, manifest)
            runtime = do.WorkflowRuntime(root, hook_registry=hooks)
            self.register(runtime, bundle, manifest)

            runtime.request_cancel("run-test", reason="disk_full")
            details = [row[0] for row in _query(
                runtime.db_path,
                "SELECT details_json FROM workflow_events WHERE run_id='run-test' AND event_type='cancel_requested'",
            )]
        self.assertTrue(any("disk_full" in d for d in details), f"reason not recorded: {details}")


class CompensationTests(RuntimeHarness):
    """Undoing a step whose side effect already landed.

    Two conditions gate this, and both matter: the step must declare real
    `side_effects`, and the *review* must reject it. A step that merely raised
    during dispatch has not necessarily changed anything, and a step declaring
    `side_effects: none` has nothing to undo -- compensating either would be
    its own kind of dishonesty about what happened.
    """

    def _registry(self, main_handler, comp_handler):
        registry = do.PythonHookRegistry()
        for hook_id, handler in (("test_hook", main_handler), ("undo_hook", comp_handler)):
            registry.register(do.HookSpec(hook_id=hook_id, version="1", handler=handler,
                                          input_schema={"type": "object"}, output_schema={"type": "object"}))
        return registry

    def _run(self, comp_handler, *, verdict="REJECT_REPLAN", side_effects="local_write",
             main_handler=lambda payload: {"ok": True, "summary": "wrote the file"}):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hooks = self._registry(main_handler, comp_handler)
            raw = workflow()
            raw["steps"][0]["compensation"] = "undo_hook"
            raw["steps"][0]["side_effects"] = side_effects
            raw["steps"][0]["acceptance_criteria"] = {"required": True, "independent_review": True}
            manifest = do.compile_workflow(raw, hook_registry=hooks)
            bundle = self.write_bundle(root, raw, manifest)
            runtime = do.WorkflowRuntime(
                root, hook_registry=hooks,
                reviewer=lambda item, result, defects: (verdict, ["reviewer_rejected_the_output"]),
            )
            self.register(runtime, bundle, manifest)
            runtime.approve_run("run-test")
            result = runtime.execute_run("run-test")
            phases = [row[0] for row in _query(
                runtime.db_path, "SELECT phase FROM workflow_checkpoints WHERE run_id='run-test'"
            )]
            return result, phases

    def test_a_rejected_step_with_real_side_effects_is_compensated(self):
        compensated = []
        _, phases = self._run(lambda payload: compensated.append(payload) or {"ok": True})

        self.assertTrue(compensated, "compensation never ran for a rejected step")
        self.assertIn("compensation_committed", phases)

    def test_the_compensation_receives_the_original_inputs_and_the_defects(self):
        seen = {}
        self._run(lambda payload: seen.update(payload) or {"ok": True})

        self.assertIn("original_inputs", seen)
        self.assertIn("reviewer_rejected_the_output", seen["error"])
        self.assertEqual(seen["item_id"], "first_step")

    def test_a_failing_compensation_is_recorded_not_swallowed(self):
        """The worst case: the step's effect landed, the review rejected it, and
        the undo failed too. Recording that as a clean rejection would hide real
        state left behind on disk."""

        def undo_fails(payload):
            raise RuntimeError("undo also failed")

        _, phases = self._run(undo_fails)

        self.assertIn("compensation_failed", phases)
        self.assertNotIn("compensation_committed", phases)

    def test_an_escalated_step_is_also_compensated(self):
        """ESCALATE means a human must look. The side effect should not be left
        in place while that happens."""
        compensated = []
        self._run(lambda payload: compensated.append(1) or {"ok": True}, verdict="ESCALATE")
        self.assertTrue(compensated)

    def test_a_step_with_no_side_effects_is_not_compensated(self):
        """Nothing to undo. Running an undo hook anyway would imply a change
        that never happened."""
        compensated = []
        self._run(lambda payload: compensated.append(1) or {"ok": True}, side_effects="none")
        self.assertEqual(compensated, [])

    def test_an_accepted_step_is_not_compensated(self):
        compensated = []
        _, phases = self._run(lambda payload: compensated.append(1) or {"ok": True}, verdict="ACCEPT")
        self.assertEqual(compensated, [], "compensation ran for a step that was accepted")
        self.assertIn("committed", phases)


class BindingResolutionTests(RuntimeHarness):
    """Steps pass data forward by binding to a prior step's result. A binding
    that silently resolves to the wrong thing feeds bad input into real work."""

    def test_a_binding_reads_the_named_value_from_the_source_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = do.WorkflowRuntime(Path(tmp), hook_registry=self.hook_registry(lambda p: {"ok": True}))
            results = {"first_step": {"outputs": {"path": "/vault/note.md"}}}
            resolved = runtime._resolve_bindings(
                {"target": {"bind": {"from_step": "first_step", "path": "outputs.path"}}}, results
            )
        self.assertEqual(resolved, {"target": "/vault/note.md"})

    def test_a_binding_to_a_missing_step_is_none_rather_than_a_stray_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = do.WorkflowRuntime(Path(tmp), hook_registry=self.hook_registry(lambda p: {"ok": True}))
            resolved = runtime._resolve_bindings(
                {"target": {"bind": {"from_step": "never_ran", "path": "outputs.path"}}}, {}
            )
        self.assertEqual(resolved, {"target": None})

    def test_bindings_resolve_inside_nested_structures(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = do.WorkflowRuntime(Path(tmp), hook_registry=self.hook_registry(lambda p: {"ok": True}))
            results = {"a": {"outputs": {"id": 7}}}
            resolved = runtime._resolve_bindings(
                {"items": [{"ref": {"bind": {"from_step": "a", "path": "outputs.id"}}}]}, results
            )
        self.assertEqual(resolved, {"items": [{"ref": 7}]})

    def test_a_plain_value_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = do.WorkflowRuntime(Path(tmp), hook_registry=self.hook_registry(lambda p: {"ok": True}))
            payload = {"literal": "bind", "n": 3, "list": ["a", "b"]}
            self.assertEqual(runtime._resolve_bindings(payload, {}), payload)


class ResourceClassTests(unittest.TestCase):
    """Resource class decides which scarce slot a step waits for. Misclassifying
    is how a host that holds one task model at a time ends up loading several."""

    def test_model_work_is_classified_as_model(self):
        for step_type in ("model_reasoning", "review"):
            with self.subTest(step_type=step_type):
                self.assertEqual(do._resource_class({"step_type": step_type, "target": "x"}), "model")

    def test_openclaw_delegation_gets_its_own_class(self):
        self.assertEqual(
            do._resource_class({
                "step_type": "tool", "target": "project_operator",
                "inputs": {"operation": "delegate_openclaw"},
            }),
            "openclaw",
        )

    def test_an_ordinary_project_operator_call_is_not_openclaw(self):
        """Only the delegating operation holds the scarce slot."""
        self.assertNotEqual(
            do._resource_class({
                "step_type": "tool", "target": "project_operator",
                "inputs": {"operation": "list"},
            }),
            "openclaw",
        )

    def test_plain_work_needs_no_scarce_slot(self):
        self.assertEqual(do._resource_class({"step_type": "python_hook", "target": "x"}), "io")

    def test_acquiring_a_slot_stops_when_the_run_is_cancelled(self):
        """Otherwise a cancelled run blocks forever waiting for a slot that a
        still-running item holds."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime = do.WorkflowRuntime(Path(tmp), hook_registry=do.PythonHookRegistry())
            exhausted = threading.BoundedSemaphore(1)
            exhausted.acquire()
            cancelled = threading.Event()
            cancelled.set()

            self.assertFalse(runtime._acquire_slot(exhausted, cancelled))

    def test_no_slot_required_means_no_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = do.WorkflowRuntime(Path(tmp), hook_registry=do.PythonHookRegistry())
            self.assertTrue(runtime._acquire_slot(None, threading.Event()))


if __name__ == "__main__":
    unittest.main()
