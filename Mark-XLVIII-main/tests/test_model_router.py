import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


class FakeResponse:
    def __init__(self, payload, status_code=200, text="OK"):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")

    def json(self):
        return self._payload


class ModelRouterTests(unittest.TestCase):
    def test_openai_env_key_takes_precedence_over_config_key(self):
        from core import model_router

        settings = model_router.resolve_settings(
            "planner",
            config={
                "openai_api_key": "config-key",
                "planner_provider": "openai",
                "planner_model": "gpt-5.5",
            },
            environ={"OPENAI_API_KEY": "env-key"},
        )

        self.assertEqual(settings.provider, "openai")
        self.assertEqual(settings.model, "gpt-5.5")
        self.assertEqual(settings.api_key, "env-key")
        self.assertEqual(settings.base_url, "https://api.openai.com/v1")

    def test_worker_role_defaults_to_lmstudio_endpoint(self):
        from core import model_router

        settings = model_router.resolve_settings(
            "worker",
            config={"worker_model": "qwen3-4b", "lmstudio_url": "http://localhost:1234/v1/"},
            environ={},
        )

        self.assertEqual(settings.provider, "lmstudio")
        self.assertEqual(settings.model, "qwen3-4b")
        self.assertEqual(settings.base_url, "http://localhost:1234/v1")
        self.assertIsNone(settings.api_key)

    def test_load_config_accepts_utf8_bom_written_by_powershell(self):
        from core import model_router

        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", delete=False) as handle:
            handle.write(json.dumps({"openai_api_key": "key-from-file"}))
            path = handle.name

        try:
            self.assertEqual(model_router.load_config(pathlib.Path(path))["openai_api_key"], "key-from-file")
        finally:
            os.unlink(path)

    def test_openai_call_uses_responses_api_and_returns_output_text(self):
        from core import model_router

        calls = []

        def fake_get(url, **kwargs):
            return FakeResponse({"data": []})

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"output_text": "planned"})

        result = model_router.call_text(
            "make a plan",
            role="planner",
            config={"planner_provider": "openai", "planner_model": "gpt-5.5"},
            environ={"OPENAI_API_KEY": "valid-test-key"},
            post=fake_post,
            get=fake_get,
        )

        self.assertEqual(result, "planned")
        self.assertEqual(calls[0][0], "https://api.openai.com/v1/responses")
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer valid-test-key")
        self.assertEqual(calls[0][1]["json"]["model"], "gpt-5.5")
        self.assertEqual(calls[0][1]["json"]["input"], "make a plan")

    def test_invalid_openai_key_falls_back_to_local_models(self):
        from core import model_router

        calls = []

        def fake_get(url, **kwargs):
            calls.append(("get", url, kwargs))
            return FakeResponse({"error": "invalid"}, status_code=401, text="invalid api key")

        def fake_post(url, **kwargs):
            calls.append(("post", url, kwargs))
            return FakeResponse({"choices": [{"message": {"content": "local fallback"}}]})

        result = model_router.call_text(
            "hello jarvis",
            role="planner",
            config={
                "planner_provider": "openai",
                "planner_model": "gpt-5.5",
                "lmstudio_url": "http://localhost:1234/v1",
                "model_routes": {"quick": ["mistralai/mistral-7b-instruct-v0.3"]},
            },
            environ={"OPENAI_API_KEY": "invalid-test-key"},
            post=fake_post,
            get=fake_get,
        )

        self.assertEqual(result, "local fallback")
        self.assertEqual(calls[0][0], "get")
        self.assertEqual(calls[1][1], "http://localhost:1234/v1/chat/completions")
        self.assertEqual(calls[1][2]["json"]["model"], "mistralai/mistral-7b-instruct-v0.3")

    def test_planner_openai_fallback_does_not_try_openai_model_id_in_lmstudio(self):
        from core import model_router

        calls = []

        def fake_get(url, **kwargs):
            return FakeResponse({"error": "invalid"}, status_code=401, text="invalid api key")

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"]["model"])
            return FakeResponse({"choices": [{"message": {"content": "local fallback"}}]})

        result = model_router.call_text(
            "Summarize these tool results for the user in a concise answer.",
            role="planner",
            config={
                "planner_provider": "openai",
                "planner_model": "gpt-5.4",
                "lmstudio_url": "http://localhost:1234/v1",
                "model_routes": {"main": ["qwen/qwen3.5-9b"], "quick": ["qwen/qwen3-4b-2507"]},
            },
            environ={"OPENAI_API_KEY": "invalid-test-key"},
            post=fake_post,
            get=fake_get,
        )

        self.assertEqual(result, "local fallback")
        self.assertNotIn("gpt-5.4", calls)

    def test_missing_openai_key_falls_back_to_local_models(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"choices": [{"message": {"content": "local no key"}}]})

        result = model_router.call_text(
            "hello jarvis",
            role="planner",
            config={
                "planner_provider": "openai",
                "planner_model": "gpt-5.5",
                "lmstudio_url": "http://localhost:1234/v1",
                "model_routes": {"quick": ["mistralai/mistral-7b-instruct-v0.3"]},
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(result, "local no key")
        self.assertEqual(calls[0][0], "http://localhost:1234/v1/chat/completions")

    def test_openai_response_error_falls_back_to_local_models(self):
        from core import model_router

        calls = []

        def fake_get(url, **kwargs):
            return FakeResponse({"data": []})

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/responses"):
                return FakeResponse({"error": "quota"}, status_code=429, text="quota exceeded")
            return FakeResponse({"choices": [{"message": {"content": "local after openai error"}}]})

        result = model_router.call_text(
            "hello jarvis",
            role="planner",
            config={
                "planner_provider": "openai",
                "planner_model": "gpt-5.5",
                "lmstudio_url": "http://localhost:1234/v1",
                "model_routes": {"quick": ["mistralai/mistral-7b-instruct-v0.3"]},
            },
            environ={"OPENAI_API_KEY": "valid-but-quota-test-key"},
            post=fake_post,
            get=fake_get,
        )

        self.assertEqual(result, "local after openai error")
        self.assertEqual(calls[0][0], "https://api.openai.com/v1/responses")
        self.assertEqual(calls[1][0], "http://localhost:1234/v1/chat/completions")

    def test_lmstudio_call_uses_chat_completions_and_returns_message_content(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"choices": [{"message": {"content": "drafted"}}]})

        result = model_router.call_text(
            "write code",
            role="worker",
            config={
                "worker_provider": "lmstudio",
                "worker_model": "qwen3-4b",
                "lmstudio_url": "http://localhost:1234/v1",
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(result, "drafted")
        self.assertEqual(calls[0][0], "http://localhost:1234/v1/chat/completions")
        payload = calls[0][1]["json"]
        self.assertEqual(payload["model"], "qwen3-4b")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "write code"}])

    def test_lmstudio_call_folds_system_prompt_into_user_message(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

        result = model_router.call_text(
            "hello",
            role="planner",
            system="Reply briefly.",
            config={
                "planner_provider": "lmstudio",
                "lmstudio_url": "http://localhost:1234/v1",
                "model_routes": {"quick": ["mistralai/mistral-7b-instruct-v0.3"]},
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(result, "ok")
        messages = calls[0][1]["json"]["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("Reply briefly.", messages[0]["content"])
        self.assertIn("User request:\nhello", messages[0]["content"])

    def test_simple_planner_prompt_routes_to_quick_local_model(self):
        from core import model_router

        candidates = model_router.select_lmstudio_models(
            "hello jarvis",
            role="planner",
            config={
                "planner_provider": "lmstudio",
                "planner_model": "qwen/qwen3.5-9b",
            },
        )

        self.assertEqual(candidates[0], "mistralai/mistral-7b-instruct-v0.3")
        self.assertIn("qwen/qwen3.5-9b", candidates)

    def test_worker_code_prompt_can_route_to_task_models_after_baseline_candidate(self):
        from core import model_router

        candidates = model_router.select_lmstudio_models(
            "debug this failing test",
            role="worker",
            config={
                "worker_provider": "lmstudio",
                "worker_model": "qwen/qwen3-4b-2507",
                "model_routes": {"code": ["deepseek-r1-0528-qwen3-8b"]},
            },
        )

        self.assertEqual(candidates[:2], ["qwen/qwen3-4b-2507", "deepseek-r1-0528-qwen3-8b"])

    def test_baseline_lmstudio_prompt_does_not_add_ttl(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"])
            return FakeResponse({"choices": [{"message": {"content": "hello"}}]})

        model_router.call_text(
            "hello jarvis",
            role="worker",
            config={
                "worker_provider": "lmstudio",
                "worker_model": "qwen/qwen3-4b-2507",
                "lmstudio_url": "http://localhost:1234/v1",
                "baseline_models": ["qwen/qwen3-4b-2507", "orpeus_text_to_speech"],
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(calls[0]["model"], "qwen/qwen3-4b-2507")
        self.assertNotIn("ttl", calls[0])

    def test_task_lmstudio_prompt_adds_ttl(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"])
            return FakeResponse({"choices": [{"message": {"content": "debugged"}}]})

        model_router.call_text(
            "debug this failing test",
            role="planner",
            config={
                "planner_provider": "lmstudio",
                "lmstudio_url": "http://localhost:1234/v1",
                "baseline_models": ["qwen/qwen3-4b-2507", "orpeus_text_to_speech"],
                "task_model_ttl_seconds": 300,
                "model_routes": {
                    "code": ["deepseek-r1-0528-qwen3-8b"],
                    "quick": ["qwen/qwen3-4b-2507"],
                },
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(calls[0]["model"], "deepseek-r1-0528-qwen3-8b")
        self.assertEqual(calls[0]["ttl"], 300)

    def test_openai_fallback_to_task_model_adds_ttl(self):
        from core import model_router

        calls = []

        def fake_get(url, **kwargs):
            return FakeResponse({"error": "invalid"}, status_code=401, text="invalid api key")

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"])
            return FakeResponse({"choices": [{"message": {"content": "local code fallback"}}]})

        result = model_router.call_text(
            "debug this failing test",
            role="planner",
            config={
                "planner_provider": "openai",
                "planner_model": "gpt-5.4",
                "lmstudio_url": "http://localhost:1234/v1",
                "baseline_models": ["qwen/qwen3-4b-2507", "orpeus_text_to_speech"],
                "task_model_ttl_seconds": 300,
                "model_routes": {
                    "code": ["deepseek-r1-0528-qwen3-8b"],
                    "quick": ["qwen/qwen3-4b-2507"],
                },
            },
            environ={"OPENAI_API_KEY": "invalid-test-key"},
            post=fake_post,
            get=fake_get,
        )

        self.assertEqual(result, "local code fallback")
        self.assertEqual(calls[0]["model"], "deepseek-r1-0528-qwen3-8b")
        self.assertEqual(calls[0]["ttl"], 300)

    def test_lmstudio_call_falls_back_after_load_failure(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"]["model"])
            if len(calls) == 1:
                return FakeResponse({}, status_code=500, text='Failed to load model "qwen/qwen3.5-9b". Error: Error loading model.')
            return FakeResponse({"choices": [{"message": {"content": "fallback ok"}}]})

        result = model_router.call_text(
            "make a plan for this project",
            role="planner",
            config={
                "planner_provider": "lmstudio",
                "planner_model": "qwen/qwen3.5-9b",
                "lmstudio_url": "http://localhost:1234/v1",
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(result, "fallback ok")
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[0], "qwen/qwen3.5-9b")
        self.assertEqual(calls[1], "mistralai/mistral-7b-instruct-v0.3")

    def test_lmstudio_fallback_treats_unloaded_model_as_retryable(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"]["model"])
            if len(calls) == 1:
                return FakeResponse({}, status_code=400, text='{"error":"Model is unloaded."}')
            return FakeResponse({"choices": [{"message": {"content": "fallback ok"}}]})

        result = model_router.call_text(
            "hello jarvis",
            role="worker",
            config={
                "worker_provider": "lmstudio",
                "worker_model": "google/gemma-4-e4b",
                "lmstudio_url": "http://localhost:1234/v1",
                "model_routes": {"quick": ["mistralai/mistral-7b-instruct-v0.3"]},
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(result, "fallback ok")
        self.assertEqual(calls[:2], ["google/gemma-4-e4b", "mistralai/mistral-7b-instruct-v0.3"])

    def test_lmstudio_tool_call_sends_schema_and_parses_arguments(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "project_operator",
                                            "arguments": json.dumps(
                                                {"operation": "list", "project_id": ""}
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            )

        result = model_router.call_with_tools(
            "list projects",
            role="planner",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "project_operator",
                        "description": "Project operations",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            config={
                "planner_provider": "lmstudio",
                "planner_model": "qwen/qwen3.5-9b",
                "lmstudio_url": "http://localhost:1234/v1",
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(calls[0][0], "http://localhost:1234/v1/chat/completions")
        self.assertEqual(calls[0][1]["json"]["tool_choice"], "auto")
        self.assertEqual(calls[0][1]["json"]["tools"][0]["function"]["name"], "project_operator")
        self.assertEqual(result.tool_calls[0].name, "project_operator")
        self.assertEqual(result.tool_calls[0].arguments["operation"], "list")

    def test_lmstudio_tool_call_folds_system_prompt_into_user_message(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"])
            return FakeResponse({"choices": [{"message": {"content": "ok", "tool_calls": []}}]})

        result = model_router.call_with_tools(
            "check status",
            role="worker",
            system="Use tools.",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "system_status",
                        "description": "Return system metrics",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            config={
                "worker_provider": "lmstudio",
                "worker_model": "qwen/qwen3-4b-2507",
                "lmstudio_url": "http://localhost:1234/v1",
            },
            environ={},
            post=fake_post,
        )

        self.assertEqual(result.text, "ok")
        self.assertEqual(len(calls[0]["messages"]), 1)
        self.assertIn("Use tools.", calls[0]["messages"][0]["content"])
        self.assertIn("User request:\ncheck status", calls[0]["messages"][0]["content"])

    def test_lmstudio_tool_call_falls_back_to_json_prompt(self):
        from core import model_router

        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"])
            if "tools" in kwargs["json"]:
                return FakeResponse({}, status_code=500, text="Internal Server Error")
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "tool_calls": [
                                            {
                                                "name": "system_status",
                                                "arguments": {},
                                            }
                                        ],
                                        "text": "",
                                    }
                                )
                            }
                        }
                    ]
                }
            )

        result = model_router.call_with_tools(
            "check the system",
            role="worker",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "system_status",
                        "description": "Return system metrics",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            config={
                "worker_provider": "lmstudio",
                "worker_model": "google/gemma-4-e4b",
                "lmstudio_url": "http://localhost:1234/v1",
            },
            environ={},
            post=fake_post,
        )

        self.assertIn("tools", calls[0])
        fallback_call = next(call for call in calls if "tools" not in call)
        self.assertIn("Available tools", fallback_call["messages"][0]["content"])
        self.assertEqual(result.tool_calls[0].name, "system_status")

    def test_model_wrapper_preserves_generate_content_text_shape(self):
        from core import model_router

        def fake_caller(prompt, **kwargs):
            self.assertEqual(prompt, "hello")
            self.assertEqual(kwargs["role"], "worker")
            return "world"

        wrapper = model_router.ModelWrapper(role="worker", caller=fake_caller)
        response = wrapper.generate_content("hello")

        self.assertEqual(response.text, "world")


class ActionRouterWiringTests(unittest.TestCase):
    def test_code_helper_uses_worker_router_wrapper(self):
        import actions.code_helper as code_helper

        with mock.patch("actions.code_helper.get_model_wrapper") as get_wrapper:
            code_helper._get_gemini()

        get_wrapper.assert_called_once_with(role="worker", model=None)

    def test_dev_agent_maps_planner_and_writer_models_to_roles(self):
        import actions.dev_agent as dev_agent

        with mock.patch("actions.dev_agent.get_model_wrapper") as get_wrapper:
            dev_agent._get_model(dev_agent.MODEL_PLANNER, role="planner")
            dev_agent._get_model(dev_agent.MODEL_WRITER, role="worker")

        self.assertEqual(
            get_wrapper.call_args_list,
            [
                mock.call(role="planner", model=None),
                mock.call(role="worker", model=None),
            ],
        )


if __name__ == "__main__":
    unittest.main()
