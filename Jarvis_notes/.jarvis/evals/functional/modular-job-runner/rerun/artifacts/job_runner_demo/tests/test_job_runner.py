from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_runner import JobRunner
from tasks import DemoTask
from telemetry import JsonlTelemetry


def events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_success_telemetry(tmp_path: Path) -> None:
    path = tmp_path / "success.jsonl"
    result = JobRunner(JsonlTelemetry(path)).execute(DemoTask())
    records = events(path)
    assert result == "completed on attempt 1"
    assert records[-1]["status"] == "run_completed"
    assert all({"run_id", "task_id", "timestamp", "status", "duration_ms", "error", "retry", "health"} <= record.keys() for record in records)


def test_retry_and_failure_telemetry(tmp_path: Path) -> None:
    retry_path = tmp_path / "retry.jsonl"
    JobRunner(JsonlTelemetry(retry_path), max_retries=1).execute(DemoTask(fail_until_attempt=1))
    assert {record["status"] for record in events(retry_path)} >= {"task_failed", "task_retry", "run_completed"}

    failure_path = tmp_path / "failure.jsonl"
    with pytest.raises(RuntimeError):
        JobRunner(JsonlTelemetry(failure_path), max_retries=1).execute(DemoTask(fail_until_attempt=2))
    records = events(failure_path)
    assert records[-1]["status"] == "run_failed"
    assert records[-1]["health"] == "unhealthy"
    assert records[-1]["error"]
