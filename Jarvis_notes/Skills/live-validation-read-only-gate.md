---
id: "skill-live-validation-read-only-gate"
title: "Live Validation Read Only Gate"
type: "skill"
status: "deprecated"
created: "2026-07-21T21:34:43Z"
updated: "2026-07-25T14:33:57Z"
project_id: "jarvis_notes"
source: "daemon"
tags: ["skill", "candidate", "approval-required", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "internal"
confidence: 1.0
valid_from: "2026-07-21T21:34:43Z"
review_after: ""
source_version: 1
content_hash: "8e43ca42d028efad6c776d41d62a2ba5c322f76146ad7ddafef622c0f13666da"
supersedes: []
contradicts: []
depends_on: []
depended_on_by: []
extends: []
extended_by: []
implements: []
implemented_by: []
consumes: []
consumed_by: []
related: []
deleted: false
deleted_at: ""
agent_permission: "propose"
approved_playbook_at: "2026-07-21T21:34:43Z"
approved_playbook_hash: "b09dd4f6b1b438387cdb7d739b15a1c1313548e337aa2a6ca20a44fb466bf655"
enabled_at: "2026-07-21T21:34:46Z"
installed_playbook_hash: "b09dd4f6b1b438387cdb7d739b15a1c1313548e337aa2a6ca20a44fb466bf655"
installed_playbook_path: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\skills\\enabled\\skill-live-validation-read-only-gate\\v1\\workflow.yaml"
lifecycle: "short_term"
manifest_hash: "9a38da5a7a8e45677f0052081ad95b1e8be27dc2472f60af8032ca10568ddc9a"
playbook_hash: "b09dd4f6b1b438387cdb7d739b15a1c1313548e337aa2a6ca20a44fb466bf655"
playbook_path: "F:\\Mark-XLVIII-main\\Jarvis_notes\\Skills\\.packages\\skill-live-validation-read-only-gate\\v1\\workflow.yaml"
playbook_step_count: 1
skill_schema_version: 1
skill_state: "deprecated"
skill_version: 1
workflow_hash: "1c67e7dfdff4514cc9ad2a0771f4091c3776f2d3580b18f7409a25e9157e210a"
---

# Live Validation Read Only Gate

## Purpose

Validate the gated declarative skill lifecycle without external side effects.

## Knowledge And Sources

- JARVIS live validation on 2026-07-21

## Executable Boundary

No executable capability is granted while this record is a candidate.

## Acceptance Tests

- Gate compiles
- Agent self-approval is rejected
- Enabled skill is discoverable

## Review Evidence

- Awaiting review.

## Change Log

- 2026-07-21T21:34:43Z: candidate created.

- 2026-07-21T21:34:43Z: candidate -> reviewed by agent. Schema compiled.

- 2026-07-21T21:34:43Z: reviewed -> tested by agent. Deterministic gate fixture passed.

- 2026-07-21T21:34:43Z: tested -> user_approved by user. Authorized by the user's live-validation request.

- 2026-07-21T21:34:46Z: user_approved -> enabled by agent. Installed for discovery check.

- 2026-07-21T21:34:46Z: enabled -> deprecated by agent. Live validation complete.
