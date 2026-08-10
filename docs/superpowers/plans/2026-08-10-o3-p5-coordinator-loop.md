# O3-P5 Coordinator Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and synthetically commission one bounded, crash-resumable, repo-only coordinator iteration by composing the accepted O2/O3 contracts.

**Architecture:** Repair the active O1 enforcement prerequisite, constrain identifiers before filesystem use, then add a thin execution layer around existing recovery, scheduling, classification, replay, sealing, and reconciliation functions. Real providers remain unavailable without a separately proven sandbox.

**Tech Stack:** Python 3.9, pytest, JSON Schema, atomic filesystem operations, `fcntl`, `subprocess`, POSIX process groups.

## Global Constraints

- Never run production DB writes, migrations, deployments, destructive actions, governed-record edits, or answer-path changes.
- Preserve every unrelated dirty file; workers own only files named by their task.
- Use `^[a-z0-9][a-z0-9._-]{0,127}$` for packet and dependency identifiers.
- Reuse accepted O2/O3 validators and state transitions; do not create a parallel state machine.
- Keep `scripts/harness_coordinator/v1/cli.py` read-only.
- Commission synthetic workers and disposable state roots only.
- Run all 391 accepted tests after every slice and require fresh Opus `ACCEPT` before the next slice.
- Do not update `PLAN.md` or `rhemata-status.md` before final Opus `ACCEPT`.
- Keep build commits and docs/records commits separate.

---

### Task 1: O1R active-hook synchronization

**Files:**
- Modify: `.claude/hooks/guard_pretooluse.py`
- Modify: `.codex/hooks/guard_pretooluse.py`
- Modify: `.claude/harness-selftest/test_current_routing_contract.py`

**Interfaces:**
- Consumes: `.claude/settings.json` and `.codex/hooks.json` hook paths.
- Produces: identical production-DB boundary behavior on both active hook copies and pytest-collected regression tests.

- [ ] Write pytest tests that assert both configured hooks reject recognizable real ingest/backfill/migration/seed/restore/direct mutating-SQL execution, allow dry runs, and contain no retired name-specific freeze.
- [ ] Run `python3 -m pytest -q .claude/harness-selftest/test_current_routing_contract.py` and capture RED caused by the stale `.claude` copy and zero prior collection.
- [ ] Make the minimum hook synchronization and test conversion.
- [ ] Run the focused test GREEN, then `python3 -m pytest -q .claude/harness-selftest/test_o2_*.py .claude/harness-selftest/test_o3_*.py` and the three legacy harness scripts.
- [ ] Commit only Task 1 files and obtain independent Opus `ACCEPT`.

### Task 2: P5A0 safe identifier contract

**Files:**
- Modify: `schemas/harness/v1/packet.schema.json`
- Modify: `scripts/harness_contracts/v1/packet.py`
- Create: `scripts/harness_coordinator/v1/paths.py`
- Create: `.claude/harness-selftest/test_o3_p5_identifiers.py`
- Modify callers under `scripts/harness_coordinator/v1/` only where an identifier becomes a path.

**Interfaces:**
- Produces: `validate_harness_id(value, path)`, `safe_state_path(root, *literal_parts, identifier=...)`.

- [ ] Add failing tests for `../../evil`, absolute paths, separators, empty IDs, overlength IDs, dependency IDs, and safe IDs.
- [ ] Capture focused RED.
- [ ] Implement one identifier validator and path containment helper; wire packet/dependency validation and path-forming callers.
- [ ] Run focused GREEN and all prior tests.
- [ ] Commit only Task 2 files and obtain independent Opus `ACCEPT`.

### Task 3: P5A enrollment, deduplication, selection, and claims

**Files:**
- Create: `scripts/harness_coordinator/v1/enroll.py`
- Create: `scripts/harness_coordinator/v1/coordinator.py`
- Create: `scripts/harness_coordinator/v1/run_cli.py`
- Create: `.claude/harness-selftest/test_o3_p5_enrollment.py`

**Interfaces:**
- Produces: `preflight_packets`, `enroll_packets`, `run_once`, and explicit `--once` selection.

- [ ] Write failing tests for invalid preflight, identical duplicate no-op, conflicting duplicate rejection, retry after partial batch, deterministic selection, singleton contention, and lower-level exactly-one claim winner.
- [ ] Capture focused RED.
- [ ] Implement preflight-before-write enrollment using `validate_packet(..., dependency_states=None)`, journal CAS, fold-based deduplication, `select_next`, and existing claim primitives.
- [ ] Run focused GREEN and all prior tests.
- [ ] Commit only Task 3 files and obtain independent Opus `ACCEPT`.

### Task 4: P5B bounded synthetic invocation

**Files:**
- Create: `scripts/harness_coordinator/v1/invoke.py`
- Create: `scripts/harness_coordinator/v1/process_sidecar.py`
- Create: `.claude/harness-selftest/test_o3_p5_invocation.py`

**Interfaces:**
- Produces: operator-owned `WorkerAdapter`, `invoke_worker`, advisory process-sidecar read/write/validation.

- [ ] Write failing tests for exit-before-result, malformed JSON, invalid schema, timeout, output cap, interruption before/during invocation, orphan process recovery, forbidden-path attempt, secret-free environment, symlink/result-path escape, and process-group termination.
- [ ] Capture focused RED.
- [ ] Implement no-shell invocation, process group lifecycle, explicit environment, coordinator-owned capture files, sidecar, and validated result ingestion.
- [ ] Run focused GREEN and all prior tests.
- [ ] Commit only Task 4 files and obtain independent Opus `ACCEPT`.

### Task 5: P5C trusted review, seals, REVISE, and promotion

**Files:**
- Create: `scripts/harness_coordinator/v1/review.py`
- Create: `scripts/harness_coordinator/v1/seals_runtime.py`
- Create: `.claude/harness-selftest/test_o3_p5_review.py`
- Modify: `scripts/harness_coordinator/v1/coordinator.py`

**Interfaces:**
- Produces: coordinator-assembled replay bundle, verdict-only inbox ingestion, REVIEW resume, idempotent seal completion.

- [ ] Write failing tests for untrusted/self reviewer, substituted bundle, incomplete ACCEPT evidence, REVIEW restart with/without unjournaled verdict, verdict-to-seal interruption, REVISE preservation, promotion after seal, contradictory seal, and malicious rehashed verdict.
- [ ] Capture focused RED.
- [ ] Implement verdict-only ingestion, durable-ground-truth bundle assembly, accepted validators, review claims, seal-before-promotion, and accepted REVISE/promotion functions.
- [ ] Run focused GREEN and all prior tests.
- [ ] Commit only Task 5 files and obtain independent Opus `ACCEPT`.

### Task 6: P5D restart, one-time fallback, reconciliation, and status

**Files:**
- Create: `scripts/harness_coordinator/v1/reassignment_runtime.py`
- Create: `.claude/harness-selftest/test_o3_p5_resume.py`
- Modify: `scripts/harness_coordinator/v1/coordinator.py`
- Modify: `scripts/harness_coordinator/v1/run_cli.py`
- Modify: `scripts/harness_coordinator/v1/cli.py` only for read-only status output.

**Interfaces:**
- Produces: immutable reassignment/checkpoint artifact, restart-safe fallback, deterministic `--once` exit result.

- [ ] Write failing tests for stale committed/abandoned intents, accepted restart, fake/stale/confirmed exhaustion, repeated Sonnet assignment, Sonnet unavailable, quarantine independence, reconciliation mismatch, and no-op `--once` reconciliation.
- [ ] Capture focused RED.
- [ ] Implement direct accepted fallback confirmation, immutable reassignment artifact, recovery ordering, reconciliation emission, and read-only status.
- [ ] Run focused GREEN and all prior tests.
- [ ] Commit only Task 6 files and obtain independent Opus `ACCEPT`.

### Task 7: P5E synthetic commissioning and final review

**Files:**
- Create: `.claude/harness-selftest/synthetic_p5_worker.py`
- Create: `.claude/harness-selftest/synthetic_p5_reviewer.py`
- Create: `.claude/harness-selftest/test_o3_p5_commissioning.py`
- Create: `docs/audits/o3_p5_synthetic_commissioning_2026-08-10.md`

**Interfaces:**
- Produces: reproducible disposable-state commissioning evidence.

- [ ] Write the commissioning test first and capture RED.
- [ ] Complete the minimum synthetic fixtures for enrollment → claim → worker → REVIEW → trusted verdict → seal → promotion → reconciliation.
- [ ] Prove deliberate interruption/resume without duplicate execution, separate singleton and claim contention, and deterministic `--once`.
- [ ] Run every P5 test and the 391-test baseline fresh.
- [ ] Record exact commands/results and explicitly state that synthetic commissioning does not prove real-provider safety.
- [ ] Commit build/audit evidence without governed-record changes and obtain final independent Opus `ACCEPT`.

### Task 8: Governed-record close after final ACCEPT

**Files:**
- Modify: `PLAN.md`
- Modify: `rhemata-status.md`

**Interfaces:**
- Consumes: final Opus verdict and fresh verification evidence.
- Produces: final O3-P5 roadmap/status state in a docs-only commit.

- [ ] Replace the existing O3/P5 status rather than stacking history.
- [ ] Update the current-state record with exact verification and known real-provider sandbox limitation.
- [ ] Verify no build files are staged with the record changes.
- [ ] Commit the records separately; do not push or deploy.
