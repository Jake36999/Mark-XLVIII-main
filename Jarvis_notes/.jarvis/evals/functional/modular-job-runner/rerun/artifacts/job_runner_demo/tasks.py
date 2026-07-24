from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DemoTask:
    task_id: str = "demo-task"
    fail_until_attempt: int = 0

    def run(self, attempt: int) -> str:
        if attempt <= self.fail_until_attempt:
            raise RuntimeError(f"intentional failure on attempt {attempt}")
        return f"completed on attempt {attempt}"
