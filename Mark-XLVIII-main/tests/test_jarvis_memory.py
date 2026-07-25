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
    def test_frontmatter_update_remerges_after_concurrent_user_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "concurrent.md"
            path.write_text(
                "---\nid: concurrent\ntitle: Concurrent\nstatus: validation\n---\n\n# Body\n",
                encoding="utf-8",
            )
            real_atomic_write = jm.atomic_write
            calls = 0

            def conflicting_write(target, text, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    metadata, body, _ = jm.read_note(target)
                    metadata["status"] = "complete"
                    real_atomic_write(target, f"{jm.render_frontmatter(metadata)}\n\n{body.rstrip()}\n")
                    raise RuntimeError("Revision conflict from simulated Obsidian edit")
                return real_atomic_write(target, text, **kwargs)

            with mock.patch("actions.jarvis_memory.atomic_write", side_effect=conflicting_write):
                result = jm.update_note_frontmatter(path, {"index_state": "indexed_local"})

            stored, _, _ = jm.read_note(path)
            self.assertEqual(calls, 2)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(stored["status"], "complete")
            self.assertEqual(stored["index_state"], "indexed_local")

    def test_research_synthesis_queues_worker_batches_before_one_final_consolidation(self):
        sources = [
            {
                "title": f"Source {index}",
                "snippet": f"Evidence statement {index} about memory, loading, telemetry, and recovery.",
                "url": f"https://example.com/{index}",
                "source": "example.com",
                "published_at": "2026-07-21",
            }
            for index in range(1, 6)
        ]
        responses = [
            json.dumps(
                {
                    "claims": [
                        {"claim": "Memory and loading require measurement.", "source_ids": [1, 2], "theme": "memory", "uncertainty": "Host dependent."}
                    ]
                }
            ),
            json.dumps(
                {
                    "claims": [
                        {"claim": "Recovery needs observable state.", "source_ids": [5], "theme": "recovery", "uncertainty": "Limited evidence."}
                    ]
                }
            ),
            json.dumps(
                {
                    "summary": "The evidence supports measured orchestration [1][5].",
                    "findings": "- Loading and telemetry need explicit controls [1][2].",
                    "uncertainty": "Mixed-vendor performance remains host-dependent [3].",
                    "contrasts": "Source guidance differs by backend [4].",
                    "recommendations": "- Benchmark and record recovery outcomes [5].",
                }
            ),
        ]
        with mock.patch("core.model_router.call_text", side_effect=responses) as call_text, mock.patch(
            "core.model_router.last_model_provenance",
            return_value={"provider": "lmstudio", "model": "research-model", "role": "research", "metrics": {"tokens_per_second": 2.0}},
        ):
            sections, provenance = jm.synthesize_report_sections(
                query="mixed-vendor dual-GPU orchestration",
                sources=sources,
                retrieved_at="2026-07-21T10:00:00Z",
            )

        roles = [call.kwargs["role"] for call in call_text.call_args_list]
        self.assertEqual(roles, ["worker", "worker", "research"])
        self.assertIn("[1][5]", sections["Summary"])
        self.assertEqual(provenance["workflow_stages"][-1]["stage"], "final_consolidation")
        self.assertEqual(provenance["workflow_stages"][-1]["status"], "accepted")

    def test_deterministic_research_fallback_groups_evidence_and_host_actions(self):
        sources = [
            {
                "title": "LM Studio model loading",
                "snippet": "Load and unload models while controlling memory allocation and GPU offload.",
                "url": "https://lmstudio.ai/docs/developer/rest/load",
                "source": "lmstudio.ai",
                "retrieved_at": "2026-07-21T10:00:00Z",
                "backend": "test",
            },
            {
                "title": "llama.cpp multi-GPU server",
                "snippet": "Tensor split and parallel request controls support multi-GPU deployment.",
                "url": "https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md",
                "source": "github.com",
                "retrieved_at": "2026-07-21T10:00:00Z",
                "backend": "test",
            },
        ]

        sections = jm.build_report_sections_from_sources(
            query="mixed-vendor dual-GPU model loading telemetry and recovery",
            sources=sources,
            retrieved_at="2026-07-21T10:00:00Z",
            mode="research",
        )

        finding_bullets = [line for line in sections["Findings"].splitlines() if line.startswith("- ")]
        self.assertLessEqual(len(finding_bullets), 7)
        for term in ("Memory allocation", "Concurrency", "Model loading", "Telemetry", "Failure recovery"):
            self.assertIn(term, sections["Findings"])
        self.assertIn("GTX 1080", sections["Actions"])
        self.assertIn("RX 5500 XT", sections["Actions"])
        self.assertIn("mixed-vendor", sections["Actions"])
        self.assertIn("https://lmstudio.ai", sections["Sources"])

    def cfg(self, root: Path, remember_enabled: bool = False) -> dict:
        return jm.resolve_config(
            {
                "jarvis_notes_root": str(root),
                "remember_api_url": "http://remember.test",
                "remember_project_id": "jarvis_notes",
                "remember_project_name": "Jarvis Notes",
                "remember_enabled": remember_enabled,
                "rag_embedding_provider": "disabled",
                # Isolate from the live runtime.json, which may have these enabled.
                # Tests that need tiers on set the flag explicitly after calling cfg().
                "memory_tiers_enabled": False,
                "memory_consolidation_enabled": False,
            }
        )

    def _report(self, cfg, title="Router Status", content=None):
        sections = content or {
            "Summary": "Original summary.",
            "Findings": "- First finding.",
            "Actions": "- Do the thing.",
        }
        return Path(
            jm.create_note(
                note_type="report",
                title=title,
                sections=sections,
                cfg=cfg,
                content_mode="sections",
            )["path"]
        )

    # ---- Task A1: section editing ------------------------------------------

    def test_update_section_replaces_one_section_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            path = self._report(cfg)
            _, before, _ = jm.read_note(path)

            result = jm.update_section(path, "## Findings", "- Replaced finding.", cfg=cfg)

            self.assertTrue(result["ok"])
            _, after, _ = jm.read_note(path)
            self.assertIn("- Replaced finding.", after)
            self.assertNotIn("- First finding.", after)
            # Sibling sections are byte-identical.
            self.assertIn("Original summary.", after)
            self.assertIn("- Do the thing.", after)

    def test_update_section_append_and_prepend(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            path = self._report(cfg)

            jm.update_section(path, "## Findings", "- Appended.", mode="append", cfg=cfg)
            jm.update_section(path, "## Findings", "- Prepended.", mode="prepend", cfg=cfg)
            _, body, _ = jm.read_note(path)

            findings = body.split("## Findings", 1)[1].split("##", 1)[0]
            self.assertLess(findings.index("Prepended"), findings.index("First finding"))
            self.assertLess(findings.index("First finding"), findings.index("Appended"))

    def test_update_section_preserves_a_concurrent_edit_to_another_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            path = self._report(cfg)

            # User edits a different section out-of-band between read and write.
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace("- Do the thing.", "- User added this."), encoding="utf-8")

            jm.update_section(path, "## Findings", "- Agent finding.", cfg=cfg)
            _, body, _ = jm.read_note(path)

            self.assertIn("- User added this.", body)   # user edit preserved
            self.assertIn("- Agent finding.", body)     # agent edit applied

    def test_update_section_conflict_on_same_section_does_not_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            path = self._report(cfg)

            # Both the caller's base and the on-disk copy diverge in Findings.
            base_meta, base_body, _ = jm.read_note(path)
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace("- First finding.", "- User's finding."), encoding="utf-8")

            result = jm.update_section(
                path, "## Findings", "- Agent's finding.", cfg=cfg, base_body=base_body
            )

            self.assertFalse(result["ok"])
            self.assertTrue(result.get("requires_user_review"))
            _, body, _ = jm.read_note(path)
            self.assertIn("- User's finding.", body)      # user content survives
            self.assertNotIn("- Agent's finding.", body)  # agent edit not forced

    def test_update_section_creates_a_missing_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            path = self._report(cfg)

            jm.update_section(path, "## Risks", "- A new risk.", mode="append", cfg=cfg)
            _, body, _ = jm.read_note(path)

            self.assertIn("## Risks", body)
            self.assertIn("- A new risk.", body)

    def test_update_section_registers_a_self_write_receipt(self):
        from core import vault_activity

        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            root = Path(tmp)
            path = self._report(cfg)
            vault_activity.baseline_vault(root)

            jm.update_section(path, "## Findings", "- Receipted edit.", cfg=cfg)
            vault_activity.process_event_batch(
                root, [{"event_type": "modified", "src_path": str(path)}]
            )
            latest = vault_activity.turn_change_context(root, "what changed?", 1)

            # A jarvis-origin edit is not surfaced as an external user change.
            self.assertEqual(latest["context"], "")

    def test_update_section_refreshes_content_hash_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            path = self._report(cfg)
            before, _, _ = jm.read_note(path)

            jm.update_section(path, "## Findings", "- Changed.", cfg=cfg)
            after, body, _ = jm.read_note(path)

            self.assertNotEqual(after["content_hash"], before["content_hash"])
            self.assertEqual(after["content_hash"], jm._content_hash(body))

    # ---- Task A2: move-safe relocation -------------------------------------

    def test_move_note_relocates_and_updates_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            path = self._report(cfg)

            dest = Path(tmp) / "Archive" / "Reports"
            result = jm.move_note(path, dest, cfg=cfg, lifecycle="archive")

            self.assertTrue(result["ok"])
            new_path = Path(result["path"])
            self.assertFalse(path.exists())
            self.assertTrue(new_path.exists())
            self.assertEqual(new_path.parent, dest)
            meta, _, _ = jm.read_note(new_path)
            self.assertEqual(meta["lifecycle"], "archive")

    def test_move_rewrites_path_qualified_inbound_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            target = self._report(cfg, title="Target Report")
            rel = target.stem  # basename
            referrer = self._report(cfg, title="Referrer", content={"Summary": "see below"})
            # A path-qualified inbound link that WOULD break on a naive move.
            jm.update_section(
                referrer,
                "## Summary",
                f"See [[Reports/{rel}|the target]] for detail.",
                cfg=cfg,
            )

            jm.move_note(target, Path(tmp) / "Long Term" / "Reports", cfg=cfg, lifecycle="long_term")

            _, body, _ = jm.read_note(referrer)
            self.assertIn(f"[[Long Term/Reports/{rel}|the target]]", body)
            self.assertNotIn(f"[[Reports/{rel}|", body)

    def test_move_leaves_basename_links_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            target = self._report(cfg, title="Basename Target")
            rel = target.stem
            referrer = self._report(cfg, title="Referrer Two", content={"Summary": "x"})
            jm.update_section(referrer, "## Summary", f"See [[{rel}]] please.", cfg=cfg)

            jm.move_note(target, Path(tmp) / "Archive" / "Reports", cfg=cfg, lifecycle="archive")

            _, body, _ = jm.read_note(referrer)
            self.assertIn(f"[[{rel}]]", body)  # basename link still resolves, unchanged

    def test_move_refuses_a_basename_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            first = self._report(cfg, title="Same Name")
            dest = Path(tmp) / "Archive" / "Reports"
            dest.mkdir(parents=True)
            (dest / first.name).write_text("---\nid: x\ntitle: X\n---\n\nbody\n", encoding="utf-8")

            result = jm.move_note(first, dest, cfg=cfg, lifecycle="archive")

            self.assertFalse(result["ok"])
            self.assertIn("collision", result["error"].lower())
            self.assertTrue(first.exists())  # original untouched on refusal

    def test_move_registers_receipts_for_every_touched_file(self):
        from core import vault_activity

        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            root = Path(tmp)
            target = self._report(cfg, title="Receipted Target")
            rel = target.stem
            referrer = self._report(cfg, title="Receipted Referrer", content={"Summary": "x"})
            jm.update_section(referrer, "## Summary", f"[[Reports/{rel}|t]]", cfg=cfg)
            vault_activity.baseline_vault(root)

            result = jm.move_note(target, root / "Archive" / "Reports", cfg=cfg, lifecycle="archive")
            events = vault_activity.process_event_batch(
                root,
                [
                    {"event_type": "moved", "src_path": str(target), "dst_path": result["path"]},
                    {"event_type": "modified", "src_path": str(referrer)},
                ],
            )
            del events
            latest = vault_activity.turn_change_context(root, "what changed?", 1)

            # Both the move and the link rewrite are jarvis-origin, not user edits.
            self.assertEqual(latest["context"], "")

    # ---- Task B1: tier field and derived location --------------------------

    def test_new_notes_default_to_short_term_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            cfg["memory_tiers_enabled"] = True
            path = self._report(cfg)
            meta, _, _ = jm.read_note(path)
            self.assertEqual(meta["lifecycle"], "short_term")
            self.assertIn("tier/short-term", meta.get("tags", []))

    def test_tier_field_absent_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))  # tiers disabled by default
            path = self._report(cfg)
            meta, _, _ = jm.read_note(path)
            self.assertNotIn("lifecycle", meta)
            self.assertNotIn("tier/short-term", meta.get("tags", []))

    def test_tier_root_maps_each_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            self.assertEqual(jm.tier_root("short_term", "report", cfg).name, "Reports")
            long_root = jm.tier_root("long_term", "report", cfg)
            self.assertEqual(long_root.parts[-1], "Long Term")
            arch = jm.tier_root("archive", "report", cfg)
            self.assertEqual(arch.parts[-2:], ("Archive", "Reports"))

    def test_note_tier_derives_from_path_when_field_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            root = Path(tmp)
            self.assertEqual(jm.note_tier({}, root / "Reports" / "x.md", cfg), "short_term")
            self.assertEqual(jm.note_tier({}, root / "Long Term" / "p" / "x.md", cfg), "long_term")
            self.assertEqual(jm.note_tier({}, root / "Archive" / "Reports" / "x.md", cfg), "archive")
            # An explicit field wins over the folder.
            self.assertEqual(
                jm.note_tier({"lifecycle": "archive"}, root / "Reports" / "x.md", cfg), "archive"
            )

    # ---- Task B2: tier-aware retrieval weighting ---------------------------

    def test_archive_notes_are_de_weighted_but_retrievable(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            cfg["memory_tiers_enabled"] = True
            # Two notes with identical content; one archived, one short-term.
            live = self._report(cfg, title="Sensing Findings Live",
                                 content={"Summary": "wifi sensing doppler csi baseline result"})
            arch = self._report(cfg, title="Sensing Findings Archived",
                                 content={"Summary": "wifi sensing doppler csi baseline result"})
            jm.move_note(arch, Path(tmp) / "Archive" / "Reports", cfg=cfg, lifecycle="archive")
            jm.reindex_local(cfg)

            res = jm.query_local("wifi sensing doppler csi baseline", cfg=cfg, limit=10)
            models = {r["title"]: r for r in res["results"]}
            self.assertIn("Sensing Findings Live", models)
            self.assertIn("Sensing Findings Archived", models)  # still retrievable
            self.assertGreater(
                models["Sensing Findings Live"]["score"],
                models["Sensing Findings Archived"]["score"],
            )

    def test_tier_filter_scopes_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            cfg["memory_tiers_enabled"] = True
            self._report(cfg, title="Only Short", content={"Summary": "unique marker alpha"})
            arch = self._report(cfg, title="Only Archived", content={"Summary": "unique marker alpha"})
            jm.move_note(arch, Path(tmp) / "Archive" / "Reports", cfg=cfg, lifecycle="archive")
            jm.reindex_local(cfg)

            res = jm.query_local("unique marker alpha", cfg=cfg, limit=10, tier="short_term")
            titles = {r["title"] for r in res["results"]}
            self.assertIn("Only Short", titles)
            self.assertNotIn("Only Archived", titles)

    def test_weighting_is_inert_when_tiers_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))  # disabled
            a = self._report(cfg, title="Doc A", content={"Summary": "shared retrieval token zeta"})
            b = self._report(cfg, title="Doc B", content={"Summary": "shared retrieval token zeta"})
            # Physically place B under Archive without enabling tiers.
            jm.move_note(b, Path(tmp) / "Archive" / "Reports", cfg=cfg)
            jm.reindex_local(cfg)

            res = jm.query_local("shared retrieval token zeta", cfg=cfg, limit=10)
            scores = {r["title"]: r["score"] for r in res["results"]}
            # RRF gives identical content slightly different scores by rank, but
            # with weighting off the archived copy must not take the 0.25 penalty:
            # its score stays close to the live copy, not a quarter of it.
            ratio = min(scores["Doc A"], scores["Doc B"]) / max(scores["Doc A"], scores["Doc B"])
            self.assertGreater(ratio, 0.8)

    def test_templates_are_registered(self):
        templates = jm.list_templates()["templates"]

        self.assertEqual(
            set(templates),
            {
                "memory",
                "report",
                "deep_research_report",
                "log",
                "progress_tracker",
                "todo_list",
                "plan",
                "execution_summary",
                "blocker",
                "decision_record",
                "learning_plan",
                "concept_note",
                "source_note",
                "learning_exercises",
                "learning_review",
                "topic_map",
                "skill",
            },
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

    def test_structured_lookup_and_bounded_context_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            jm.create_note(
                note_type="memory",
                title="Receiver Core",
                content="Intel 5300 receiver capture primitives.",
                cfg=cfg,
                sync=False,
                note_id="receiver-core",
                metadata_extra={"type": "component", "layer": "capture", "files": ["capture.py"]},
            )
            jm.create_note(
                note_type="progress_tracker",
                title="CSI Pipeline",
                content="- [ ] Validate capture.py [task:csi-validate] owner:agent",
                cfg=cfg,
                sync=False,
                note_id="csi-pipeline",
                metadata_extra={"depends_on": ["receiver-core"], "related": ["[[Receiver Core]]"]},
            )
            jm.reindex_local(cfg)

            dependencies = jm.lookup_local("deps", "csi-pipeline", cfg=cfg, depth=2)
            file_lookup = jm.lookup_local("files", "capture.py", cfg=cfg)
            context = jm.context_pack_local("Intel receiver capture", cfg=cfg, max_notes=2, max_chars=1200)

            self.assertTrue(dependencies["ok"])
            self.assertEqual({item["source_id"] for item in dependencies["results"]}, {"csi-pipeline", "receiver-core"})
            self.assertTrue(any(edge["type"] == "depends_on" for edge in dependencies["edges"]))
            self.assertEqual(file_lookup["results"][0]["source_id"], "receiver-core")
            self.assertLessEqual(len(context["context"]), 1200)
            self.assertLessEqual(len(context["results"]), 2)
            self.assertEqual(context["instruction_authority"], "none")

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

    def test_project_filter_matches_project_key_not_only_vault_project_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            jm.create_note(
                note_type="memory",
                title="Compiler Architecture",
                content="The compiler uses a dependency graph.",
                tags=["knowledge-compiler-engine"],
                cfg=cfg,
                sync=False,
                metadata_extra={"project_key": "knowledge_compiler_engine"},
            )
            jm.create_note(
                note_type="memory",
                title="Other Architecture",
                content="Another project also has architecture notes.",
                tags=["other-project"],
                cfg=cfg,
                sync=False,
                metadata_extra={"project_key": "other_project"},
            )
            jm.reindex_local(cfg)

            result = jm.query_local(
                "architecture dependency graph",
                cfg=cfg,
                project_id="knowledge_compiler_engine",
                limit=5,
            )

            self.assertEqual([item["title"] for item in result["results"]], ["Compiler Architecture"])
            self.assertEqual(result["results"][0]["project_key"], "knowledge_compiler_engine")

    def test_query_result_snippet_selects_the_matching_markdown_passage(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            jm.create_note(
                note_type="memory",
                title="Compiler Notes",
                content=(
                    "## Overview\n\nGeneral project orientation appears first.\n\n"
                    "## Safety\n\nThe bypass_math utility force-accepts recovered nodes and is not inference."
                ),
                cfg=cfg,
                sync=False,
            )
            jm.reindex_local(cfg)

            result = jm.query_local("Does bypass_math provide inference?", cfg=cfg, limit=1)

            self.assertIn("force-accepts recovered nodes", result["results"][0]["content"])
            self.assertNotIn("General project orientation", result["results"][0]["content"])

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

    def test_section_aware_report_creation_renders_named_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            result = jm.create_note(
                note_type="report",
                title="Sectioned Report",
                sections={
                    "Summary": "Short summary.",
                    "Findings": "- Finding one [1]",
                    "Actions": "- Review next.",
                    "Sources": "1. Example\n   https://example.com/report",
                },
                cfg=cfg,
                sync=False,
            )

            _, body, _ = jm.read_note(Path(result["path"]))
            self.assertIn("## Summary\n\nShort summary.", body)
            self.assertIn("## Findings\n\n- Finding one [1]", body)
            self.assertIn("## Sources\n\n1. Example", body)

    def test_report_validation_rejects_placeholder_sources(self):
        quality = jm.validate_report_sections(
            {
                "Summary": "Generic summary.",
                "Findings": "- Uncited finding.",
                "Sources": "Source: Web Search Results",
            },
            min_sources=1,
        )

        self.assertFalse(quality["ok"])
        self.assertTrue(any("placeholder" in error for error in quality["errors"]))

    def test_create_report_from_search_saves_cited_report_and_reindexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            search_payload = {
                "ok": True,
                "query": "AI news",
                "mode": "news",
                "date_from": "2026-07-20",
                "date_to": "2026-07-20",
                "retrieved_at": "2026-07-20T12:00:00Z",
                "date_scope_note": "Used Google News RSS fallback over the last 48 hours.",
                "results": [
                    {
                        "title": "AI Lab Ships Safer Tool Use Model",
                        "snippet": "The release focuses on tool routing, citations, and agent safety.",
                        "url": "https://example.com/ai-tool-use",
                        "source": "Example News",
                        "published_at": "2026-07-20",
                        "retrieved_at": "2026-07-20T12:00:00Z",
                        "backend": "ddg_news",
                    }
                ],
            }

            result = jm.create_report_from_search(
                query="AI news",
                search_payload=search_payload,
                mode="news",
                date_from="2026-07-20",
                date_to="2026-07-20",
                tags=["ai", "news", "report"],
                cfg=cfg,
                min_sources=1,
            )

            metadata, body, _ = jm.read_note(Path(result["path"]))
            queried = jm.query_local("safer tool routing citations", cfg=cfg, limit=3)

            self.assertTrue(result["ok"])
            self.assertEqual(result["source_count"], 1)
            self.assertEqual(metadata["workflow_id"], "current_news_report")
            self.assertEqual(metadata["quality_state"], "validated")
            self.assertIn("last 48 hours", metadata["date_scope_note"])
            self.assertIn("AI News Briefing - 2026-07-20", metadata["title"])
            self.assertIn("Scope note: Used Google News RSS fallback", body)
            self.assertIn("https://example.com/ai-tool-use", body)
            self.assertTrue(queried["results"])

    def test_create_report_from_search_refuses_uncited_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            result = jm.create_report_from_search(
                query="AI news",
                search_payload={"ok": True, "results": [{"title": "No URL", "snippet": "Generic."}]},
                mode="news",
                date_from="2026-07-20",
                cfg=cfg,
                min_sources=1,
                require_citations=True,
            )

            self.assertFalse(result["ok"])
            self.assertIn("No cited sources", result["error"])

    def test_hostile_url_schemes_are_not_accepted_as_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            # A citation is a claim the user can verify. Only fetchable web
            # schemes qualify; `javascript:` and friends are executable payloads
            # that would be persisted into the vault as a clickable link.
            result = jm.create_report_from_search(
                query="security news",
                search_results=[
                    {
                        "title": "Script Source",
                        "snippet": "Click to verify.",
                        "url": "javascript:fetch('https://attacker.example/'+document.cookie)",
                        "source": "Example",
                    },
                    {
                        "title": "Data Source",
                        "snippet": "Inline.",
                        "url": "data:text/html;base64,PHNjcmlwdD4=",
                        "source": "Example",
                    },
                    {
                        "title": "Local File",
                        "snippet": "Local.",
                        "url": "file:///C:/Users/jakem/.ssh/id_rsa",
                        "source": "Example",
                    },
                    {
                        "title": "Real Source",
                        "snippet": "Legitimate.",
                        "url": "https://example.com/real",
                        "source": "Example",
                    },
                ],
                mode="news",
                cfg=cfg,
                min_sources=1,
                require_citations=True,
                synthesize=False,
            )

            self.assertTrue(result["ok"])
            raw = Path(result["path"]).read_text(encoding="utf-8")
            self.assertNotIn("javascript:", raw)
            self.assertNotIn("data:text/html", raw)
            self.assertNotIn("file:///", raw)
            self.assertIn("https://example.com/real", raw)

    def test_report_with_only_hostile_urls_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            result = jm.create_report_from_search(
                query="security news",
                search_results=[
                    {"title": "Script", "snippet": "x", "url": "javascript:alert(1)", "source": "E"}
                ],
                mode="news",
                cfg=cfg,
                min_sources=1,
                require_citations=True,
                synthesize=False,
            )

            self.assertFalse(result["ok"])
            self.assertIn("No cited sources", result["error"])

    def test_source_titles_cannot_inject_markdown_fences(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            result = jm.create_report_from_search(
                query="security news",
                search_results=[
                    {
                        "title": 'Benign"\n---\nsensitivity: public\ninjected: yes\n---\n',
                        "snippet": "Line one.\n---\nLine two.",
                        "url": "https://example.com/a",
                        "source": "Example",
                    }
                ],
                mode="news",
                cfg=cfg,
                min_sources=1,
                require_citations=True,
                synthesize=False,
            )

            self.assertTrue(result["ok"])
            metadata, body, _ = jm.read_note(Path(result["path"]))
            self.assertNotIn("injected", metadata)
            self.assertNotEqual(metadata.get("sensitivity"), "public")
            # A source title must not be able to open a YAML fence in the body.
            for line in body.splitlines():
                self.assertNotEqual(line.strip(), "---")

    def test_create_todo_template_writes_blank_obsidian_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            result = jm.create_todo_template(cfg=cfg)

            path = Path(result["path"])
            metadata, body, _ = jm.read_note(path)
            queried_tasks = jm.tasks_local(cfg, include_done=True)

            self.assertTrue(result["ok"])
            self.assertEqual(path.name, "to-do-list-template.md")
            self.assertEqual(metadata["type"], "todo_list")
            self.assertEqual(metadata["workflow_id"], "todo_list_template")
            self.assertIn("## Inbox", body)
            self.assertIn("- [ ]", body)
            self.assertIn("## Done", body)
            self.assertIn("- [x]", body)
            self.assertTrue(result["reindex"]["ok"])
            self.assertEqual(queried_tasks["ok"], True)

    def test_learn_topic_creates_report_memory_and_indexes_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            search_payload = {
                "ok": True,
                "query": "WiFi sensing datasets",
                "mode": "research",
                "retrieved_at": "2026-07-21T09:00:00Z",
                "results": [
                    {
                        "title": "WiFi CSI Dataset Collection",
                        "snippet": "A collection of channel state information datasets for WiFi sensing experiments.",
                        "url": "https://example.com/wifi-csi-datasets",
                        "source": "Example Research",
                        "backend": "html_search",
                    },
                    {
                        "title": "Intel 5300 CSI Tool Dataset Notes",
                        "snippet": "Documents datasets captured with Intel 5300 receivers and CSI extraction tooling.",
                        "url": "https://example.com/intel-5300-csi",
                        "source": "Example Lab",
                        "backend": "github_search",
                    },
                ],
            }

            result = jm.learn_topic(
                topic="WiFi sensing datasets",
                search_payload=search_payload,
                cfg=cfg,
                min_sources=2,
                synthesize=False,
            )

            report_path = Path(result["report_path"])
            memory_path = Path(result["memory_path"])
            report_metadata, report_body, _ = jm.read_note(report_path)
            memory_metadata, memory_body, _ = jm.read_note(memory_path)
            queried = jm.query_local("channel state information datasets Intel 5300", cfg=cfg, limit=5)

            self.assertTrue(result["ok"])
            self.assertTrue(report_path.exists())
            self.assertTrue(memory_path.exists())
            self.assertEqual(report_metadata["type"], "deep_research_report")
            self.assertEqual(report_metadata["workflow_id"], "learn_topic_memory")
            self.assertEqual(memory_metadata["id"], "memory-learned-topics-wifi-sensing-datasets")
            self.assertEqual(memory_metadata["workflow_id"], "learn_topic_memory")
            self.assertIn("WiFi sensing datasets", report_body)
            self.assertIn("https://example.com/wifi-csi-datasets", report_body)
            self.assertIn("Full review note", memory_body)
            self.assertIn("Intel 5300", memory_body)
            self.assertEqual(result["reindex"]["indexed_notes"], 1)
            self.assertEqual(len(result["learning_notes"]), 6)
            self.assertTrue(any("WiFi" in item["title"] or "Learned Topic" in item["title"] for item in queried["results"]))

    def test_learn_topic_refuses_uncited_or_sparse_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))

            result = jm.learn_topic(
                topic="Sparse Topic",
                search_payload={"ok": True, "results": [{"title": "No URL", "snippet": "Uncited."}]},
                cfg=cfg,
                min_sources=2,
                require_citations=True,
                synthesize=False,
            )

            self.assertFalse(result["ok"])
            self.assertIn("at least 2 cited", result["error"])

    def test_dispatcher_supports_learn_topic_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            payload = {
                "ok": True,
                "retrieved_at": "2026-07-21T09:00:00Z",
                "results": [
                    {"title": "A", "snippet": "Alpha topic source.", "url": "https://example.com/a"},
                    {"title": "B", "snippet": "Beta topic source.", "url": "https://example.com/b"},
                ],
            }

            result = json.loads(
                jm.jarvis_memory(
                    {
                        "operation": "learn_topic",
                        "topic": "Dispatcher Learning",
                        "search_payload": payload,
                        "synthesize": False,
                        "_config": cfg,
                    }
                )
            )

            self.assertTrue(result["ok"])
            self.assertTrue(Path(result["report_path"]).exists())
            self.assertTrue(Path(result["memory_path"]).exists())

    def test_rag_excludes_private_opt_out_and_tombstoned_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            excluded = jm.create_note(
                note_type="memory",
                title="Private Credential Procedure",
                content="secretalphavalue",
                cfg=cfg,
                sync=False,
                metadata_extra={"rag_index": False, "sensitivity": "private"},
            )
            included = jm.create_note(
                note_type="memory",
                title="Temporary Indexed Fact",
                content="publicbetavalue",
                cfg=cfg,
                sync=False,
            )
            jm.reindex_local(cfg)

            self.assertFalse(jm.query_local("secretalphavalue", cfg=cfg)["results"])
            self.assertTrue(jm.query_local("publicbetavalue", cfg=cfg)["results"])

            tombstoned = jm.tombstone_note(included["path"], reason="Superseded", cfg=cfg)
            self.assertTrue(tombstoned["ok"])
            self.assertFalse(jm.query_local("publicbetavalue", cfg=cfg)["results"])
            metadata, _, _ = jm.read_note(Path(excluded["path"]))
            self.assertEqual(metadata["index_state"], "excluded_local")

    def test_skill_state_requires_tests_and_explicit_user_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            candidate = jm.create_skill_candidate(
                title="Cited WiFi Dataset Scout",
                purpose="Gather source metadata without interpretation.",
                workflow={
                    "schema_version": "jarvis_dual_orchestrator/v1",
                    "workflow_id": "candidate",
                    "version": "1",
                    "name": "Candidate",
                    "max_steps": 1,
                    "steps": [
                        {
                            "step_id": "confirm_scope",
                            "orchestrator": "deterministic",
                            "step_type": "gate",
                            "target": "approval_gate",
                            "description": "Confirm the approved dataset scouting scope.",
                            "depends_on": [],
                            "inputs": {"passed": True},
                            "risk_tier": "T1",
                            "side_effects": "none",
                            "retry_policy": {"safe": True, "max_attempts": 1},
                            "acceptance_criteria": {"required": True, "required_keys": ["status"]},
                            "on_failure": "halt",
                        }
                    ],
                },
                cfg=cfg,
            )
            path = candidate["path"]

            reviewed = jm.transition_skill(path=path, target_state="reviewed", cfg=cfg)
            missing_evidence = jm.transition_skill(path=path, target_state="tested", cfg=cfg)
            tested = jm.transition_skill(path=path, target_state="tested", evidence="Fixture passed.", cfg=cfg)
            self_approval = jm.transition_skill(path=path, target_state="user_approved", actor="agent", cfg=cfg)
            approved = jm.transition_skill(path=path, target_state="user_approved", actor="user", cfg=cfg)
            enabled = jm.transition_skill(path=path, target_state="enabled", cfg=cfg)

            self.assertTrue(reviewed["ok"])
            self.assertFalse(missing_evidence["ok"])
            self.assertTrue(tested["ok"])
            self.assertFalse(self_approval["ok"])
            self.assertTrue(approved["ok"])
            self.assertTrue(enabled["ok"])
            self.assertTrue(enabled["installation"]["ok"])
            from actions.skill_registry import capability_workflows, enabled_skills

            self.assertEqual(len(enabled_skills(cfg)), 1)
            self.assertEqual(len(capability_workflows(cfg)), 1)

    def test_scheduled_task_scan_requires_explicit_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            blocked = jm.tasks_local(cfg, scheduled=True)
            allowed = jm.tasks_local(cfg, scheduled=True, scheduled_permission=True)

            self.assertFalse(blocked["ok"])
            self.assertTrue(allowed["ok"])
            self.assertTrue(allowed["scheduled"])

    def test_rag_exclusions_are_relative_to_nested_vault_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / ".jarvis" / "evals" / "nested-vault"
            cfg = self.cfg(vault)
            included = jm.create_note(
                note_type="memory",
                title="Nested Vault Fact",
                content="nestedvaultsentinel",
                cfg=cfg,
                sync=False,
            )
            internal = vault / ".jarvis" / "ignored.md"
            internal.parent.mkdir(parents=True, exist_ok=True)
            internal.write_text("# ignored nestedvaultsentinel", encoding="utf-8")

            indexed = jm.reindex_local(cfg)
            queried = jm.query_local("nestedvaultsentinel", cfg=cfg, limit=5)

            self.assertEqual(indexed["indexed_notes"], 1)
            self.assertEqual([item["path"] for item in queried["results"]], [included["path"]])

    def test_uninstantiated_templates_are_excluded_and_unknown_confidence_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self.cfg(root)
            template = root / "Templates" / "Takeaway.md"
            template.parent.mkdir(parents=True)
            template.write_text(
                "---\nid: 'takeaway-{{date}}'\ntitle: '{{title}}'\nrag_index: true\nconfidence: unknown\n---\n# {{title}}\n",
                encoding="utf-8",
            )
            note = jm.create_note(
                note_type="memory",
                title="Known Note",
                content="usable fact",
                cfg=cfg,
                sync=False,
                metadata_extra={"confidence": "unknown"},
            )

            indexed = jm.reindex_local(cfg)
            result = jm.query_local("usable fact", cfg=cfg)

            self.assertEqual(indexed["excluded_by_reason"]["template_source"], 1)
            self.assertEqual(indexed["indexed_notes"], 1)
            self.assertEqual(result["results"][0]["path"], note["path"])
            self.assertEqual(result["results"][0]["confidence"], 0.5)

    def test_incremental_index_tracks_unchanged_changes_and_deletions(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self.cfg(Path(tmp))
            note = jm.create_note(note_type="memory", title="Lifecycle", content="alpha", cfg=cfg, sync=False)

            first = jm.reindex_local(cfg)
            second = jm.reindex_local(cfg)
            Path(note["path"]).unlink()
            third = jm.reindex_local(cfg)
            connection = jm._connect_index(cfg)
            try:
                tombstone = connection.execute("SELECT * FROM note_tombstones WHERE path=?", (note["path"],)).fetchone()
            finally:
                connection.close()

            self.assertEqual(first["changed_notes"], 1)
            self.assertEqual(second["unchanged_notes"], 1)
            self.assertEqual(third["removed_notes"], 1)
            self.assertIsNotNone(tombstone)

    def test_hybrid_query_uses_lmstudio_embeddings_when_model_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = jm.resolve_config({
                "jarvis_notes_root": tmp,
                "remember_enabled": False,
                "rag_embedding_provider": "lmstudio",
                "rag_embedding_model": "embed-test",
                "rag_embedding_url": "http://lm.test/v1",
            })
            jm.create_note(note_type="memory", title="Apple", content="orchard fruit", cfg=cfg, sync=False)
            jm.create_note(note_type="memory", title="Router", content="wireless packets", cfg=cfg, sync=False)

            def post(_url, json=None, **_kwargs):
                inputs = json["input"]
                vectors = []
                for text in inputs:
                    vectors.append([1.0, 0.0] if "apple" in text.casefold() or "orchard" in text.casefold() else [0.0, 1.0])
                return FakeResponse({"data": [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)]})

            with mock.patch("actions.jarvis_memory.requests.get", return_value=FakeResponse({"data": [{"id": "embed-test"}]})), \
                 mock.patch("actions.jarvis_memory.requests.post", side_effect=post), \
                 mock.patch("actions.model_lifecycle.active_snapshot", return_value={"active_count": 0}):
                indexed = jm.reindex_local(cfg)
                result = jm.query_local("apple", cfg=cfg, limit=2)

            self.assertTrue(indexed["embedding"]["ok"])
            self.assertGreater(result["semantic_candidates"], 0)
            self.assertEqual(result["results"][0]["title"], "Apple")

    def test_embedding_model_is_loaded_on_demand_when_budget_is_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = jm.resolve_config({
                "jarvis_notes_root": tmp,
                "remember_enabled": False,
                "rag_embedding_provider": "lmstudio",
                "rag_embedding_model": "embed-auto-test",
                "rag_embedding_url": "http://auto-load.test/v1",
                "rag_embedding_auto_load": True,
            })
            jm.create_note(note_type="memory", title="Compiler", content="dependency graph", cfg=cfg, sync=False)

            def post(_url, json=None, **_kwargs):
                return FakeResponse({"data": [{"index": index, "embedding": [1.0, 0.0]} for index, _ in enumerate(json["input"])]})

            with mock.patch("actions.jarvis_memory.requests.get", return_value=FakeResponse({"data": []})), \
                 mock.patch("actions.jarvis_memory.requests.post", side_effect=post), \
                 mock.patch("actions.model_lifecycle.active_snapshot", return_value={"active_count": 0}), \
                 mock.patch(
                     "actions.model_lifecycle.ensure_model_loaded",
                     return_value={"ok": True, "instance_id": "embed-auto-test"},
                 ) as ensure_loaded:
                indexed = jm.reindex_local(cfg)

            ensure_loaded.assert_called_once_with("embed-auto-test", route="rag_embedding")
            self.assertTrue(indexed["embedding"]["ok"])
            self.assertEqual(indexed["embedding"]["indexed_notes"], 1)

    def test_embedding_backfill_splits_a_rejected_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = jm.resolve_config({
                "jarvis_notes_root": tmp,
                "remember_enabled": False,
                "rag_embedding_provider": "lmstudio",
                "rag_embedding_model": "embed-split-test",
                "rag_embedding_url": "http://split.test/v1",
                "rag_embedding_batch_size": 8,
            })
            jm.create_note(note_type="memory", title="One", content="alpha graph", cfg=cfg, sync=False)
            jm.create_note(note_type="memory", title="Two", content="beta graph", cfg=cfg, sync=False)

            def post(_url, json=None, **_kwargs):
                if len(json["input"]) > 1:
                    return FakeResponse({"error": "batch too large"}, status_code=400)
                return FakeResponse({"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

            with mock.patch("actions.jarvis_memory.requests.get", return_value=FakeResponse({"data": [{"id": "embed-split-test"}]})), \
                 mock.patch("actions.jarvis_memory.requests.post", side_effect=post), \
                 mock.patch("actions.model_lifecycle.active_snapshot", return_value={"active_count": 0}), \
                 mock.patch(
                     "actions.model_lifecycle.ensure_model_loaded",
                     return_value={"ok": True, "already_loaded": True, "instance": {"instance_id": "embed-split-test"}},
                 ):
                indexed = jm.reindex_local(cfg)

            self.assertTrue(indexed["embedding"]["ok"])
            self.assertEqual(indexed["embedding"]["indexed_notes"], 2)
            self.assertEqual(indexed["embedding"]["failed_notes"], [])

    def test_three_way_note_reconciliation_preserves_user_section_conflict(self):
        base = {"metadata": {"status": "draft"}, "body": "# Plan\n\n## Scope\nOriginal\n\n## Notes\nBase\n"}
        current = {"metadata": {"status": "draft"}, "body": "# Plan\n\n## Scope\nUser edit\n\n## Notes\nBase\n"}
        proposed = {"metadata": {"status": "reviewed"}, "body": "# Plan\n\n## Scope\nAgent edit\n\n## Notes\nAgent notes\n"}

        result = jm.reconcile_note(base, current, proposed)

        self.assertFalse(result["ok"])
        self.assertTrue(result["requires_user_review"])
        self.assertIn("User edit", result["body"])
        self.assertIn("Agent notes", result["body"])
        self.assertEqual(result["metadata"]["status"], "reviewed")


if __name__ == "__main__":
    unittest.main()


class MemoryTierMigrationTests(unittest.TestCase):
    def _cfg(self, root):
        return jm.resolve_config(
            {"jarvis_notes_root": str(root), "remember_enabled": False,
             "rag_embedding_provider": "disabled", "memory_tiers_enabled": True}
        )

    def test_backfill_is_idempotent_and_folder_aware(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_memory_tiers", str(Path(__file__).resolve().parent.parent / "scripts" / "migrate-memory-tiers.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._cfg(root)
            short = Path(jm.create_note(note_type="report", title="Working", sections={"Summary": "s"},
                                        cfg=cfg, content_mode="sections")["path"])
            # Strip the tier a fresh note would have, to simulate a legacy note.
            jm.update_note_frontmatter(short, {"lifecycle": ""})
            # A note physically under Archive should backfill as archive.
            arch_dir = root / "Archive" / "Reports"
            arch_dir.mkdir(parents=True)
            arch = arch_dir / "old.md"
            arch.write_text("---\nid: a\ntitle: Old\ntype: report\n---\n\n# Old\n\nbody\n", encoding="utf-8")

            first = mod.backfill(root, cfg, apply=True)
            self.assertTrue(any(t == "archive" for _, t in first["changed"]))

            meta_short, _, _ = jm.read_note(short)
            meta_arch, _, _ = jm.read_note(arch)
            self.assertEqual(meta_short["lifecycle"], "short_term")
            self.assertEqual(meta_arch["lifecycle"], "archive")

            # Re-running changes nothing.
            second = mod.backfill(root, cfg, apply=True)
            self.assertEqual(second["changed"], [])

    def test_seed_mocs_creates_one_per_tier_and_is_idempotent(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_memory_tiers", str(Path(__file__).resolve().parent.parent / "scripts" / "migrate-memory-tiers.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._cfg(root)
            created = mod.seed_mocs(root, cfg, apply=True)
            self.assertEqual(len(created), 2)
            self.assertTrue((root / "Long Term" / "Long-Term Map.md").exists())
            self.assertTrue((root / "Archive" / "Archive Map.md").exists())
            # MOCs are excluded from RAG.
            meta, _, _ = jm.read_note(root / "Long Term" / "Long-Term Map.md")
            self.assertFalse(meta["rag_index"])
            self.assertEqual(mod.seed_mocs(root, cfg, apply=True), [])


class LifecycleFieldMigrationTests(unittest.TestCase):
    """Phase 0 (2026-07-25): memory_tier -> lifecycle rename, scripts/migrate-lifecycle-field.py."""

    def _cfg(self, root):
        return jm.resolve_config(
            {"jarvis_notes_root": str(root), "remember_enabled": False,
             "rag_embedding_provider": "disabled", "memory_tiers_enabled": True}
        )

    def _load_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_lifecycle_field",
            str(Path(__file__).resolve().parent.parent / "scripts" / "migrate-lifecycle-field.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_dry_run_reports_but_never_writes(self):
        mod = self._load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._cfg(root)
            path = Path(jm.create_note(note_type="report", title="Legacy", sections={"Summary": "s"},
                                        cfg=cfg, content_mode="sections")["path"])
            # Simulate a pre-rename note on disk: has memory_tier, not lifecycle.
            metadata, body = jm.parse_frontmatter(path.read_text(encoding="utf-8"))
            del metadata["lifecycle"]
            metadata["memory_tier"] = "short_term"
            path.write_text(f"{jm.render_frontmatter(metadata)}\n\n{body.rstrip()}\n", encoding="utf-8")
            raw = path.read_bytes()

            result = mod.migrate(root, apply=False)

            self.assertEqual(len(result["renamed"]), 1)
            self.assertEqual(path.read_bytes(), raw)  # untouched on disk

    def test_apply_renames_the_field_and_preserves_the_value(self):
        mod = self._load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._cfg(root)
            path = Path(jm.create_note(note_type="report", title="Legacy Note", sections={"Summary": "s"},
                                        cfg=cfg, content_mode="sections")["path"])
            jm.update_note_frontmatter(path, {"lifecycle": "archive"})
            # Simulate the pre-migration shape directly: memory_tier present, no lifecycle key.
            metadata, body = jm.parse_frontmatter(path.read_text(encoding="utf-8"))
            del metadata["lifecycle"]
            metadata["memory_tier"] = "archive"
            path.write_text(f"{jm.render_frontmatter(metadata)}\n\n{body.rstrip()}\n", encoding="utf-8")

            result = mod.migrate(root, apply=True)

            self.assertEqual(len(result["renamed"]), 1)
            meta_after, _, _ = jm.read_note(path)
            self.assertEqual(meta_after["lifecycle"], "archive")
            self.assertNotIn("memory_tier", meta_after)

    def test_a_note_already_migrated_is_left_alone(self):
        mod = self._load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._cfg(root)
            path = Path(jm.create_note(note_type="report", title="Already Migrated", sections={"Summary": "s"},
                                        cfg=cfg, content_mode="sections")["path"])
            # A fresh note already has "lifecycle" (create_note writes it directly).
            result = mod.migrate(root, apply=True)
            self.assertEqual(result["renamed"], [])
            self.assertEqual(result["already"], 1)

    def test_a_note_with_neither_field_is_untouched(self):
        mod = self._load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._cfg(root)
            path = root / "Reports" / "bare.md"
            path.parent.mkdir(parents=True)
            path.write_text("---\nid: x\ntitle: Bare\n---\n\n# Bare\n\nbody\n", encoding="utf-8")

            result = mod.migrate(root, apply=True)

            self.assertEqual(result["renamed"], [])
            self.assertEqual(result["unset"], 1)
            meta, _, _ = jm.read_note(path)
            self.assertNotIn("lifecycle", meta)
            self.assertNotIn("memory_tier", meta)

    def test_apply_is_idempotent(self):
        mod = self._load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = self._cfg(root)
            path = Path(jm.create_note(note_type="report", title="Idempotent", sections={"Summary": "s"},
                                        cfg=cfg, content_mode="sections")["path"])
            metadata, body = jm.parse_frontmatter(path.read_text(encoding="utf-8"))
            del metadata["lifecycle"]
            metadata["memory_tier"] = "short_term"
            path.write_text(f"{jm.render_frontmatter(metadata)}\n\n{body.rstrip()}\n", encoding="utf-8")

            first = mod.migrate(root, apply=True)
            second = mod.migrate(root, apply=True)

            self.assertEqual(len(first["renamed"]), 1)
            self.assertEqual(second["renamed"], [])
            self.assertEqual(second["already"], 1)


class FrontmatterParsingTests(unittest.TestCase):
    def test_crlf_frontmatter_parses(self):
        # A note authored with Windows CRLF must parse, or update_note_frontmatter
        # doubles the frontmatter (real corruption seen on the live vault 2026-07-23).
        note = '---\r\nid: "x"\r\ntitle: "T"\r\nsnapshot_hash: "abc"\r\n---\r\n\r\n# Body\r\n'
        meta, body = jm.parse_frontmatter(note)
        self.assertEqual(meta["id"], "x")
        self.assertEqual(meta["snapshot_hash"], "abc")
        self.assertEqual(body.strip(), "# Body")

    def test_crlf_note_update_does_not_double_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "crlf.md"
            path.write_bytes(
                b'---\r\nid: "x"\r\ntitle: "T"\r\nsnapshot_hash: "keep"\r\n---\r\n\r\n# Body\r\n'
            )
            jm.update_note_frontmatter(path, {"lifecycle": "short_term"})
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("\n---\n"), 1)  # exactly one frontmatter block
            meta, _, _ = jm.read_note(path)
            self.assertEqual(meta["lifecycle"], "short_term")
            self.assertEqual(meta["snapshot_hash"], "keep")  # original field preserved


class UnquotedYamlListTests(unittest.TestCase):
    def test_unquoted_flow_list_parses_as_list_not_string(self):
        # Codex-authored notes use YAML flow lists without quotes. Returning a raw
        # string here let a later list() explode "developer-handbook" into chars,
        # corrupting tags across the vault during the tier migration (2026-07-23).
        meta, _ = jm.parse_frontmatter(
            "---\ntags: [developer-handbook, vault, watcher]\n---\n\nbody\n"
        )
        self.assertEqual(meta["tags"], ["developer-handbook", "vault", "watcher"])
        self.assertIsInstance(meta["tags"], list)

    def test_empty_flow_list(self):
        meta, _ = jm.parse_frontmatter("---\ntags: []\nid: x\n---\n\nb\n")
        self.assertEqual(meta["tags"], [])

    def test_quoted_json_list_still_parses(self):
        meta, _ = jm.parse_frontmatter('---\ntags: ["a", "b"]\n---\n\nb\n')
        self.assertEqual(meta["tags"], ["a", "b"])

    def test_update_does_not_explode_unquoted_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "n.md"
            path.write_text(
                "---\nid: x\ntitle: T\ntags: [developer-handbook, vault]\n---\n\n# B\n",
                encoding="utf-8",
            )
            jm.update_note_frontmatter(path, {"lifecycle": "short_term"})
            meta, _, _ = jm.read_note(path)
            self.assertEqual(meta["tags"], ["developer-handbook", "vault"])


class FrontmatterCharacterizationTests(unittest.TestCase):
    """Contract the YAML swap must preserve. Types match JSON, not YAML 1.1:
    timestamps and yes/no stay strings; only true/false are bool.
    """

    def parse(self, fm_body: str):
        meta, body = jm.parse_frontmatter(f"---\n{fm_body}\n---\n\n# Body\n")
        return meta

    def test_quoted_string(self):
        self.assertEqual(self.parse('id: "x"')["id"], "x")

    def test_quoted_json_list(self):
        self.assertEqual(self.parse('tags: ["a", "b"]')["tags"], ["a", "b"])

    def test_unquoted_flow_list(self):
        self.assertEqual(self.parse("tags: [developer-handbook, vault]")["tags"],
                         ["developer-handbook", "vault"])

    def test_empty_string_stays_empty_string(self):
        self.assertEqual(self.parse('review_after: ""')["review_after"], "")

    def test_quoted_iso_timestamp_stays_string(self):
        self.assertEqual(self.parse('created: "2026-07-22T01:25:00Z"')["created"],
                         "2026-07-22T01:25:00Z")

    def test_unquoted_iso_timestamp_stays_string(self):
        # Must NOT become a datetime object (json.dumps can't serialise it; Z->+00:00 drift).
        v = self.parse("created: 2026-07-22T01:25:00Z")["created"]
        self.assertEqual(v, "2026-07-22T01:25:00Z")
        self.assertIsInstance(v, str)

    def test_unquoted_date_stays_string(self):
        v = self.parse("valid_from: 2026-07-22")["valid_from"]
        self.assertEqual(v, "2026-07-22")
        self.assertIsInstance(v, str)

    def test_int_and_float(self):
        m = self.parse("source_version: 9\nconfidence: 0.8")
        self.assertEqual(m["source_version"], 9)
        self.assertIsInstance(m["source_version"], int)
        self.assertEqual(m["confidence"], 0.8)
        self.assertIsInstance(m["confidence"], float)

    def test_true_false_are_bool(self):
        m = self.parse("rag_index: true\ndeleted: false")
        self.assertIs(m["rag_index"], True)
        self.assertIs(m["deleted"], False)

    def test_yes_no_stay_strings(self):
        # YAML 1.1 would make these bool; JSON-typing keeps them strings, matching
        # the current parser and avoiding silent status flips.
        m = self.parse("status: no\nother: yes")
        self.assertEqual(m["status"], "no")
        self.assertEqual(m["other"], "yes")

    def test_quoted_value_with_colon(self):
        self.assertEqual(self.parse('title: "Models: A Guide"')["title"], "Models: A Guide")

    def test_windows_path_value(self):
        # Frontmatter stores the path JSON-escaped (double backslash); parse yields one.
        self.assertEqual(
            self.parse(r'project_root: "F:\\Mark-XLVIII-main"')["project_root"],
            r"F:\Mark-XLVIII-main",
        )

    def test_round_trip_is_idempotent(self):
        original = (
            'id: "x"\ntitle: "T"\ntags: ["a", "b"]\ncreated: "2026-07-22T01:25:00Z"\n'
            'review_after: ""\nsource_version: 9\nconfidence: 0.8\nrag_index: true\ndeleted: false'
        )
        meta = self.parse(original)
        rendered = jm.render_frontmatter(meta)
        meta2, _ = jm.parse_frontmatter(rendered + "\n\n# B\n")
        self.assertEqual(meta, meta2)


class FrontmatterYamlUpgradeTests(unittest.TestCase):
    """Cases the line-parser mishandles that a real YAML load must fix.

    Obsidian's property editor writes block-style lists; the old parser turned
    them into an empty string, silently dropping the values on the next write.
    """

    def parse(self, fm_body: str):
        return jm.parse_frontmatter(f"---\n{fm_body}\n---\n\n# Body\n")[0]

    def test_block_style_list_parses(self):
        m = self.parse("id: x\ntags:\n  - developer-handbook\n  - vault")
        self.assertEqual(m["tags"], ["developer-handbook", "vault"])

    def test_block_list_survives_round_trip(self):
        m = self.parse("id: x\ntitle: T\ntags:\n  - a\n  - b")
        rendered = jm.render_frontmatter(m)
        self.assertEqual(jm.parse_frontmatter(rendered + "\n\n# B\n")[0]["tags"], ["a", "b"])

    def test_malformed_frontmatter_does_not_raise(self):
        # A real YAML load raises on malformed input; the parser must fall back,
        # never raise, and never lose the note.
        bad = "id: x\ntags: [unclosed, list\n  weird: : :"
        meta = self.parse(bad)  # must not raise
        self.assertIsInstance(meta, dict)

    def test_empty_frontmatter(self):
        self.assertEqual(jm.parse_frontmatter("---\n---\n\nbody\n")[0], {})
