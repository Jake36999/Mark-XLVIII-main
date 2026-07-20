import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from actions import jarvis_memory as jm


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = text or json.dumps(self.payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class JarvisMemoryTests(unittest.TestCase):
    def cfg(self, root: Path, remember_enabled: bool = False) -> dict:
        return jm.resolve_config(
            {
                "jarvis_notes_root": str(root),
                "remember_api_url": "http://remember.test",
                "remember_project_id": "jarvis_notes",
                "remember_project_name": "Jarvis Notes",
                "remember_enabled": remember_enabled,
            }
        )

    def test_templates_are_registered(self):
        templates = jm.list_templates()["templates"]

        self.assertEqual(
            set(templates),
            {"memory", "report", "deep_research_report", "log", "progress_tracker"},
        )

    def test_markdown_creation_has_required_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            result = jm.create_note(
                note_type="report",
                title="Router Status",
                content="The local router is active.",
                tags=["mark", "router"],
                cfg=cfg,
                sync=False,
            )

            path = Path(result["path"])
            metadata, body, markdown = jm.read_note(path)
            self.assertTrue(path.exists())
            self.assertTrue(markdown.startswith("---\n"))
            for field in jm.FRONTMATTER_FIELDS:
                self.assertIn(field, metadata)
            self.assertEqual(metadata["title"], "Router Status")
            self.assertEqual(metadata["type"], "report")
            self.assertEqual(metadata["sync_state"], "local_only")
            self.assertIn("The local router is active.", body)

    def test_remember_payload_maps_to_note_ingest_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp), remember_enabled=True)
            result = jm.create_note(
                note_type="memory",
                title="User Preference",
                content="Prefers local models for grunt work.",
                cfg=cfg,
                sync=False,
            )

            payload = jm.build_remember_payload(Path(result["path"]), cfg)

            self.assertEqual(payload["project_id"], "jarvis_notes")
            self.assertEqual(payload["project_name"], "Jarvis Notes")
            self.assertEqual(payload["intent_type"], "important_info")
            self.assertEqual(payload["source"], "user")
            self.assertEqual(payload["schema_version"], 1)
            self.assertIn("Prefers local models", payload["markdown"])

    def test_offline_backend_still_creates_local_pending_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp), remember_enabled=True)

            with mock.patch("actions.jarvis_memory.requests.post", side_effect=requests.ConnectionError("offline")):
                result = jm.create_note(
                    note_type="memory",
                    title="Offline Note",
                    content="Persist locally first.",
                    cfg=cfg,
                    sync=True,
                )

            metadata, _, _ = jm.read_note(Path(result["path"]))
            self.assertTrue(result["local_written"])
            self.assertFalse(result["sync"]["ok"])
            self.assertEqual(metadata["sync_state"], "backend_pending")

    def test_sync_pending_updates_frontmatter_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp), remember_enabled=True)
            result = jm.create_note(
                note_type="log",
                title="Sync Me",
                content="Ready for backend.",
                cfg=cfg,
                sync=False,
            )

            def fake_post(url, **kwargs):
                if url.endswith("/remember/projects/register"):
                    return FakeResponse({"ok": True})
                if url.endswith("/remember/notes/ingest"):
                    return FakeResponse({"note_id": "note-123", "status": "synced"})
                raise AssertionError(url)

            with mock.patch("actions.jarvis_memory.requests.post", side_effect=fake_post):
                sync = jm.sync_pending(cfg)

            metadata, _, _ = jm.read_note(Path(result["path"]))
            self.assertTrue(sync["ok"])
            self.assertEqual(sync["synced"], 1)
            self.assertEqual(metadata["sync_state"], "backend_synced")
            self.assertEqual(metadata["remember_note_id"], "note-123")

    def test_query_calls_project_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp), remember_enabled=True)
            calls = []

            def fake_post(url, **kwargs):
                calls.append((url, kwargs["json"]))
                return FakeResponse({"results": [{"title": "A", "content": "B"}]})

            with mock.patch("actions.jarvis_memory.requests.post", side_effect=fake_post):
                result = jm.query_memory("local model plan", cfg=cfg, scope="project", limit=3)

            self.assertTrue(result["ok"])
            self.assertTrue(calls[0][0].endswith("/remember/query/project"))
            self.assertEqual(calls[0][1]["project_id"], "jarvis_notes")
            self.assertEqual(calls[0][1]["limit"], 3)

    def test_reindex_marks_synced_notes_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp), remember_enabled=True)
            result = jm.create_note(
                note_type="memory",
                title="Indexed Memory",
                content="This has been synced.",
                cfg=cfg,
                sync=False,
            )
            jm.update_note_frontmatter(Path(result["path"]), {"sync_state": "backend_synced"})

            with mock.patch("actions.jarvis_memory.requests.post", return_value=FakeResponse({"ok": True})):
                reindex = jm.reindex_project(cfg)

            metadata, _, _ = jm.read_note(Path(result["path"]))
            self.assertTrue(reindex["ok"])
            self.assertEqual(reindex["updated_notes"], 1)
            self.assertEqual(metadata["index_state"], "indexed")

    def test_memory_manager_mirrors_json_updates_to_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            with mock.patch("actions.jarvis_memory.resolve_config", return_value=cfg), \
                 mock.patch("actions.jarvis_memory.requests.post", side_effect=requests.ConnectionError("offline")):
                results = jm.mirror_memory_update({"preferences": {"models": {"value": "Use local workers."}}})

            self.assertEqual(len(results), 1)
            path = Path(results[0]["path"])
            metadata, body, _ = jm.read_note(path)
            self.assertEqual(metadata["id"], "memory-preferences-models")
            self.assertEqual(metadata["sync_state"], "local_only")
            self.assertIn("Use local workers.", body)

    def test_local_reindex_query_graph_tasks_and_dag_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            linked = jm.create_note(
                note_type="memory",
                title="Linked Note",
                content="Local models can handle worker tasks.",
                tags=["models"],
                cfg=cfg,
                sync=False,
            )
            source = jm.create_note(
                note_type="progress_tracker",
                title="Router Plan",
                content="Connect this to [[Linked Note]].\n\n- [ ] calibrate antenna\n- [x] verify local speech",
                tags=["router"],
                cfg=cfg,
                sync=False,
            )

            indexed = jm.reindex_local(cfg)
            queried = jm.query_local("local models worker", cfg=cfg, limit=3)
            graph = jm.graph_local(cfg)
            tasks = jm.tasks_local(cfg, include_done=False)
            candidates = jm.dag_candidates(cfg, write=True)

            self.assertEqual(indexed["indexed_notes"], 2)
            self.assertTrue(any("Linked Note" == item["title"] for item in queried["results"]))
            self.assertTrue(any(edge["type"] == "wikilink" for edge in graph["edges"]))
            self.assertEqual([task["text"] for task in tasks["tasks"]], ["calibrate antenna"])
            self.assertEqual(candidates["count"], 1)
            self.assertTrue(Path(candidates["output_path"]).exists())
            self.assertTrue(Path(linked["path"]).exists())
            self.assertTrue(Path(source["path"]).exists())

    def test_export_training_candidates_uses_reviewed_notes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            reviewed = jm.create_note(
                note_type="memory",
                title="Reviewed Memory",
                content="This can train future lightweight agents.",
                cfg=cfg,
                sync=False,
            )
            jm.update_note_frontmatter(Path(reviewed["path"]), {"status": "reviewed"})
            jm.create_note(
                note_type="memory",
                title="Draft Memory",
                content="Do not export this yet.",
                cfg=cfg,
                sync=False,
            )
            jm.reindex_local(cfg)

            exported = jm.export_training_candidates(cfg)

            self.assertEqual(exported["count"], 1)
            text = Path(exported["output_path"]).read_text(encoding="utf-8")
            self.assertIn("Reviewed Memory", text)
            self.assertNotIn("Draft Memory", text)


if __name__ == "__main__":
    unittest.main()
