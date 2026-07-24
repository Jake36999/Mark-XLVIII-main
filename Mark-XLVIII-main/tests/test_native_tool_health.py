import unittest

from core.native_tool_health import NATIVE_CONTRACTS, probe_native_tools


class NativeToolHealthTests(unittest.TestCase):
    def test_contracts_expose_read_write_risk_and_side_effect_free_health(self):
        result = probe_native_tools(import_probe=lambda _: True, executable_probe=lambda _: True)

        self.assertTrue(result["ok"])
        self.assertEqual(set(result["tools"]), set(NATIVE_CONTRACTS))
        self.assertTrue(all(item["available"] for item in result["tools"].values()))
        self.assertTrue(all(item["probe_side_effects"] == "none" for item in result["tools"].values()))
        self.assertTrue(all("risk" in item and "read_actions" in item and "write_actions" in item for item in result["tools"].values()))

    def test_missing_hard_dependency_is_unavailable_and_optional_executable_is_degraded(self):
        missing_import = probe_native_tools(import_probe=lambda name: name != "playwright", executable_probe=lambda _: True)
        no_media_binary = probe_native_tools(import_probe=lambda _: True, executable_probe=lambda _: False)

        self.assertEqual(missing_import["tools"]["browser_control"]["status"], "unavailable")
        self.assertEqual(no_media_binary["tools"]["file_processor"]["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
