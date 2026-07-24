---
title: "JARVIS Obsidian Document Contract"
type: "system-schema"
status: "active"
updated: "2026-07-21T12:55:28Z"
tags: ""
index_state: "indexed_local"
content_hash: "958b1b1677d7bd2778d6922a846ba46b642ee9f88da155be011055874692b754"
schema_version: 1
---

# JARVIS Obsidian Document Contract

This contract defines the fields shared across workflow notes. Templates may add type-specific properties, but they should not change the meaning of these fields.

## Identity and lifecycle fields

| Property | Type | Meaning |
| --- | --- | --- |
| `id` | Text | Stable identifier; never reuse it for another note |
| `type` | Text | Document type, such as `research-plan` or `project-tracker` |
| `workflow` | Text | `deep-research`, `learning`, or `productivity` |
| `workflow_id` | Text | Stable ID shared by every note in one workflow instance |
| `status` | Text | Current lifecycle state for this document |
| `version` | Number | Increment after material edits |
| `created` | Date-time | Creation timestamp |
| `updated` | Date-time | Latest material update |
| `owner` | Text | Person or system accountable for the note |
| `assigned_agent` | Text | Agent currently responsible for action, if any |
| `sensitivity` | Text | `normal`, `private`, `restricted`, or `secret` |

## Typed relationship fields

Relationship values should contain stable IDs or Obsidian links where supported.

| Property | Meaning |
| --- | --- |
| `parent` | Immediate parent note or workflow control document |
| `depends_on` | Work that must complete first |
| `blocks` | Work prevented by this note's unresolved state |
| `derived_from` | Evidence, reports, or notes from which this content was produced |
| `supports` | Claims or decisions strengthened by this note |
| `contradicts` | Claims or reports this note materially disputes |
| `related` | Useful but untyped relationships |
| `supersedes` | Older note or conclusion replaced by this one |
| `superseded_by` | Newer note or conclusion that replaces this one |

These fields provide the minimum data needed to generate useful DAGs later.

## RAG fields

| Property | Allowed values or purpose |
| --- | --- |
| `rag_index` | Boolean controlling whether the note contributes memory |
| `rag_mode` | `none`, `takeaways-only`, or `full-note` |
| `rag_priority` | `low`, `normal`, `high`, or `critical` |
| `rag_summary` | One to three sentences describing the current, verified meaning |
| `rag_takeaways` | Atomic facts, conclusions, decisions, gaps, or actions |
| `rag_valid_from` | Date from which the memory is considered current |
| `rag_review_after` | Date after which JARVIS should re-verify the memory |

### RAG ingestion rules

1. Do not index a note when `rag_index` is `false`.
2. With `takeaways-only`, index identity, state, summary, takeaways, and source links rather than the full body.
3. With `full-note`, index the complete note only when it is compact, stable, and safe.
4. Never index secrets or content marked `sensitivity: secret`.
5. Store the canonical note ID, version, and path with every RAG record.
6. Re-index after material changes and invalidate records produced from superseded versions.
7. If retrieval conflicts with the source note, the source note wins.

## Permission fields

| Property | Allowed values or purpose |
| --- | --- |
| `agent_permission` | `propose-only`, `execute-approved-scope`, `operator-nondestructive`, or `blocked` |
| `approval_status` | `not-requested`, `requested`, `approved`, `denied`, or `revoked` |
| `approved_by` | User or authority granting approval |
| `approved_at` | Approval timestamp |
| `approval_scope` | Plain-language boundary of the approval |
| `confirmation_required` | Boolean; whether the next material action requires confirmation |

### Permission rules

1. Lack of an approval is not approval.
2. Approval applies only to the recorded scope.
3. Destructive operations require specific confirmation even in operator mode.
4. JARVIS should stop and request direction if new information materially changes risk or scope.
5. Revoked and denied approvals prevent execution immediately.
6. The note must record what was actually executed and the evidence of its result.

## Recommended status values

| Document family | Typical states |
| --- | --- |
| Plans | `draft`, `proposed`, `approved`, `active`, `blocked`, `complete`, `cancelled` |
| Work items | `queued`, `active`, `blocked`, `review`, `complete`, `cancelled` |
| Evidence | `unverified`, `verified`, `disputed`, `superseded` |
| Reports | `draft`, `review`, `final`, `superseded` |
| Knowledge notes | `seedling`, `developing`, `verified`, `superseded` |
| Knowledge gaps | `open`, `researching`, `resolved`, `deferred` |
| Skill candidates | `proposed`, `reviewed`, `validation`, `rejected`, `approved` |
| Projects | `proposed`, `active`, `blocked`, `on-hold`, `complete`, `cancelled` |
| Tasks | `inbox`, `clarifying`, `ready`, `active`, `blocked`, `complete`, `cancelled` |

## Merge and consolidation rules

- Merge reports when they address the same question, rely on compatible evidence, and reach compatible conclusions.
- Preserve separate reports when their themes, assumptions, methods, or conclusions materially differ.
- A synthesis must explicitly describe unresolved disagreement rather than averaging it away.
- Consolidated reports list every document in `derived_from`.
- Old reports can remain for provenance but should be marked `superseded` when no longer current.

## Editing rules

- Preserve user-authored wording unless the task explicitly authorizes rewriting it.
- Prefer bounded section updates over replacing the entire document.
- Append dated progress entries where history is operationally important.
- Preserve unrecognized properties for forward compatibility.
- Update reciprocal links when doing so is safe and unambiguous.
- Use ISO dates and stable enumerated values.
- Do not place credentials, tokens, or secrets in ordinary workflow notes.
