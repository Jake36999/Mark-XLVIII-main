"""Declared vs effective configuration, and where they disagree.

Two real defects this session were the same shape: a value written in
`config/runtime.json` did not survive to the code that used it, and nothing
surfaced the gap until something crashed or a review caught it.

  * `baseline_models` said one model. `model_lifecycle._resolved_config()`
    appended two more, silently overriding a recorded decision, and made the
    task-model TTL unreachable for speech.
  * `MODEL_PROFILES` advertised a 32768-token context for a model that
    `lmstudio_model_load_profiles` actually loads at 4096 -- an eightfold
    overestimate that produced `n_keep: 4223 >= n_ctx: 4096` at runtime and
    looked like "the small model cannot cope".

Both would have been one command away.

Read-only: it never writes config, never runs inference, and redacts
secret-like keys. It does ask LM Studio which models are *installed* (a
management call, not a generation) and degrades to skipping that check when the
host is unreachable.

Output has two levels, so the signal stays usable:

  DIFF  a contradiction -- declared config and effective behaviour disagree.
        Exit code 1.
  NOTE  an expected transform worth knowing about, such as a context window
        deliberately capped below what the model advertises. Exit code 0.

    python scripts/config_audit.py
    python scripts/config_audit.py --quiet     # contradictions and notes only
    python scripts/config_audit.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SECRET_HINTS = ("key", "secret", "token", "password", "credential")


def _redact(name: str, value: Any) -> Any:
    if any(hint in name.lower() for hint in _SECRET_HINTS):
        return "<redacted>"
    return value


def _runtime_config() -> dict[str, Any]:
    from core.runtime_config import load_runtime_config

    return load_runtime_config()


def _findings() -> list[dict[str, Any]]:
    """Each finding: key, declared, effective, ok, note."""
    findings: list[dict[str, Any]] = []
    declared = _runtime_config()

    # --- model lifecycle: the resolver may transform what it was given -------
    try:
        from actions.model_lifecycle import _resolved_config

        resolved = _resolved_config(None)
        for key in ("baseline_models", "task_model_ttl_seconds", "max_task_models_loaded"):
            left, right = declared.get(key), resolved.get(key)
            same = sorted(left) == sorted(right) if isinstance(left, list) and isinstance(right, list) else left == right
            findings.append(
                {
                    "area": "model_lifecycle",
                    "key": key,
                    "declared": left,
                    "effective": right,
                    "ok": bool(same),
                    "severity": "error",
                    "note": "" if same else "the lifecycle resolver silently changed a configured value",
                }
            )
    except Exception as exc:
        findings.append(
            {"area": "model_lifecycle", "key": "*", "declared": None, "effective": None,
             "ok": False, "note": f"could not resolve: {type(exc).__name__}: {exc}"}
        )

    # --- context windows: advertised vs what LM Studio actually loads --------
    try:
        from actions.model_registry import char_budget_for, effective_profile

        profiles = declared.get("lmstudio_model_load_profiles") or {}
        for model in sorted({*profiles.keys()} - {"default"}):
            profile = effective_profile(model)
            advertised = profile.get("declared_context_window")
            real = profile.get("effective_context_window")
            findings.append(
                {
                    "area": "context_window",
                    "key": model,
                    "declared": advertised,
                    "effective": real,
                    "ok": advertised == real,
                    "severity": "info",
                    "note": ""
                    if advertised == real
                    else (
                        f"loaded at {real} not {advertised}; usable budget {char_budget_for(model)} chars. "
                        "Size prompts with model_registry.char_budget_for(), never the advertised window"
                    ),
                }
            )
    except Exception as exc:
        findings.append(
            {"area": "context_window", "key": "*", "declared": None, "effective": None,
             "ok": False, "note": f"could not resolve: {type(exc).__name__}: {exc}"}
        )

    # --- routing: does every route name a model that is actually installed? --
    # Deliberately probes LM Studio rather than comparing against
    # `lmstudio_model_load_profiles`: a model with no explicit profile is not
    # misconfigured, it inherits the `default` entry. The real hazard is a route
    # pointing at something not installed at all, which only the host can answer.
    try:
        from core.model_router import _lmstudio_routes

        installed: set[str] | None
        try:
            from actions.model_lifecycle import list_models

            payload = list_models(None, timeout=4)
            installed = {
                str(item.get("key") or "").strip()
                for item in (payload.get("models") or [])
                if str(item.get("key") or "").strip()
            } or None
        except Exception:
            installed = None

        if installed is None:
            findings.append(
                {"area": "model_routes", "key": "*", "declared": None, "effective": None,
                 "ok": True, "severity": "info",
                 "note": "skipped -- LM Studio not reachable, so installed models are unknown"}
            )
        else:
            for route, models in sorted(_lmstudio_routes(declared).items()):
                missing = [model for model in models if model not in installed]
                findings.append(
                    {
                        "area": "model_routes",
                        "key": route,
                        "declared": models,
                        "effective": [model for model in models if model in installed],
                        "ok": not missing,
                        "severity": "error",
                        "note": "" if not missing else f"route names models that are not installed: {', '.join(missing)}",
                    }
                )
    except Exception as exc:
        findings.append(
            {"area": "model_routes", "key": "*", "declared": None, "effective": None,
             "ok": False, "severity": "error", "note": f"could not resolve: {type(exc).__name__}: {exc}"}
        )

    # --- policy flags that only matter if something reads them ---------------
    try:
        from core.tool_dispatcher import READ_ONLY_TOOLS

        from actions.capability_registry import CAPABILITY_POLICY

        contradictions = sorted(
            name
            for name in READ_ONLY_TOOLS
            if (CAPABILITY_POLICY.get(name) or {}).get("requires_confirmation")
        )
        findings.append(
            {
                "area": "tool_policy",
                "key": "read_only_vs_requires_confirmation",
                "declared": "no overlap",
                "effective": contradictions or "no overlap",
                "ok": not contradictions,
                "severity": "error",
                "note": "" if not contradictions
                else "tools classified read-only while the registry demands confirmation",
            }
        )
    except Exception as exc:
        findings.append(
            {"area": "tool_policy", "key": "*", "declared": None, "effective": None,
             "ok": False, "note": f"could not resolve: {type(exc).__name__}: {exc}"}
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Report declared vs effective configuration.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--quiet", action="store_true", help="only show divergences")
    args = parser.parse_args()

    findings = _findings()
    diverged = [f for f in findings if not f["ok"]]
    errors = [f for f in diverged if f.get("severity", "error") == "error"]
    notes = [f for f in diverged if f.get("severity") == "info"]

    if args.json:
        print(json.dumps({"findings": findings, "error_count": len(errors), "note_count": len(notes)}, indent=2, default=str))
        return 1 if errors else 0

    area = None
    for finding in findings:
        if args.quiet and finding["ok"]:
            continue
        if finding["area"] != area:
            area = finding["area"]
            print(f"\n=== {area} ===")
        mark = "  ok " if finding["ok"] else ("NOTE " if finding.get("severity") == "info" else "DIFF ")
        print(f"{mark} {finding['key']}")
        if not finding["ok"]:
            print(f"       declared : {_redact(finding['key'], finding['declared'])}")
            print(f"       effective: {_redact(finding['key'], finding['effective'])}")
            if finding["note"]:
                print(f"       -> {finding['note']}")

    print()
    if errors:
        print(f"{len(errors)} contradiction(s) between declared and effective configuration.")
    else:
        print(f"No contradictions. {len(findings) - len(notes)} checks passed.")
    if notes:
        print(f"{len(notes)} note(s): expected transforms worth knowing about, not errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
