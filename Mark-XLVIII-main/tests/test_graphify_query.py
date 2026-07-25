from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from actions.graphify_query import graphify_query


class FakeCompletedProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _enabled_config(**overrides):
    cfg = {"graphify_enabled": True, "graphify_bin": "graphify", "graphify_timeout_seconds": 30}
    cfg.update(overrides)
    return cfg


def test_requires_a_question():
    result = graphify_query({})
    assert "no question" in result.lower()


def test_rejects_unknown_mode():
    result = graphify_query({"question": "x", "mode": "delete"})
    assert "unknown mode" in result.lower()


def test_path_mode_requires_target_b():
    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()):
        result = graphify_query({"question": "NodeA", "mode": "path"})
    assert "target_b" in result


def test_disabled_via_config_short_circuits_without_subprocess():
    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config(graphify_enabled=False)):
        result = graphify_query(
            {"question": "x"},
            run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("subprocess called while disabled")),
        )
    assert "disabled" in result.lower()


def test_missing_graph_returns_guard_message_without_subprocess(tmp_path: Path):
    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()), patch(
        "actions.graphify_query._resolve_project_root", return_value=tmp_path
    ):
        result = graphify_query(
            {"question": "x"},
            run=lambda *a, **k: (_ for _ in ()).throw(AssertionError("subprocess called with no graph")),
        )
    assert "no knowledge graph" in result.lower()
    assert "graph.json" in result


def test_query_mode_builds_expected_command_and_returns_stdout(tmp_path: Path):
    graph = tmp_path / "graphify-out" / "graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}", encoding="utf-8")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeCompletedProcess(stdout="NODE foo [src=bar.py]")

    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()), patch(
        "actions.graphify_query._resolve_project_root", return_value=tmp_path
    ):
        result = graphify_query({"question": "how does X work", "budget": 500}, run=fake_run)

    assert result == "NODE foo [src=bar.py]"
    command = captured["command"]
    assert command[0] == "graphify"
    assert command[1] == "query"
    assert command[2] == "how does X work"
    assert "--graph" in command
    assert str(graph) in command
    assert "--budget" in command and "500" in command


def test_path_mode_includes_target_b(tmp_path: Path):
    graph = tmp_path / "graphify-out" / "graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}", encoding="utf-8")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeCompletedProcess(stdout="path found")

    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()), patch(
        "actions.graphify_query._resolve_project_root", return_value=tmp_path
    ):
        result = graphify_query({"question": "NodeA", "mode": "path", "target_b": "NodeB"}, run=fake_run)

    assert result == "path found"
    assert captured["command"][:4] == ["graphify", "path", "NodeA", "NodeB"]


def test_timeout_is_reported_without_raising(tmp_path: Path):
    graph = tmp_path / "graphify-out" / "graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}", encoding="utf-8")

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout", 30))

    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()), patch(
        "actions.graphify_query._resolve_project_root", return_value=tmp_path
    ):
        result = graphify_query({"question": "x"}, run=fake_run)

    assert "timed out" in result.lower()


def test_missing_binary_is_reported_without_raising(tmp_path: Path):
    graph = tmp_path / "graphify-out" / "graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}", encoding="utf-8")

    def fake_run(command, **kwargs):
        raise FileNotFoundError("graphify not found")

    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()), patch(
        "actions.graphify_query._resolve_project_root", return_value=tmp_path
    ):
        result = graphify_query({"question": "x"}, run=fake_run)

    assert "not installed" in result.lower() or "could not be found" in result.lower()


def test_nonzero_exit_with_stderr_surfaces_error(tmp_path: Path):
    graph = tmp_path / "graphify-out" / "graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}", encoding="utf-8")

    def fake_run(command, **kwargs):
        return FakeCompletedProcess(stdout="", stderr="graph file not found", returncode=1)

    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()), patch(
        "actions.graphify_query._resolve_project_root", return_value=tmp_path
    ):
        result = graphify_query({"question": "x"}, run=fake_run)

    assert "graph file not found" in result


def test_explicit_graph_path_override_takes_precedence(tmp_path: Path):
    real_graph = tmp_path / "elsewhere" / "graph.json"
    real_graph.parent.mkdir(parents=True)
    real_graph.write_text("{}", encoding="utf-8")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeCompletedProcess(stdout="ok")

    with patch("actions.graphify_query.load_runtime_config", return_value=_enabled_config()):
        result = graphify_query({"question": "x", "graph_path": str(real_graph)}, run=fake_run)

    assert result == "ok"
    assert str(real_graph) in captured["command"]


def test_archive_project_id_resolves_via_the_real_registry():
    # Workflow 2: no mocks -- confirms project_registry.json's real "archive"
    # entry (Tier 3, registered so this tool can locate it) resolves to the
    # real Jarvis_notes/Archive path and produces the correct guard message,
    # since no graph has been extracted there yet (it holds one placeholder
    # note as of 2026-07-25, not worth extracting until real content exists).
    result = graphify_query({"question": "anything", "project_id": "archive"})
    assert "no knowledge graph is built yet" in result.lower()
    assert "Jarvis_notes" in result and "Archive" in result


def test_tool_is_declared_and_routed():
    import main
    from core import tool_dispatcher

    names = {t["name"] for t in main.TOOL_DECLARATIONS}
    assert "graphify_query" in names
    assert "graphify_query" in tool_dispatcher.HEADLESS_TOOLS
    assert "graphify_query" in tool_dispatcher.READ_ONLY_TOOLS
    assert tool_dispatcher.classify_effect("graphify_query", {})["requires_approval"] is False
