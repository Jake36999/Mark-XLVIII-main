import unittest

from core.aletheia_supervisor import AletheiaSupervisor


class AletheiaSupervisorTests(unittest.TestCase):
    def test_unreachable_bridge_does_not_spawn_when_autostart_is_disabled(self):
        supervisor = AletheiaSupervisor()

        result = supervisor.ensure_available({"host": "127.0.0.1", "port": 1, "aletheia_autostart": False})

        self.assertFalse(result["reachable"])
        self.assertFalse(result["started"])
        self.assertEqual(result["reason"], "autostart_disabled")


if __name__ == "__main__":
    unittest.main()
