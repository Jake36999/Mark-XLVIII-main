"""Threshold alerts, back in service and costing no model call.

`SystemMonitor` was started only as a Gemini Live background task, so it went
inert when Live was switched off and stayed that way for the whole local-first
era. Rewired to router mode on 2026-07-30.

`ProactiveEngine` was retired in the same pass rather than rewired: it handed
the time plus stored memory to a model and let it decide whether to speak
unprompted, which on a host holding one task model at a time evicts whatever is
warm to start a conversation nobody asked for.
"""
import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main
from actions.system_monitor import SystemMonitor


def _jarvis():
    jarvis = main.JarvisLive.__new__(main.JarvisLive)
    jarvis.ui = mock.Mock()
    jarvis.ui.muted = False
    jarvis.speak = mock.Mock()
    jarvis._speaking_lock = threading.Lock()
    jarvis._is_speaking = False
    jarvis._sys_monitor = mock.Mock()
    jarvis._assistant_busy_for_filler = mock.Mock(return_value=False)
    return jarvis


class AlertTextTests(unittest.TestCase):
    """`check()` used to return a prompt -- "[SYSTEM_ALERT] RAM is at 95%. Warn
    the user in their language..." -- because a model was going to phrase it.
    There is no model in this path now, so it returns what the user hears."""

    def _monitor(self):
        return SystemMonitor(thresholds={"cpu": 0, "ram": 0, "temp": 0, "gpu": 0})

    def test_an_alert_is_speakable_not_an_instruction_to_a_model(self):
        alert = self._monitor().check()
        self.assertIsNotNone(alert)
        for leftover in ("[SYSTEM_ALERT]", "Warn the user", "in their language"):
            self.assertNotIn(leftover, alert)

    def test_an_alert_carries_the_actual_number(self):
        with mock.patch("actions.system_monitor.psutil") as psutil:
            psutil.cpu_percent.return_value = 5.0
            psutil.virtual_memory.return_value = mock.Mock(percent=97.0)
            monitor = SystemMonitor(thresholds={"cpu": 99, "ram": 90, "temp": 999, "gpu": 999})
            with mock.patch("actions.system_monitor._get_cpu_temp", return_value=0), \
                 mock.patch("actions.system_monitor._get_gpu_usage", return_value=-1):
                alert = monitor.check()
        self.assertIn("97%", alert)

    def test_nothing_is_said_while_everything_is_healthy(self):
        monitor = SystemMonitor(thresholds={"cpu": 999, "ram": 999, "temp": 999, "gpu": 999})
        self.assertIsNone(monitor.check())

    def test_a_sustained_condition_warns_once_not_every_cycle(self):
        """Without the cooldown a busy machine would be told about it every
        fifteen seconds."""
        monitor = self._monitor()
        self.assertIsNotNone(monitor.check())
        self.assertIsNone(monitor.check())

    def test_a_metrics_failure_is_silent_rather_than_alarming(self):
        with mock.patch("actions.system_monitor.psutil.cpu_percent", side_effect=OSError("no counters")):
            self.assertIsNone(self._monitor().check())


class MonitorLoopTests(unittest.IsolatedAsyncioTestCase):
    async def _one_pass(self, jarvis):
        """Run a single iteration of the monitor loop, then stop it."""
        with mock.patch("main.asyncio.sleep", new=mock.AsyncMock(side_effect=[None, asyncio.CancelledError()])):
            with self.assertRaises(asyncio.CancelledError):
                await jarvis._run_system_monitor()

    async def test_an_alert_is_spoken_without_calling_a_model(self):
        jarvis = _jarvis()
        jarvis._sys_monitor.check.return_value = "Memory is at 96%, sir."
        with mock.patch("main.call_text") as call_text, \
             mock.patch("main.call_with_tools") as call_with_tools:
            await self._one_pass(jarvis)

        jarvis.speak.assert_called_once_with("Memory is at 96%, sir.")
        call_text.assert_not_called()
        call_with_tools.assert_not_called()

    async def test_silence_when_there_is_nothing_to_report(self):
        jarvis = _jarvis()
        jarvis._sys_monitor.check.return_value = None
        await self._one_pass(jarvis)
        jarvis.speak.assert_not_called()

    async def test_it_does_not_talk_over_a_reply_the_user_asked_for(self):
        jarvis = _jarvis()
        jarvis._is_speaking = True
        jarvis._sys_monitor.check.return_value = "Memory is at 96%, sir."
        await self._one_pass(jarvis)
        jarvis.speak.assert_not_called()

    async def test_it_stays_quiet_when_muted(self):
        jarvis = _jarvis()
        jarvis.ui.muted = True
        jarvis._sys_monitor.check.return_value = "Memory is at 96%, sir."
        await self._one_pass(jarvis)
        jarvis.speak.assert_not_called()

    async def test_it_stays_quiet_while_the_assistant_is_busy(self):
        jarvis = _jarvis()
        jarvis._assistant_busy_for_filler.return_value = True
        jarvis._sys_monitor.check.return_value = "Memory is at 96%, sir."
        await self._one_pass(jarvis)
        jarvis.speak.assert_not_called()

    async def test_a_failing_check_cannot_take_the_assistant_down(self):
        """A monitor is the last thing that should be able to kill the loop."""
        jarvis = _jarvis()
        jarvis._sys_monitor.check.side_effect = RuntimeError("psutil exploded")
        await self._one_pass(jarvis)          # must not raise RuntimeError
        jarvis.speak.assert_not_called()


class ProactiveEngineRetiredTests(unittest.TestCase):
    def test_the_module_is_gone(self):
        with self.assertRaises(ImportError):
            import actions.proactive  # noqa: F401

    def test_nothing_references_it(self):
        source = Path(main.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ProactiveEngine", source.replace("# ProactiveEngine", ""))

    def test_the_assistant_does_not_speak_unprompted_on_idle(self):
        """The property the retirement buys: nothing schedules speech from
        silence alone."""
        source = Path(main.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_run_proactive_mode", source)
        self.assertNotIn("should_trigger", source)


if __name__ == "__main__":
    unittest.main()
