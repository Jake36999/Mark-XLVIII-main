---
id: "jarvis-20260724T193024Z-6cb9d667"
title: "Canvas Plan Approval — WS4a Live Test: Broken Wikilink Scanner"
type: "plan"
status: "pending_review"
created: "2026-07-24T19:30:24Z"
updated: "2026-07-25T14:33:56Z"
project_id: "jarvis_notes"
source: "canvas_plan"
tags: ["canvas-plan", "approval", "ws4a-live-test", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
sensitivity: "internal"
confidence: 0.5
valid_from: "2026-07-24T19:30:24Z"
review_after: ""
source_version: 1
content_hash: "ca1f215d1ee3978ec28a7910a74d7c9b2e752e0ead6958df86fe68955799c9a3"
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
approval_path: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\canvas_approvals\\ws4a_live_test\\v1\\approval.json"
approval_signature: "7e1312b18c4f3dbb87d0e11fb2d254cc6062fb12e87a32909f59088b45b40a03"
approval_state: "approved"
approved_at: "2026-07-24T19:32:03Z"
bundle_path: "F:\\Mark-XLVIII-main\\Jarvis_notes\\.jarvis\\canvas_approvals\\ws4a_live_test\\v1"
canvas_path: "Canvases/JARVIS/write_a_small_read_only_script_that_scan_a4f2e6.canvas"
execution_state: "blocked"
lifecycle: "short_term"
manifest_hash: "944178e3b81bece4c57b3afb44747a365600bf45a4f55edb92fdf4b3467ea17a"
plan_fingerprint_hash: "19bc8fe4d45d35366e5e8eb97a97386faf1365aaf07078983d3f252018d8d499"
plan_version: 1
run_id: "ws4a_live_test-v1"
workflow_hash: "8a06feef220ac84d91cb204f43770c5ac08faedcc21c9385664b61a8edee94fe"
workflow_id: "ws4a_live_test"
workflow_name: "WS4a Live Test: Broken Wikilink Scanner"
---

# WS4a Live Test: Broken Wikilink Scanner — Canvas Plan Review

**Workflow id:** `ws4a_live_test`
**Steps:** 7

## Compiled Execution Order

| Order | Step | Type | Resource | Risk | Side effects | Confirm | Resolved target |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | Define the task: scan Jarvis_notes vault for [[wikilinks]] that reference non-existent notes and report them. | gate | io | T1 | none | no | — |
| 2 | Investigate the structure and format of the Jarvis_notes vault to understand how wikilinks are stored and referenced. | model_reasoning | model | T1 | none | no | — |
| 3 | Extract and analyze the pattern of [[wikilink]] syntax in the vault files to determine how links are encoded. | model_reasoning | model | T1 | none | no | — |
| 4 | Implement a function that checks whether a given wikilink resolves to an existing note by looking up the note name in the vault directory structure. | tool | openclaw | T3 | external_write | yes | ⚠ no project target — will not write anything |
| 5 | Iterate through all files in the Jarvis_notes vault, extract all [[wikilink]]s, and validate each one using the resolution function; collect any unresolved links. | tool | openclaw | T3 | external_write | yes | ⚠ no project target — will not write anything |
| 6 | Write a simple read-only script that outputs a list of broken wikilinks with their source file and line number, formatted for human readability. | tool | openclaw | T3 | external_write | yes | ⚠ no project target — will not write anything |
| 7 | Run the script on a test vault with known broken links and confirm that it correctly identifies and reports all unresolved wikilinks. | command | command | T2 | local_read | no | ⚠ no scope — runs the entire suite |

## Approval Decision

Mark exactly one box below, then save this note.

- [x] **Approve** — execute the plan exactly as compiled.
- [ ] **Correct** — the plan needs changes before it can run.
- [ ] **Deny** — do not execute this plan.

> [!note] Correction details (only read if **Correct** is checked)
> Describe what should change.

> [!note] Reason for denial (only read if **Deny** is checked)
> Explain why this plan should not run.
