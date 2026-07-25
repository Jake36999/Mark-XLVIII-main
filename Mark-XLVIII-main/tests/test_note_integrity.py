import tempfile
import unittest
from pathlib import Path

from core import note_integrity as ni


def kinds(text):
    return {f["kind"] for f in ni.inspect_note(text)}


class InspectNoteTests(unittest.TestCase):
    def test_clean_note_has_no_findings(self):
        note = '---\nid: "x"\ntitle: "T"\ntags: ["a", "b"]\n---\n\n# Body\n'
        self.assertEqual(ni.inspect_note(note), [])

    def test_detects_doubled_frontmatter(self):
        # A minimal block, then the original frontmatter pushed into the body.
        note = (
            '---\nupdated: "z"\nlifecycle: "short_term"\n---\n\n'
            '---\nid: "x"\ntitle: "T"\n---\n\n# Body\n'
        )
        findings = ni.inspect_note(note)
        self.assertIn("doubled_frontmatter", {f["kind"] for f in findings})
        self.assertEqual(findings[0]["severity"], "error")

    def test_detects_exploded_tags(self):
        note = '---\nid: "x"\ntags: ["[", "d", "e", "v", "e", "l", "o"]\n---\n\n# B\n'
        self.assertIn("exploded_tags", kinds(note))

    def test_unquoted_tags_are_not_flagged_as_exploded(self):
        note = "---\nid: x\ntags: [developer-handbook, vault, watcher]\n---\n\n# B\n"
        self.assertNotIn("exploded_tags", kinds(note))

    def test_detects_unparsable_frontmatter(self):
        note = "---\nid: x\n"  # no closing fence
        self.assertIn("unparsable_frontmatter", kinds(note))

    def test_flags_crlf_frontmatter_as_warning(self):
        note = '---\r\nid: "x"\r\ntitle: "T"\r\n---\r\n\r\n# B\r\n'
        findings = ni.inspect_note(note)
        crlf = [f for f in findings if f["kind"] == "crlf_frontmatter"]
        self.assertTrue(crlf)
        self.assertEqual(crlf[0]["severity"], "warning")
        # CRLF alone must not be misread as doubled/unparsable.
        self.assertNotIn("doubled_frontmatter", {f["kind"] for f in findings})
        self.assertNotIn("unparsable_frontmatter", {f["kind"] for f in findings})

    def test_flags_bare_file_citation_as_info(self):
        note = "---\nid: x\ntitle: T\n---\n\nSee [file:src/main.py] here.\n"
        findings = ni.inspect_note(note)
        bare = [f for f in findings if f["kind"] == "bare_file_citation"]
        self.assertTrue(bare)
        self.assertEqual(bare[0]["severity"], "info")

    def test_clickable_citation_is_not_flagged(self):
        note = "---\nid: x\ntitle: T\n---\n\n[src/main.py](file:///F:/repo/src/main.py)\n"
        self.assertNotIn("bare_file_citation", kinds(note))

    def test_findings_are_severity_ordered(self):
        note = (
            '---\nupdated: "z"\n---\n\n---\nid: "x"\ntitle: "T"\n---\n\n'
            "See [file:a.py].\n"
        )
        sev = [f["severity"] for f in ni.inspect_note(note)]
        self.assertEqual(sev, sorted(sev, key=lambda s: ni.SEVERITIES.index(s)))


class ScanVaultTests(unittest.TestCase):
    def test_scan_aggregates_and_reports_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text('---\nid: "a"\ntitle: "A"\n---\n\nok\n', encoding="utf-8")
            (root / "b.md").write_text('---\nid: "b"\ntitle: "B"\n---\n\nok\n', encoding="utf-8")
            result = ni.scan_vault(root)
            self.assertTrue(result["ok"])
            self.assertEqual(result["scanned"], 2)
            self.assertEqual(result["error_count"], 0)

    def test_scan_flags_corruption_and_sets_not_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.md").write_text(
                '---\nupdated: "z"\n---\n\n---\nid: "x"\ntitle: "T"\n---\n\nbody\n',
                encoding="utf-8",
            )
            result = ni.scan_vault(root)
            self.assertFalse(result["ok"])
            self.assertGreaterEqual(result["error_count"], 1)
            self.assertIn("doubled_frontmatter", result["counts"])

    def test_scan_skips_system_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".obsidian").mkdir()
            (root / ".obsidian" / "junk.md").write_text("---\nid: x\n", encoding="utf-8")
            (root / "real.md").write_text('---\nid: "r"\ntitle: "R"\n---\n\nok\n', encoding="utf-8")
            result = ni.scan_vault(root)
            self.assertEqual(result["scanned"], 1)


if __name__ == "__main__":
    unittest.main()
