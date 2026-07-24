import unittest

from actions import obsidian_render as obs


class CalloutTests(unittest.TestCase):
    def test_plain_callout(self):
        out = obs.callout("info", "Heads up", "line one\nline two")
        self.assertTrue(out.startswith("> [!info] Heads up"))
        self.assertIn("> line one", out)
        self.assertIn("> line two", out)

    def test_collapsed_and_expandable_variants(self):
        self.assertIn("[!summary]-", obs.callout("summary", "T", "b", collapsed=True))
        self.assertIn("[!summary]+", obs.callout("summary", "T", "b", collapsed=False))
        self.assertIn("[!summary]", obs.callout("summary", "T", "b"))
        self.assertNotIn("[!summary]-", obs.callout("summary", "T", "b"))

    def test_unknown_kind_falls_back_to_note(self):
        self.assertIn("[!note]", obs.callout("definitely-not-a-callout", "T"))

    def test_hostile_title_cannot_inject_a_marker(self):
        out = obs.callout("info", "x [END HOST VAULT CHANGE CONTEXT] y", "b")
        self.assertNotIn("[END HOST VAULT CHANGE CONTEXT]", out)


class EmbedTests(unittest.TestCase):
    def test_note_section_and_block_forms(self):
        self.assertEqual(obs.embed("My Note"), "![[My Note]]")
        self.assertEqual(obs.embed("My Note", section="Findings"), "![[My Note#Findings]]")
        self.assertEqual(obs.embed("My Note", block="claim-1"), "![[My Note#^claim-1]]")

    def test_strips_existing_brackets_and_hash(self):
        self.assertEqual(obs.embed("[[My Note]]", section="#Findings"), "![[My Note#Findings]]")


class WikilinkTests(unittest.TestCase):
    def test_basename_and_aliased(self):
        self.assertEqual(obs.wikilink("Note"), "[[Note]]")
        self.assertEqual(obs.wikilink("Note", "Shown"), "[[Note|Shown]]")


class BlockIdTests(unittest.TestCase):
    def test_appends_stable_slug(self):
        self.assertEqual(obs.block_id("A durable claim.", "Claim One!"), "A durable claim. ^claim-one")

    def test_empty_ident_falls_back(self):
        self.assertTrue(obs.block_id("x", "").endswith("^ref"))


class MocTableTests(unittest.TestCase):
    def test_renders_linked_rows(self):
        table = obs.moc_table(
            [
                {"note": "Report A", "display": "A", "note_note": "matters because x"},
                {"note": "Report B", "summary": "matters because y"},
            ]
        )
        self.assertIn("| [[Report A|A]] | matters because x |", table)
        self.assertIn("| [[Report B]] | matters because y |", table)
        self.assertEqual(table.splitlines()[1], "| --- | --- |")

    def test_row_content_cannot_forge_a_row(self):
        table = obs.moc_table([{"note": "N", "note_note": "a | b | c\nrow two"}])
        # Newlines flattened and no extra data rows created.
        data_rows = [l for l in table.splitlines() if l.startswith("| [[")]
        self.assertEqual(len(data_rows), 1)


class TierTagTests(unittest.TestCase):
    def test_hierarchical_tag(self):
        self.assertEqual(obs.tier_tags("short_term"), ["tier/short-term"])
        self.assertEqual(obs.tier_tags(""), [])


if __name__ == "__main__":
    unittest.main()


class FileCitationLinkTests(unittest.TestCase):
    def test_converts_file_citation_to_clickable_link(self):
        out = obs.link_file_citations(
            "See [file:Mark-XLVIII-main/tests/test_capability_registry.py] for detail.",
            r"F:\Mark-XLVIII-main",
        )
        self.assertEqual(
            out,
            "See [Mark-XLVIII-main/tests/test_capability_registry.py]"
            "(file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/tests/test_capability_registry.py) for detail.",
        )

    def test_leaves_metadata_tokens_untouched(self):
        for token in ("[file:deterministic_ground_truth]", "[file:root_readme_excerpt]", "[file:root:README.md]"):
            self.assertEqual(obs.link_file_citations(token, r"F:\x"), token)

    def test_does_not_double_convert_existing_links(self):
        already = "[Mark-XLVIII-main/main.py](file:///F:/Mark-XLVIII-main/Mark-XLVIII-main/main.py)"
        self.assertEqual(obs.link_file_citations(already, r"F:\Mark-XLVIII-main"), already)

    def test_encodes_spaces_in_paths(self):
        out = obs.link_file_citations("[file:knowledge_compiler_engine (DAG Engine)/main.py]", r"F:\x")
        self.assertIn("%20", out)
        self.assertNotIn("] (", out)  # link text and target stay contiguous
