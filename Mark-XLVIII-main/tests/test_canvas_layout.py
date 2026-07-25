import copy
import unittest

from core.canvas_layout import layout_document


def _node(node_id: str, *, branch: str | None = None, width: int = 400, height: int = 180) -> dict:
    node = {"id": node_id, "type": "text", "text": node_id, "x": 0, "y": 0, "width": width, "height": height}
    if branch is not None:
        node["branch"] = branch
    return node


def _edge(src: str, dst: str) -> dict:
    return {"id": f"{src}-{dst}", "fromNode": src, "toNode": dst, "fromSide": "right", "toSide": "left"}


class SingleBranchBackwardCompatibilityTests(unittest.TestCase):
    """WS4c: a canvas with 0 or 1 distinct `branch` values must lay out
    byte-identically to the original single-chain algorithm -- this is the
    load-bearing backward-compatibility property, pinned directly rather than
    only inferred from the rest of the suite staying green."""

    def _linear_payload(self) -> dict:
        return {
            "nodes": [_node("root"), _node("a"), _node("b"), _node("c")],
            "edges": [_edge("root", "a"), _edge("a", "b"), _edge("b", "c")],
        }

    def test_no_branch_key_matches_pre_ws4c_output(self):
        payload = self._linear_payload()
        expected = {
            "root": (0, 0), "a": (0, 320), "b": (0, 640), "c": (0, 960),
        }
        laid_out, _metrics = layout_document(payload, profile="dependency", managed_prefix="")
        by_id = {node["id"]: (node["x"], node["y"]) for node in laid_out["nodes"]}
        self.assertEqual(by_id, expected)

    def test_every_node_sharing_the_same_branch_matches_no_branch_output(self):
        payload = self._linear_payload()
        for node in payload["nodes"]:
            node["branch"] = "only"
        laid_out, _metrics = layout_document(payload, profile="dependency", managed_prefix="")

        payload_no_branch = self._linear_payload()
        laid_out_no_branch, _metrics2 = layout_document(payload_no_branch, profile="dependency", managed_prefix="")

        by_id = {node["id"]: (node["x"], node["y"]) for node in laid_out["nodes"]}
        by_id_no_branch = {node["id"]: (node["x"], node["y"]) for node in laid_out_no_branch["nodes"]}
        self.assertEqual(by_id, by_id_no_branch)

    def test_non_uniform_node_heights_still_match(self):
        # Guards against a flat row-spacing constant silently diverging from
        # the original dynamic per-layer max-height accumulation.
        payload = {
            "nodes": [_node("root", height=889), _node("a", height=60), _node("b", height=440)],
            "edges": [_edge("root", "a"), _edge("a", "b")],
        }
        expected = copy.deepcopy(payload)
        expected_out, _ = layout_document(expected, profile="dependency", managed_prefix="")

        tagged = copy.deepcopy(payload)
        for node in tagged["nodes"]:
            node["branch"] = "solo"
        tagged_out, _ = layout_document(tagged, profile="dependency", managed_prefix="")

        by_id_expected = {node["id"]: (node["x"], node["y"]) for node in expected_out["nodes"]}
        by_id_tagged = {node["id"]: (node["x"], node["y"]) for node in tagged_out["nodes"]}
        self.assertEqual(by_id_expected, by_id_tagged)


class MultiBranchFanOutLayoutTests(unittest.TestCase):
    """WS4c: 2+ distinct `branch` values switch on the column/row fan-out."""

    def _two_branch_payload(self) -> dict:
        # Branch A: a1 (root) <- a2 <- a3 (a3 is the deepest prerequisite)
        # Branch B: b1 (root) <- b2
        # a1 depends on b1 (branch A's root depends on branch B's root, i.e.
        # branch B finishes first) -- mirrors the reference example's
        # right-to-left execution direction.
        return {
            "nodes": [
                _node("a1", branch="A"), _node("a2", branch="A"), _node("a3", branch="A"),
                _node("b1", branch="B"), _node("b2", branch="B"),
            ],
            "edges": [
                _edge("a2", "a1"), _edge("a3", "a2"),
                _edge("b2", "b1"),
                _edge("b1", "a1"),
            ],
        }

    def test_branches_get_distinct_columns(self):
        laid_out, _metrics = layout_document(self._two_branch_payload(), profile="dependency", managed_prefix="")
        by_id = {node["id"]: node for node in laid_out["nodes"]}
        # every node in branch A shares one x; every node in branch B shares a different x
        a_xs = {by_id[nid]["x"] for nid in ("a1", "a2", "a3")}
        b_xs = {by_id[nid]["x"] for nid in ("b1", "b2")}
        self.assertEqual(len(a_xs), 1)
        self.assertEqual(len(b_xs), 1)
        self.assertNotEqual(a_xs, b_xs)

    def test_in_branch_depth_is_monotonic_and_root_is_topmost(self):
        laid_out, _metrics = layout_document(self._two_branch_payload(), profile="dependency", managed_prefix="")
        by_id = {node["id"]: node for node in laid_out["nodes"]}
        # a1 (root, depth 0) sits above a2 (depth 1), which sits above a3 (depth 2)
        self.assertLess(by_id["a1"]["y"], by_id["a2"]["y"])
        self.assertLess(by_id["a2"]["y"], by_id["a3"]["y"])
        self.assertLess(by_id["b1"]["y"], by_id["b2"]["y"])

    def test_untagged_cross_branch_node_lands_at_column_midpoint(self):
        payload = self._two_branch_payload()
        # a genuinely shared node -- no branch tag of its own -- depending on
        # both a2 (branch A) and b2 (branch B)
        payload["nodes"].append(_node("bridge"))
        payload["edges"].append(_edge("a2", "bridge"))
        payload["edges"].append(_edge("b2", "bridge"))

        laid_out, _metrics = layout_document(payload, profile="dependency", managed_prefix="")
        by_id = {node["id"]: node for node in laid_out["nodes"]}
        a_x, b_x = by_id["a1"]["x"], by_id["b1"]["x"]
        expected_mid = (min(a_x, b_x) + max(a_x, b_x)) // 2
        self.assertEqual(by_id["bridge"]["x"], expected_mid)

    def test_tagged_node_stays_in_its_column_even_when_fed_from_another_branch(self):
        # The exact live-decomposition case that exposed the original bug: a
        # branch's own entry node, explicitly tagged, fed only by a node from
        # a *different* branch (or the plan node) -- must NOT be pulled to a
        # midpoint. Only an untagged node gets that treatment.
        payload = {
            "nodes": [_node("plan"), _node("a_entry", branch="A"), _node("b1", branch="B")],
            "edges": [_edge("plan", "a_entry"), _edge("b1", "a_entry")],
        }
        laid_out, _metrics = layout_document(payload, profile="dependency", managed_prefix="")
        by_id = {node["id"]: node for node in laid_out["nodes"]}
        # a_entry (tagged "A") must not collapse to a midpoint with b1's
        # column just because its only feeder is a different branch/the plan.
        self.assertNotEqual(by_id["a_entry"]["x"], by_id["b1"]["x"])

    def test_untagged_root_with_no_feeders_sits_left_of_the_first_branch(self):
        payload = self._two_branch_payload()
        laid_out, _metrics = layout_document(payload, profile="dependency", managed_prefix="")
        by_id = {node["id"]: node for node in laid_out["nodes"]}
        # a1/a2/a3 are all explicitly branch "A" in _two_branch_payload, so
        # there's no untagged plan node there -- add one directly.
        payload2 = self._two_branch_payload()
        payload2["nodes"].append(_node("plan"))
        payload2["edges"].append(_edge("plan", "a3"))
        laid_out2, _ = layout_document(payload2, profile="dependency", managed_prefix="")
        by_id2 = {node["id"]: node for node in laid_out2["nodes"]}
        self.assertLess(by_id2["plan"]["x"], min(by_id2["a1"]["x"], by_id2["b1"]["x"]))

    def test_no_overlaps_across_branches(self):
        laid_out, metrics = layout_document(self._two_branch_payload(), profile="dependency", managed_prefix="")
        self.assertEqual(metrics["overlap_count"], 0)


if __name__ == "__main__":
    unittest.main()
