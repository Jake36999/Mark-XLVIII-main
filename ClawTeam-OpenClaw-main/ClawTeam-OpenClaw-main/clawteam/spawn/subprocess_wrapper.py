"""Small wrapper that runs an agent command and reports its exit."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from clawteam.spawn.cli_env import resolve_clawteam_executable


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a spawned agent command and report its exit.")
    parser.add_argument("--team", required=True, help="Team name")
    parser.add_argument("--agent", required=True, help="Agent name")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    return parser.parse_args(argv)


def _platform_command(command: list[str]) -> list[str]:
    """Resolve Windows command shims without enabling a general shell."""
    if os.name != "nt" or not command:
        return list(command)
    resolved = shutil.which(command[0])
    if not resolved:
        return list(command)
    suffix = os.path.splitext(resolved)[1].lower()
    if suffix not in {".cmd", ".bat"}:
        return list(command)
    if os.path.splitext(os.path.basename(resolved))[0].lower() == "openclaw":
        entrypoint = os.path.join(
            os.path.dirname(resolved),
            "node_modules",
            "openclaw",
            "openclaw.mjs",
        )
        if os.path.isfile(entrypoint):
            node = shutil.which("node") or "node"
            return [node, entrypoint, *command[1:]]
    comspec = os.environ.get("COMSPEC") or os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"
    )
    return [comspec, "/d", "/s", "/c", resolved, *command[1:]]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        return 2

    returncode = 1
    try:
        completed = subprocess.run(_platform_command(command), check=False)
        returncode = completed.returncode
    finally:
        clawteam_bin = os.environ.get("CLAWTEAM_BIN") or resolve_clawteam_executable()
        lifecycle_cmd = [
            clawteam_bin,
            "lifecycle",
            "on-exit",
            "--team",
            args.team,
            "--agent",
            args.agent,
        ]
        try:
            subprocess.run(lifecycle_cmd, check=False)
        except FileNotFoundError:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "clawteam",
                    "lifecycle",
                    "on-exit",
                    "--team",
                    args.team,
                    "--agent",
                    args.agent,
                ],
                check=False,
            )

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
