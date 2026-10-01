import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import capability_schema


class ToolCapabilitiesTests(unittest.TestCase):
    def test_covers_exactly_the_workflow_dispatchable_tools(self):
        ids = capability_schema.ids_by_kind("tool")
        self.assertEqual(ids, capability_schema._WORKFLOW_DISPATCHABLE_TOOL_IDS)

    def test_each_tool_carries_real_keywords_from_capability_registry(self):
        # web_search's keywords are hand-authored in CAPABILITY_HELP and
        # known non-empty -- confirms the merge actually reads real data,
        # not just constructs empty Capability shells.
        web_search = capability_schema.get("web_search")
        self.assertIsNotNone(web_search)
        self.assertIn("web", web_search.keywords)

    def test_risk_tier_is_mapped_not_hardcoded(self):
        # web_search's risk_level is "low" in CAPABILITY_POLICY -> T1.
        web_search = capability_schema.get("web_search")
        self.assertEqual(web_search.risk_tier, "T1")
        # project_operator's risk_level is "high" -> T3.
        project_operator = capability_schema.get("project_operator")
        self.assertEqual(project_operator.risk_tier, "T3")

    def test_requires_confirmation_reflects_capability_policy(self):
        web_search = capability_schema.get("web_search")
        self.assertFalse(web_search.requires_confirmation)
        project_operator = capability_schema.get("project_operator")
        self.assertTrue(project_operator.requires_confirmation)


class DerivedKeywordsTests(unittest.TestCase):
    """scripts/derive_capability_keywords.py's offline output, loaded
    read-only and kept separate from hand-authored `keywords` -- never
    merged, so a human can compare both before trusting either."""

    def test_derived_keywords_load_when_the_cache_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "derived.json"
            cache.write_text(
                json.dumps({"web_search": {"keywords": ["latest news", "current price"]}}),
                encoding="utf-8",
            )
            with mock.patch.object(capability_schema, "_DERIVED_KEYWORDS_PATH", cache):
                web_search = capability_schema.get("web_search")
            self.assertEqual(web_search.derived_keywords, ("latest news", "current price"))

    def test_missing_cache_file_degrades_to_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "definitely_does_not_exist.json"
            with mock.patch.object(capability_schema, "_DERIVED_KEYWORDS_PATH", missing):
                web_search = capability_schema.get("web_search")
            self.assertEqual(web_search.derived_keywords, ())

    def test_malformed_cache_file_degrades_to_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "derived.json"
            cache.write_text("not valid json {{{", encoding="utf-8")
            with mock.patch.object(capability_schema, "_DERIVED_KEYWORDS_PATH", cache):
                web_search = capability_schema.get("web_search")
            self.assertEqual(web_search.derived_keywords, ())

    def test_derived_keywords_never_overwrite_hand_authored_keywords(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "derived.json"
            cache.write_text(
                json.dumps({"web_search": {"keywords": ["totally different phrasing"]}}),
                encoding="utf-8",
            )
            with mock.patch.object(capability_schema, "_DERIVED_KEYWORDS_PATH", cache):
                web_search = capability_schema.get("web_search")
            self.assertIn("web", web_search.keywords)  # hand-authored, untouched
            self.assertEqual(web_search.derived_keywords, ("totally different phrasing",))


class ModelRoleCapabilitiesTests(unittest.TestCase):
    def test_covers_exactly_the_known_model_router_roles(self):
        # "quick"/"main"/"reasoning"/"code" joined 2026-09-25 alongside their
        # runtime.json provider config; "vision" deliberately never does --
        # it's hardcoded local-only in call_vision() (core/model_router.py)
        # so a screen/camera capture can never leave the machine as a side
        # effect of a routing decision.
        ids = capability_schema.ids_by_kind("model_role")
        self.assertEqual(
            ids, frozenset({"planner", "worker", "research", "reviewer", "quick", "main", "reasoning", "code"})
        )

    def test_model_roles_are_health_eligible(self):
        for role_id in ("planner", "worker", "research", "reviewer", "quick", "main", "reasoning", "code"):
            with self.subTest(role=role_id):
                self.assertTrue(capability_schema.get(role_id).health_eligible)


class ToolIdsForRoleTests(unittest.TestCase):
    def test_research_role_gets_the_three_read_only_tools(self):
        self.assertEqual(
            frozenset(capability_schema.tool_ids_for_role("research")),
            frozenset({"web_search", "jarvis_memory", "capability_registry"}),
        )

    def test_project_operator_has_no_role_ceiling(self):
        # implementation reaches project_operator through a fixed,
        # compile-time-frozen target assignment, never through the
        # allowed_tools + rank_tools mechanism this governs.
        self.assertEqual(capability_schema.get("project_operator").allowed_roles, ())

    def test_unknown_role_gets_no_tools(self):
        self.assertEqual(capability_schema.tool_ids_for_role("nonexistent_role"), ())


class AllCapabilitiesTests(unittest.TestCase):
    def test_all_capabilities_is_the_union_of_both_kinds(self):
        all_ids = {c.id for c in capability_schema.all_capabilities()}
        expected = capability_schema._WORKFLOW_DISPATCHABLE_TOOL_IDS | set(capability_schema._MODEL_ROLE_IDS)
        self.assertEqual(all_ids, expected)

    def test_get_returns_none_for_an_unknown_id(self):
        self.assertIsNone(capability_schema.get("definitely_not_a_real_capability"))

    def test_by_kind_returns_only_matching_entries(self):
        for capability in capability_schema.by_kind("tool"):
            self.assertEqual(capability.kind, "tool")
        for capability in capability_schema.by_kind("model_role"):
            self.assertEqual(capability.kind, "model_role")

    def test_no_lens_capabilities_exist_yet(self):
        self.assertEqual(capability_schema.by_kind("lens"), ())


if __name__ == "__main__":
    unittest.main()
