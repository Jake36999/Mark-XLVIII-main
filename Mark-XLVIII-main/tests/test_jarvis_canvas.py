import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import jarvis_canvas as canvas
from actions import jarvis_memory as memory
from core import canvas_index
from core.canvas_document import CanvasValidationError


class JarvisCanvasTests(unittest.TestCase):
    def cfg(self, root: Path) -> dict:
        return {
            "jarvis_notes_root": str(root),
            "jarvis_canvas_folder": "Canvases/JARVIS",
            "jarvis_canvas_max_plan_nodes": 8,
            "jarvis_canvas_max_task_nodes": 10,
        }

    def test_sync_plan_creates_bounded_native_canvas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_cfg = memory.resolve_config({"jarvis_notes_root": str(root), "remember_enabled": False})
            note = memory.create_note(
                note_type="plan",
                title="Canvas Plan",
                content="\n".join(f"- [ ] Work item {index} [task:item-{index}]" for index in range(12)),
                content_mode="full_body",
                cfg=mem_cfg,
                sync=False,
                note_id="canvas-plan",
                metadata_extra={"approval_state": "pending_review", "execution_state": "not_started"},
            )

            result = canvas.sync_plan_canvas(note["path"], cfg=self.cfg(root), max_nodes=8)
            payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertLessEqual(len(payload["nodes"]), 8)
            self.assertTrue(any(node.get("type") == "file" for node in payload["nodes"]))
            self.assertTrue(all(edge["fromNode"] in {node["id"] for node in payload["nodes"]} for edge in payload["edges"]))
            self.assertEqual(result["canonical_source"], note["path"])

    def test_task_dashboard_rolls_active_and_completed_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_cfg = memory.resolve_config({"jarvis_notes_root": str(root), "remember_enabled": False})
            body = "\n".join(
                [f"- [ ] Active {index} [task:active-{index}]" for index in range(8)]
                + [f"- [x] Done {index} [task:done-{index}]" for index in range(8)]
            )
            memory.create_note(
                note_type="progress_tracker",
                title="Tracked Tasks",
                content=body,
                content_mode="full_body",
                cfg=mem_cfg,
                sync=False,
                reindex=True,
            )

            result = canvas.sync_task_canvas(cfg=self.cfg(root), max_nodes=10)
            payload = canvas.load_canvas(Path(result["path"]))

            self.assertTrue(result["ok"])
            self.assertLessEqual(len(payload["nodes"]), 10)
            self.assertEqual(result["active_task_count"], 8)
            self.assertEqual(result["completed_task_count"], 8)

    def test_dashboard_stays_non_overlapping_as_it_grows_across_syncs(self):
        # Regression for a real cramped/overlapping dashboard: layout used to
        # run only at creation, so a dashboard that kept growing across many
        # syncs froze its first-ever layout and new nodes piled up around it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_cfg = memory.resolve_config({"jarvis_notes_root": str(root), "remember_enabled": False})
            memory.create_note(
                note_type="progress_tracker",
                title="Tracked Tasks",
                content="\n".join(f"- [ ] Active {index} [task:active-{index}]" for index in range(6)),
                content_mode="full_body",
                cfg=mem_cfg,
                sync=False,
                reindex=True,
            )
            cfg = self.cfg(root)
            canvas.sync_task_canvas(cfg=cfg, max_nodes=40)

            # simulate real accumulation: several more sync passes each adding tasks
            for wave in range(3):
                memory.create_note(
                    note_type="progress_tracker",
                    title=f"Tracked Tasks Wave {wave}",
                    content="\n".join(
                        f"- [ ] Wave {wave} item {index} [task:wave-{wave}-{index}]" for index in range(6)
                    ),
                    content_mode="full_body",
                    cfg=mem_cfg,
                    sync=False,
                    reindex=True,
                )
                result = canvas.sync_task_canvas(cfg=cfg, max_nodes=40)

            payload = canvas.load_canvas(Path(result["path"]))
            metrics = canvas.geometry_metrics(payload)
            self.assertEqual(metrics["overlap_count"], 0, metrics["overlaps"])

    def test_neighbor_extension_adds_one_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self.cfg(root)
            path = root / "Canvases" / "JARVIS" / "scratch.canvas"
            canvas.write_canvas(path, {"nodes": [{"id": "root", "type": "text", "text": "Main", "x": 0, "y": 0, "width": 300, "height": 120}], "edges": []})

            with mock.patch("actions.jarvis_canvas.call_text", return_value="## Next\nA bounded child."):
                result = canvas.extend_node(path, "root", cfg=cfg)
            payload = canvas.load_canvas(path)

            self.assertTrue(result["ok"])
            self.assertEqual(len(payload["nodes"]), 2)
            self.assertEqual(len(payload["edges"]), 1)
            self.assertEqual(payload["edges"][0]["fromNode"], "root")

    def test_canvas_task_change_requires_confirmation_and_updates_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_cfg = memory.resolve_config({"jarvis_notes_root": str(root), "remember_enabled": False})
            note = memory.create_note(
                note_type="progress_tracker",
                title="Canvas Edit",
                content="- [ ] Review result [task:review-result] permission:propose",
                content_mode="full_body",
                cfg=mem_cfg,
                sync=False,
                reindex=True,
            )
            synced = canvas.sync_task_canvas(cfg=self.cfg(root), max_nodes=8)
            canvas_path = Path(synced["path"])
            payload = canvas.load_canvas(canvas_path)
            task_node = next(node for node in payload["nodes"] if (node.get("jarvis") or {}).get("kind") == "task")
            task_node["text"] = task_node["text"].replace("## [ ]", "## [x]")
            canvas.write_canvas(canvas_path, payload)

            gated = canvas.apply_canvas_task_changes(canvas_path, cfg=self.cfg(root))
            applied = canvas.apply_canvas_task_changes(canvas_path, confirmed=True, cfg=self.cfg(root))
            _, body, _ = memory.read_note(Path(note["path"]))

            self.assertFalse(gated["ok"])
            self.assertTrue(applied["ok"])
            self.assertIn("- [x] Review result", body)

    def test_task_review_schedule_is_explicit_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = memory.resolve_config({"jarvis_notes_root": str(root), "remember_enabled": False})

            rejected = memory.configure_task_reviews(enabled=True, confirmed=False, cfg=cfg)
            enabled = memory.configure_task_reviews(enabled=True, confirmed=True, cadence_hours=6, cfg=cfg)
            review = memory.run_task_review(scheduled=True, force=True, cfg=cfg)

            self.assertFalse(rejected["ok"])
            self.assertTrue(enabled["enabled"])
            self.assertEqual(enabled["cadence_hours"], 6)
            self.assertEqual(review["status"], "review_complete")

    def test_empty_canvas_and_extension_fields_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "empty.canvas"
            path.write_text("{}", encoding="utf-8")

            payload = canvas.load_canvas(path)
            payload["plugin_extension"] = {"mode": "kept"}
            canvas.write_canvas(path, payload, vault_root=root)
            reloaded = canvas.load_canvas(path)

            self.assertEqual(reloaded["nodes"], [])
            self.assertEqual(reloaded["edges"], [])
            self.assertEqual(reloaded["plugin_extension"], {"mode": "kept"})

    def test_malformed_canvas_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "broken.canvas"
            original = b'{"nodes": ['
            path.write_bytes(original)

            inspected = canvas.inspect_canvas(path, cfg=self.cfg(root))
            with self.assertRaises(CanvasValidationError):
                canvas.load_canvas(path)

            self.assertFalse(inspected["ok"])
            self.assertTrue(inspected["original_preserved"])
            self.assertEqual(path.read_bytes(), original)

    def test_layout_preview_is_deterministic_and_revision_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self.cfg(root)
            path = root / "layout.canvas"
            payload = {
                "nodes": [
                    {"id": "manual-anchor", "type": "text", "text": "Pinned", "x": 50, "y": 50, "width": 260, "height": 120},
                    {"id": "jarvis-plan", "type": "text", "text": "Plan", "x": 0, "y": 0, "width": 320, "height": 140},
                    {"id": "jarvis-task", "type": "text", "text": "[ ] Work item", "x": 0, "y": 0, "width": 320, "height": 140, "jarvis": {"kind": "task"}},
                ],
                "edges": [{"id": "jarvis-edge", "fromNode": "jarvis-plan", "toNode": "jarvis-task", "label": "next"}],
                "extension": {"keep": True},
            }
            canvas.write_canvas(path, payload, vault_root=root)

            first = canvas.preview_layout(path, profile="plan", cfg=cfg)
            second = canvas.preview_layout(path, profile="plan", cfg=cfg)
            committed = canvas.commit_layout(
                path,
                base_revision=first["base_revision"],
                expected_proposal_hash=first["proposal_hash"],
                profile="plan",
                confirmed=True,
                cfg=cfg,
            )
            reloaded = canvas.load_canvas(path)

            self.assertEqual(first["proposal_hash"], second["proposal_hash"])
            self.assertTrue(committed["ok"])
            self.assertEqual(committed["layout"]["overlap_count"], 0)
            self.assertEqual(next(node for node in reloaded["nodes"] if node["id"] == "manual-anchor")["x"], 50)
            self.assertNotIn("label", reloaded["edges"][0])
            self.assertEqual(reloaded["extension"], {"keep": True})

    def test_layout_commit_refuses_revision_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self.cfg(root)
            path = root / "drift.canvas"
            canvas.write_canvas(
                path,
                {"nodes": [{"id": "jarvis-one", "type": "text", "text": "One", "x": 0, "y": 0, "width": 200, "height": 100}], "edges": []},
                vault_root=root,
            )
            preview = canvas.preview_layout(path, cfg=cfg)
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")

            result = canvas.commit_layout(
                path,
                base_revision=preview["base_revision"],
                expected_proposal_hash=preview["proposal_hash"],
                confirmed=True,
                cfg=cfg,
            )

            self.assertFalse(result["ok"])
            self.assertTrue(result["conflict"])

    def test_user_moved_managed_node_becomes_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self.cfg(root)
            path = root / "pin.canvas"
            canvas.write_canvas(
                path,
                {"nodes": [{"id": "jarvis-one", "type": "text", "text": "One", "x": 0, "y": 0, "width": 200, "height": 100}], "edges": []},
                vault_root=root,
            )
            preview = canvas.preview_layout(path, cfg=cfg)
            canvas.commit_layout(path, base_revision=preview["base_revision"], expected_proposal_hash=preview["proposal_hash"], confirmed=True, cfg=cfg)
            payload = canvas.load_canvas(path)
            payload["nodes"][0]["x"] = 777
            canvas.write_canvas(path, payload, vault_root=root)

            moved_preview = canvas.preview_layout(path, cfg=cfg)
            self.assertEqual(moved_preview["after"]["pinned_count"], 1)
            self.assertEqual(moved_preview["after"]["managed_count"], 0)

    def test_plan_resync_preserves_manual_nodes_and_top_level_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_cfg = memory.resolve_config({"jarvis_notes_root": str(root), "remember_enabled": False})
            note = memory.create_note(
                note_type="plan",
                title="Preserve Canvas",
                content="- [ ] First task [task:first]",
                content_mode="full_body",
                cfg=mem_cfg,
                sync=False,
                note_id="preserve-canvas",
            )
            first = canvas.sync_plan_canvas(note["path"], cfg=self.cfg(root))
            path = Path(first["path"])
            payload = canvas.load_canvas(path)
            payload["plugin"] = {"custom": True}
            payload["nodes"].append({"id": "user-note", "type": "text", "text": "Manual", "x": 3000, "y": 50, "width": 240, "height": 100})
            canvas.write_canvas(path, payload, vault_root=root)

            canvas.sync_plan_canvas(note["path"], cfg=self.cfg(root))
            reloaded = canvas.load_canvas(path)
            self.assertEqual(reloaded["plugin"], {"custom": True})
            self.assertTrue(any(node["id"] == "user-note" for node in reloaded["nodes"]))

    def test_cross_canvas_relationships_find_shared_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self.cfg(root)
            for name in ("alpha", "beta"):
                path = root / f"{name}.canvas"
                canvas.write_canvas(
                    path,
                    {
                        "nodes": [{"id": f"{name}-note", "type": "file", "file": "Projects/shared.md", "x": 0, "y": 0, "width": 300, "height": 180}],
                        "edges": [],
                        "jarvis": {"view_kind": "project", "title": name.title()},
                    },
                    vault_root=root,
                )
            canvas.canvas_relationships(cfg=cfg)
            related = canvas.canvas_relationships(root / "alpha.canvas", cfg=cfg)

            self.assertTrue(related["ok"])
            self.assertTrue(any(item["canvas_path"] == "beta.canvas" for item in related["related_canvases"]))

    def test_canvas_index_ignores_internal_recovery_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recovery = root / ".jarvis" / "canvas_history" / "backup.canvas"
            recovery.parent.mkdir(parents=True)
            recovery.write_text("{}", encoding="utf-8")

            result = canvas_index.index_canvas(root, recovery)

            self.assertTrue(result["ok"])
            self.assertTrue(result["ignored"])
            self.assertEqual(result["reason"], "derived_vault_path")


if __name__ == "__main__":
    unittest.main()
