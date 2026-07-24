import json
import tempfile
import unittest
from pathlib import Path

from actions import jarvis_memory as jm
from actions import memory_consolidation as mc


def cfg_for(root: Path, **extra) -> dict:
    base = {
        "jarvis_notes_root": str(root),
        "remember_enabled": False,
        "rag_embedding_provider": "disabled",
        "memory_tiers_enabled": True,
        "memory_consolidation_enabled": True,
        "memory_short_term_age_days": 21,
        "memory_review_default_days": 30,
    }
    base.update(extra)
    return jm.resolve_config(base)


def make_note(cfg, title, *, content=None, extra=None, note_type="report"):
    return Path(
        jm.create_note(
            note_type=note_type,
            title=title,
            sections=content or {"Summary": "content"},
            cfg=cfg,
            content_mode="sections",
            metadata_extra=extra or {},
            reindex=True,
        )["path"]
    )


class CandidateDetectionTests(unittest.TestCase):
    def test_stale_note_past_review_after_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            stale = make_note(cfg, "Old Finding", extra={"review_after": "2020-01-01T00:00:00Z"})
            make_note(cfg, "Fresh Finding", extra={"review_after": "2099-01-01T00:00:00Z"})

            result = mc.detect_candidates(cfg, now=1893456000.0)  # 2030
            stale_paths = {c["path"] for c in result["stale"]}
            self.assertIn(str(stale), stale_paths)
            self.assertEqual(len(result["stale"]), 1)

    def test_aged_snapshot_bound_note_is_flagged_even_without_review_after(self):
        # The project_operator case: a project-memory note carrying snapshot_hash,
        # old, with no review_after set. Its source may have moved.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(
                cfg, "Project Memory",
                extra={"snapshot_hash": "abc123", "updated": "2020-06-01T00:00:00Z"},
            )
            result = mc.detect_candidates(cfg, now=1893456000.0)
            self.assertIn(str(note), {c["path"] for c in result["stale"]})
            reason = next(c for c in result["stale"] if c["path"] == str(note))["reason"]
            self.assertIn("snapshot", reason.lower())

    def test_near_duplicate_notes_are_paired(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp), memory_consolidation_similarity_threshold=0.3)
            make_note(cfg, "WiFi Sensing CSI Doppler A",
                      content={"Summary": "wifi sensing csi doppler motion detection baseline"})
            make_note(cfg, "WiFi Sensing CSI Doppler B",
                      content={"Summary": "wifi sensing csi doppler motion detection baseline"})

            result = mc.detect_candidates(cfg)
            self.assertGreaterEqual(len(result["duplicate"]), 1)
            pair = result["duplicate"][0]
            self.assertIn("path", pair)
            self.assertIn("duplicate_of", pair)

    def test_promotable_short_term_note_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(
                cfg, "Durable Project Result",
                extra={"project_id": "wifi-sensing", "updated": "2020-01-01T00:00:00Z"},
            )
            result = mc.detect_candidates(cfg, now=1893456000.0)
            self.assertIn(str(note), {c["path"] for c in result["promotable"]})

    def test_recent_short_term_note_is_not_promotable(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(cfg, "Today Note", extra={"project_id": "wifi-sensing"})
            result = mc.detect_candidates(cfg)  # now = actual now
            self.assertNotIn(str(note), {c["path"] for c in result["promotable"]})

    def test_detection_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp), memory_consolidation_max_candidates=3)
            for i in range(10):
                make_note(cfg, f"Stale {i}", extra={"review_after": "2020-01-01T00:00:00Z"})
            result = mc.detect_candidates(cfg, now=1893456000.0)
            self.assertLessEqual(len(result["stale"]), 3)

    def test_detection_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(cfg, "Untouched", extra={"review_after": "2020-01-01T00:00:00Z"})
            before = note.read_bytes()
            mc.detect_candidates(cfg, now=1893456000.0)
            self.assertEqual(note.read_bytes(), before)

    def test_disabled_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp), memory_consolidation_enabled=False)
            make_note(cfg, "Stale", extra={"review_after": "2020-01-01T00:00:00Z"})
            result = mc.detect_candidates(cfg, now=1893456000.0)
            self.assertFalse(result["ok"])
            self.assertEqual(result["stale"], [])


class SnapshotDriftTests(unittest.TestCase):
    """The real project_operator fix: flag a note whose source repo has changed."""

    def test_drifted_snapshot_is_flagged_stale(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(
                cfg, "Project Memory",
                extra={"snapshot_hash": "OLD-HASH", "project_root": r"F:\SomeRepo"},
            )
            # Current repo hashes differently → drifted.
            with mock.patch(
                "actions.project_learning.inventory_repository",
                return_value={"ok": True, "snapshot_hash": "NEW-HASH"},
            ):
                result = mc.detect_candidates(cfg)  # now = actual now (note is recent)
            paths = {c["path"] for c in result["stale"]}
            self.assertIn(str(note), paths)
            reason = next(c for c in result["stale"] if c["path"] == str(note))["reason"]
            self.assertIn("drift", reason.lower())

    def test_matching_snapshot_is_not_flagged(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(
                cfg, "Fresh Project Memory",
                extra={"snapshot_hash": "SAME", "project_root": r"F:\SomeRepo"},
            )
            with mock.patch(
                "actions.project_learning.inventory_repository",
                return_value={"ok": True, "snapshot_hash": "SAME"},
            ):
                result = mc.detect_candidates(cfg)
            self.assertNotIn(str(note), {c["path"] for c in result["stale"]})

    def test_missing_repo_does_not_falsely_flag(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(
                cfg, "Gone Repo Memory",
                extra={"snapshot_hash": "OLD", "project_root": r"F:\Gone"},
            )
            with mock.patch(
                "actions.project_learning.inventory_repository",
                return_value={"ok": False, "error": "not found"},
            ):
                result = mc.detect_candidates(cfg)
            self.assertNotIn(str(note), {c["path"] for c in result["stale"]})


class ProposalTests(unittest.TestCase):
    def test_proposal_is_written_under_consolidations(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            make_note(cfg, "Stale One", extra={"review_after": "2020-01-01T00:00:00Z"})

            result = mc.propose(cfg, now=1893456000.0)
            self.assertTrue(result["ok"])
            path = Path(result["path"])
            self.assertTrue(path.exists())
            self.assertEqual(path.parent.name, "Consolidations")

    def test_proposal_has_a_collapsible_callout_and_embed_per_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            stale = make_note(cfg, "Stale Two", extra={"review_after": "2020-01-01T00:00:00Z"})

            result = mc.propose(cfg, now=1893456000.0)
            _, body, _ = jm.read_note(Path(result["path"]))

            self.assertIn("[!warning]-", body)  # collapsible callout
            self.assertIn(f"![[{stale.stem}", body)  # transclusion of the note
            self.assertIn("Reversible", body)

    def test_proposal_lists_exact_target_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            stale = make_note(cfg, "Target Path Note", extra={"review_after": "2020-01-01T00:00:00Z"})

            result = mc.propose(cfg, now=1893456000.0)
            self.assertIn(str(stale), {a["path"] for a in result["actions"]})

    def test_proposal_modifies_no_canonical_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(cfg, "Should Not Change", extra={"review_after": "2020-01-01T00:00:00Z"})
            before = note.read_bytes()

            mc.propose(cfg, now=1893456000.0)
            self.assertEqual(note.read_bytes(), before)

    def test_proposal_reports_nothing_to_do_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            make_note(cfg, "Fresh", extra={"review_after": "2099-01-01T00:00:00Z"})

            result = mc.propose(cfg)
            self.assertTrue(result["ok"])
            self.assertEqual(result["actions"], [])
            self.assertFalse(result.get("path"))


class ApplyTests(unittest.TestCase):
    def test_archive_moves_note_and_sets_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(cfg, "To Archive", extra={"review_after": "2020-01-01T00:00:00Z"})
            action = {"kind": "archive", "path": str(note), "title": "To Archive"}

            result = mc.apply_action(action, cfg=cfg)
            self.assertTrue(result["ok"])
            self.assertFalse(note.exists())
            new_path = Path(result["path"])
            self.assertIn("Archive", new_path.parts)
            meta, _, _ = jm.read_note(new_path)
            self.assertEqual(meta["memory_tier"], "archive")

    def test_archive_never_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(cfg, "Preserve Me", extra={"review_after": "2020-01-01T00:00:00Z"})
            result = mc.apply_action({"kind": "archive", "path": str(note), "title": "Preserve Me"}, cfg=cfg)
            # The file still exists, just relocated.
            self.assertTrue(Path(result["path"]).exists())

    def test_promote_creates_long_term_and_archives_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            src = make_note(cfg, "Durable Result",
                            content={"Summary": "the key durable finding"},
                            extra={"project_id": "wifi-sensing", "updated": "2020-01-01T00:00:00Z"})
            action = {"kind": "promote", "path": str(src), "title": "Durable Result", "project_id": "wifi-sensing"}

            result = mc.apply_action(action, cfg=cfg)
            self.assertTrue(result["ok"])
            long_path = Path(result["long_term_path"])
            self.assertTrue(long_path.exists())
            self.assertIn("Long Term", long_path.parts)
            # Source archived, and the long-term note records supersession.
            self.assertIn("Archive", Path(result["path"]).parts)
            lt_meta, lt_body, _ = jm.read_note(long_path)
            self.assertEqual(lt_meta["memory_tier"], "long_term")

    def test_merge_folds_into_survivor_and_archives_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            newer = make_note(cfg, "Survivor", content={"Summary": "shared body content"},
                              extra={"updated": "2026-01-02T00:00:00Z"})
            older = make_note(cfg, "Duplicate", content={"Summary": "shared body content"},
                              extra={"updated": "2026-01-01T00:00:00Z"})
            action = {"kind": "merge", "path": str(older), "title": "Duplicate", "into": str(newer)}

            result = mc.apply_action(action, cfg=cfg)
            self.assertTrue(result["ok"])
            self.assertIn("Archive", Path(result["path"]).parts)  # older archived
            self.assertTrue(newer.exists())  # survivor stays
            _, survivor_body, _ = jm.read_note(newer)
            self.assertIn(f"![[{older.stem}", survivor_body)  # transclusion of the merged note

    def test_flag_records_contradiction_without_moving(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            a = make_note(cfg, "Claim A", extra={"project_id": "p"})
            b = make_note(cfg, "Claim B", extra={"project_id": "p"})
            action = {"kind": "flag", "path": str(a), "title": "Claim A", "conflicts_with": str(b)}

            result = mc.apply_action(action, cfg=cfg)
            self.assertTrue(result["ok"])
            self.assertTrue(a.exists())  # nothing moved
            meta, body, _ = jm.read_note(a)
            self.assertIn(str(b), meta.get("contradicts", []) if isinstance(meta.get("contradicts"), list) else [b])
            self.assertIn("[!danger]", body)  # visible contradiction callout

    def test_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            note = make_note(cfg, "Once", extra={"review_after": "2020-01-01T00:00:00Z"})
            action = {"kind": "archive", "path": str(note), "title": "Once"}
            first = mc.apply_action(action, cfg=cfg)
            # Re-applying the same action (source already gone) is a clean no-op.
            second = mc.apply_action(action, cfg=cfg)
            self.assertTrue(second["ok"])
            self.assertTrue(second.get("already_applied"))
            del first

    def test_inbound_links_survive_archive_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            target = make_note(cfg, "Linked Target", extra={"review_after": "2020-01-01T00:00:00Z"})
            rel = target.stem
            referrer = make_note(cfg, "Referrer", content={"Summary": "x"})
            jm.update_section(referrer, "## Summary", f"See [[Reports/{rel}|it]].", cfg=cfg)

            result = mc.apply_action({"kind": "archive", "path": str(target), "title": "Linked Target"}, cfg=cfg)
            _, body, _ = jm.read_note(referrer)
            self.assertNotIn(f"[[Reports/{rel}|", body)
            self.assertIn(rel, body)  # link rewritten to the archive location
            del result

    def test_apply_all_runs_every_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            make_note(cfg, "S1", extra={"review_after": "2020-01-01T00:00:00Z"})
            make_note(cfg, "S2", extra={"review_after": "2020-01-01T00:00:00Z"})
            proposal = mc.propose(cfg, now=1893456000.0)

            result = mc.apply_proposal(proposal["path"], cfg=cfg)
            self.assertTrue(result["ok"])
            self.assertEqual(result["applied"], len(proposal["actions"]))


class RegistrationTests(unittest.TestCase):
    def test_facade_dispatches_detect(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            make_note(cfg, "Stale", extra={"review_after": "2020-01-01T00:00:00Z"})
            payload = json.loads(mc.memory_consolidation({"operation": "detect", "_config": cfg}))
            self.assertTrue(payload["ok"])
            self.assertIn("stale", payload)

    def test_apply_requires_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = cfg_for(Path(tmp))
            payload = json.loads(mc.memory_consolidation({"operation": "apply", "_config": cfg}))
            self.assertFalse(payload["ok"])

    def test_tool_is_declared_and_routed(self):
        import main
        from core import tool_dispatcher

        names = {t["name"] for t in main.TOOL_DECLARATIONS}
        self.assertIn("memory_consolidation", names)
        self.assertIn("memory_consolidation", tool_dispatcher.HEADLESS_TOOLS)

    def test_detect_is_read_only_apply_is_gated(self):
        from core import tool_dispatcher

        self.assertFalse(
            tool_dispatcher.classify_effect("memory_consolidation", {"operation": "detect"})["requires_approval"]
        )
        self.assertTrue(
            tool_dispatcher.classify_effect("memory_consolidation", {"operation": "apply"})["requires_approval"]
        )


if __name__ == "__main__":
    unittest.main()
