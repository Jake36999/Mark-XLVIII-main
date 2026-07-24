import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.process_events import PROCESS_EVENTS, emit_process_event
from jarvis_ui_components.process_trace import ProcessTraceWidget


class ProcessTraceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        PROCESS_EVENTS.clear()

    def test_background_event_reaches_widget_through_queued_signal(self):
        widget = ProcessTraceWidget()
        widget.show()

        thread = threading.Thread(
            target=lambda: emit_process_event(
                category="tool",
                source="web_search",
                summary="Authorization: Bearer sk-secret-value",
                state="completed",
            )
        )
        thread.start()
        thread.join()
        deadline = time.time() + 2
        while widget._tree.topLevelItemCount() == 0 and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.01)

        self.assertEqual(widget._tree.topLevelItemCount(), 1)
        self.assertNotIn("sk-secret", widget._tree.topLevelItem(0).text(3))
        widget.close()

    def test_pause_keeps_hub_history_and_resume_refreshes(self):
        widget = ProcessTraceWidget()
        widget._pause.setChecked(True)
        emit_process_event(category="vault", source="watcher", summary="External note edit indexed.")
        self.app.processEvents()

        self.assertEqual(widget._tree.topLevelItemCount(), 0)
        self.assertEqual(PROCESS_EVENTS.status()["event_count"], 1)
        widget._pause.setChecked(False)
        self.app.processEvents()

        self.assertEqual(widget._tree.topLevelItemCount(), 1)
        widget.close()


if __name__ == "__main__":
    unittest.main()
