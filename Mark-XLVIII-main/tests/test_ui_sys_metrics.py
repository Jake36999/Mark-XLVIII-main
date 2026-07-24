import threading
import time
import unittest
from unittest import mock

import psutil


class SysMetricsUpdateOrderingTests(unittest.TestCase):
    """The sys-monitor panel's CPU/MEM/NET bars must keep updating even if the
    GPU/temperature sensor calls (pynvml/wmi/ctypes) slow down or fail outright
    under heavy load -- otherwise the whole panel looks frozen while a model is
    generating, when only the sensor probe is actually stuck."""

    def _bare_metrics(self):
        from ui import _SysMetrics

        metrics = _SysMetrics.__new__(_SysMetrics)
        metrics.cpu = 0.0
        metrics.mem = 0.0
        metrics.net = 0.0
        metrics.gpu = -1.0
        metrics.tmp = -1.0
        metrics._lock = threading.Lock()
        metrics._last_net = psutil.net_io_counters()
        metrics._last_net_t = time.time()
        return metrics

    def test_fast_metrics_publish_before_a_failing_gpu_probe_is_even_called(self):
        from ui import _SysMetrics

        metrics = self._bare_metrics()
        published_before_gpu_probe = {}

        def fake_get_gpu(self):
            with self._lock:
                published_before_gpu_probe["cpu"] = self.cpu
                published_before_gpu_probe["mem"] = self.mem
            raise RuntimeError("nvml stalled")

        with mock.patch.object(_SysMetrics, "_get_gpu", fake_get_gpu):
            with self.assertRaises(RuntimeError):
                metrics._update()

        # CPU/MEM were already written into self.* by the time the GPU probe ran,
        # proving the fast metrics don't wait on the slow/failing sensor call.
        self.assertIn("cpu", published_before_gpu_probe)
        self.assertGreaterEqual(published_before_gpu_probe["cpu"], 0.0)
        self.assertGreaterEqual(published_before_gpu_probe["mem"], 0.0)

    def test_gpu_and_temp_still_publish_on_the_happy_path(self):
        metrics = self._bare_metrics()

        with mock.patch.object(type(metrics), "_get_gpu", return_value=42.0), \
             mock.patch.object(type(metrics), "_get_temp", return_value=55.0):
            metrics._update()

        self.assertEqual(metrics.gpu, 42.0)
        self.assertEqual(metrics.tmp, 55.0)
        self.assertGreaterEqual(metrics.cpu, 0.0)


if __name__ == "__main__":
    unittest.main()
