"""Optional, explicit persistence for cloud-provider session keys.

Deliberately separate from `core/session_credentials.py` (the in-memory-only
broker) and `core/runtime_config.py` (whose `sanitize_config` actively strips
anything secret-shaped from `config/runtime.json` on every read *and* write --
see `SECRET_FIELD_TOKENS`). Both of those are "never persist a secret" by
design; this module exists because the owner explicitly asked for the
opposite trade for this one file, after repeated OpenAI key expiry made
re-pasting a key every session a real cost. Nothing here is wired in
automatically -- a caller opts in per save/load, same as the UI's own
"remember" checkbox does.

One file, `config/session_keys.env`, one `{PROVIDER}_API_KEY=value` line per
provider, overwritten in place -- "the key most recently saved" per provider,
not a history. Plain `KEY=value` lines, not real dotenv syntax (no quoting,
no comments, no multi-line values) -- this only ever round-trips through
`save_session_key`/`load_session_key`, never hand-edited, so the minimal
shape is enough and avoids a new dependency for it.

`config/session_keys.env` MUST be gitignored -- confirmed added to
`.gitignore` alongside this module. `config/` itself carries no repo-wide
ignore rule (runtime.json is tracked on purpose), so this file needs its own
explicit line.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from core.runtime_config import CONFIG_DIR

SESSION_KEYS_PATH = CONFIG_DIR / "session_keys.env"

_VAR_RE = re.compile(r"^([A-Z0-9_]+)=(.*)$")


def _var_name(provider: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(provider or "").strip()).strip("_").upper()
    return f"{normalized}_API_KEY"


def _read_all(path: Path = SESSION_KEYS_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _VAR_RE.match(line.strip())
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _write_all(values: dict[str, str], path: Path = SESSION_KEYS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic order so a diff (if this file's presence is ever inspected,
    # not its contents) is stable rather than dict-order-dependent noise.
    body = "".join(f"{name}={value}\n" for name, value in sorted(values.items()))
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best-effort on platforms/filesystems that don't support it (e.g. some Windows volumes)


def save_session_key(provider: str, key: str, *, path: Path = SESSION_KEYS_PATH) -> None:
    """Overwrite this provider's line with `key`. Every other provider's saved
    key in the file is left untouched."""
    key = str(key or "").strip()
    if not key:
        raise ValueError("refusing to save an empty key")
    values = _read_all(path)
    values[_var_name(provider)] = key
    _write_all(values, path)


def load_session_key(provider: str, *, path: Path = SESSION_KEYS_PATH) -> str | None:
    return _read_all(path).get(_var_name(provider)) or None


def forget_session_key(provider: str, *, path: Path = SESSION_KEYS_PATH) -> None:
    values = _read_all(path)
    if values.pop(_var_name(provider), None) is not None:
        _write_all(values, path)


def saved_providers(*, path: Path = SESSION_KEYS_PATH) -> list[str]:
    """Provider names (lowercase) with a key currently saved, for UI display."""
    return sorted(
        name[: -len("_API_KEY")].lower()
        for name in _read_all(path)
        if name.endswith("_API_KEY")
    )
