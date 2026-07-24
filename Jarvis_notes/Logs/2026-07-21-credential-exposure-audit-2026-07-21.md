---
id: "jarvis-20260721T131047Z-2ff5c2d4"
title: "Credential Exposure Audit - 2026-07-21"
type: "log"
status: "action_required"
created: "2026-07-21T13:10:47Z"
updated: "2026-07-23T02:52:43Z"
project_id: "jarvis_notes"
source: "security_audit"
tags: ["security", "credential-audit", "private", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "private"
confidence: 0.5
valid_from: "2026-07-21T13:10:47Z"
review_after: ""
source_version: 1
content_hash: "70a87ebfa98fcba0ec6f08a5d8979957128d5c9448e3c0d031250ca04d5ee965"
supersedes: []
contradicts: []
deleted: false
deleted_at: ""
finding_count: 21
memory_tier: "short_term"
revocation_acknowledged: false
---

# Credential Exposure Audit - 2026-07-21

## Context

> [!danger]
> Found 21 credential-shaped occurrence(s). Values are intentionally omitted.

## Events

| Source | Location | Line | Pattern | Fingerprint |
| --- | --- | ---: | --- | --- |
| git_history | `794368f1af14:Mark-XLVIII-main/tests/test_model_router.py` | 60 | configured_secret | `1d0a477377e2` |
| git_history | `a45789a3bbc2:Mark-XLVIII-main/tests/test_model_router.py` | 60 | configured_secret | `1d0a477377e2` |
| worktree | `F:\Mark-XLVIII-main\Agent_backend\.claude\worktrees\strange-noyce-9ad0c3\backend\python-daemon\tests\test_integration_policy.py` | 333 | configured_secret | `5c0b62eb5fb3` |
| worktree | `F:\Mark-XLVIII-main\ClawTeam-OpenClaw-main\ClawTeam-OpenClaw-main\tests\test_spawn_cli.py` | 153 | configured_secret | `a5cf79d9d0ed` |
| worktree | `F:\Mark-XLVIII-main\ClawTeam-OpenClaw-main\ClawTeam-OpenClaw-main\tests\test_spawn_cli.py` | 193 | configured_secret | `d9688081105b` |
| worktree | `F:\Mark-XLVIII-main\ClawTeam-OpenClaw-main\ClawTeam-OpenClaw-main\tests\test_spawn_cli.py` | 231 | configured_secret | `a5cf79d9d0ed` |
| worktree | `F:\Mark-XLVIII-main\ClawTeam-OpenClaw-main\ClawTeam-OpenClaw-main\tests\test_spawn_cli.py` | 335 | configured_secret | `a5cf79d9d0ed` |
| worktree | `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_model_router.py` | 74 | configured_secret | `1d0a477377e2` |
| worktree | `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_model_router.py` | 93 | configured_secret | `7f6e21dc0bfc` |
| worktree | `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_model_router.py` | 121 | configured_secret | `c7044184c279` |
| worktree | `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_model_router.py` | 151 | configured_secret | `b106e15d6656` |
| worktree | `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_model_router.py` | 207 | configured_secret | `7f6e21dc0bfc` |
| worktree | `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_model_router.py` | 382 | configured_secret | `b106e15d6656` |
| worktree | `F:\Mark-XLVIII-main\Mark-XLVIII-main\tests\test_runtime_security.py` | 19 | configured_secret | `afbb9b6c7c26` |
| worktree | `F:\Mark-XLVIII-main\ToolSet\.cache\semantic_ast\8697f6966eb0dd445437f9a17f84efa3af8bd60e6c4b01533908e7756af4bf55.json` | 1 | configured_secret | `edfcaac57902` |
| worktree | `F:\Mark-XLVIII-main\ToolSet\.cache\semantic_ast\c1c2a9feef5f3d63d182577f11183487a66a381049567b9b411c25493a07c564.json` | 1 | configured_secret | `bf87a44773b4` |
| worktree | `F:\Mark-XLVIII-main\ToolSet\.cache\semantic_ast\e84d4e23ac5d556ffdce09ff2fdb2dc353d921e92541cbfe9c85a8cc81be11e4.json` | 1 | configured_secret | `bf87a44773b4` |
| worktree | `F:\Mark-XLVIII-main\ToolSet\aletheia_toolchain\.cache\semantic_ast\e84d4e23ac5d556ffdce09ff2fdb2dc353d921e92541cbfe9c85a8cc81be11e4.json` | 1 | configured_secret | `bf87a44773b4` |
| worktree | `F:\Mark-XLVIII-main\ToolSet\aletheia_toolchain\tests\test_runtime_forensics.py` | 466 | configured_secret | `bf87a44773b4` |
| worktree | `F:\Mark-XLVIII-main\ToolSet\aletheia_toolchain\tests\test_security.py` | 53 | configured_secret | `edfcaac57902` |
| worktree | `F:\Mark-XLVIII-main\ToolSet\aletheia_toolchain\tests\test_workspace_packager_v2_4.py` | 339 | configured_secret | `bf87a44773b4` |

## Outcome

- [ ] Revoke any previously exposed OpenAI or Google keys.
- [ ] Review provider usage and billing history.
- [ ] Confirm revocation before marking this audit resolved.

## Next Steps

- Current worktree scanned
- Runtime logs and local crash/temp text scanned
- Git history scanned (bounded to 500 commits)
- Keep this note excluded from RAG.
