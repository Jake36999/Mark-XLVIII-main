from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from actions.jarvis_memory import create_note, iter_note_paths, read_note, reindex_local


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    allowed = root.resolve()
    return resolved == allowed or allowed in resolved.parents


def _safe_output_root(value: str, vault_root: Path) -> Path:
    target = Path(str(value or "")).expanduser().resolve()
    if not str(value or "").strip():
        raise ValueError("An approved output_root is required.")
    if not (_within(target, vault_root) or _within(target, WORKSPACE_ROOT)):
        raise ValueError(f"Output root is outside registered workflow roots: {target}")
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"Output root is not empty: {target}")
    return target


def _job_runner_files() -> dict[str, str]:
    return {
        "telemetry.py": '''from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Event:
    run_id: str
    task_id: str
    timestamp: str
    status: str
    duration_ms: float = 0.0
    error: str = ""
    retry: int = 0
    health: str = "healthy"


class TelemetryAdapter(Protocol):
    def emit(self, event: Event) -> None: ...


class JsonlTelemetry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(event), sort_keys=True) + "\\n")
''',
        "tasks.py": '''from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DemoTask:
    task_id: str = "demo-task"
    fail_until_attempt: int = 0

    def run(self, attempt: int) -> str:
        if attempt <= self.fail_until_attempt:
            raise RuntimeError(f"intentional failure on attempt {attempt}")
        return f"completed on attempt {attempt}"
''',
        "job_runner.py": '''from __future__ import annotations

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
''',
        "tests/test_job_runner.py": '''from __future__ import annotations

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
''',
        "README.md": '''# Modular Job Runner Demo

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
''',
        "pyproject.toml": '''[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
''',
    }


def build_python_job_runner(args: dict[str, Any], vault_root: Path) -> dict[str, Any]:
    output_root = _safe_output_root(str(args.get("output_root") or ""), vault_root)
    files = _job_runner_files()
    for relative, content in files.items():
        _atomic_text(output_root / relative, content)
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=output_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    success_events = output_root / "fresh-success.jsonl"
    failure_events = output_root / "fresh-retry.jsonl"
    success = subprocess.run(
        [sys.executable, "job_runner.py", "--events", str(success_events)],
        cwd=output_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    retry = subprocess.run(
        [sys.executable, "job_runner.py", "--events", str(failure_events), "--fail-until", "1"],
        cwd=output_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    ok = tests.returncode == 0 and success.returncode == 0 and retry.returncode == 0
    return {
        "ok": ok,
        "output_root": str(output_root),
        "artifacts": [str(output_root / relative) for relative in sorted(files)],
        "tests": {"returncode": tests.returncode, "stdout": tests.stdout[-4000:], "stderr": tests.stderr[-4000:]},
        "fresh_process": {
            "success_returncode": success.returncode,
            "retry_returncode": retry.returncode,
            "success_events": str(success_events),
            "retry_events": str(failure_events),
        },
        "model_provenance": {"provider": "deterministic", "model": "python_job_runner_template/v1", "role": "artifact_builder"},
        "summary": "Created and verified a replaceable task/telemetry job-runner demo." if ok else "Job-runner validation failed.",
    }


def validate_python_project(args: dict[str, Any], vault_root: Path) -> dict[str, Any]:
    output_root = Path(str(args.get("output_root") or "")).resolve()
    if not (_within(output_root, vault_root) or _within(output_root, WORKSPACE_ROOT)):
        raise ValueError("Project root is outside registered workflow roots.")
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=output_root, capture_output=True, text=True, timeout=120)
    required = ["job_runner.py", "tasks.py", "telemetry.py", "README.md", "tests/test_job_runner.py"]
    missing = [name for name in required if not (output_root / name).exists()]
    return {
        "ok": tests.returncode == 0 and not missing,
        "output_root": str(output_root),
        "missing": missing,
        "returncode": tests.returncode,
        "stdout": tests.stdout[-4000:],
        "stderr": tests.stderr[-4000:],
        "summary": "Fresh validation passed." if tests.returncode == 0 and not missing else "Fresh validation failed.",
    }


def _note_ref(path: Path, vault_root: Path) -> str:
    relative = path.relative_to(vault_root).with_suffix("").as_posix()
    return f"[[{relative}|{path.stem}]]"


def vault_inventory(args: dict[str, Any], vault_root: Path) -> dict[str, Any]:
    cfg = {"jarvis_notes_root": str(vault_root), "notes_root": str(vault_root), "remember_enabled": False}
    notes = []
    for path in iter_note_paths(cfg):
        metadata, body, _ = read_note(path)
        notes.append(
            {
                "id": str(metadata.get("id") or path.stem),
                "title": str(metadata.get("title") or path.stem),
                "type": str(metadata.get("type") or "note"),
                "path": str(path),
                "headings": re.findall(r"(?m)^#{1,6}\s+(.+)$", body),
                "citation": _note_ref(path, vault_root),
            }
        )
    return {"ok": bool(notes), "count": len(notes), "notes": notes, "summary": f"Inspected {len(notes)} vault note(s)."}


def create_vault_documentation_set(args: dict[str, Any], vault_root: Path) -> dict[str, Any]:
    cfg = {
        "jarvis_notes_root": str(vault_root),
        "notes_root": str(vault_root),
        "remember_enabled": False,
        "remember_project_id": "jarvis_notes",
        "remember_project_name": "Jarvis Notes",
    }
    inventory = vault_inventory(args, vault_root)
    source_notes = [note for note in inventory["notes"] if "Reports" not in Path(note["path"]).parts]
    citations = "\n".join(f"- {note['citation']} (`{note['type']}`)" for note in source_notes)
    type_counts: dict[str, int] = {}
    for note in source_notes:
        type_counts[note["type"]] = type_counts.get(note["type"], 0) + 1
    architecture_id = "functional-eval-workflow-architecture"
    gaps_id = "functional-eval-knowledge-gaps"
    moc_id = "functional-eval-moc"
    architecture = create_note(
        note_type="report",
        title="Workflow Architecture Report",
        note_id=architecture_id,
        sections={
            "Summary": (
                "> [!abstract] Inspected architecture\n"
                f"> Reviewed {len(source_notes)} source note(s). The vault presents JARVIS as the assistant, MARK XLVIII as the shell, Obsidian as the canonical record, and local RAG as a derived recall layer."
            ),
            "Findings": (
                "### Observed themes\n\n"
                "- Capability discovery is exposed through tool and workflow manifests.\n"
                "- Plans use Markdown for user intent and YAML/JSON/SQLite for controlled execution state.\n"
                "- Vault notes remain the readable source of truth; local retrieval should store compact pointers.\n\n"
                "### Note inventory\n\n"
                + "\n".join(f"- `{kind}`: {count}" for kind, count in sorted(type_counts.items()))
            ),
            "Actions": "- Keep executable workflow state linked to readable plans.\n- Validate links and typed relationships after generation.",
            "Sources": citations,
        },
        tags=["evaluation", "workflow-architecture"],
        source="dual_orchestrator",
        cfg=cfg,
        metadata_extra={"rag_index": False, "related": [moc_id], "depends_on": [note["id"] for note in source_notes[:12]]},
        sync=False,
        reindex=False,
    )
    architecture_link = _note_ref(Path(architecture["path"]), vault_root)
    gaps = create_note(
        note_type="report",
        title="Knowledge Gaps and Next Actions Report",
        note_id=gaps_id,
        sections={
            "Summary": "> [!warning] Evidence boundary\n> Gaps below are derived from the inspected fixture inventory, not assumed platform defects.",
            "Findings": (
                f"- The inspected set contains {len(source_notes)} source note(s); coverage outside those files is unknown.\n"
                "- Static capability descriptions do not prove live tool health or end-to-end artifact quality.\n"
                "- Versioned examples and repeatable functional evidence should accompany architecture claims."
            ),
            "Actions": (
                "- [ ] Link each claimed capability to a current health check or functional run.\n"
                "- [ ] Add version and review dates to architecture notes.\n"
                "- [ ] Re-run link, YAML, RAG, and workflow telemetry validation after material changes."
            ),
            "Sources": f"- {architecture_link}\n{citations}",
        },
        tags=["evaluation", "knowledge-gaps", "next-actions"],
        source="dual_orchestrator",
        cfg=cfg,
        metadata_extra={"rag_index": False, "depends_on": [architecture_id], "related": [moc_id]},
        sync=False,
        reindex=False,
    )
    gaps_link = _note_ref(Path(gaps["path"]), vault_root)
    moc = create_note(
        note_type="report",
        title="Evaluation MOC",
        note_id=moc_id,
        sections={
            "Summary": "> [!info] Evaluation map\n> Entry point for the inspected workflow architecture and its evidence-backed next actions.",
            "Findings": f"- {architecture_link}\n- {gaps_link}\n\n### Inspected source notes\n\n{citations}",
            "Actions": "- Review the architecture report first.\n- Resolve or schedule the evidence gaps.\n- Keep this map bounded to validated links.",
            "Sources": citations,
        },
        tags=["evaluation", "moc"],
        source="dual_orchestrator",
        cfg=cfg,
        metadata_extra={"rag_index": False, "related": [architecture_id, gaps_id], "depends_on": [note["id"] for note in source_notes[:12]]},
        sync=False,
        reindex=False,
    )
    reindex = reindex_local(cfg)
    artifacts = [moc["path"], architecture["path"], gaps["path"]]
    return {
        "ok": True,
        "artifacts": artifacts,
        "moc_path": moc["path"],
        "architecture_path": architecture["path"],
        "gaps_path": gaps["path"],
        "source_count": len(source_notes),
        "reindex": reindex,
        "summary": "Created a linked evaluation MOC, architecture report, and knowledge-gap report.",
    }


def _resolve_links(vault_root: Path, paths: list[Path]) -> list[dict[str, str]]:
    stems = {path.stem.casefold() for path in iter_note_paths({"notes_root": vault_root})}
    unresolved = []
    for source in paths:
        text = source.read_text(encoding="utf-8", errors="replace")
        for target in re.findall(r"\[\[([^\]|#]+)", text):
            if Path(target.strip()).stem.casefold() not in stems:
                unresolved.append({"source": str(source), "target": target.strip()})
    return unresolved


def validate_vault_artifacts(args: dict[str, Any], vault_root: Path) -> dict[str, Any]:
    paths = [Path(str(value)) for value in args.get("artifacts") or []]
    if not paths:
        paths = [path for path in iter_note_paths({"notes_root": vault_root}) if path.parent.name == "Reports"]
    errors = []
    for path in paths:
        if not path.is_file() or not _within(path, vault_root):
            errors.append(f"missing_or_outside:{path}")
            continue
        metadata, _, _ = read_note(path)
        if not metadata.get("id") or not metadata.get("type"):
            errors.append(f"frontmatter:{path}")
    unresolved = _resolve_links(vault_root, [path for path in paths if path.is_file()])
    return {
        "ok": not errors and not unresolved,
        "artifacts": [str(path) for path in paths],
        "errors": errors,
        "unresolved_links": unresolved,
        "summary": "Vault artifact validation passed." if not errors and not unresolved else "Vault artifact validation failed.",
    }


def productivity_assessment(args: dict[str, Any], vault_root: Path) -> dict[str, Any]:
    source_path = Path(str(args.get("source_path") or "")).resolve()
    if not source_path.is_file() or not _within(source_path, vault_root):
        raise ValueError("Canonical task note must be an existing Markdown file inside the vault.")
    metadata, body, _ = read_note(source_path)
    rows = []
    for line in body.splitlines():
        match = re.match(r"^\s*[-*]\s+\[([ xX])\]\s+(.+?)(?:\s+\^(task-[A-Za-z0-9_-]+))?\s*$", line)
        if not match:
            continue
        text = match.group(2).strip()
        task_id = match.group(3) or f"task-{hashlib.sha256(text.encode()).hexdigest()[:12]}"
        lowered = text.lower()
        if lowered.startswith("user:"):
            owner = "user-owned"
            permission = "advice-only"
        elif lowered.startswith("agent:"):
            owner = "agent-owned"
            permission = "confirmation-required"
        elif lowered.startswith("shared:"):
            owner = "shared"
            permission = "confirmation-required"
        else:
            owner = "advice-only"
            permission = "propose"
        rows.append({"task_id": task_id, "text": text, "owner": owner, "permission": permission, "done": match.group(1).lower() == "x"})
    table = ["| Task ID | Task | Ownership | Permission | Status |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        table.append(f"| `{row['task_id']}` | {row['text']} | {row['owner']} | {row['permission']} | {'done' if row['done'] else 'open'} |")
    cfg = {
        "notes_root": str(vault_root),
        "jarvis_notes_root": str(vault_root),
        "remember_enabled": False,
        "remember_project_id": "jarvis_notes",
        "remember_project_name": "Jarvis Notes",
    }
    note = create_note(
        note_type="report",
        title=f"Task Ownership Assessment - {metadata.get('title') or source_path.stem}",
        sections={
            "Summary": "> [!important] Permission boundary\n> This assessment does not reassign user work and does not authorize execution.",
            "Findings": "\n".join(table),
            "Actions": "- Offer help only for agent-owned or shared work.\n- Require explicit approval before dispatch.\n- Preserve canonical task IDs and completion evidence.",
            "Sources": f"- {_note_ref(source_path, vault_root)}",
        },
        tags=["tasks", "ownership", "assessment"],
        source="dual_orchestrator",
        cfg=cfg,
        metadata_extra={"rag_index": False, "depends_on": [str(metadata.get("id") or source_path.stem)], "agent_permission": "propose"},
        sync=False,
        reindex=False,
    )
    return {"ok": bool(rows), "source_path": str(source_path), "artifact_path": note["path"], "tasks": rows, "summary": f"Classified {len(rows)} task(s) without mutating the canonical note."}
