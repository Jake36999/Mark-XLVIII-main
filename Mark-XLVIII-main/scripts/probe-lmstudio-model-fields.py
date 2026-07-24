"""Read-only discovery probe for the LM Studio native model API.

Dumps the field structure of GET {native_url}/models so the VRAM admission work
can be built against what LM Studio actually reports rather than an assumption.

Supports Task B1 of docs/superpowers/plans/2026-07-22-mark-model-health-and-vram-admission.md.

Usage:
    python scripts/probe-lmstudio-model-fields.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from actions import model_lifecycle
from core.runtime_config import load_runtime_config

SIZE_HINTS = ("size", "bytes", "vram", "memory", "gpu", "footprint", "ram")


def _walk_keys(value, prefix: str = "", out: set[str] | None = None) -> set[str]:
    out = set() if out is None else out
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.add(path)
            _walk_keys(item, path, out)
    elif isinstance(value, list) and value:
        _walk_keys(value[0], f"{prefix}[]", out)
    return out


def main() -> int:
    cfg = model_lifecycle.resolve_config(load_runtime_config())
    url = f"{cfg['native_url']}/models"
    print(f"GET {url}\n")

    response = requests.get(url, headers=model_lifecycle._headers(cfg), timeout=15)
    response.raise_for_status()
    payload = response.json()
    models = payload.get("models") if isinstance(payload, dict) else []

    print(f"top-level keys: {sorted(payload)}")
    print(f"model count: {len(models)}\n")

    all_keys: set[str] = set()
    for model in models:
        _walk_keys(model, "", all_keys)

    print("=== union of all field paths ===")
    for key in sorted(all_keys):
        print(f"  {key}")

    print("\n=== fields matching size/memory hints ===")
    hits = [k for k in sorted(all_keys) if any(h in k.lower() for h in SIZE_HINTS)]
    for key in hits:
        print(f"  {key}")
    if not hits:
        print("  (none — declared vram_gb is the only available source)")

    loaded = [m for m in models if m.get("loaded_instances")]
    unloaded = [m for m in models if not m.get("loaded_instances")]

    print(f"\n=== sample LOADED model ({len(loaded)} loaded) ===")
    print(json.dumps(loaded[0], indent=2)[:4000] if loaded else "  (none loaded)")

    print(f"\n=== sample UNLOADED model ({len(unloaded)} unloaded) ===")
    print(json.dumps(unloaded[0], indent=2)[:4000] if unloaded else "  (none unloaded)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
