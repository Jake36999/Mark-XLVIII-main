---
id: "skill-validation-{{date:YYYYMMDDHHmmss}}"
title: "{{title}}"
type: "skill-validation"
status: "planned"
created: "{{date:YYYY-MM-DD}} {{time:HH:mm}}"
updated: "2026-07-21T12:55:28Z"
tags: ""
index_state: "excluded_local"
rag_index: false
sensitivity: "normal"
content_hash: "0e8945b9579f13baa11b98e24e2ab7ecacbff2c07669c5380942a6bc56bcb468"
contradicts: []
agent_permission: "blocked"
approval_scope: ""
approval_status: "not-requested"
approved_at: ""
approved_by: ""
assigned_agent: "JARVIS"
blocks: []
confirmation_required: true
depends_on: []
derived_from: []
owner: "user"
parent: ""
rag_mode: "none"
rag_priority: "normal"
rag_review_after: ""
rag_summary: ""
rag_takeaways: []
rag_valid_from: ""
related: []
skill_activation: "disabled"
supports: []
validation_result: "pending"
version: 1
workflow: "learning"
workflow_id: ""
---

# {{title}}

> [!danger] Activation gate
> Passing tests is not approval. The skill remains disabled until the user explicitly approves activation and defines its operating scope.

## Candidate under review

- **Skill candidate:**
- **Candidate version:**
- **Proposed scope:**
- **Execution risk:**

## Acceptance criteria

- [ ] Produces the expected result on representative cases.
- [ ] Refuses or safely handles out-of-scope requests.
- [ ] Observes permission and confirmation gates.
- [ ] Does not expose secrets or sensitive data.
- [ ] Leaves a useful audit trail and evidence.
- [ ] Can be disabled or rolled back safely.

## Test environment

- **Environment:**
- **Tools and versions:**
- **Test data:**
- **Isolation or safeguards:**

## Test cases

| ID | Scenario | Expected result | Actual result | Pass |
| --- | --- | --- | --- | --- |
| SV-01 | Normal case |  |  |  |
| SV-02 | Boundary case |  |  |  |
| SV-03 | Unsafe or prohibited case | Refuse or request confirmation |  |  |
| SV-04 | Failure or interruption | Fail safely and preserve state |  |  |

## Observed failures and risks

-

## Validation result

- **Result:** Pending / Passed / Failed / Conditional
- **Evidence:**
- **Required changes:**
- **Retest needed:**

## User decision

- **Activation decision:** Not decided / Approved / Denied
- **Approved scope:**
- **Required confirmations:**
- **Restrictions:**
- **Review date:**

## Activation record

- **Activated on:**
- **Activated by:**
- **Skill location or identifier:**
- **Version enabled:**
- **Disable or rollback procedure:**

## Post-activation monitoring

- **Success signals:**
- **Failure signals:**
- **Review trigger:**
