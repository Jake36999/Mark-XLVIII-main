import unittest
from unittest import mock

from core import tool_catalogue


class LexicalCandidatesTests(unittest.TestCase):
    def test_filters_to_dispatchable_tool_ids_only(self):
        # select_capability ranks across every live-chat capability (~20);
        # most (browser_control, reminder, ...) aren't reachable from
        # dual_orchestrator._dispatch_tool at all -- confirming they're
        # dropped is the whole point of this filter.
        fake_result = {
            "candidates": [
                {"id": "browser_control", "score": 9},
                {"id": "web_search", "score": 5},
                {"id": "jarvis_memory", "score": 3},
                {"id": "reminder", "score": 2},
            ]
        }
        with mock.patch("actions.capability_registry.select_capability", return_value=fake_result):
            result = tool_catalogue.lexical_candidates("search the web for something")

        ids = [c["id"] for c in result]
        self.assertEqual(ids, ["web_search", "jarvis_memory"])

    def test_returns_empty_list_on_any_failure(self):
        with mock.patch("actions.capability_registry.select_capability", side_effect=RuntimeError("boom")):
            result = tool_catalogue.lexical_candidates("anything")
        self.assertEqual(result, [])

    def test_returns_empty_list_when_candidates_field_is_malformed(self):
        with mock.patch("actions.capability_registry.select_capability", return_value={"candidates": "not-a-list"}):
            result = tool_catalogue.lexical_candidates("anything")
        self.assertEqual(result, [])


class SemanticScoresTests(unittest.TestCase):
    def test_computes_cosine_similarity_against_each_tool_summary(self):
        # query vector first, then one vector per (sorted) tool id --
        # _semantic_scores must pair them back up correctly.
        vectors = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        with mock.patch("actions.jarvis_memory._embed_texts", return_value=(vectors, {"ok": True})), mock.patch(
            "core.runtime_config.load_runtime_config", return_value={}
        ):
            scores = tool_catalogue._semantic_scores("query", frozenset({"jarvis_memory", "web_search"}))

        # sorted(["jarvis_memory", "web_search"]) == ["jarvis_memory", "web_search"]
        self.assertAlmostEqual(scores["jarvis_memory"], 1.0, places=4)
        self.assertAlmostEqual(scores["web_search"], 0.0, places=4)

    def test_degrades_to_empty_dict_when_embeddings_unavailable(self):
        with mock.patch("actions.jarvis_memory._embed_texts", return_value=([], {"ok": False, "status": "disabled"})), mock.patch(
            "core.runtime_config.load_runtime_config", return_value={}
        ):
            scores = tool_catalogue._semantic_scores("query", frozenset({"web_search"}))
        self.assertEqual(scores, {})

    def test_degrades_to_empty_dict_on_exception(self):
        with mock.patch("actions.jarvis_memory._embed_texts", side_effect=RuntimeError("boom")), mock.patch(
            "core.runtime_config.load_runtime_config", return_value={}
        ):
            scores = tool_catalogue._semantic_scores("query", frozenset({"web_search"}))
        self.assertEqual(scores, {})

    def test_empty_query_or_empty_tool_ids_short_circuits(self):
        self.assertEqual(tool_catalogue._semantic_scores("", frozenset({"web_search"})), {})
        self.assertEqual(tool_catalogue._semantic_scores("query", frozenset()), {})


class RankToolsTests(unittest.TestCase):
    def test_fuses_lexical_and_semantic_signals_by_reciprocal_rank(self):
        lexical = {"candidates": [{"id": "web_search", "score": 9}, {"id": "jarvis_memory", "score": 1}]}
        semantic = {"web_search": 0.9, "jarvis_memory": 0.1, "project_operator": 0.0, "capability_registry": 0.0}
        with mock.patch("actions.capability_registry.select_capability", return_value=lexical), mock.patch.object(
            tool_catalogue, "_semantic_scores", return_value=semantic
        ):
            ranked = tool_catalogue.rank_tools("remember this and search the web")

        # every dispatchable id is present, not just the ones with a hit
        self.assertEqual({item["tool_id"] for item in ranked}, tool_catalogue.DISPATCHABLE_TOOL_IDS)
        # web_search ranks #1 on both signals -- it must win outright, not tie
        self.assertEqual(ranked[0]["tool_id"], "web_search")
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])

    def test_allowed_tools_restricts_the_candidate_set(self):
        lexical = {"candidates": [{"id": "jarvis_memory", "score": 9}, {"id": "web_search", "score": 1}]}
        with mock.patch("actions.capability_registry.select_capability", return_value=lexical), mock.patch.object(
            tool_catalogue, "_semantic_scores", return_value={}
        ):
            ranked = tool_catalogue.rank_tools("anything", allowed_tools=["jarvis_memory"])

        self.assertEqual([item["tool_id"] for item in ranked], ["jarvis_memory"])

    def test_empty_allowed_tools_returns_empty_ranking(self):
        ranked = tool_catalogue.rank_tools("anything", allowed_tools=[])
        self.assertEqual(ranked, [])

    def test_use_semantic_false_skips_the_semantic_signal_entirely(self):
        lexical = {"candidates": [{"id": "web_search", "score": 1}]}
        with mock.patch("actions.capability_registry.select_capability", return_value=lexical), mock.patch.object(
            tool_catalogue, "_semantic_scores"
        ) as semantic_mock:
            tool_catalogue.rank_tools("anything", use_semantic=False)
        semantic_mock.assert_not_called()

    def test_lexical_only_still_ranks_when_semantic_signal_is_unavailable(self):
        lexical = {"candidates": [{"id": "web_search", "score": 9}, {"id": "jarvis_memory", "score": 1}]}
        with mock.patch("actions.capability_registry.select_capability", return_value=lexical), mock.patch.object(
            tool_catalogue, "_semantic_scores", return_value={}
        ):
            ranked = tool_catalogue.rank_tools("search the web")

        self.assertEqual(ranked[0]["tool_id"], "web_search")
        self.assertGreater(ranked[0]["score"], 0)


class RelevantToolIdsTests(unittest.TestCase):
    def test_floor_excludes_zero_scoring_tools(self):
        lexical = {"candidates": [{"id": "web_search", "score": 5}]}
        with mock.patch("actions.capability_registry.select_capability", return_value=lexical), mock.patch.object(
            tool_catalogue, "_semantic_scores", return_value={}
        ):
            ids = tool_catalogue.relevant_tool_ids("search the web", floor=0.0)

        self.assertIn("web_search", ids)
        self.assertNotIn("project_operator", ids)  # no signal at all -> score 0, excluded by floor


if __name__ == "__main__":
    unittest.main()
