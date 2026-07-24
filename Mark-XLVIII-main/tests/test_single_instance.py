import os
import unittest
import uuid
from unittest import mock


class SingleInstanceGuardTests(unittest.TestCase):
    def test_second_guard_with_same_name_is_rejected(self):
        from core.single_instance import SingleInstanceGuard

        name = f"jarvis-test-{os.getpid()}-{uuid.uuid4().hex}"
        first = SingleInstanceGuard(name)
        second = SingleInstanceGuard(name)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
        finally:
            second.release()
            first.release()

    def test_guard_can_be_reacquired_after_release(self):
        from core.single_instance import SingleInstanceGuard

        name = f"jarvis-test-{os.getpid()}-{uuid.uuid4().hex}"
        first = SingleInstanceGuard(name)
        second = SingleInstanceGuard(name)
        self.assertTrue(first.acquire())
        first.release()
        try:
            self.assertTrue(second.acquire())
        finally:
            second.release()

    def test_focus_existing_window_is_disabled_off_windows(self):
        from core.single_instance import SingleInstanceGuard

        with mock.patch("core.single_instance.os.name", "posix"):
            self.assertFalse(SingleInstanceGuard.focus_existing_window())


if __name__ == "__main__":
    unittest.main()
