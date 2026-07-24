from __future__ import annotations

from clawteam.spawn import subprocess_wrapper


class Result:
    def __init__(self, returncode: int):
        self.returncode = returncode


def test_subprocess_wrapper_runs_command_and_invokes_lifecycle(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, check=False):
        calls.append(command)
        if len(calls) == 1:
            return Result(returncode=7)
        return Result(returncode=0)

    monkeypatch.setenv("CLAWTEAM_BIN", "clawteam")
    monkeypatch.setattr("clawteam.spawn.subprocess_wrapper.subprocess.run", fake_run)

    exit_code = subprocess_wrapper.main(
        ["--team", "demo-team", "--agent", "worker1", "--", "codex", "fix the bug"]
    )

    assert exit_code == 7
    assert calls == [
        ["codex", "fix the bug"],
        ["clawteam", "lifecycle", "on-exit", "--team", "demo-team", "--agent", "worker1"],
    ]


def test_subprocess_wrapper_returns_2_when_command_missing():
    assert subprocess_wrapper.main(["--team", "demo-team", "--agent", "worker1"]) == 2


def test_platform_command_wraps_windows_cmd_shim(monkeypatch):
    monkeypatch.setattr(subprocess_wrapper.os, "name", "nt")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setattr(subprocess_wrapper.shutil, "which", lambda _value: r"F:\npm-global\tool.cmd")

    command = subprocess_wrapper._platform_command(["tool", "agent", "--message", "hello"])

    assert command == [
        r"C:\Windows\System32\cmd.exe",
        "/d",
        "/s",
        "/c",
        r"F:\npm-global\tool.cmd",
        "agent",
        "--message",
        "hello",
    ]


def test_platform_command_bypasses_openclaw_cmd_and_preserves_multiline_prompt(monkeypatch):
    prompt = "first line\nsecond line"

    def fake_which(value):
        if value == "openclaw":
            return r"F:\npm-global\openclaw.cmd"
        if value == "node":
            return r"C:\Program Files\nodejs\node.exe"
        return None

    monkeypatch.setattr(subprocess_wrapper.os, "name", "nt")
    monkeypatch.setattr(subprocess_wrapper.shutil, "which", fake_which)
    monkeypatch.setattr(subprocess_wrapper.os.path, "isfile", lambda _path: True)

    command = subprocess_wrapper._platform_command(
        ["openclaw", "agent", "--message", prompt]
    )

    assert command == [
        r"C:\Program Files\nodejs\node.exe",
        r"F:\npm-global\node_modules\openclaw\openclaw.mjs",
        "agent",
        "--message",
        prompt,
    ]
