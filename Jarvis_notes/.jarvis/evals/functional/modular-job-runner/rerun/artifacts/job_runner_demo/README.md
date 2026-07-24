# Modular Job Runner Demo

This isolated Python demo separates the task module (`tasks.py`) from the telemetry adapter (`telemetry.py`). `JobRunner` depends only on their protocols, so either implementation can be replaced.

## Run

```powershell
python job_runner.py --events success.jsonl
python job_runner.py --events retry.jsonl --fail-until 1
```

## Test

```powershell
python -m pytest -q
```

Events include run/task IDs, UTC timestamps, status, duration, error, retry count, and health. The tests cover success, retry recovery, and terminal failure telemetry.
