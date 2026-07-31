"""Everything main.py asks of the UI must exist on the real UI.

The blind spot this closes: every test in this suite builds
`jarvis.ui = mock.Mock()`, and a Mock answers to **any** attribute name. So a
call to a UI method that does not exist passes the entire suite and raises
AttributeError the first time a real user reaches that line.

That is not hypothetical. `_run_task_review_scheduler` called `self.ui.log(...)`;
`JarvisUI` has `write_log` and no `log`. Every completed scheduled review raised
AttributeError, the summary never reached the log, and the user got a stdout
error instead of their overdue count. 1187 tests passed throughout.

Checked statically rather than by constructing widgets: `ui.py` builds a Qt
application, and a test that needed a display would be skipped exactly where it
is most needed.
"""
import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = ROOT / "main.py"
UI_PY = ROOT / "ui.py"


def _ui_class_names(class_name: str = "JarvisUI") -> set[str]:
    """Every attribute the named UI class exposes: methods, properties, and
    anything assigned to `self` anywhere in its body."""
    tree = ast.parse(UI_PY.read_text(encoding="utf-8"))
    cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name),
        None,
    )
    assert cls is not None, f"{class_name} not found in ui.py"
    names: set[str] = set()
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    for node in ast.walk(cls):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and isinstance(getattr(node, "ctx", None), ast.Store)
        ):
            names.add(node.attr)
    return names


def _self_ui_attributes() -> dict[str, list[int]]:
    """Every `self.ui.X` main.py touches, with line numbers."""
    used: dict[str, list[int]] = {}
    for node in ast.walk(ast.parse(MAIN_PY.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            inner = node.value
            if (
                isinstance(inner.value, ast.Name)
                and inner.value.id == "self"
                and inner.attr == "ui"
            ):
                used.setdefault(node.attr, []).append(node.lineno)
    return used


class MainToUiContractTests(unittest.TestCase):
    def test_every_ui_attribute_main_uses_exists(self):
        provided = _ui_class_names()
        used = _self_ui_attributes()
        self.assertTrue(used, "found no self.ui.* usage -- the extractor is broken, not main.py")

        missing = {
            name: lines for name, lines in used.items() if name not in provided
        }
        detail = "; ".join(
            f"self.ui.{name} (main.py:{','.join(str(n) for n in lines)})"
            for name, lines in sorted(missing.items())
        )
        self.assertEqual(
            missing, {},
            "main.py calls UI attributes that JarvisUI does not define. Each is an "
            f"AttributeError for a real user and invisible to Mock-based tests: {detail}",
        )

    def test_the_logging_method_is_the_one_that_exists(self):
        """Named explicitly because this is the one that shipped broken."""
        provided = _ui_class_names()
        self.assertIn("write_log", provided)
        self.assertNotIn("log", provided, "if `log` is added, the guard below is stale")
        self.assertNotIn("log", _self_ui_attributes())

    def test_the_extractor_would_notice_a_missing_method(self):
        """Guards the test itself: if the AST walk silently stopped finding
        anything, the assertion above would pass vacuously."""
        provided = _ui_class_names()
        self.assertIn("write_log", provided)
        self.assertIn("set_state", provided)
        self.assertNotIn("definitely_not_a_real_ui_method", provided)


class CallbackWiringTests(unittest.TestCase):
    """The UI calls back into main. A callback the UI invokes but main never
    assigns stays None and the interaction silently does nothing."""

    def test_every_callback_the_ui_exposes_is_assigned_by_main(self):
        provided = _ui_class_names()
        callbacks = {n for n in provided if n.startswith("on_")}
        self.assertTrue(callbacks, "no on_* callbacks found -- extractor broken")

        source = MAIN_PY.read_text(encoding="utf-8")
        unassigned = sorted(c for c in callbacks if f"self.ui.{c}" not in source)
        self.assertEqual(
            unassigned, [],
            f"JarvisUI exposes these callbacks but main.py never assigns them: {unassigned}",
        )


class DocumentedShortcutsExistTests(unittest.TestCase):
    """The User Guide and capability registry promise specific key combinations."""

    def _shortcuts(self) -> set[str]:
        import re

        return {
            s.lower()
            for s in re.findall(r'QKeySequence\(\s*["\']([^"\']+)["\']', UI_PY.read_text(encoding="utf-8"))
        }

    def test_the_documented_shortcuts_are_bound(self):
        shortcuts = self._shortcuts()
        for combo, what in (("ctrl+k", "command palette"), ("ctrl+shift+o", "operations dialog")):
            with self.subTest(combo=combo):
                self.assertIn(combo, shortcuts, f"{combo} is documented as the {what} but is not bound")

    def test_the_registry_description_matches_what_is_bound(self):
        from actions.capability_registry import CAPABILITY_HELP

        details = CAPABILITY_HELP["operational_ui"]["details"]
        shortcuts = self._shortcuts()
        for combo in ("Ctrl+K", "Ctrl+Shift+O"):
            if combo in details:
                with self.subTest(combo=combo):
                    self.assertIn(combo.lower(), shortcuts)


class PlayerObjectContractTests(unittest.TestCase):
    """Action modules receive the UI as `player`. Same Mock blindness applies."""

    def test_every_unguarded_player_attribute_exists_on_the_ui(self):
        import re

        ui_names: set[str] = set()
        tree = ast.parse(UI_PY.read_text(encoding="utf-8"))
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            for node in cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    ui_names.add(node.name)
            for node in ast.walk(cls):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and isinstance(getattr(node, "ctx", None), ast.Store)
                ):
                    ui_names.add(node.attr)

        action_sources = {
            path: path.read_text(encoding="utf-8", errors="replace")
            for path in (ROOT / "actions").glob("*.py")
        }
        offenders: list[str] = []
        for path, source in action_sources.items():
            try:
                module = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(module):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "player"
                    and node.attr not in ui_names
                ):
                    # A hasattr check makes the call safe by construction.
                    if re.search(rf'hasattr\(\s*player\s*,\s*["\']{re.escape(node.attr)}["\']', source):
                        continue
                    offenders.append(f"{path.name}:{node.lineno} player.{node.attr}")

        self.assertEqual(
            sorted(offenders), [],
            f"action modules call UI attributes that do not exist and are not hasattr-guarded: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
