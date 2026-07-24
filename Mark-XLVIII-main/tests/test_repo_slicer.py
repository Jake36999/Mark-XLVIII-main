import textwrap
import unittest

from core import repo_slicer as rs

SAMPLE = textwrap.dedent('''
    """Module docstring."""
    import os
    from typing import Any

    TOP = 1

    @decorator
    def alpha(x: int, y: str = "z") -> bool:
        """Alpha does a thing."""
        v = helper(x)
        return bool(v)

    async def beta(items):
        for i in items:
            await sink(i)

    class Widget:
        def method_one(self):
            return alpha(1)
''')


class SlicePythonTests(unittest.TestCase):
    def setUp(self):
        self.slices = rs.slice_python_source(SAMPLE, "sample.py")
        self.by_name = {s["name"]: s for s in self.slices}

    def test_extracts_functions_classes_and_methods(self):
        names = {s["name"] for s in self.slices}
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertIn("Widget", names)
        self.assertIn("method_one", names)

    def test_kinds_are_classified(self):
        self.assertEqual(self.by_name["alpha"]["kind"], "function")
        self.assertEqual(self.by_name["beta"]["kind"], "async_function")
        self.assertEqual(self.by_name["Widget"]["kind"], "class")
        self.assertEqual(self.by_name["method_one"]["kind"], "method")

    def test_signature_is_real(self):
        sig = self.by_name["alpha"]["signature"]
        self.assertEqual(sig["args"], ["x: int", "y: str = 'z'"])
        self.assertEqual(sig["returns"], "bool")

    def test_qualname_for_method(self):
        self.assertEqual(self.by_name["method_one"]["qualname"], "Widget.method_one")

    def test_calls_and_decorators_and_docstring(self):
        alpha = self.by_name["alpha"]
        self.assertIn("helper", alpha["calls"])
        self.assertIn("decorator", alpha["decorators"])
        self.assertEqual(alpha["docstring"], "Alpha does a thing.")

    def test_stable_and_content_ids(self):
        alpha = self.by_name["alpha"]
        self.assertTrue(alpha["slice_id"].startswith("sample.py::alpha@"))
        self.assertEqual(len(alpha["content_id"]), 16)  # short sha
        # re-slicing identical source yields identical content id
        again = {s["name"]: s for s in rs.slice_python_source(SAMPLE, "sample.py")}
        self.assertEqual(again["alpha"]["content_id"], alpha["content_id"])

    def test_line_span_and_code(self):
        alpha = self.by_name["alpha"]
        self.assertLess(alpha["start_line"], alpha["end_line"])
        self.assertIn("def alpha", alpha["code"])
        self.assertNotIn("|", alpha["code"].splitlines()[0])  # no line-number prefix

    def test_complexity_reflects_branches(self):
        # beta has a loop; method_one is straight-line
        self.assertGreater(self.by_name["beta"]["complexity"], self.by_name["method_one"]["complexity"])

    def test_module_imports_collected(self):
        module = rs.module_summary(SAMPLE, "sample.py")
        self.assertIn("os", module["imports"])
        self.assertIn("typing.Any", module["imports"])


class RobustnessTests(unittest.TestCase):
    def test_syntax_error_returns_empty_not_raises(self):
        self.assertEqual(rs.slice_python_source("def broken(:\n  pass", "x.py"), [])

    def test_non_python_file_is_skipped_gracefully(self):
        self.assertEqual(rs.slice_python_source("", "x.py"), [])


class DedupTests(unittest.TestCase):
    def test_identical_slices_across_files_dedupe(self):
        body = "def f(a):\n    return a + 1\n"
        combined = rs.dedupe_slices(
            rs.slice_python_source(body, "a.py") + rs.slice_python_source(body, "b.py")
        )
        self.assertEqual(len(combined), 1)
        self.assertGreaterEqual(len(combined[0]["seen_in"]), 2)


class ContextRenderTests(unittest.TestCase):
    def test_render_is_compact_and_labelled(self):
        slices = rs.slice_python_source(SAMPLE, "sample.py")
        text = rs.render_slices(slices, max_chars=4000)
        self.assertIn("[file:sample.py]", text)      # keeps the citation convention
        self.assertIn("def alpha", text)
        self.assertLessEqual(len(text), 4000)

    def test_render_respects_char_budget(self):
        big = "\n\n".join(f"def f{i}(x):\n    return x\n" for i in range(200))
        slices = rs.slice_python_source(big, "big.py")
        text = rs.render_slices(slices, max_chars=800)
        self.assertLessEqual(len(text), 800)

    def test_render_without_citation_omits_file_token(self):
        # project_learning renders with cite=False so _defuse_source_text does not
        # strip a [file: token out of the source body; provenance is the batch wrapper.
        slices = rs.slice_python_source(SAMPLE, "sample.py")
        text = rs.render_slices(slices, max_chars=4000, cite=False)
        self.assertNotIn("[file:", text)
        self.assertIn("def alpha", text)          # still code-bearing
        self.assertIn("function alpha", text)      # still labelled by kind


if __name__ == "__main__":
    unittest.main()
