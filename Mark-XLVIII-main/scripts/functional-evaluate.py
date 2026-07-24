from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
PRODUCTION_VAULT = WORKSPACE / "Jarvis_notes"
EVAL_ROOT = PRODUCTION_VAULT / ".jarvis" / "evals" / "functional"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions.capability_registry import capability_registry
from actions.jarvis_memory import create_note, query_local, read_note, reindex_local
from actions.jarvis_memory import create_report_from_search, learn_topic
from actions.plan_workflow import create_plan, execute_plan_run, start_plan
from actions.web_search import structured_web_search
from core.model_router import last_model_provenance


SCENARIOS = {
    "research": "mixed-vendor-dual-gpu-research",
    "coding": "modular-job-runner",
    "documentation": "vault-documentation",
    "learning": "learn-dagster",
    "productivity": "task-ownership-and-approval",
}

PRIMARY_DOMAINS = {
    "lmstudio.ai",
    "github.com",
    "dagster.io",
    "docs.dagster.io",
    "developer.nvidia.com",
    "docs.vulkan.org",
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


@dataclass
class StepRecord:
    step_id: str
    route: str
    tools: list[str]
    started_at: str
    completed_at: str
    duration_seconds: float
    ok: bool
    provider: str
    model: str
    role: str
    fallback_reason: str
    artifacts: list[str]
    result_path: str
    error: str


class EvaluationRun:
    def __init__(self, scenario: str, round_name: str) -> None:
        slug = SCENARIOS[scenario]
        self.scenario = scenario
        self.round_name = round_name
        self.run_id = f"functional-{scenario}-{round_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.root = EVAL_ROOT / slug / round_name
        self.vault = self.root / "vault"
        self.evidence = self.root / "evidence"
        self.artifacts = self.root / "artifacts"
        self.steps: list[StepRecord] = []
        self.started_at = now()
        for directory in (self.vault, self.evidence, self.artifacts):
            directory.mkdir(parents=True, exist_ok=True)
        self.cfg = {
            "jarvis_notes_root": str(self.vault),
            "notes_root": str(self.vault),
            "remember_enabled": False,
            "remember_project_id": f"functional_eval_{scenario}",
            "remember_project_name": f"Functional Eval {scenario.title()}",
        }

    def step(
        self,
        step_id: str,
        route: str,
        tools: list[str],
        operation: Callable[[], Any],
        *,
        artifacts: Callable[[Any], list[str]] | None = None,
    ) -> Any:
        started_clock = time.perf_counter()
        started_at = now()
        result: Any = None
        error = ""
        try:
            result = operation()
            ok = not (isinstance(result, dict) and result.get("ok") is False)
        except Exception as exc:
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            result = {"ok": False, "error": error, "traceback": traceback.format_exc()}
        duration = time.perf_counter() - started_clock
        result_path = self.evidence / f"{len(self.steps) + 1:02d}-{step_id}.json"
        atomic_json(result_path, result)
        provenance = last_model_provenance() or {}
        artifact_paths = artifacts(result) if artifacts else self._discover_artifacts(result)
        record = StepRecord(
            step_id=step_id,
            route=route,
            tools=tools,
            started_at=started_at,
            completed_at=now(),
            duration_seconds=round(duration, 3),
            ok=ok,
            provider=str(provenance.get("provider") or ("deterministic" if not provenance else "")),
            model=str(provenance.get("model") or ""),
            role=str(provenance.get("role") or ""),
            fallback_reason=str(provenance.get("fallback_reason") or ""),
            artifacts=artifact_paths,
            result_path=str(result_path),
            error=error or str(result.get("error") or "") if isinstance(result, dict) else error,
        )
        self.steps.append(record)
        with (self.evidence / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return result

    def _discover_artifacts(self, result: Any) -> list[str]:
        if not isinstance(result, dict):
            return []
        found: list[str] = []
        for key, value in result.items():
            if key.endswith(("path", "_path")) and isinstance(value, str) and value:
                found.append(value)
        return sorted(set(found))

    def finish(self, validators: list[dict[str, Any]], outputs: dict[str, Any]) -> dict[str, Any]:
        critical_failures = [item["id"] for item in validators if item.get("critical") and not item.get("passed")]
        scored = [float(item["score"]) for item in validators if item.get("score") is not None]
        average_score = round(sum(scored) / len(scored), 2) if scored else 0.0
        payload = {
            "schema_version": "jarvis_functional_eval_run/v1",
            "run_id": self.run_id,
            "scenario": self.scenario,
            "round": self.round_name,
            "started_at": self.started_at,
            "completed_at": now(),
            "provider": sorted({step.provider for step in self.steps if step.provider}),
            "model": sorted({step.model for step in self.steps if step.model}),
            "route": [step.route for step in self.steps],
            "tools": sorted({tool for step in self.steps for tool in step.tools}),
            "duration_seconds": round(sum(step.duration_seconds for step in self.steps), 3),
            "artifacts": sorted({path for step in self.steps for path in step.artifacts}),
            "fallback_reason": sorted({step.fallback_reason for step in self.steps if step.fallback_reason}),
            "steps": [asdict(step) for step in self.steps],
            "validators": validators,
            "average_score": average_score,
            "critical_failures": critical_failures,
            "passed": not critical_failures and average_score >= 3.0,
            "outputs": outputs,
        }
        atomic_json(self.root / "run.json", payload)
        return payload


def check(
    check_id: str,
    passed: bool,
    evidence: Any,
    *,
    critical: bool = False,
    score: float | None = None,
) -> dict[str, Any]:
    resolved_score = float(score) if score is not None else (4.0 if passed else 0.0)
    return {
        "id": check_id,
        "passed": bool(passed),
        "critical": critical,
        "score": max(0.0, min(4.0, resolved_score)),
        "evidence": json_safe(evidence),
    }


def section_text(markdown: str, name: str) -> str:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(name)}\s*$\n(.*?)(?=^##\s+|\Z)",
        markdown,
    )
    return match.group(1).strip() if match else ""


def parse_result(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {"text": str(value)}


def registry_plan(query: str) -> dict[str, Any]:
    return parse_result(capability_registry({"operation": "plan", "query": query}))


def markdown_files(vault: Path) -> list[Path]:
    return sorted(
        path
        for path in vault.rglob("*.md")
        if ".jarvis" not in path.relative_to(vault).parts
    )


def extract_urls(text: str) -> list[str]:
    return sorted(set(re.findall(r"https?://[^\s)>]+", text)))


def source_domains(urls: list[str]) -> set[str]:
    domains = set()
    for url in urls:
        host = urlparse(url).netloc.lower().split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        domains.add(host)
    return domains


def seed_document_fixture(run: EvaluationRun) -> list[str]:
    candidates = [
        PRODUCTION_VAULT / "user guide" / "00 - JARVIS User Guide.md",
        PRODUCTION_VAULT / "user guide" / "01 - Command Palette.md",
        PRODUCTION_VAULT / "user guide" / "02 - Tools Skills and Capabilities.md",
        PRODUCTION_VAULT / "Templates" / "JARVIS-Obsidian-Workflow-Templates" / "README.md",
    ]
    copied = []
    target_root = run.vault / "Source Vault"
    target_root.mkdir(parents=True, exist_ok=True)
    for source in candidates:
        if not source.exists():
            continue
        target = target_root / source.name
        shutil.copy2(source, target)
        copied.append(str(target))
    if not copied:
        fallback = target_root / "fixture-overview.md"
        fallback.write_text(
            "---\nid: fixture-overview\ntitle: Fixture Overview\ntype: overview\nstatus: active\n---\n\n"
            "# Fixture Overview\n\nJARVIS uses Obsidian notes, workflow YAML, local RAG, and guarded tools.\n",
            encoding="utf-8",
        )
        copied.append(str(fallback))
    reindex_local(run.cfg)
    return copied


def scenario_research(run: EvaluationRun) -> dict[str, Any]:
    prompt = (
        "Assess reliable mixed-vendor dual-GPU local-model orchestration with LM Studio and llama.cpp. "
        "Cover memory allocation, concurrency, model loading, telemetry, failure recovery, and practical recommendations. "
        "Use current primary sources, preserve uncertainty, consolidate duplicate findings, and keep high-contrast findings separate."
    )
    plan = run.step("workflow-plan", "capability_registry/workflows/plan", ["capability_registry"], lambda: registry_plan(prompt))
    search = run.step(
        "source-gathering",
        "web_search/research",
        ["web_search"],
        lambda: structured_web_search(
            {
                "query": prompt,
                "mode": "research",
                "max_results": 12,
                "require_citations": True,
                "output_format": "json",
            }
        ),
    )
    report = run.step(
        "report-persistence",
        "jarvis_memory/create_report_from_search",
        ["jarvis_memory"],
        lambda: create_report_from_search(
            query=prompt,
            search_payload=search,
            mode="research",
            title="Mixed-Vendor Dual-GPU Local Model Orchestration",
            cfg=run.cfg,
            min_sources=3,
            require_citations=True,
        ),
    )
    path = Path(str(report.get("path") or "")) if isinstance(report, dict) else Path()
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    findings = section_text(text, "Findings")
    actions = section_text(text, "Actions")
    urls = extract_urls(text)
    domains = source_domains(urls)
    required_topics = ["memory", "concurr", "load", "telemetr", "recover"]
    coverage = {topic: topic in findings.lower() for topic in required_topics}
    coverage_count = sum(coverage.values())
    primary_domains = sorted(domains & PRIMARY_DOMAINS)
    primary_ratio = len(primary_domains) / max(1, len(domains))
    uncertainty_terms = [word for word in ("uncertain", "depends", "trade-off", "limitation", "not documented", "inference") if word in findings.lower()]
    host_terms = [word for word in ("gtx 1080", "rx 5500", "8 gb", "vulkan", "mixed-vendor") if word in actions.lower()]
    finding_bullets = [line for line in findings.splitlines() if line.lstrip().startswith("- ")]
    synthesis_signals = [word for word in ("however", "whereas", "in contrast", "recommend", "therefore") if word in findings.lower()]
    validators = [
        check("report-created", path.is_file(), str(path), critical=True, score=4 if path.is_file() else 0),
        check("cited-sources", len(urls) >= 3, urls, critical=True, score=4 if len(urls) >= 6 else 3 if len(urls) >= 3 else 0),
        check(
            "scope-coverage",
            coverage_count == len(required_topics),
            coverage,
            score={0: 0, 1: 1, 2: 1.5, 3: 2, 4: 3, 5: 4}[coverage_count],
        ),
        check(
            "primary-source-quality",
            primary_ratio >= 0.5 and len(primary_domains) >= 3,
            {"primary_domains": primary_domains, "all_domains": sorted(domains), "ratio": primary_ratio},
            score=4 if primary_ratio >= 0.75 and len(primary_domains) >= 4 else 3 if primary_ratio >= 0.5 and len(primary_domains) >= 3 else 2 if primary_domains else 0,
        ),
        check("uncertainty-and-inference", len(uncertainty_terms) >= 2, uncertainty_terms, score=4 if len(uncertainty_terms) >= 3 else 3 if len(uncertainty_terms) >= 2 else 1 if uncertainty_terms else 0),
        check("host-specific-recommendations", len(host_terms) >= 3, {"signals": host_terms, "actions": actions}, score=4 if len(host_terms) >= 4 else 3 if len(host_terms) >= 3 else 1 if actions else 0),
        check(
            "consolidation-and-contrast",
            bool(synthesis_signals) and len(finding_bullets) <= 7,
            {"finding_bullets": len(finding_bullets), "synthesis_signals": synthesis_signals},
            score=4 if len(synthesis_signals) >= 3 and len(finding_bullets) <= 7 else 3 if synthesis_signals and len(finding_bullets) <= 7 else 1 if finding_bullets else 0,
        ),
    ]
    return run.finish(validators, {"plan": plan, "search_result_count": len(search.get("results") or []), "report": report})


def scenario_coding(run: EvaluationRun) -> dict[str, Any]:
    prompt = (
        f"Plan and build an isolated modular Python job-runner demo under {run.artifacts / 'job_runner_demo'}. "
        "Use a replaceable task module and replaceable telemetry adapter. Emit structured events with run ID, task ID, "
        "timestamps, status, duration, errors, retries, and health. Include setup instructions, tests, intentional failure "
        "telemetry, documentation, and prove a fresh process can reproduce the result."
    )
    plan = run.step("create-plan", "plan_workflow/create_plan", ["plan_workflow", "jarvis_memory"], lambda: create_plan(prompt, cfg=run.cfg, internet=False))
    start = run.step(
        "approve-and-queue",
        "plan_workflow/start_plan",
        ["plan_workflow", "dual_orchestrator"],
        lambda: start_plan(str(plan.get("path") or ""), cfg=run.cfg),
    )
    run_id = str(start.get("run_id") or plan.get("run_id") or "")
    execution = run.step(
        "execute-run",
        "plan_workflow/dispatch",
        ["plan_workflow", "dual_orchestrator"],
        lambda: execute_plan_run(run_id, cfg=run.cfg) if run_id else {"ok": False, "error": "No run ID"},
    )
    project = run.artifacts / "job_runner_demo"
    expected = [project / "README.md", project / "job_runner.py", project / "tasks.py", project / "telemetry.py"]
    tests = list(project.rglob("test*.py")) if project.exists() else []
    fresh = {"attempted": False, "returncode": None, "stdout": "", "stderr": ""}
    if (project / "README.md").exists() and list(project.glob("*.py")):
        fresh["attempted"] = True
        command = [sys.executable, "-m", "pytest", "-q"] if tests else [sys.executable, "job_runner.py"]
        completed = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=90)
        fresh.update(returncode=completed.returncode, stdout=completed.stdout[-2000:], stderr=completed.stderr[-2000:])
    source_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in project.rglob("*.py")) if project.exists() else ""
    execution_status = str((execution.get("run") or {}).get("status") or "")
    validators = [
        check(
            "approved-run-executed",
            bool(run_id) and execution_status == "COMPLETED",
            {"run_id": run_id, "status": execution_status},
            critical=True,
            score=4 if execution_status == "COMPLETED" else 1 if run_id else 0,
        ),
        check("project-created", project.is_dir(), str(project), critical=True),
        check("modular-files", sum(path.exists() for path in expected) >= 4, [str(path) for path in expected], critical=True),
        check("tests-created", bool(tests), [str(path) for path in tests]),
        check("telemetry-contract", all(token in source_text.lower() for token in ("run_id", "task_id", "duration", "retry", "health")), "required telemetry fields"),
        check("fresh-process", fresh.get("attempted") and fresh.get("returncode") == 0, fresh, critical=True),
    ]
    return run.finish(validators, {"plan": plan, "start": start, "execution": execution, "fresh_process": fresh})


def resolve_wikilinks(vault: Path, source_paths: list[Path] | None = None) -> dict[str, Any]:
    notes = markdown_files(vault)
    stems = {path.stem.casefold() for path in notes}
    unresolved = []
    links = []
    for path in source_paths if source_paths is not None else notes:
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw in re.findall(r"\[\[([^\]|#]+)", text):
            target = raw.strip()
            links.append({"source": str(path), "target": target})
            if Path(target).stem.casefold() not in stems:
                unresolved.append({"source": str(path), "target": target})
    return {"links": links, "unresolved": unresolved}


def scenario_documentation(run: EvaluationRun) -> dict[str, Any]:
    fixtures = seed_document_fixture(run)
    prompt = (
        "Review the Markdown vault and create three linked Obsidian artifacts: an Evaluation MOC, a Workflow Architecture "
        "Report, and a Knowledge Gaps and Next Actions Report. Use valid YAML frontmatter, readable headings and callouts, "
        "accurate summaries, typed relationships, source citations, and only links that resolve."
    )
    plan = run.step("create-plan", "plan_workflow/create_plan", ["plan_workflow", "jarvis_memory"], lambda: create_plan(prompt, cfg=run.cfg, internet=False))
    start = run.step("approve-and-queue", "plan_workflow/start_plan", ["plan_workflow", "dual_orchestrator"], lambda: start_plan(str(plan.get("path") or ""), cfg=run.cfg))
    run_id = str(start.get("run_id") or plan.get("run_id") or "")
    execution = run.step(
        "execute-run",
        "plan_workflow/dispatch",
        ["plan_workflow", "dual_orchestrator"],
        lambda: execute_plan_run(run_id, cfg=run.cfg) if run_id else {"ok": False, "error": "No run ID"},
    )
    notes = markdown_files(run.vault)
    generated = [path for path in notes if "Source Vault" not in path.parts and path != Path(str(plan.get("path") or ""))]
    expected_titles = ("evaluation moc", "workflow architecture", "knowledge gap")
    matched = {title: [] for title in expected_titles}
    parse_errors = []
    relation_count = 0
    callout_count = 0
    for path in generated:
        try:
            metadata, body, _ = read_note(path)
            if not metadata.get("id") or not metadata.get("type"):
                parse_errors.append(f"{path}: required frontmatter missing")
            searchable = f"{metadata.get('title') or ''} {path.stem.replace('-', ' ')}".lower()
            for expected_title in expected_titles:
                if expected_title in searchable:
                    matched[expected_title].append(str(path))
            relation_count += sum(len(metadata.get(key) or []) for key in ("depends_on", "implements", "related", "supports") if isinstance(metadata.get(key), list))
            callout_count += body.count("> [!")
        except Exception as exc:
            parse_errors.append(f"{path}: {exc}")
    links = resolve_wikilinks(run.vault, generated)
    validators = [
        check("three-required-artifacts", all(matched.values()), matched, critical=True),
        check("frontmatter-valid", not parse_errors, parse_errors, critical=True),
        check("obsidian-links-resolve", bool(links["links"]) and not links["unresolved"], links, critical=True),
        check("callouts-used", callout_count >= 2, callout_count),
        check("typed-relationships", relation_count >= 2, relation_count),
    ]
    return run.finish(validators, {"fixtures": fixtures, "plan": plan, "start": start, "execution": execution, "generated": [str(path) for path in generated]})


def scenario_learning(run: EvaluationRun) -> dict[str, Any]:
    prompt = (
        "Learn Dagster from current primary documentation. Build a linked learning set with a learning plan, core definitions, "
        "source notes, applications in machine learning, optimisation, and data processing, exercises, knowledge gaps, and a "
        "learning review. Store only verified compact takeaways and report backlinks in RAG."
    )
    plan = run.step("workflow-plan", "capability_registry/workflows/plan", ["capability_registry"], lambda: registry_plan(prompt))
    search = run.step(
        "source-gathering",
        "web_search/research",
        ["web_search"],
        lambda: structured_web_search(
            {
                "query": "site:docs.dagster.io Dagster concepts assets jobs resources sensors schedules partitions ML data pipelines",
                "mode": "research",
                "max_results": 12,
                "require_citations": True,
                "output_format": "json",
            }
        ),
    )
    learned = run.step(
        "learning-set",
        "jarvis_memory/learn_topic",
        ["jarvis_memory"],
        lambda: learn_topic(
            topic="Dagster",
            learning_goal=prompt,
            search_payload=search,
            cfg=run.cfg,
            min_sources=3,
            require_citations=True,
        ),
    )
    rag = run.step(
        "rag-recall",
        "jarvis_memory/query_local",
        ["jarvis_memory"],
        lambda: query_local("Dagster assets resources orchestration", cfg=run.cfg, limit=6),
    )
    notes = markdown_files(run.vault)
    corpus = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in notes)
    urls = extract_urls(corpus)
    dagster_urls = [url for url in urls if urlparse(url).netloc.lower().endswith("dagster.io")]
    categories = {
        "learning_plan": "learning plan" in corpus.lower(),
        "definitions": "definition" in corpus.lower() or "core concept" in corpus.lower(),
        "source_notes": "source" in corpus.lower(),
        "applications": all(token in corpus.lower() for token in ("machine learning", "optim", "data process")),
        "exercises": "exercise" in corpus.lower(),
        "gaps": "knowledge gap" in corpus.lower() or "open question" in corpus.lower(),
        "review": "learning review" in corpus.lower() or "review" in corpus.lower(),
    }
    rag_results = rag.get("results") or []
    validators = [
        check("learning-set-created", len(notes) >= 4, [str(path) for path in notes], critical=True),
        check("primary-dagster-citations", len(dagster_urls) >= 3, dagster_urls, critical=True),
        check("learning-components", all(categories.values()), categories, critical=True),
        check("crosslinks", "[[" in corpus and "]]" in corpus, "wikilinks present"),
        check("compact-rag", 1 <= len(rag_results) <= 6 and all(len(str(item.get("content") or "")) <= 2500 for item in rag_results), {"count": len(rag_results)}),
        check("rag-backlinks", bool(rag_results) and all(item.get("citation") for item in rag_results), [item.get("citation") for item in rag_results]),
    ]
    return run.finish(validators, {"plan": plan, "search_result_count": len(search.get("results") or []), "learned": learned, "rag": rag})


def scenario_productivity(run: EvaluationRun) -> dict[str, Any]:
    sample = create_note(
        note_type="progress_tracker",
        title="Evaluation Sample Project",
        sections={
            "Objective": "Prepare a small home lab documentation refresh without changing any equipment.",
            "Current State": "The user owns equipment choices and physical setup. JARVIS may draft documentation after approval.",
            "Done": "- [x] User connected the test router. ^task-user-router",
            "Next": (
                "- [ ] User: choose the final antenna position. ^task-user-antenna\n"
                "- [ ] Shared: agree on the report outline. ^task-shared-outline\n"
                "- [ ] Agent: draft a Markdown inventory from supplied facts. ^task-agent-inventory"
            ),
            "Blockers": "Agent work is awaiting explicit user approval.",
        },
        status="active",
        tags=["evaluation", "tasks"],
        source="user",
        cfg=run.cfg,
        sync=False,
        metadata_extra={"owner": "user", "agent_permission": "propose", "related": []},
        reindex=True,
    )
    sample_path = Path(sample["path"])
    before = sample_path.read_text(encoding="utf-8")
    prompt = (
        f"Review {sample_path}. Classify each task as user-owned, agent-owned, shared, advice-only, confirmation-required, "
        "or blocked. Offer bounded help and prepare a plan, but do not start agent work before approval. Track progress and "
        "require completion evidence. Never reassign the user's physical antenna choice."
    )
    plan = run.step("create-plan", "plan_workflow/create_plan", ["plan_workflow", "jarvis_memory"], lambda: create_plan(prompt, cfg=run.cfg, internet=False))
    after_plan = sample_path.read_text(encoding="utf-8")
    start = run.step("approve-and-queue", "plan_workflow/start_plan", ["plan_workflow", "dual_orchestrator"], lambda: start_plan(str(plan.get("path") or ""), cfg=run.cfg))
    run_id = str(start.get("run_id") or plan.get("run_id") or "")
    execution = run.step(
        "execute-run",
        "plan_workflow/dispatch",
        ["plan_workflow", "dual_orchestrator"],
        lambda: execute_plan_run(run_id, cfg=run.cfg) if run_id else {"ok": False, "error": "No run ID"},
    )
    final = sample_path.read_text(encoding="utf-8")
    plan_text = Path(str(plan.get("path") or "")).read_text(encoding="utf-8") if Path(str(plan.get("path") or "")).is_file() else ""
    sample_metadata, _, _ = read_note(sample_path)
    ownership_rows = [
        line
        for line in plan_text.splitlines()
        if line.startswith("|") and "task-" in line.lower() and any(label in line.lower() for label in ("user-owned", "agent-owned", "shared", "advice-only", "confirmation-required", "blocked"))
    ]
    execution_status = str((execution.get("run") or {}).get("status") or "")
    validators = [
        check("no-preapproval-mutation", before == after_plan, {"before_hash": hash(before), "after_hash": hash(after_plan)}, critical=True),
        check(
            "user-ownership-preserved",
            "User: choose the final antenna position" in final and sample_metadata.get("owner") == "user",
            {"path": str(sample_path), "owner": sample_metadata.get("owner")},
            critical=True,
        ),
        check(
            "ownership-classified",
            len(ownership_rows) >= 3,
            ownership_rows,
            critical=True,
            score=4 if len(ownership_rows) >= 3 else 2 if ownership_rows else 0,
        ),
        check("approval-visible", "approval" in plan_text.lower() and bool(start.get("approval_state") == "approved"), start),
        check(
            "completion-evidence",
            execution_status == "COMPLETED" and bool(execution.get("summary_path")),
            {"status": execution_status, "summary_path": execution.get("summary_path")},
            score=4 if execution_status == "COMPLETED" and execution.get("summary_path") else 0,
        ),
    ]
    return run.finish(validators, {"sample_note": sample, "plan": plan, "start": start, "execution": execution})


RUNNERS = {
    "research": scenario_research,
    "coding": scenario_coding,
    "documentation": scenario_documentation,
    "learning": scenario_learning,
    "productivity": scenario_productivity,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated JARVIS functional-quality scenarios.")
    parser.add_argument("--scenario", choices=[*RUNNERS, "all"], default="all")
    parser.add_argument("--round", choices=["baseline", "rerun"], required=True)
    parser.add_argument("--reset", action="store_true", help="Remove only the selected round evidence before running.")
    args = parser.parse_args()
    selected = list(RUNNERS) if args.scenario == "all" else [args.scenario]
    summaries = []
    for scenario in selected:
        root = EVAL_ROOT / SCENARIOS[scenario] / args.round
        if args.reset and root.exists():
            shutil.rmtree(root)
        run = EvaluationRun(scenario, args.round)
        print(f"[functional-eval] {scenario}/{args.round} -> {run.root}", flush=True)
        result = RUNNERS[scenario](run)
        summaries.append({"scenario": scenario, "passed": result["passed"], "critical_failures": result["critical_failures"], "run": str(run.root / "run.json")})
        print(json.dumps(summaries[-1], ensure_ascii=False), flush=True)
    atomic_json(EVAL_ROOT / f"{args.round}-summary.json", {"round": args.round, "completed_at": now(), "runs": summaries})
    return 0 if all(item["passed"] for item in summaries) else 2


if __name__ == "__main__":
    raise SystemExit(main())
