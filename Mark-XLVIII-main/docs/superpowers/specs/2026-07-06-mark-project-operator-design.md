# Mark Project Operator Integration Design

Date: 2026-07-06
Status: Draft for user review

## Purpose

Set up Mark XLVIII as the operator front door for long-running personal project development without building a new platform. Mark should be able to launch, inspect, coordinate, and hand off work across the user's projects while Aletheia supplies project-scoped memory, policy, ToolSet analysis, and safe execution boundaries.

OpenClaw is not the main orchestration brain. It is a lightweight continuity layer for periods between Claude and Codex sessions, especially when token budgets run out or a small coding-assistance worker is useful.

## Project Registry

Create a local project registry owned by the Mark/Aletheia setup. Each entry records:

- Stable project id
- Absolute root path
- Purpose summary
- Preferred operator mode
- Allowed non-destructive commands
- Confirmation-gated commands
- Blocked/destructive actions
- Preferred analysis/coding agents
- Notes that should be injected into handoffs

Initial projects:

| Project id | Path | Role |
| --- | --- | --- |
| `quantule_mapper` | `F:\quantule_mapper` | Custom physics exploration bench. Mark can orchestrate runs and inspect runtime state. Scientific analysis remains user-led or Claude-led. |
| `knowledge_compiler_engine` | `F:\knowledge_compiler_engine (DAG Engine)` | Compute-heavy DAG/data-curation and agent-training system. Mark can inspect, run lightweight checks, and later trigger lightweight tool-assist mode. Heavy training requires confirmation. |
| `mark_platform` | `F:\Mark-XLVIII-main` | The current Mark/Aletheia/ToolSet/OpenClaw integration workspace. |
| `network_management` | `F:\network_management` | CSI/RF/network management pipeline. Mark can run verify/deploy/stop flows through existing scripts, with safety-invariant failures treated as blocking. |

## Authority Model

Use operator mode by default. The system should be capable, not ornamental.

Allowed without confirmation:

- Read project docs, manifests, logs, and non-secret config.
- Run status and health commands.
- Run test discovery and lightweight test commands.
- Run ToolSet/Aletheia read-only repo analysis.
- Start non-destructive scouting, handoff, and memory update workflows.
- Launch lightweight OpenClaw/Codex/Claude continuity tasks that do not mutate project files unless the task itself requests edits.

Require confirmation:

- Deleting, moving, overwriting, or bulk-modifying files.
- Git writes: commit, push, merge, rebase, checkout that discards changes, branch deletion.
- Starting expensive compute, GPU-heavy training, long sweeps, or high-volume ingestion.
- RF/network deployment changes, mode changes, service restart/stop, router/receiver actions, or anything that may alter live infrastructure.
- Commands that touch secrets, credentials, environment files, certificates, raw CSI captures, large datasets, or model weights.
- Any command outside the registered project roots.

Always block:

- Destructive filesystem commands without an explicit confirmation record.
- Broad drive-wide operations.
- Secret exfiltration or printing sensitive token/certificate material.
- Raw arbitrary shell execution from model text without registry/policy classification.
- Network/RF safety-invariant bypasses in `network_management`.

## Components

### Mark XLVIII

Mark remains the human-facing assistant: voice, UI, dashboard, memory prompts, and interaction flow.

Add a `project_operator` action that accepts:

- `project_id`
- `intent`
- `operation`
- Optional `command`
- Optional `requires_confirmation`
- Optional `agent_preference`

This action should delegate to Aletheia rather than implementing direct shell behavior in Mark.

### Aletheia

Aletheia is the control plane. It should load the project registry, enforce allowed roots, record memory, and call existing MCP/tool adapters.

First useful surfaces:

- `mcp_scout_workspace`
- `mcp_code_intelligence`
- `mcp_agent_workflow_run`
- `mcp_commit_memory`
- ToolSet investigation and handoff tools

Deferred useful surfaces, outside the first setup slice:

- A registry-aware command runner with risk classification.
- Confirmation records persisted in Aletheia state.
- Project-specific workflow templates.

### ToolSet

ToolSet remains the deterministic analysis layer. It should produce file maps, semantic slices, manifest reports, handoff bundles, and command-lint reports. Generated artifacts should remain outside project source trees unless explicitly requested.

### OpenClaw

OpenClaw is a lightweight helper for continuity and small coding assistance. It can summarize, inspect, produce small patches, and preserve context between Claude/Codex sessions. It should not become the primary policy engine.

## Project-Specific Policies

### `quantule_mapper`

Mark may start/stop/check ASTE runtime through documented scripts and inspect logs/telemetry. It may stage runs only through documented interfaces. It must not interpret scientific results as final analysis. Claude or the user should own scientific claims and result interpretation.

Confirm before starting long hunts, GPU workers, cleanup, archive deletion, or modifying result queues.

### `knowledge_compiler_engine`

Mark may inspect repo state, run lightweight unit checks, prepare handoffs, and identify lightweight-mode integration points. Heavy training, Docker/Celery stack launch, dataset generation, and model refinement require confirmation.

The future lightweight mode should expose a small tool-assist surface first, then expand after successful verification.

### `mark_platform`

Mark may manage local daemon setup, project registry, Aletheia/ToolSet integration scripts, and operator documentation. It should avoid mutating embedded upstream projects unless the task is explicitly about that project.

### `network_management`

Mark may run `Verify-RfBackend.ps1`, inspect manifests, and summarize backend status. Deploy/stop/mode changes require confirmation. Safety invariants in `RF_BACKEND_DEPLOYMENT_DIRECTIVE.md` and `rf_backend_manifest.json` are authoritative. Invariant failures block escalation rather than being bypassed.

## Data Flow

1. User asks Mark to operate on a project.
2. Mark maps the request to a `project_id` and operation.
3. Mark sends the request to Aletheia.
4. Aletheia loads the project registry and classifies risk.
5. If confirmation is required, Aletheia returns a confirmation request with the exact command and reason.
6. If allowed, Aletheia runs the operation through a registered tool or safe command adapter.
7. Aletheia records durable project memory and returns a concise result.
8. Mark reports the result through voice/UI and stores any useful user-facing memory.

## Error Handling

- Unknown project ids return a registry error with known project choices.
- Commands outside allowed roots are rejected.
- Missing tools or scripts return setup guidance, not blind fallback shell attempts.
- Long-running operations stream or poll status where possible.
- Policy blocks should explain the gate and the exact approval needed.
- Infrastructure safety failures are treated as stop conditions.

## Verification

Initial verification should prove:

- Project registry parses and validates.
- Aletheia allowed roots include exactly the registered project roots and integration workspace.
- Mark can call a read-only Aletheia project operation.
- Each project can run at least one safe status/scout action.
- Confirmation-gated actions return a gate instead of executing.
- Destructive commands are blocked without confirmation.

## First Implementation Slice

1. Add a project registry file under the Mark/Aletheia integration workspace.
2. Add local startup scripts for Aletheia using the registered project roots as `ALETHEIA_ALLOWED_ROOTS`.
3. Add a small Mark `project_operator` action that calls Aletheia's bridge for read-only and gated operations.
4. Add project-specific command metadata for safe status actions.
5. Verify with safe commands only.
