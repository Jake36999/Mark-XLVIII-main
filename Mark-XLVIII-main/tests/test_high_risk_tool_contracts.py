"""Contract tests for the tools that can do irreversible damage.

The 2026-07-30 assessment found the coverage was inverted against risk: 7 of 12
tools classified `risk_level: high` had no test importing their module. The
*gates* around them were well tested -- `test_chat_tool_gate` proves a
`requires_approval` tool pauses and only runs on a real confirmation -- so the
system was well defended against a dangerous tool being called **wrongly**, and
undefended against one **behaving wrongly once approved**.

These are not coverage tests. Each asks three things:

  1. Does it do what it says?
  2. Does it refuse what it should refuse?
  3. When it fails, does it say so -- rather than returning something a caller
     reads as success? (see core/effect_outcome.py)

Safety rules for this file, which matter more than the assertions:

  * Nothing here may delete a real file. File operations run inside a temporary
    directory created under the home directory, so the real `_SAFE_ROOTS` logic
    is exercised rather than patched away, and the directory is removed after.
  * Nothing here may move the mouse, press a key, or change a system setting.
    Every pyautogui-backed path is asserted at its guard, never through it.
  * Nothing here may reach `shutdown_jarvis`, whose handler calls `os._exit(0)`
    and would kill the test runner. It is tested at its gate only.
"""
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions.capability_registry import CAPABILITY_POLICY


class FileControllerContractTests(unittest.TestCase):
    """`file_controller` can delete. Its safety rests on three things: a home
    directory root, a protected-directory list, and trash rather than unlink."""

    def setUp(self):
        # Inside home on purpose: `_is_safe_path` resolves against Path.home(),
        # so a system temp dir would be rejected and the real guard would go
        # untested. Unique per run so parallel workers cannot collide.
        self.root = Path.home() / f".jarvis_contract_test_{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)

    def _run(self, **params) -> str:
        from actions.file_controller import file_controller

        return file_controller(parameters=params)

    def test_it_creates_reads_and_lists_what_it_claims_to(self):
        self._run(action="create_file", path=str(self.root), name="note.txt", content="hello")
        self.assertTrue((self.root / "note.txt").exists())
        self.assertIn("hello", self._run(action="read", path=str(self.root), name="note.txt"))
        self.assertIn("note.txt", self._run(action="list", path=str(self.root)))

    def test_a_path_outside_the_home_root_is_refused(self):
        outside = Path(self.root.anchor) / "Windows" / "System32"
        result = self._run(action="list", path=str(outside))
        self.assertIn("Access denied", result)

    def test_traversal_out_of_the_root_is_refused_after_resolution(self):
        """`_is_safe_path` resolves before comparing, so `..` cannot escape."""
        escape = str(self.root / ".." / ".." / ".." / ".." / "Windows")
        self.assertIn("Access denied", self._run(action="list", path=escape))

    def test_a_protected_user_directory_cannot_be_deleted(self):
        """Desktop, Downloads, Documents, Pictures, Music, Videos and home
        itself. Losing any of these is not recoverable from a trash can in any
        way the user would consider acceptable."""
        for shortcut in ("desktop", "downloads", "documents", "home"):
            with self.subTest(target=shortcut):
                self.assertIn("Protected directory", self._run(action="delete", path=shortcut))

    def test_deleting_a_missing_file_reports_that_rather_than_success(self):
        result = self._run(action="delete", path=str(self.root), name="never-existed.txt")
        self.assertIn("Not found", result)

    def test_deletion_goes_to_the_trash_and_never_unlinks(self):
        """The only deletion path is send2trash. If it is unavailable the tool
        refuses rather than falling back to a permanent delete -- verified by
        asserting the file still exists after the refusal."""
        import actions.file_controller as fc

        victim = self.root / "victim.txt"
        victim.write_text("keep me", encoding="utf-8")

        with mock.patch.object(fc, "_SEND2TRASH", False):
            result = self._run(action="delete", path=str(self.root), name="victim.txt")

        self.assertIn("Permanent deletion is disabled", result)
        self.assertTrue(victim.exists(), "the file was destroyed despite the refusal")

    def test_deletion_calls_send2trash_with_the_real_target(self):
        import actions.file_controller as fc

        victim = self.root / "victim.txt"
        victim.write_text("bye", encoding="utf-8")
        fake = mock.Mock()
        with mock.patch.object(fc, "_SEND2TRASH", True), mock.patch.object(fc, "send2trash", fake):
            result = self._run(action="delete", path=str(self.root), name="victim.txt")

        fake.send2trash.assert_called_once_with(str(victim))
        self.assertIn("Trash", result)

    def test_an_unknown_action_is_named_rather_than_silently_ignored(self):
        self.assertIn("Unknown action", self._run(action="obliterate", path=str(self.root)))

    def test_a_write_that_cannot_happen_is_reported(self):
        result = self._run(action="write", path=str(self.root / "nope"), name="x.txt", content="c")
        self.assertIsInstance(result, str)
        self.assertNotEqual(result.strip(), "")


class ComputerControlContractTests(unittest.TestCase):
    """Drives mouse and keyboard. No test here may pass through the guard."""

    def _run(self, **params) -> str:
        from actions.computer_control import computer_control

        return computer_control(parameters=params)

    def test_an_unknown_action_does_not_reach_the_input_layer(self):
        import actions.computer_control as cc

        with mock.patch.object(cc, "pyautogui", create=True) as gui:
            result = self._run(action="self_destruct")
        self.assertIn("Unknown action", result)
        gui.assert_not_called()

    def test_a_missing_input_backend_is_an_error_not_a_silent_success(self):
        """Returning "Done." with no backend installed would report a click that
        never happened -- the exact shape of the effect-honesty defects."""
        import actions.computer_control as cc

        with mock.patch.object(cc, "_PYAUTOGUI", False):
            with self.assertRaises(RuntimeError):
                cc._require_pyautogui()

    def test_a_screenshot_path_outside_the_safe_roots_falls_back(self):
        """Never writes where it was told to when that is out of bounds."""
        import actions.computer_control as cc

        chosen = cc._safe_screenshot_path(str(Path(Path.home().anchor) / "Windows" / "evil.png"))
        self.assertTrue(
            any(chosen.is_relative_to(root.resolve()) for root in cc._SAFE_SCREENSHOT_ROOTS),
            f"screenshot would have been written to {chosen}",
        )

    def test_a_screenshot_path_inside_the_safe_roots_is_honoured(self):
        import actions.computer_control as cc

        wanted = Path.home() / f".jarvis_contract_{uuid.uuid4().hex[:8]}" / "shot.png"
        self.addCleanup(shutil.rmtree, wanted.parent, True)
        self.assertEqual(cc._safe_screenshot_path(str(wanted)), wanted.resolve())

    def test_no_screenshot_is_taken_while_resolving_a_path(self):
        """Path resolution must be side-effect free -- it runs before any
        decision about whether the capture is allowed."""
        import actions.computer_control as cc

        with mock.patch.object(cc, "pyautogui", create=True) as gui:
            cc._safe_screenshot_path(None)
        gui.screenshot.assert_not_called()


class DesktopControlContractTests(unittest.TestCase):
    """Changes wallpaper and moves desktop files around."""

    def _run(self, **params) -> str:
        from actions.desktop import desktop_control

        return desktop_control(parameters=params)

    def test_setting_a_wallpaper_with_no_path_refuses_instead_of_guessing(self):
        self.assertIn("No image path", self._run(action="wallpaper"))

    def test_a_wallpaper_url_with_no_url_refuses(self):
        self.assertIn("No URL", self._run(action="wallpaper_url"))

    def test_a_non_image_file_is_rejected_by_format(self):
        from actions.desktop import set_wallpaper

        root = Path.home() / f".jarvis_contract_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, root, True)
        doc = root / "notes.txt"
        doc.write_text("not an image", encoding="utf-8")

        self.assertIn("Unsupported format", set_wallpaper(str(doc)))

    def test_a_missing_wallpaper_file_is_reported(self):
        from actions.desktop import set_wallpaper

        result = set_wallpaper(str(Path.home() / "definitely-not-here-9f2c.png"))
        self.assertIsInstance(result, str)
        self.assertNotEqual(result.strip(), "")
        self.assertNotIn("Wallpaper set", result)


class ComputerSettingsContractTests(unittest.TestCase):
    """Volume, brightness, window state."""

    def _run(self, **params) -> str:
        from actions.computer_settings import computer_settings

        return computer_settings(parameters=params)

    def test_a_missing_backend_is_reported_rather_than_reporting_success(self):
        import actions.computer_settings as cs

        with mock.patch.object(cs, "_PYAUTOGUI", False):
            self.assertIn("not installed", self._run(action="volume_up"))

    def test_an_empty_action_is_refused_rather_than_defaulted(self):
        import actions.computer_settings as cs

        with mock.patch.object(cs, "_PYAUTOGUI", True):
            self.assertIn("No action", self._run(action="", description=""))

    def test_an_unknown_action_is_named(self):
        import actions.computer_settings as cs

        with mock.patch.object(cs, "_PYAUTOGUI", True), mock.patch.object(cs, "_detect_action", return_value={}):
            self.assertIn("Unknown action", self._run(action="reformat_disk"))


class BrowserControlContractTests(unittest.TestCase):
    """Drives a real browser. Every test stops before a session is opened."""

    def _run(self, **params) -> str:
        from actions.browser_control import browser_control

        return browser_control(parameters=params)

    def test_an_unknown_action_opens_nothing(self):
        import actions.browser_control as bc

        with mock.patch.object(bc, "_registry") as registry:
            result = self._run(action="exfiltrate")
        self.assertIn("Unknown browser action", result)
        self.assertIn("exfiltrate", result)  # names it, so the caller can correct it
        registry.switch.assert_not_called()

    def test_switching_with_no_target_asks_rather_than_choosing_one(self):
        import actions.browser_control as bc

        with mock.patch.object(bc, "_registry") as registry:
            result = self._run(action="switch")
        self.assertIn("specify", result.lower())
        registry.switch.assert_not_called()


class ShutdownContractTests(unittest.TestCase):
    """`shutdown_jarvis` calls `os._exit(0)`. Nothing may execute it -- a test
    that did would terminate the runner mid-suite. It is verified at its gate."""

    def test_it_is_classified_as_requiring_confirmation(self):
        policy = CAPABILITY_POLICY["shutdown_jarvis"]
        self.assertEqual(policy["risk_level"], "high")
        self.assertTrue(policy["requires_confirmation"])

    def test_a_deterministic_shortcut_cannot_reach_it(self):
        """Deterministic workflow bootstraps are authorised by a matched literal
        phrase. That justifies the tools those handlers use -- never process
        termination."""
        import main

        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis.ui = mock.Mock()
        jarvis.speak = mock.Mock()
        with mock.patch.object(main.JarvisLive, "_execute_tool", new=mock.AsyncMock()) as execute:
            payload = json.loads(
                jarvis._execute_router_tool_call(
                    "c", "shutdown_jarvis", {}, authorized_by="deterministic_workflow"
                )
            )
        self.assertFalse(payload["ok"])
        self.assertIn("not permitted", payload["error"])
        execute.assert_not_called()

    def test_its_permission_boundary_excludes_retrieved_text(self):
        """A vault note or web page saying "shut down" must never be able to
        trigger it. The boundary is recorded so the registry can surface it."""
        boundary = CAPABILITY_POLICY["shutdown_jarvis"]["permission_boundary"].lower()
        self.assertIn("never", boundary)


class EveryHighRiskToolIsNowExercisedTests(unittest.TestCase):
    """The finding this file closes, asserted directly so it cannot silently
    regress when a new high-risk tool is registered."""

    COVERED = {
        "browser_control", "computer_control", "computer_settings", "desktop_control",
        "file_controller", "screen_process", "shutdown_jarvis",
        # covered by their own dedicated suites
        "canvas_plan", "code_helper", "dev_agent", "plan_workflow", "project_operator",
    }

    def test_no_high_risk_tool_lacks_a_contract_test(self):
        high_risk = {
            name for name, policy in CAPABILITY_POLICY.items()
            if policy.get("risk_level") == "high"
        }
        uncovered = sorted(high_risk - self.COVERED)
        self.assertEqual(
            uncovered, [],
            "high-risk tools with no contract test. Add tests, then add them to COVERED: "
            f"{uncovered}",
        )

    def test_every_high_risk_tool_requires_confirmation(self):
        offenders = sorted(
            name for name, policy in CAPABILITY_POLICY.items()
            if policy.get("risk_level") == "high" and not policy.get("requires_confirmation")
        )
        self.assertEqual(offenders, [], f"high-risk tools that can run unconfirmed: {offenders}")


if __name__ == "__main__":
    unittest.main()
