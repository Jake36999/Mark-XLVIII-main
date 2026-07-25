"""Ad-hoc structural queries against a pre-built graphify knowledge graph.

Wraps the `graphify` CLI (query / explain / path) so a model can ask a
targeted relationship question about a codebase instead of reading or
grepping multiple files. Companion to project_learning.py's deterministic
graphify-informed centrality (_apply_graphify_centrality) -- that boosts
which files repo-learning selects automatically; this is the on-demand path
for a specific question mid-conversation.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any

from core.runtime_config import load_runtime_config


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
DEFAULT_GRAPH_RELATIVE_PATH = Path("graphify-out") / "graph.json"
DEFAULT_PROJECT_ID = "mark_platform"
DEFAULT_TIMEOUT_SECONDS = 30
_MAX_OUTPUT_CHARS = 6000
_MODES = {"query", "explain", "path"}


def _resolve_project_root(project_id: str) -> Path:
    try:
        from actions.project_operator import load_registry

        project = load_registry().get("projects", {}).get(project_id)
        if project and project.get("root"):
            return Path(str(project["root"]))
    except (OSError, ValueError, KeyError):
        pass
    return BASE_DIR.parent


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    cut = len(text) - _MAX_OUTPUT_CHARS
    return text[:_MAX_OUTPUT_CHARS] + f"\n... (truncated, {cut} more characters)"


def _run_graphify(command: list[str], timeout: int, *, run: Any = subprocess.run) -> str:
    try:
        result = run(
            command,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"The knowledge graph query timed out after {timeout}s."
    except FileNotFoundError:
        return "graphify is not installed or could not be found."
    except Exception as e:
        return f"Knowledge graph query failed: {e}"

    output = result.stdout.strip()
    error = result.stderr.strip()
    if result.returncode != 0 and not output:
        return f"Knowledge graph query failed: {error or 'unknown error'}"
    return _truncate(output or error or "No results.")


def graphify_query(parameters: dict, player=None, *, run: Any = subprocess.run) -> str:
    params = parameters or {}
    question = str(params.get("question") or "").strip()
    if not question:
        return "No question provided for the knowledge graph."

    mode = str(params.get("mode") or "query").strip().lower()
    if mode not in _MODES:
        return f"Unknown mode '{mode}'. Use one of: query, explain, path."

    target_b = str(params.get("target_b") or "").strip()
    if mode == "path" and not target_b:
        return "mode='path' needs a 'target_b' parameter -- the second node to find a path to."

    runtime_config = load_runtime_config()
    if runtime_config.get("graphify_enabled") is False:
        return "The codebase knowledge graph tool is disabled in configuration."

    project_id = str(params.get("project_id") or DEFAULT_PROJECT_ID).strip()
    root = _resolve_project_root(project_id)

    graph_override = params.get("graph_path") or runtime_config.get("graphify_graph_path")
    graph_path = Path(str(graph_override)) if graph_override else root / DEFAULT_GRAPH_RELATIVE_PATH
    if not graph_path.is_file():
        return (
            f"No knowledge graph is built yet for project '{project_id}' "
            f"(expected {graph_path}). Run `graphify extract` on that project first."
        )

    graphify_bin = str(runtime_config.get("graphify_bin") or "").strip() or "graphify"

    command = [graphify_bin, mode, question]
    if mode == "path":
        command.append(target_b)
    command += ["--graph", str(graph_path)]
    if mode == "query":
        budget = params.get("budget")
        if budget:
            try:
                command += ["--budget", str(int(budget))]
            except (TypeError, ValueError):
                pass

    timeout = int(runtime_config.get("graphify_timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    return _run_graphify(command, timeout, run=run)
