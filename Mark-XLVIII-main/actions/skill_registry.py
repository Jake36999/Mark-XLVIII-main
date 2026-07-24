from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:80] or "skill"


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value.replace(b"\r\n", b"\n")).hexdigest()


def _registry_path(cfg: dict[str, Any]) -> Path:
    return Path(cfg["notes_root"]).resolve() / ".jarvis" / "skills" / "registry.json"


def _candidate_root(cfg: dict[str, Any], skill_id: str, version: int) -> Path:
    return Path(cfg["notes_root"]).resolve() / "Skills" / ".packages" / _slug(skill_id) / f"v{version}"


def _installed_root(cfg: dict[str, Any], skill_id: str, version: int) -> Path:
    return Path(cfg["notes_root"]).resolve() / ".jarvis" / "skills" / "enabled" / _slug(skill_id) / f"v{version}"


def _load_registry(cfg: dict[str, Any]) -> dict[str, Any]:
    path = _registry_path(cfg)
    if not path.exists():
        return {"schema_version": "jarvis_skill_registry/v1", "updated_at": _now(), "skills": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    payload.setdefault("schema_version", "jarvis_skill_registry/v1")
    payload.setdefault("skills", {})
    return payload


def _atomic_text(path: Path, text: str) -> None:
    from actions.jarvis_memory import atomic_write

    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    atomic_write(path, normalized)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n")


def validate_playbook(workflow: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    from actions.dual_orchestrator import WorkflowRuntime, compile_workflow, validate_workflow
    from core.tool_dispatcher import get_tool_dispatcher

    validated = validate_workflow(workflow)
    runtime = WorkflowRuntime(Path(cfg["notes_root"]))
    tool_names = {tool["name"] for tool in get_tool_dispatcher().list_tools() if tool.get("available")}
    manifest = compile_workflow(
        validated,
        tool_names=tool_names,
        hook_registry=runtime.hooks,
        command_registry=runtime.commands,
    )
    return {"ok": True, "workflow": validated, "manifest": manifest}


def write_candidate_playbook(
    *,
    skill_id: str,
    title: str,
    workflow: dict[str, Any],
    version: int,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    prepared = dict(workflow or {})
    prepared["schema_version"] = "jarvis_dual_orchestrator/v1"
    prepared["workflow_id"] = _slug(skill_id).replace("-", "_")
    prepared["version"] = str(version)
    prepared.setdefault("name", title)
    prepared.setdefault("description", f"Approved declarative skill: {title}")
    prepared.setdefault("max_steps", min(50, max(1, len(prepared.get("steps") or []))))
    validation = validate_playbook(prepared, cfg)
    text = yaml.safe_dump(validation["workflow"], sort_keys=False, allow_unicode=False)
    path = _candidate_root(cfg, skill_id, version) / "workflow.yaml"
    _atomic_text(path, text)
    return {
        "ok": True,
        "path": str(path),
        "playbook_hash": _hash_bytes(text.encode("utf-8")),
        "workflow_hash": validation["manifest"]["workflow_hash"],
        "manifest_hash": validation["manifest"]["manifest_hash"],
        "step_count": len(validation["manifest"]["items"]),
    }


def install_skill(note_path: str | Path, cfg: dict[str, Any]) -> dict[str, Any]:
    from actions.jarvis_memory import read_note

    note = Path(note_path).resolve()
    vault = Path(cfg["notes_root"]).resolve()
    try:
        note.relative_to(vault)
    except ValueError:
        return {"ok": False, "error": "Skill note must remain inside the canonical vault."}
    metadata, _body, _markdown = read_note(note)
    if str(metadata.get("skill_state") or "") != "user_approved":
        return {"ok": False, "error": "Skill must be user_approved before installation."}
    playbook_path = Path(str(metadata.get("playbook_path") or "")).resolve()
    try:
        playbook_path.relative_to(vault)
    except ValueError:
        return {"ok": False, "error": "Skill playbook must remain inside the canonical vault."}
    if not playbook_path.is_file():
        return {"ok": False, "error": "Skill has no validated declarative playbook."}
    raw = playbook_path.read_bytes()
    playbook_hash = _hash_bytes(raw)
    approved_hash = str(metadata.get("approved_playbook_hash") or "")
    if not approved_hash or playbook_hash != approved_hash:
        return {"ok": False, "error": "Skill playbook changed after user approval."}
    try:
        workflow = yaml.safe_load(raw.decode("utf-8-sig"))
        validation = validate_playbook(workflow, cfg)
    except Exception as exc:
        return {"ok": False, "error": f"Skill playbook validation failed: {exc}"}
    skill_id = str(metadata.get("id") or note.stem)
    version = max(1, int(metadata.get("skill_version") or 1))
    install_root = _installed_root(cfg, skill_id, version)
    installed_playbook = install_root / "workflow.yaml"
    _atomic_text(installed_playbook, raw.decode("utf-8"))
    record = {
        "skill_id": skill_id,
        "title": str(metadata.get("title") or skill_id),
        "version": version,
        "state": "enabled",
        "note_path": str(note),
        "playbook_path": str(installed_playbook),
        "playbook_hash": playbook_hash,
        "workflow_hash": validation["manifest"]["workflow_hash"],
        "manifest_hash": validation["manifest"]["manifest_hash"],
        "enabled_at": _now(),
        "steps": validation["manifest"]["items"],
    }
    registry = _load_registry(cfg)
    registry["skills"][skill_id] = record
    registry["updated_at"] = _now()
    _atomic_json(_registry_path(cfg), registry)
    return {"ok": True, "registry_path": str(_registry_path(cfg)), "installed": record}


def deprecate_skill(skill_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    registry = _load_registry(cfg)
    record = registry.get("skills", {}).get(skill_id)
    if not record:
        return {"ok": True, "removed": False}
    record["state"] = "deprecated"
    record["deprecated_at"] = _now()
    registry["updated_at"] = _now()
    _atomic_json(_registry_path(cfg), registry)
    return {"ok": True, "removed": True, "skill_id": skill_id}


def enabled_skills(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    registry = _load_registry(cfg)
    skills = []
    for record in registry.get("skills", {}).values():
        if record.get("state") != "enabled":
            continue
        path = Path(str(record.get("playbook_path") or ""))
        if not path.is_file() or _hash_bytes(path.read_bytes()) != record.get("playbook_hash"):
            continue
        skills.append(dict(record))
    return sorted(skills, key=lambda item: str(item.get("title") or item.get("skill_id")))


def capability_workflows(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    for skill in enabled_skills(cfg):
        steps = []
        invokes = []
        for item in skill.get("steps") or []:
            target = str(item.get("target") or "")
            if target:
                invokes.append(target)
            steps.append(
                {
                    "id": item.get("id"),
                    "tool": target,
                    "operation": (item.get("inputs") or {}).get("operation") or item.get("step_type"),
                    "requires": sorted((item.get("inputs") or {}).keys()),
                    "produces": list((item.get("outputs") or {}).keys()),
                }
            )
        workflows.append(
            {
                "name": skill["skill_id"],
                "workflow_id": skill["skill_id"],
                "title": skill["title"],
                "summary": f"User-approved declarative skill v{skill['version']}",
                "details": "Hash-verified playbook composed only from registered JARVIS tools, hooks, commands, gates, and model steps.",
                "categories": ["skill", "enabled", "workflow"],
                "steps": steps,
                "invokes": sorted(set(invokes)),
                "artifacts": [skill["note_path"], skill["playbook_path"]],
                "examples": [f"run skill {skill['title']}"],
                "safety": "Execution still requires a hash-bound plan approval.",
                "keywords": [skill["title"], skill["skill_id"], "skill"],
                "triggers": [f"run skill {skill['title']}", f"use {skill['title']}"],
                "risk_level": max((item.get("risk_tier", "T1") for item in skill.get("steps") or []), default="T1"),
                "requires_confirmation": True,
                "success_statuses": ["completed"],
                "block_statuses": ["approval_required", "capability_unavailable", "hash_drift"],
                "progress": ["Preparing approved skill", "Executing playbook", "Reviewing results"],
                "playbook_path": skill["playbook_path"],
                "playbook_hash": skill["playbook_hash"],
                "skill_version": skill["version"],
            }
        )
    return workflows
