import tempfile
import unittest
from pathlib import Path

from actions import workflow_artifacts as wa
from actions.jarvis_memory import create_note, read_note


class WorkflowArtifactTests(unittest.TestCase):
    def cfg(self, root: Path) -> dict:
        return {
            "jarvis_notes_root": str(root),
            "notes_root": str(root),
            "remember_enabled": False,
            "remember_project_id": "jarvis_notes",
            "remember_project_name": "Jarvis Notes",
        }

    def test_job_runner_builder_creates_modular_verified_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "artifacts" / "job_runner_demo"

            result = wa.build_python_job_runner({"output_root": str(output_root)}, root)
            validated = wa.validate_python_project({"output_root": str(output_root)}, root)

            self.assertTrue(result["ok"])
            self.assertTrue(validated["ok"])
            self.assertEqual(result["tests"]["returncode"], 0)
            self.assertEqual(result["fresh_process"]["success_returncode"], 0)
            self.assertEqual(result["fresh_process"]["retry_returncode"], 0)
            self.assertTrue((output_root / "tests" / "test_job_runner.py").is_file())

    def test_documentation_set_has_resolvable_links_and_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_note(
                note_type="report",
                title="Source Architecture Note",
                content="## Architecture\n\nJARVIS uses a deterministic workflow runtime.",
                cfg=self.cfg(root),
                sync=False,
                reindex=False,
            )

            result = wa.create_vault_documentation_set({}, root)
            validation = wa.validate_vault_artifacts({"artifacts": result["artifacts"]}, root)

            self.assertTrue(result["ok"])
            self.assertTrue(validation["ok"])
            self.assertEqual(len(result["artifacts"]), 3)
            for raw_path in result["artifacts"]:
                metadata, body, _ = read_note(Path(raw_path))
                self.assertTrue(metadata.get("id"))
                self.assertIn("> [!", body)

    def test_productivity_assessment_preserves_canonical_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = create_note(
                note_type="progress_tracker",
                title="Owned Tasks",
                content=(
                    "- [ ] User: choose hardware. ^task-user-hardware\n"
                    "- [ ] Shared: agree report outline. ^task-shared-outline\n"
                    "- [ ] Agent: draft inventory. ^task-agent-inventory"
                ),
                cfg=self.cfg(root),
                sync=False,
                reindex=False,
                metadata_extra={"owner": "user", "agent_permission": "propose"},
            )
            source = Path(note["path"])
            before = source.read_text(encoding="utf-8")

            result = wa.productivity_assessment({"source_path": str(source)}, root)

            self.assertTrue(result["ok"])
            self.assertEqual(before, source.read_text(encoding="utf-8"))
            self.assertEqual([item["owner"] for item in result["tasks"]], ["user-owned", "shared", "agent-owned"])
            self.assertTrue(Path(result["artifact_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
