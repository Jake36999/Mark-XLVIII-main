---
id: "developer-fanout-review-recovery"
title: "Fan-Out, Workers, Review, and Recovery"
type: "guide"
status: "active"
created: "2026-07-22"
updated: "2026-09-24T18:22:21Z"
project_id: "jarvis_notes"
source: "codex"
tags: ["developer-handbook", "fan-out", "workers", "review", "recovery", "tier/short-term"]
sync_state: "local_only"
index_state: "indexed_local"
remember_note_id: ""
rag_index: true
confidence: 0.97
content_hash: "8543430a8506b5f5c630c55ad3fc7887bb5aa13fc244573cc59c06e2583a9a7a"
lifecycle: "short_term"
project_key: "mark_xlviii"
schema_version: "jarvis_developer_handbook/v1"
---

# Fan-Out, Workers, Review, and Recovery

> [!abstract] Bounded parallelism
> JARVIS can execute independent approved work items concurrently, but the worker pool is not allowed to multiply scarce model generations or invent new work. Parallelism follows the compiled dependency graph and runtime resource classes.

## Dependency-Ready Scheduling

The deterministic runtime creates a `ThreadPoolExecutor` with a default maximum of four workers. On each scheduling pass it:

1. reads current item states from SQLite;
2. finds `PENDING` or `REPAIR` items whose dependencies are all `ACCEPTED`;
3. submits ready items until the worker limit is reached;
4. waits for at least one item to finish;
5. stores accepted result records for downstream bindings;
6. repeats until all items are accepted or a terminal condition occurs.

```mermaid
flowchart TD
    A["Approved manifest"] --> B["Find dependency-ready items"]
    B --> C1["I/O worker"]
    B --> C2["I/O worker"]
    B --> C3["Model slot"]
    B --> C4["OpenClaw slot"]
    C1 --> D["Deterministic checks"]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E{"Review verdict"}
    E -->|ACCEPT| F["Atomic result commit"]
    E -->|REPAIR| B
    E -->|REJECT_REPLAN| G["Block run"]
    E -->|ESCALATE| H["User/reviewer decision"]
    F --> B
```

## Resource Classes

| Class | Runtime capacity | Examples |
| --- | --- | --- |
| `io` | Up to the general worker limit | Search, file reads, deterministic hooks, note creation |
| `model` | `max_workers` by default (was a hardcoded single slot, see below) | Model reasoning and independent model review |
| `openclaw` | One active slot | Approved coding scout or development task |
| `command` | General pool plus command policy | Registered executable and argument specification |

> [!important] The model semaphore is no longer hardcoded to one slot (2026-09-23)
> This used to be a fixed `BoundedSemaphore(1)` regardless of `max_workers`, because the only provider was LM Studio holding one local model in VRAM at a time. That constraint doesn't apply to a cloud provider — see [[07 Models Credentials Speech and Resource Lifecycle|Note 07]] on the DeepInfra move — so it now defaults to `max_workers` itself (genuinely concurrent model dispatch), overridable via `model_concurrency=` for a caller that needs to stay under a specific provider's own rate limit.

The one-slot OpenClaw semaphore is unrelated and still serialised regardless of provider — it exists to prevent overlapping coding sessions from competing for the same project and resources, not for model-VRAM reasons.

> [!important] LM Studio `parallel=4`
> LM Studio's parallel value is an instance configuration, not four agents. JARVIS does not interpret it as permission to submit four complete TTS or research requests.

## Two Kinds of Fan-Out

### Scheduler fan-out

Independent predeclared steps run concurrently when their dependencies allow it. This is the primary form of real fan-out.

### YAML `fanout` step

The `fanout` step aggregates a list of **predeclared child results**. It counts children and failures and returns an aggregate status. It does not dynamically create executable children.

This preserves the visible-queue invariant: every executable child must already have a Markdown row, YAML step, and JSON item before approval.

## Worker Selection

Plan packets include a suggested worker based on task shape:

- deterministic local hook or tool for bounded operations;
- lightweight local model for extraction, formatting, and constrained summaries;
- strongest healthy research/reasoning model for synthesis or review;
- OpenClaw for approved coding scouts and development implementation;
- user or Claude boundary for final scientific interpretation where project policy requires it.

OpenClaw defaults to one agent. Two or three agents require explicit multi-file or parallel intent and remain subject to project gates. Every delegation creates a vault handoff record.

## Result Bindings

Downstream inputs can bind to approved fields from dependency results. Bindings are restricted to paths such as:

```yaml
input:
  bind:
    from_step: gather_sources
    path: result.sources
```

The compiler rejects bindings to non-dependencies or arbitrary object paths. Runtime resolution occurs immediately before dispatch.

## Acceptance and Review

Every result passes deterministic acceptance checks before optional model review. Checks can require:

- `ok: true`;
- required output fields;
- artifact paths that exist;
- source or citation counts;
- test return codes;
- schema-conforming structured output;
- negative constraints and scope boundaries.

Review verdicts are:

| Verdict | Meaning |
| --- | --- |
| `ACCEPT` | Hard criteria pass and no material defect remains |
| `REPAIR` | Defect is bounded, localizable, retry-safe, and within the attempt budget |
| `REJECT_REPLAN` | Critical defect, scope breach, unsupported conclusion, exhausted attempts, or unsafe output |
| `ESCALATE` | Reviewer confidence is insufficient for a safe classification |

High-risk or model-generated work can require an independent reviewer context. The reviewer receives the original evidence and acceptance criteria rather than only a worker summary. Model provenance is stored with the result.

> [!important] Pre-dispatch intent check for tool calls (2026-09-24)
> Everything above judges a result *after* dispatch. A `step_type: "tool"` item now also gets checked *before* it runs: `WorkflowRuntime._check_tool_intent` shows a larger/planner-tier model the item's declared intent alongside its fully-resolved arguments (bindings already substituted) and can deny the call outright, converting straight to `REPAIR`/`REJECT_REPLAN` without `_dispatch_tool` ever executing it. This exists because a compiled tool step's arguments are frozen at compile time and dispatched verbatim — nothing previously checked that what actually got bound in (a binding result, a directive value) still matched the item's own description. Additive to every gate above, never a replacement; fails closed on any error (an unavailable checker denies rather than waving the call through). Injectable via `intent_checker=`, mirroring `reviewer=`.

## Retry and Repair

The compiler caps attempts at three. A repair is allowed only when the step is marked retry-safe. Reaching the attempt limit converts another repair request into `REJECT_REPLAN`.

Percentage error estimates may be retained as telemetry, but they do not authorize execution.

> [!important] `ESCALATE` and `REJECT_REPLAN` are both terminal to the automatic dispatch loop, but recover differently
> Neither state is ever revisited by `execute_run`'s own scheduling pass. `retry_escalated_item(run_id, item_id)` is the entry point a human-in-the-loop decision (or a driver acting on one) uses to resume an `ESCALATE`d item — refunding the attempt it resumes, so a role with no inflated `max_attempts` can still be escalated and retried more than once. `execute_canvas_plan` calls it automatically on every invocation for any currently-`ESCALATE`d item, so Mode 2 resumes on its own once a human note is resolved. `retry_rejected_item(run_id, item_id)` (2026-09-24) is the equivalent for `REJECT_REPLAN`, but deliberately **never** called automatically by anything — `REJECT_REPLAN` usually means a genuine plan or model failure that needs a human to actually look at it, not just retry blindly; this is the explicit escape hatch for the narrower case a human has confirmed the rejection was an infrastructure problem (a run dispatched against an unlinked credential, say) rather than the model actually failing the task.

## Leases and Checkpoints

When a worker claims an item, SQLite records:

- worker and lease owner;
- lease expiration and heartbeat;
- attempt and repair count;
- idempotency key;
- retry-safe classification;
- side-effect class;
- result path and error state.

Checkpoints include preparation, before dispatch, side-effect start, result write, commit, interruption, lease recovery, and compensation outcome. A heartbeat thread extends the active lease while work proceeds.

## Idempotency

Each item receives an idempotency key derived from the workflow ID, version, and normalized step. Accepted result paths are recorded separately. A restarted run reuses an existing committed result instead of repeating the action.

## Crash Recovery

Expired `RUNNING` items are handled by side-effect safety:

- Retry-safe item: reclaim into `REPAIR`.
- Non-retry-safe item: mark `UNKNOWN_OUTCOME` and stop.
- Unexpired lease: return `RUN_ALREADY_ACTIVE` rather than launching a duplicate.
- Missing or changed manifest item: pause for item drift.

`UNKNOWN_OUTCOME` is intentionally conservative because an external action may have succeeded before the process died.

## Cancellation

User interruption sets a run cancellation event, marks the run `PAUSING`, and cancels pending or repairable items. Active hooks and commands receive cancellation signals where supported. Model results completed after cancellation are discarded.

Cancellation cannot guarantee reversal of an external side effect already committed. Such cases require checkpoint review.

## Compensation

A side-effecting step may name a registered compensation hook. On rejection, unknown outcome, or terminal failure, the runtime invokes that hook with the original inputs, partial result, and error. Compensation success or failure is checkpointed and logged.

## Run Finalization

| Item condition | Run state |
| --- | --- |
| All items `ACCEPTED` | `COMPLETED` |
| Any `ESCALATE` | `ESCALATED` |
| Any `UNKNOWN_OUTCOME`, `REJECT_REPLAN`, or `BLOCKED` | `BLOCKED` |
| Remaining repairable item | `REPAIRING` |
| Cancellation requested | `CANCELLED` |

## Related Notes

- [[03 Planning Approval and Dual Orchestration]]
- [[07 Models Credentials Speech and Resource Lifecycle]]
- [[09 Implementation Log and Known Boundaries]]
