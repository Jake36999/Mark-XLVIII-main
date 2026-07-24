import tempfile
import threading
import unittest
from pathlib import Path

from core.process_events import ProcessEventHub


class ProcessEventTests(unittest.TestCase):
    def test_events_are_redacted_and_forbidden_details_are_removed(self):
        hub = ProcessEventHub(max_events=20, max_bytes=64_000)
        event = hub.emit(
            category="model",
            source="openai",
            summary="Authorization: Bearer sk-example-secret-value",
            detail={"prompt": "private prompt", "api_key": "sk-another-secret", "model": "test"},
        )

        rendered = str(event.to_dict())
        self.assertNotIn("sk-example", rendered)
        self.assertNotIn("private prompt", rendered)
        self.assertNotIn("sk-another", rendered)
        self.assertEqual(event.detail["prompt"], "[REDACTED]")

    def test_string_details_cannot_expose_prompts_or_private_reasoning(self):
        hub = ProcessEventHub()
        first = hub.emit(
            category="router",
            source="smoke",
            summary="System prompt: do not reveal this instruction",
            detail="raw_reasoning: private model trace",
        )

        rendered = str(first.to_dict())
        self.assertNotIn("do not reveal", rendered)
        self.assertNotIn("private model trace", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_ring_is_bounded_by_count(self):
        hub = ProcessEventHub(max_events=10, max_bytes=128_000)
        for index in range(30):
            hub.emit(category="test", source="suite", summary=f"event {index}")

        snapshot = hub.snapshot()
        self.assertEqual(len(snapshot), 10)
        self.assertEqual(snapshot[-1]["summary"], "event 29")

    def test_multithreaded_delivery_is_safe(self):
        hub = ProcessEventHub(max_events=250, max_bytes=512_000)
        delivered = []
        lock = threading.Lock()

        def receive(event):
            with lock:
                delivered.append(event.event_id)

        hub.subscribe(receive)
        threads = [
            threading.Thread(
                target=lambda offset=offset: [
                    hub.emit(category="worker", source=str(offset), summary=f"{offset}-{index}")
                    for index in range(20)
                ]
            )
            for offset in range(5)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(hub.snapshot()), 100)
        self.assertEqual(len(delivered), 100)

    def test_export_is_session_summary_and_excluded_from_rag(self):
        hub = ProcessEventHub()
        hub.emit(category="tool", source="web_search", summary="Search completed.")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "trace.md"
            result = hub.export_markdown(target)
            text = target.read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertIn("rag_index: false", text)
        self.assertIn("does not contain hidden reasoning", text)
        self.assertIn("Search completed", text)


if __name__ == "__main__":
    unittest.main()
