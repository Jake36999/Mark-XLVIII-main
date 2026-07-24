import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from actions import security_audit
from core import runtime_config
from core.session_credentials import (
    SessionCredentialBroker,
    _link_validation_request,
    _provider_headers,
    classify_provider_failure,
    detect_key_provider,
)


class RuntimeConfigurationSecurityTests(unittest.TestCase):
    def test_runtime_configuration_never_serializes_secret_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.json"
            saved = runtime_config.save_runtime_config(
                {
                    "planner_model": "gpt-test",
                    "openai_api_key": "test-secret-value",
                    "nested": {"access_token": "test-token", "enabled": True},
                },
                path,
            )
            text = path.read_text(encoding="utf-8")

            self.assertNotIn("api_key", saved)
            self.assertNotIn("access_token", saved["nested"])
            self.assertNotIn("test-secret-value", text)
            self.assertNotIn("test-token", text)
            self.assertEqual(saved["planner_model"], "gpt-test")

    def test_legacy_configuration_is_migrated_once_then_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            runtime_path = config_dir / "runtime.json"
            legacy_path = config_dir / "api_keys.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "planner_model": "gpt-test",
                        "openai_api_key": "test-secret-value",
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(runtime_config, "RUNTIME_CONFIG_PATH", runtime_path), \
                 mock.patch.object(runtime_config, "LEGACY_CONFIG_PATH", legacy_path):
                result = runtime_config.migrate_legacy_config()
                loaded = runtime_config.load_runtime_config()

            self.assertTrue(result["ok"])
            self.assertEqual(loaded["planner_model"], "gpt-test")
            self.assertNotIn("openai_api_key", loaded)
            self.assertEqual(json.loads(legacy_path.read_text(encoding="utf-8")), {})

    def test_provider_failure_classification_only_clears_invalid_authentication(self):
        invalid = classify_provider_failure(401, {"error": "invalid_api_key"})
        restricted = classify_provider_failure(403, {"error": "region"})
        limited = classify_provider_failure(429, {"error": "rate limit"})

        self.assertTrue(invalid["clear_key"])
        self.assertEqual(invalid["state"], "invalid")
        self.assertFalse(restricted["clear_key"])
        self.assertEqual(restricted["state"], "degraded")
        self.assertFalse(limited["clear_key"])
        self.assertEqual(limited["reason"], "rate_limited")

    def test_broker_is_a_child_process_and_terminates_at_session_end(self):
        broker = SessionCredentialBroker()
        status = broker.status()
        process = broker._process

        self.assertEqual(status["state"], "unlinked")
        self.assertIsNotNone(process)
        self.assertTrue(process.is_alive())
        broker.close()
        self.assertFalse(process.is_alive())

    def test_anthropic_uses_x_api_key_not_bearer_auth(self):
        """WS3: Anthropic authenticates via x-api-key + a version header, not
        an Authorization: Bearer token like OpenAI/openai-compatible providers."""
        key = bytearray(b"sk-ant-test-key")

        anthropic_headers = _provider_headers(key, "anthropic")
        openai_headers = _provider_headers(key, "openai")

        self.assertEqual(anthropic_headers["x-api-key"], "sk-ant-test-key")
        self.assertIn("anthropic-version", anthropic_headers)
        self.assertNotIn("Authorization", anthropic_headers)
        self.assertEqual(openai_headers["Authorization"], "Bearer sk-ant-test-key")
        self.assertNotIn("x-api-key", openai_headers)

    def test_anthropic_link_probe_uses_messages_endpoint_with_max_tokens(self):
        """Anthropic's Messages API has no /responses endpoint and always
        requires max_tokens -- unlike OpenAI's probe payload."""
        path, payload = _link_validation_request("anthropic", "claude-sonnet-5")

        self.assertEqual(path, "messages")
        self.assertEqual(payload["model"], "claude-sonnet-5")
        self.assertIn("max_tokens", payload)
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Reply with OK."}])

    def test_openai_link_probe_is_unchanged(self):
        path, payload = _link_validation_request("openai", "gpt-5.5")

        self.assertEqual(path, "responses")
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertIn("input", payload)

    def test_detect_key_provider_by_shape(self):
        self.assertEqual(detect_key_provider("sk-ant-api03-realkey"), "anthropic")
        self.assertEqual(detect_key_provider("sk-proj-realkey"), "openai")

    def test_redacted_audit_does_not_return_matched_secret(self):
        fake_secret = "sk-" + "A" * 28
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.log"
            path.write_text(f"Authorization: Bearer {fake_secret}\n", encoding="utf-8")

            findings = security_audit.scan_paths([Path(tmp)])

            self.assertTrue(findings)
            encoded = json.dumps(findings)
            self.assertNotIn(fake_secret, encoded)
            self.assertIn("fingerprint", findings[0])
            self.assertTrue(any(item["location"] == str(path) for item in findings))


if __name__ == "__main__":
    unittest.main()
