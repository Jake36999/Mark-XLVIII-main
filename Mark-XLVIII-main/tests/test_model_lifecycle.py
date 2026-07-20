import json
import unittest


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


def lifecycle_config():
    from actions import model_lifecycle

    return model_lifecycle.resolve_config(
        {
            "lmstudio_native_url": "http://localhost:1234/api/v1",
            "baseline_models": ["qwen/qwen3-4b-2507", "orpeus_text_to_speech"],
            "task_model_ttl_seconds": 300,
            "idle_cleanup_seconds": 300,
            "max_task_models_loaded": 1,
        }
    )


def models_payload():
    return {
        "models": [
            {
                "type": "llm",
                "key": "qwen/qwen3-4b-2507",
                "display_name": "Qwen3 4B",
                "loaded_instances": [
                    {
                        "id": "qwen/qwen3-4b-2507",
                        "config": {"parallel": 4, "context_length": 4096},
                    }
                ],
            },
            {
                "type": "llm",
                "key": "deepseek-r1-0528-qwen3-8b",
                "display_name": "DeepSeek R1 Qwen 8B",
                "loaded_instances": [
                    {
                        "id": "deepseek-r1-0528-qwen3-8b:0",
                        "config": {"parallel": 2, "context_length": 8192},
                    }
                ],
            },
        ]
    }


class ModelLifecycleTests(unittest.TestCase):
    def test_list_models_treats_parallel_as_instance_config(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()

        def fake_get(url, **kwargs):
            self.assertEqual(url, "http://localhost:1234/api/v1/models")
            return FakeResponse(models_payload())

        listed = model_lifecycle.list_models(cfg, get=fake_get)

        self.assertEqual(listed["loaded_count"], 2)
        self.assertEqual(listed["task_loaded_count"], 1)
        baseline = listed["loaded"][0]
        self.assertTrue(baseline["baseline"])
        self.assertEqual(baseline["parallel"], 4)

    def test_prepare_payload_adds_ttl_only_for_non_baseline_models(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()

        baseline_payload = model_lifecycle.prepare_lmstudio_payload(
            {"model": "qwen/qwen3-4b-2507"},
            model="qwen/qwen3-4b-2507",
            route="quick",
            config=cfg,
        )
        task_payload = model_lifecycle.prepare_lmstudio_payload(
            {"model": "deepseek-r1-0528-qwen3-8b"},
            model="deepseek-r1-0528-qwen3-8b",
            route="code",
            config=cfg,
        )

        self.assertNotIn("ttl", baseline_payload)
        self.assertEqual(task_payload["ttl"], 300)

    def test_unload_non_baseline_keeps_baseline_models(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()
        posts = []

        def fake_get(url, **kwargs):
            return FakeResponse(models_payload())

        def fake_post(url, **kwargs):
            posts.append((url, kwargs["json"]))
            return FakeResponse({"instance_id": kwargs["json"]["instance_id"]})

        result = model_lifecycle.unload_non_baseline(cfg, get=fake_get, post=fake_post)

        self.assertTrue(result["ok"])
        self.assertEqual(posts, [("http://localhost:1234/api/v1/models/unload", {"instance_id": "deepseek-r1-0528-qwen3-8b:0"})])
        self.assertEqual(len(result["kept"]), 1)
        self.assertEqual(result["kept"][0]["model_key"], "qwen/qwen3-4b-2507")

    def test_cleanup_idle_skips_while_requests_are_active(self):
        from actions import model_lifecycle

        cfg = lifecycle_config()
        token = model_lifecycle.mark_request_start("deepseek-r1-0528-qwen3-8b", kind="code")
        try:
            def fake_get(url, **kwargs):
                raise AssertionError("cleanup should not query LM Studio while active")

            result = model_lifecycle.cleanup_idle(cfg, get=fake_get)
        finally:
            model_lifecycle.mark_request_done(token)

        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "active_requests")

    def test_tool_baseline_operation_returns_json(self):
        from actions import model_lifecycle

        result = json.loads(
            model_lifecycle.model_lifecycle(
                {"operation": "baseline", "_config": {"baseline_models": ["qwen/qwen3-4b-2507"]}}
            )
        )

        self.assertTrue(result["ok"])
        self.assertIn("qwen/qwen3-4b-2507", result["baseline_models"])


if __name__ == "__main__":
    unittest.main()
