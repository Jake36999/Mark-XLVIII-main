import unittest


class LinkValidationRequestTests(unittest.TestCase):
    """core/session_credentials.py's link-time probe shape per provider.

    Every non-anthropic provider used to get the same OpenAI-Responses-shaped
    probe (`path="responses"`, `max_output_tokens`). DeepInfra's OpenAI-
    compatible surface has no /responses endpoint at all -- sending that probe
    would 404 and a perfectly valid DeepInfra key would never link. This pins
    the chat/completions-shaped probe added for it, and that anthropic/openai
    are unaffected by the new branch.
    """

    def test_deepinfra_probe_uses_chat_completions_not_responses(self):
        from core.session_credentials import _link_validation_request

        path, payload = _link_validation_request("deepinfra", "openai/gpt-oss-20b")

        self.assertEqual(path, "chat/completions")
        self.assertEqual(payload["model"], "openai/gpt-oss-20b")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Reply with OK."}])
        self.assertNotIn("input", payload)

    def test_deepinfra_probe_budget_survives_hidden_reasoning_tokens(self):
        """8 tokens (the OpenAI/Anthropic probe budget) measured empty on a
        live reasoning-tagged DeepInfra model; this asserts the probe carries
        real headroom rather than reusing that budget."""
        from core.session_credentials import _link_validation_request

        _, payload = _link_validation_request("deepinfra", "openai/gpt-oss-20b")

        self.assertGreater(payload["max_tokens"], 8)

    def test_anthropic_probe_unchanged(self):
        from core.session_credentials import _link_validation_request

        path, payload = _link_validation_request("anthropic", "claude-sonnet-5")

        self.assertEqual(path, "messages")
        self.assertEqual(payload["max_tokens"], 8)

    def test_openai_probe_unchanged(self):
        from core.session_credentials import _link_validation_request

        path, payload = _link_validation_request("openai", "gpt-5.5")

        self.assertEqual(path, "responses")
        self.assertEqual(payload["max_output_tokens"], 8)


class ProviderDefaultBaseUrlTests(unittest.TestCase):
    def test_deepinfra_has_a_registered_default_base_url(self):
        from core.session_credentials import _PROVIDER_DEFAULT_BASE_URL

        self.assertEqual(_PROVIDER_DEFAULT_BASE_URL["deepinfra"], "https://api.deepinfra.com/v1/openai")


class ProviderHeadersTests(unittest.TestCase):
    def test_deepinfra_uses_bearer_auth_like_openai(self):
        from core.session_credentials import _provider_headers

        headers = _provider_headers(bytearray(b"test-key"), "deepinfra")

        self.assertEqual(headers["Authorization"], "Bearer test-key")
        self.assertNotIn("x-api-key", headers)


if __name__ == "__main__":
    unittest.main()
