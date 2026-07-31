"""A turn that fails outright must still answer the user.

Found live on 2026-07-31. A gap-analysis battery ran while LM Studio happened to
be stopped, and all eight scenarios returned an **empty string** to the user:
the outermost handler in `_handle_router_text_command` wrote a line to the
activity log, emitted a trace event, and returned without speaking.

For a chat user that means noticing a log line. For a voice user it means total
silence -- you ask a question and nothing happens at all.

The success path already refuses to end on an empty reply ("Router mode is
active, but the model returned no text."). Failure should not be the one case
that does.
"""
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main


def _jarvis():
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.ui = mock.Mock()
    jarvis.ui.muted = False
    jarvis.speak = mock.Mock()
    jarvis._speaking_lock = threading.Lock()
    jarvis._is_speaking = False
    jarvis._pending_plan_run_id = ""
    jarvis._active_plan_run_id = ""
    jarvis._pending_tool_confirmation = None
    jarvis._phone_active = False
    jarvis._last_user_speech = time.monotonic()
    return jarvis


def _spoken(jarvis) -> str:
    return " ".join(str(c.args[0]) for c in jarvis.speak.call_args_list if c.args)


class FailedTurnStillRepliesTests(unittest.TestCase):
    def test_an_unreachable_model_server_produces_a_spoken_reply(self):
        import requests

        jarvis = _jarvis()
        boom = requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='localhost', port=1234): Max retries exceeded"
        )
        with mock.patch("main.call_with_tools", side_effect=boom), \
             mock.patch("main.call_text", side_effect=boom):
            jarvis._handle_router_text_command("what is the weather", turn_id=None)

        reply = _spoken(jarvis)
        self.assertTrue(reply.strip(), "the user received nothing at all")

    def test_the_reply_names_the_actual_cause(self):
        """"Something went wrong" is not actionable. "LM Studio may not be
        running" is."""
        import requests

        jarvis = _jarvis()
        boom = requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='localhost', port=1234): "
            "Failed to establish a new connection"
        )
        with mock.patch("main.call_with_tools", side_effect=boom), \
             mock.patch("main.call_text", side_effect=boom):
            jarvis._handle_router_text_command("what is the weather", turn_id=None)

        self.assertIn("LM Studio", _spoken(jarvis))

    def test_a_non_connection_failure_is_still_answered(self):
        jarvis = _jarvis()
        with mock.patch("main.call_with_tools", side_effect=ValueError("malformed schema")), \
             mock.patch("main.call_text", side_effect=ValueError("malformed schema")):
            jarvis._handle_router_text_command("what is the weather", turn_id=None)

        reply = _spoken(jarvis)
        self.assertTrue(reply.strip())
        self.assertIn("ValueError", reply)

    def test_the_failure_is_still_logged_and_traced(self):
        """The spoken reply is added to the existing signals, not instead of
        them -- the activity log and the process trace both still record it."""
        import requests

        jarvis = _jarvis()
        boom = requests.exceptions.ConnectionError("Max retries exceeded")
        with mock.patch("main.call_with_tools", side_effect=boom), \
             mock.patch("main.call_text", side_effect=boom):
            jarvis._handle_router_text_command("what is the weather", turn_id=None)

        logged = " ".join(str(c.args[0]) for c in jarvis.ui.write_log.call_args_list if c.args)
        self.assertIn("Router model unavailable", logged)

    def test_a_stale_turn_stays_silent(self):
        """An interrupted or superseded turn must not speak over the turn that
        replaced it -- the same rule the success path follows."""
        import requests

        jarvis = _jarvis()
        boom = requests.exceptions.ConnectionError("Max retries exceeded")
        with mock.patch("main.call_with_tools", side_effect=boom), \
             mock.patch("main.call_text", side_effect=boom), \
             mock.patch.object(main.JarvisLive, "_is_stale_router_turn", return_value=True):
            jarvis._handle_router_text_command("what is the weather", turn_id=7)

        self.assertEqual(_spoken(jarvis).strip(), "")


if __name__ == "__main__":
    unittest.main()
