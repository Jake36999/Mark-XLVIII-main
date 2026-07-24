from __future__ import annotations

import argparse
import time
import uuid
from pathlib import Path
from typing import Protocol

from tasks import DemoTask
from telemetry import Event, JsonlTelemetry, TelemetryAdapter, utc_now


class TaskModule(Protocol):
    task_id: str
    def run(self, attempt: int) -> str: ...


class JobRunner:
    def __init__(self, telemetry: TelemetryAdapter, max_retries: int = 1) -> None:
        self.telemetry = telemetry
        self.max_retries = max(0, max_retries)

    def execute(self, task: TaskModule, run_id: str | None = None) -> str:
        run_id = run_id or uuid.uuid4().hex
        run_started = time.perf_counter()
        self.telemetry.emit(Event(run_id, task.task_id, utc_now(), "run_started"))
        for attempt in range(1, self.max_retries + 2):
            started = time.perf_counter()
            self.telemetry.emit(Event(run_id, task.task_id, utc_now(), "task_started", retry=attempt - 1))
            try:
                result = task.run(attempt)
            except Exception as exc:
                duration = (time.perf_counter() - started) * 1000
                final = attempt > self.max_retries
                self.telemetry.emit(Event(run_id, task.task_id, utc_now(), "task_failed", duration, str(exc), attempt - 1, "degraded"))
                if final:
                    self.telemetry.emit(Event(run_id, task.task_id, utc_now(), "run_failed", (time.perf_counter() - run_started) * 1000, str(exc), attempt - 1, "unhealthy"))
                    raise
                self.telemetry.emit(Event(run_id, task.task_id, utc_now(), "task_retry", duration, str(exc), attempt, "recovering"))
                continue
            duration = (time.perf_counter() - started) * 1000
            self.telemetry.emit(Event(run_id, task.task_id, utc_now(), "task_succeeded", duration, retry=attempt - 1))
            self.telemetry.emit(Event(run_id, task.task_id, utc_now(), "run_completed", (time.perf_counter() - run_started) * 1000))
            return result
        raise RuntimeError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", default="events.jsonl")
    parser.add_argument("--fail-until", type=int, default=0)
    args = parser.parse_args()
    runner = JobRunner(JsonlTelemetry(Path(args.events)), max_retries=1)
    runner.execute(DemoTask(fail_until_attempt=args.fail_until))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
