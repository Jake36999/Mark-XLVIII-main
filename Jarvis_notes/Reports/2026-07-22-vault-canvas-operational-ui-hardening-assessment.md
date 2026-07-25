---
id: "hardening-assessment-vault-canvas-ui-2026-07-22"
title: "Vault, Canvas, and Operational UI Hardening Assessment"
type: "report"
status: "awaiting_review"
created: "2026-07-22"
updated: "2026-07-25T14:33:57Z"
project_id: "mark_xlviii"
source: "codex"
tags: ["security", "reliability", "hardening", "review", "tier/short-term"]
sync_state: "local_only"
index_state: "excluded_local"
remember_note_id: ""
rag_index: false
sensitivity: "private"
confidence: 0.9
content_hash: "3f81f35a44c860b7ac088b23fdd1f1b58f67cf1a0ba92777910be2a100bb7883"
lifecycle: "short_term"
schema_version: "jarvis_hardening_report/v1"
---

# Vault, Canvas, and Operational UI Hardening Assessment

> [!warning]
> This is a recommendations-only review. It does not authorize or implement further hardening changes.

## Priority Summary

| Priority | Finding | Severity | Likelihood | Effort |
| --- | --- | --- | --- | --- |
| P1 | Dashboard/LAN transport and device-revocation audit | High | Medium | Medium |
| P1 | Workflow recovery fault injection for external side effects | High | Medium | High |
| P1 | Vault reparse-point and symlink containment tests | High | Low-Medium | Medium |
| P2 | SQLite contention and interrupted-migration recovery | Medium | Medium | Medium |
| P2 | Prompt-injection and sensitivity policy expansion | Medium | Medium | Medium |
| P2 | Process-trace diagnostic export privacy | Medium | Low-Medium | Low |
| P2 | Safe-mode startup and port ownership diagnostics | Medium | Medium | Medium |
| P3 | Dependency pinning and reproducible UI packaging | Medium | Low | Medium |

## P1 Findings

### Dashboard and LAN Transport

**Evidence:** MARK exposes dashboard, pairing, WebSocket, upload/download, and remote-control surfaces in the existing dashboard modules. The new Operations UI reports service reachability but does not change transport authorization.

**Scenario:** A device on the same LAN reuses a stale pairing/session token or reaches an insufficiently protected command or file endpoint.

**Recommendation:** Audit authentication on every HTTP/WebSocket route, token expiry and rotation, device revocation, origin checks, upload/download authorization, and TLS expectations. Add a paired-device inventory and explicit revocation smoke test.

**Tradeoff:** Stronger session expiry and TLS setup add friction to local pairing. **Verification:** unauthorized route matrix, revoked-device test, replay test, origin test, and packet-level confirmation that credentials are not exposed. Migration and user confirmation may be required for existing paired devices.

### External Side-Effect Recovery

**Evidence:** `actions/dual_orchestrator.py` has leases, heartbeats, idempotency records, cancellation, compensation metadata, and `UNKNOWN_OUTCOME`; current tests exercise simulated recovery rather than real external effects.

**Scenario:** MARK is terminated after a remote mutation succeeds but before its result commit, causing duplicate execution or an uncertain outcome after restart.

**Recommendation:** Build fault-injection adapters for retry-safe and non-retry-safe tools, kill workers at each side-effect checkpoint, and prove duplicate prevention, compensation, and manual review of unknown outcomes.

**Tradeoff:** Tests require controlled disposable services. **Verification:** restart matrix across pre-call, in-call, post-call/pre-commit, and post-commit states. No data migration is required.

### Vault Reparse-Point Containment

**Evidence:** vault and Canvas services resolve configured roots and reject ordinary traversal. Windows junctions, symlinks, and path replacement races need dedicated adversarial coverage.

**Scenario:** A link created inside the vault resolves to a sensitive external path and is read, indexed, or overwritten by a permitted semantic operation.

**Recommendation:** Define whether reparse points are rejected or allowed through an explicit root allowlist, validate final handles before reads/writes, and test link replacement between preview and commit.

**Tradeoff:** Rejecting links may affect users who deliberately link external notes. **Verification:** junction, symlink, case-folding, UNC, short-name, and replacement-race tests. User confirmation is required before changing supported link behavior.

## P2 Findings

### SQLite Contention and Migration Recovery

**Evidence:** the vault watcher, router, Canvas index, and operations reader open the same WAL-backed `memory.sqlite`; schema v5 is additive and backed up before migration.

**Scenario:** an abrupt shutdown or antivirus/file-lock delay occurs during migration or simultaneous journal/index writes.

**Recommendation:** add migration fault injection, integrity checks, busy-time telemetry, bounded retry metrics, and a restore-from-backup command that never overwrites the only recoverable copy.

**Tradeoff:** startup checks add a small delay. **Verification:** lock-holder, disk-full, interrupted-DDL, corrupt-WAL, and backup-restore tests. Migration behavior must remain backward compatible.

### Untrusted Content and Sensitivity

**Evidence:** vault changes enter turns as bounded user-controlled evidence and process events redact secret-like fields. Sensitivity relies on frontmatter and current exclusion rules.

**Scenario:** a note or web source contains instructions that attempt to alter permissions, disclose private material, or create hidden work.

**Recommendation:** extend adversarial fixtures across changed-note context, RAG, web reports, Canvas text, and worker output. Centralize sensitivity inheritance and require provenance on every retrieved excerpt.

**Tradeoff:** conservative filtering can reduce recall. **Verification:** prompt-injection corpus, sensitive-note query tests, hidden-work parity checks, and redacted trace/export snapshots. No migration is required unless sensitivity inheritance changes.

### Process Trace Exports

**Evidence:** `core/process_events.py` applies secret/prompt/reasoning redaction, caps the session ring, and exports Markdown with `rag_index: false`. Evidence references can still reveal private path names or operational metadata.

**Scenario:** a diagnostic export is shared outside the machine and exposes project names or local paths.

**Recommendation:** add an export preview, optional path anonymization, sensitivity scanning, and a prominent private-data warning.

**Tradeoff:** anonymization reduces diagnostic value. **Verification:** golden export fixtures with secrets, paths, private note titles, and headers. No migration is required.

### Safe-Mode Startup and Port Ownership

**Evidence:** previous launches encountered occupied ports and single-instance confusion. Operations health now distinguishes optional-offline services but startup recovery remains distributed.

**Scenario:** a stale process or incompatible database prevents normal startup, leaving the desktop shortcut with an opaque failure.

**Recommendation:** add a read-only safe mode, named process/port ownership diagnostics, selective service disablement, and a recovery screen that never starts workflows or speech automatically.

**Tradeoff:** another startup mode requires clear UX. **Verification:** occupied ports, stale lock, unavailable LM Studio, corrupt optional index, and disabled watcher tests. No data migration is required.

## P3 Finding

### Dependency and Package Reproducibility

**Evidence:** the supplied UI package was nested and not importable from top-level discovery; selected modules are now promoted into the application package. Runtime dependencies are not yet fully locked with hashes.

**Scenario:** a fresh machine resolves a different Qt/watchdog/layout dependency and produces startup or rendering regressions.

**Recommendation:** define a reproducible lock/install process, record supported Python/Qt versions, retain package attribution, and test a clean installation in CI or a disposable environment.

**Tradeoff:** pinned dependencies need deliberate updates. **Verification:** clean install, offline install from cache, package-license inventory, and minimum/default/fullscreen screenshot run.

## Deferred Decisions

> [!question]
> Review is required before changing LAN trust rules, reparse-point behavior, paired-device migration, trace anonymization defaults, or startup modes.

The recommended order is: transport audit, real side-effect recovery testing, vault link containment, SQLite recovery, content/sensitivity tests, then usability-oriented safe-mode and export improvements.
