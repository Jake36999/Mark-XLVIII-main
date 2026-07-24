import unittest

from jarvis_ui_components.graph_layout import force_layout
from jarvis_ui_components.models import GraphEdge, GraphNode


def _fixture():
    nodes = [
        GraphNode("a", "A", project_id="one"),
        GraphNode("b", "B", project_id="one"),
        GraphNode("c", "C", project_id="two"),
    ]
    edges = [GraphEdge("a", "b"), GraphEdge("b", "c")]
    return nodes, edges


class GraphLayoutTests(unittest.TestCase):
    def test_force_layout_is_deterministic(self) -> None:
        nodes, edges = _fixture()
        first = force_layout(nodes, edges, iterations=12)
        second = force_layout(nodes, edges, iterations=12)
        self.assertEqual(first, second)

    def test_force_layout_keeps_nodes_in_bounds(self) -> None:
        nodes, edges = _fixture()
        result = force_layout(nodes, edges, width=500, height=300, iterations=12)
        self.assertEqual(set(result), {"a", "b", "c"})
        self.assertTrue(
            all(0 <= x <= 500 and 0 <= y <= 300 for x, y in result.values())
        )

    def test_single_node_is_centered(self) -> None:
        result = force_layout([GraphNode("a", "A")], [], width=400, height=200)
        self.assertEqual(result, {"a": (200.0, 100.0)})


if __name__ == "__main__":
    unittest.main()
