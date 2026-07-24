from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions.jarvis_memory import create_skill_candidate, resolve_config, transition_skill
from actions.skill_registry import capability_workflows, enabled_skills


def main() -> int:
    cfg = resolve_config()
    candidate = create_skill_candidate(
        title="Live Validation Read Only Gate",
        purpose="Validate the gated declarative skill lifecycle without external side effects.",
        sources=["JARVIS live validation on 2026-07-21"],
        acceptance_tests=["Gate compiles", "Agent self-approval is rejected", "Enabled skill is discoverable"],
        workflow={
            "schema_version": "jarvis_dual_orchestrator/v1",
            "workflow_id": "live_validation_read_only_gate",
            "version": "1",
            "name": "Live Validation Read Only Gate",
            "max_steps": 1,
            "steps": [
                {
                    "step_id": "confirm_scope",
                    "orchestrator": "deterministic",
                    "step_type": "gate",
                    "target": "approval_gate",
                    "description": "Confirm the already approved read-only validation scope.",
                    "depends_on": [],
                    "inputs": {"passed": True},
                    "risk_tier": "T1",
                    "side_effects": "none",
                    "retry_policy": {"safe": True, "max_attempts": 1},
                    "acceptance_criteria": {"required": True, "required_keys": ["status"]},
                    "on_failure": "halt",
                }
            ],
        },
        cfg=cfg,
    )
    if not candidate.get("ok"):
        print(json.dumps(candidate, indent=2, ensure_ascii=True))
        return 1

    path = str(candidate["path"])
    reviewed = transition_skill(path=path, target_state="reviewed", evidence="Schema compiled.", cfg=cfg)
    tested = transition_skill(path=path, target_state="tested", evidence="Deterministic gate fixture passed.", cfg=cfg)
    self_approval = transition_skill(path=path, target_state="user_approved", actor="agent", cfg=cfg)
    approved = transition_skill(
        path=path,
        target_state="user_approved",
        actor="user",
        evidence="Authorized by the user's live-validation request.",
        cfg=cfg,
    )
    enabled = transition_skill(path=path, target_state="enabled", evidence="Installed for discovery check.", cfg=cfg)
    skill_id = "skill-live-validation-read-only-gate"
    enabled_records = enabled_skills(cfg)
    workflow_records = capability_workflows(cfg)
    discoverable = any(item.get("skill_id") == skill_id for item in enabled_records) and any(
        item.get("workflow_id") == skill_id for item in workflow_records
    )
    deprecated = transition_skill(path=path, target_state="deprecated", evidence="Live validation complete.", cfg=cfg)

    summary = {
        "ok": all(
            [
                reviewed.get("ok"),
                tested.get("ok"),
                not self_approval.get("ok"),
                approved.get("ok"),
                enabled.get("ok"),
                discoverable,
                deprecated.get("ok"),
            ]
        ),
        "note": path,
        "playbook": (candidate.get("playbook") or {}).get("path"),
        "self_approval_rejected": not self_approval.get("ok"),
        "enabled_discoverable": discoverable,
        "enabled_skill_ids": [item.get("skill_id") for item in enabled_records],
        "enabled_workflow_ids": [item.get("workflow_id") for item in workflow_records],
        "installed_playbook": ((enabled.get("installation") or {}).get("installed") or {}).get("playbook_path"),
        "final_state": deprecated.get("skill_state"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
