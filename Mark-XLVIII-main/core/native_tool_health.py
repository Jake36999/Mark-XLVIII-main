"""Side-effect-free health contracts for JARVIS native integrations."""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable


NATIVE_CONTRACTS: dict[str, dict[str, Any]] = {
    "browser_control": {
        "dependencies": ["playwright"],
        "executables_any": ["chrome", "msedge", "firefox"],
        "risk": "high",
        "read_actions": ["status", "screenshot", "read_page", "list_tabs"],
        "write_actions": ["navigate", "click", "type", "close_tab"],
    },
    "reminder": {
        "dependencies": [],
        "executables_all": ["schtasks"] if os.name == "nt" else [],
        "risk": "medium",
        "read_actions": ["health", "list"],
        "write_actions": ["create", "cancel"],
    },
    "weather_report": {
        "dependencies": ["requests"],
        "risk": "low",
        "read_actions": ["forecast"],
        "write_actions": [],
    },
    "computer_control": {
        "dependencies": ["pyautogui"],
        "risk": "high",
        "read_actions": ["status"],
        "write_actions": ["click", "type", "hotkey", "scroll"],
    },
    "send_message": {
        "dependencies": ["pyautogui", "pyperclip"],
        "risk": "critical",
        "read_actions": ["health"],
        "write_actions": ["send"],
    },
    "file_processor": {
        "dependencies": ["requests"],
        "executables_any": ["ffmpeg", "ffprobe"],
        "risk": "medium",
        "read_actions": ["analyze", "analyze_large", "info", "extract_text"],
        "write_actions": ["convert", "extract", "save"],
    },
    "speech": {
        "dependencies": ["vosk", "sounddevice", "miniaudio"],
        "risk": "medium",
        "read_actions": ["health", "stt_status", "tts_status"],
        "write_actions": ["capture_microphone", "play_audio"],
    },
}


def _default_import(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _which_candidates(name: str) -> list[str]:
    aliases = {
        "chrome": ["chrome", "chrome.exe", str(Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe")],
        "msedge": ["msedge", "msedge.exe", str(Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe")],
        "firefox": ["firefox", "firefox.exe", str(Path(os.environ.get("PROGRAMFILES", "")) / "Mozilla Firefox/firefox.exe")],
    }
    return aliases.get(name, [name])


def _default_which(name: str) -> bool:
    return any(bool(shutil.which(candidate)) or Path(candidate).is_file() for candidate in _which_candidates(name))


def probe_native_tools(
    *,
    import_probe: Callable[[str], bool] | None = None,
    executable_probe: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    import_probe = import_probe or _default_import
    executable_probe = executable_probe or _default_which
    results = {}
    for tool_id, contract in NATIVE_CONTRACTS.items():
        dependencies = {name: bool(import_probe(name)) for name in contract.get("dependencies", [])}
        all_exec = {name: bool(executable_probe(name)) for name in contract.get("executables_all", [])}
        any_exec = {name: bool(executable_probe(name)) for name in contract.get("executables_any", [])}
        hard_ok = all(dependencies.values()) and all(all_exec.values())
        optional_ok = not any_exec or any(any_exec.values())
        available = hard_ok and optional_ok
        results[tool_id] = {
            "tool_id": tool_id,
            "status": "available" if available else ("degraded" if hard_ok else "unavailable"),
            "available": available,
            "dependencies": dependencies,
            "executables_required": all_exec,
            "executables_any": any_exec,
            "risk": contract["risk"],
            "read_actions": list(contract["read_actions"]),
            "write_actions": list(contract["write_actions"]),
            "probe_side_effects": "none",
        }
    return {
        "ok": True,
        "tools": results,
        "available_count": sum(1 for item in results.values() if item["available"]),
        "degraded_count": sum(1 for item in results.values() if item["status"] == "degraded"),
        "unavailable_count": sum(1 for item in results.values() if item["status"] == "unavailable"),
    }


def writable_runtime_probe(root: str | Path | None = None) -> dict[str, Any]:
    """Check runtime write mechanics without touching user documents."""
    target = Path(root) if root else Path(tempfile.gettempdir()) / "jarvis-native-health"
    target.mkdir(parents=True, exist_ok=True)
    probe = target / ".write-probe"
    try:
        probe.write_text("ok", encoding="ascii")
        return {"ok": probe.read_text(encoding="ascii") == "ok", "root": str(target)}
    finally:
        probe.unlink(missing_ok=True)
