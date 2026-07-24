from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from actions.jarvis_memory import create_note, resolve_config


PATTERNS = {
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "google_key": re.compile(r"\bAIza[A-Za-z0-9_-]{25,}\b"),
    "bearer_token": re.compile(r"(?i)authorization\s*[:=]\s*['\"]?bearer\s+([A-Za-z0-9._-]{20,})"),
    "configured_secret": re.compile(r"(?i)['\"]?(openai_api_key|gemini_api_key|api_key|access_token)['\"]?\s*[:=]\s*['\"]([^'\"\s]{12,})"),
}
TEXT_SUFFIXES = {
    ".py", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".env", ".txt", ".md", ".log",
    ".ps1", ".bat", ".cmd", ".js", ".ts", ".tsx", ".html", ".css", ".xml", ".csv",
}
IGNORED_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _matches(text: str, *, location: str, source: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pattern_id, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            value = match.group(match.lastindex or 0)
            if pattern_id == "configured_secret" and match.lastindex and match.lastindex >= 2:
                value = match.group(2)
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                {
                    "pattern": pattern_id,
                    "location": location,
                    "line": line,
                    "source": source,
                    "fingerprint": _fingerprint(value),
                }
            )
    return findings


def scan_paths(roots: Iterable[Path], *, max_file_bytes: int = 5_000_000) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            findings.extend(_matches(text, location=str(path), source="worktree"))
    return findings


def scan_git_history(repo_root: Path, *, max_commits: int = 500) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        commits = subprocess.run(
            ["git", "rev-list", "--all", f"--max-count={max_commits}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        ).stdout.splitlines()
    except Exception:
        return findings
    combined_pattern = "sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{25,}|(openai_api_key|gemini_api_key|api_key).{0,8}[:=].{0,4}[^[:space:]]{12,}"
    for commit in commits:
        try:
            completed = subprocess.run(
                ["git", "grep", "-I", "-n", "-E", combined_pattern, commit, "--"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=15,
                shell=False,
            )
        except Exception:
            continue
        for line in completed.stdout.splitlines():
            match = re.match(r"^[^:]+:([^:]+):(\d+):(.*)$", line)
            if not match:
                continue
            path, line_number, content = match.groups()
            for finding in _matches(content, location=f"{commit[:12]}:{path}", source="git_history"):
                finding["line"] = int(line_number)
                findings.append(finding)
    return findings


def run_security_audit(
    *,
    repo_root: Path | None = None,
    cfg: dict[str, Any] | None = None,
    include_git_history: bool = True,
    write_note: bool = True,
) -> dict[str, Any]:
    repo = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    cfg = resolve_config(cfg)
    roots = [
        repo,
        repo / "Mark-XLVIII-main" / "runtime_logs",
        Path.home() / "AppData" / "Local" / "Temp",
    ]
    findings = scan_paths(roots)
    if include_git_history:
        findings.extend(scan_git_history(repo))
    unique: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    for finding in findings:
        key = (finding["source"], finding["location"], int(finding["line"]), finding["fingerprint"])
        unique[key] = finding
    findings = sorted(unique.values(), key=lambda item: (item["source"], item["location"], item["line"]))
    result: dict[str, Any] = {
        "ok": True,
        "audited_at": _now(),
        "repo_root": str(repo),
        "finding_count": len(findings),
        "findings": findings,
        "requires_revocation_review": bool(findings),
        "revocation_acknowledged": False,
    }
    if write_note:
        rows = [
            "| Source | Location | Line | Pattern | Fingerprint |",
            "| --- | --- | ---: | --- | --- |",
        ]
        for item in findings:
            escaped_location = item["location"].replace("|", "\\|")
            rows.append(
                f"| {item['source']} | `{escaped_location}` | {item['line']} | {item['pattern']} | `{item['fingerprint']}` |"
            )
        if not findings:
            rows.append("| - | No credential-shaped values found | - | - | - |")
        sections = {
            "Context": f"> [!{'danger' if findings else 'success'}]\n> Found {len(findings)} credential-shaped occurrence(s). Values are intentionally omitted.",
            "Events": "\n".join(rows),
            "Outcome": (
                "- [ ] Revoke any previously exposed OpenAI or Google keys.\n"
                "- [ ] Review provider usage and billing history.\n"
                "- [ ] Confirm revocation before marking this audit resolved."
            ),
            "Next Steps": "- Current worktree scanned\n- Runtime logs and local crash/temp text scanned\n- Git history scanned (bounded to 500 commits)\n- Keep this note excluded from RAG.",
        }
        note = create_note(
            note_type="log",
            title=f"Credential Exposure Audit - {_now()[:10]}",
            sections=sections,
            tags=["security", "credential-audit", "private"],
            status="action_required" if findings else "reviewed",
            source="security_audit",
            cfg=cfg,
            sync=False,
            metadata_extra={
                "sensitivity": "private",
                "rag_index": False,
                "index_state": "excluded_local",
                "finding_count": len(findings),
                "revocation_acknowledged": False,
            },
            reindex=False,
        )
        result["note_path"] = note.get("path", "")
    return result


def security_audit(parameters: dict[str, Any] | None = None, response=None, player=None, session_memory=None, speak=None) -> str:
    params = dict(parameters or {})
    try:
        result = run_security_audit(
            cfg=params.get("_config"),
            include_git_history=bool(params.get("include_git_history", True)),
            write_note=bool(params.get("write_note", True)),
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    return json.dumps(result, ensure_ascii=True, indent=2)
