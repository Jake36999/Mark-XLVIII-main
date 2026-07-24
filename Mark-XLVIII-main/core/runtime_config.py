from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping


SECRET_FIELD_TOKENS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
RUNTIME_CONFIG_PATH = CONFIG_DIR / "runtime.json"
LEGACY_CONFIG_PATH = CONFIG_DIR / "api_keys.json"


def is_secret_field(name: str) -> bool:
    normalized = str(name or "").strip().lower().replace("-", "_")
    return any(token in normalized for token in SECRET_FIELD_TOKENS)


def sanitize_config(value: Mapping[str, Any] | None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, item in dict(value or {}).items():
        if is_secret_field(str(key)):
            continue
        if isinstance(item, Mapping):
            data[str(key)] = sanitize_config(item)
        elif isinstance(item, list):
            data[str(key)] = [sanitize_config(v) if isinstance(v, Mapping) else v for v in item]
        else:
            data[str(key)] = item
    return data


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), ensure_ascii=True, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def load_runtime_config(
    path: Path | str | None = None,
    *,
    include_legacy_non_secrets: bool = False,
) -> dict[str, Any]:
    target = Path(path) if path is not None else RUNTIME_CONFIG_PATH
    data: dict[str, Any] = {}
    if include_legacy_non_secrets and target == RUNTIME_CONFIG_PATH:
        data.update(sanitize_config(_read_json(LEGACY_CONFIG_PATH)))
    data.update(sanitize_config(_read_json(target)))
    return data


def save_runtime_config(payload: Mapping[str, Any], path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else RUNTIME_CONFIG_PATH
    sanitized = sanitize_config(payload)
    atomic_write_json(target, sanitized)
    return sanitized


def migrate_legacy_config() -> dict[str, Any]:
    legacy = _read_json(LEGACY_CONFIG_PATH)
    legacy_secret_fields = sorted(key for key in legacy if is_secret_field(key) and legacy.get(key))
    merged = sanitize_config(legacy)
    merged.update(load_runtime_config(include_legacy_non_secrets=False))
    if merged or not RUNTIME_CONFIG_PATH.exists():
        save_runtime_config(merged)
    if legacy:
        atomic_write_json(LEGACY_CONFIG_PATH, {})
    return {
        "ok": True,
        "runtime_path": str(RUNTIME_CONFIG_PATH),
        "legacy_path": str(LEGACY_CONFIG_PATH),
        "removed_secret_fields": legacy_secret_fields,
    }
