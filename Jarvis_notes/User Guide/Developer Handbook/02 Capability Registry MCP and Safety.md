---
id: "developer-capabilities-mcp-safety"
title: "Capability Registry MCP and Safety"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-07-25T14:55:45Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "capabilities", "mcp", "tools", "safety", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.96
content_hash: "ab9c673842f08328b0b99e8afa0cdf59eb6fbff442470a1bdc0cf5eae3e7d1ad"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Capability Registry, MCP, and Safety

> [!abstract] Purpose
> The capability system gives models enough information to select a useful tool without placing every schema, playbook, and implementation detail into every prompt.

## Progressive Disclosure

| Level | Contents | Loaded when |
| --- | --- | --- |
| L0 capability card | ID, one-line purpose, triggers, risk, availability, health | Capability selection |
| L1 manifest | Inputs, outputs, constraints, permissions, quality floor, safety rules | A capability is shortlisted |
| Workflow playbook | Ordered steps, tools, artifacts, success/block states | A workflow is selected or planned |
| Function schema | Exact tool parameters and operations | Immediately before validation or dispatch |

The stateless selector receives L0 cards plus live health. Source documents and user-provided evidence are not allowed to select their own capabilities.

> [!note] L0 selection scoring is word-tokenized (fixed 2026-07-25)
> `_search_cards()` used to score a card by raw substring counting on its id/summary/triggers text, not word-tokenized matching like the sibling `_search_records()`. Short query words that survive the stopword filter (e.g. "in", "on") could match as substrings inside unrelated longer words — "in" inside "installing", "on" inside "consolidation" — occasionally outranking a genuinely relevant tool. Found live while validating `graphify_query`'s own discoverability. Now tokenizes the haystack into words with the same plural-variant handling `_search_records()` already used, and `SEARCH_STOPWORDS` gained `in`/`on`/`this` as defense in depth.

## Registry Interfaces

`capability_registry` exposes direct operations and JSON-RPC-style methods:

| Method family | Use |
| --- | --- |
| `cards/list` | Compact capability selection set |
| `manifests/get` | Full constraints and quality requirements for one capability |
| `workflows/list` | Workflow catalog |
| `workflows/get` | Full workflow metadata |
| `workflows/search` | Trigger and keyword lookup |
| `workflows/plan` | Metadata-only match and proposed tool order for a request |
| `schemas/get` | Exact execution schema loaded just in time |
| `tools/list` | Registered executable tool declarations |
| `tools/get` | Tool help and parameter metadata |
| `tools/call` | Guarded dispatch through the standalone MCP server |
| `health` | Registry and native capability availability |

The MCP server supports stdio and loopback HTTP modes. HTTP mode binds only to localhost and uses a local token and origin allowlist.

## Current Workflow Catalog

| Workflow | Risk | Main result |
| --- | --- | --- |
| `bounded_rag_orientation` | Low | Compact cited project context |
| `browser_task_automation` | Medium | Browser state or screenshot; sensitive actions gated |
| `current_news_report` | Low | Date-scoped cited report |
| `deep_research_report` | Low | Sourced long-form report |
| `folder_analysis` | Low | Folder inventory and optional report |
| `large_document_analysis` | Low | Checkpointed chunk/map/reduce report |
| `learn_topic_memory` | Low | Cited report plus compact learned-topic memory |
| `local_file_management` | Medium | Read or approved local file changes |
| `long_form_plan_execution` | Medium | Plan, approved run, summary or blocker |
| `rag_memory_roundtrip` | Low | Canonical note indexed and queried back |
| `registered_project_handoff` | Medium | Project scout and continuity note |
| `repository_learning` | Low | Read-only project brief and compact project memory |
| `rolling_canvas_tracking` | Medium | Bounded Canvas derived from Markdown |
| `scheduled_reminder` | Low | Local reminder |
| `short_term_json_memory` | Low | Prompt-cache fact plus vault mirror |
| `skill_learning_gate` | Medium | Reviewed and user-approved executable skill candidate |
| `task_tracking_review` | Low | Overdue/stale task review |
| `todo_list_template` | Low | Blank canonical checklist template |
| `vault_markdown_note` | Low | Frontmatter-equipped Markdown note |

## Tool Dispatcher

`core/tool_dispatcher.py` is the execution boundary for model-requested tools:

1. Load declarations from the application source.
2. Resolve the requested operation.
3. Classify its effect as read-only, local write, external side effect, destructive, or workflow-authorized.
4. Verify confirmation or approved-workflow authorization when required.
5. Resolve the registered Python handler.
6. Execute it under a per-tool lock where needed.
7. Decode the result and attach the policy decision.

> [!warning] Registry metadata is not permission
> Discovering that a tool exists does not authorize its use. The dispatcher still applies effect policy and workflow approval.

## Safety Boundaries

### Read-only and low-risk actions

Typical examples include local search, file reads, capability help, weather queries, RAG queries, model status, and vault note creation.

### Confirmation-gated actions

Examples include file moves, overwrites, browser submissions, account changes, shell commands, broad project operations, heavy jobs, and OpenClaw delegation.

### Workflow authorization

An executable workflow step must match the approved action ID and frozen manifest. The deterministic orchestrator, not the model, verifies this contract.

## Registered Hooks and Commands

YAML cannot contain inline Python or arbitrary shell strings. It may reference only:

- Registered Python hooks with input/output schemas, timeout, risk, side effects, retry class, and acceptance checks.
- Registered command specifications containing an executable, argument array, allowed working roots, timeout, side-effect class, and confirmation policy.

The compiler rejects unknown hooks, unknown tools, unknown commands, missing dependencies, invalid binding paths, cycles, and command steps lacking required confirmation metadata.

## Evidence Isolation

Model-reasoning and review steps receive source material inside an explicit `untrusted evidence` boundary. Runtime system prompts state that evidence cannot:

- change permissions;
- select tools or models;
- add workflow steps;
- override negative constraints;
- modify approval scope;
- authorize external actions.

## Aletheia and External Connectivity

MARK reuses Aletheia patterns and can call its loopback JSON-RPC bridge through `project_operator`, but MARK remains independently runnable. The Mark-native dispatcher, workflow compiler, queues, and RAG do not require the separate Aletheia application to launch.

OpenClaw is similarly optional and is invoked through a registered project operation for bounded coding continuity. It is not an always-on worker pool.

## Extending the Registry

To add a capability safely:

1. Implement a deterministic handler or registered hook.
2. Add a tool declaration and operation schema.
3. Define effect classification and confirmation behavior.
4. Add L0 and L1 help metadata.
5. Add a workflow record only if the capability participates in a repeatable sequence.
6. Add health checks and a quality floor.
7. Test selection, schema retrieval, policy rejection, and successful dispatch.

## Related Notes

- [[01 Runtime Architecture and Turn Lifecycle]]
- [[03 Planning Approval and Dual Orchestration]]
- [[04 Fan-Out Workers Review and Recovery]]
- [[14 Graphify Knowledge Graph Integration]] — a full worked example of the registration chain (L0 card → risk policy → tool schema → dispatch)
