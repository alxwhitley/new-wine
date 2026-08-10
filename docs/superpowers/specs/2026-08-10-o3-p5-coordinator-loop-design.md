# O3-P5 Repo-Only Coordinator Loop Design

## Status and authority

This design incorporates the 2026-08-10 Sonnet and fresh Opus pressure tests. Both returned `REVISE`; the corrections below are binding. The coordinator remains repo-only, synthetic-only for commissioning, and incapable of production database writes, migrations, deployments, destructive actions, governed-record edits, or answer-path changes.

## Architecture

P5 is a thin orchestration layer over the accepted O2/O3 validators, journal, recovery fold, claims, scheduler, classification, replay, seals, promotion, and reconciliation. It does not introduce another state machine. The existing `cli.py` remains read-only; a separate `run_cli.py` owns explicit write-capable `--once` execution.

Before P5 execution becomes live, O1R synchronizes the hook that Claude Code actually runs and converts the routing checks into collected pytest tests. P5A0 then constrains every packet/dependency identifier before it can enter a filesystem path.

## O1R enforcement prerequisite

`.claude/settings.json` executes `.claude/hooks/guard_pretooluse.py`, so that file—not the refreshed `.codex` copy—is the active Claude Code enforcement surface. O1R must synchronize the production-DB boundary into both copies and make the regression suite collect under pytest. P5 cannot claim repo-only subprocess enforcement from post-hoc result validation.

Real Kimi/Sonnet invocation remains fail-closed until an independently proven pre-execution sandbox constrains filesystem, command, environment, and network access. P5E uses synthetic workers in disposable directories only.

## Identifier and path safety

`packet_id` and every dependency ID use one grammar: `^[a-z0-9][a-z0-9._-]{0,127}$`. Validation occurs in the authoritative packet contract before enrollment or path construction. One helper joins state-root paths only after validating every identifier and then verifies the resolved path remains beneath the intended root. Claims, results, seals, reassignments, projections, and rejected evidence must use it.

Unsafe legacy journal data fails closed. No component sanitizes or rewrites an unsafe identifier into a different identifier.

## Enrollment

Enrollment preflights the entire input batch before its first write. It calls `validate_packet(packet, dependency_states=None)` and computes canonical digests. Against the current fold:

- new ID: preserve the canonical packet artifact atomically, append one validated `PACKET_ENROLLED`, then refresh projections;
- same ID and same digest: deterministic no-op with no journal append;
- same ID and different digest: reject before dispatch and preserve rejection evidence outside the state-changing journal;
- any invalid item in the batch: reject the batch before enrollment writes.

A crash midway through a valid batch may leave an independently valid prefix; retry skips identical enrolled packets. A second `PACKET_ENROLLED` for an existing ID is forbidden because `_fold_journal` treats it as state-root corruption.

## One bounded iteration

`run_once(context)` performs:

1. started-run recovery and fold;
2. resolution of durable open attempts;
3. missing terminal-seal completion;
4. dependency promotion;
5. eligible REVISE requeue;
6. deterministic `select_next`;
7. intent-scoped O_EXCL claim;
8. `ATTEMPT_STARTED` journal commit;
9. configured synthetic worker invocation;
10. structured result capture and validation;
11. valid-result artifact persistence and `WORKER_RESULT_RECORDED`;
12. accepted O3 classification and `ATTEMPT_FINISHED` transition to REVIEW or another classified state;
13. REVIEW resume or trusted verdict ingestion;
14. terminal seal completion before promotion;
15. reconciliation emission;
16. bounded return.

`WORKER_RESULT_RECORDED` is emitted only for a valid worker result, exactly matching recovery semantics. No `RUN_ENDED` event is added: the accepted contracts have no writer or verified external design for it.

## Invocation boundary

Operator-owned configuration selects fixed argv arrays. Packets never select executables, argv, shells, environment variables, or result locations. Invocation uses no shell, creates a process group, redirects stdout/stderr to coordinator-created files, enforces bounded output and wall time, sends SIGTERM then SIGKILL to the group, and verifies group death.

The coordinator creates an advisory process sidecar containing state-root ID, packet ID, attempt, intent ID, PID, PGID, process-start identity, and self-hash. It is recovery evidence, not authoritative state and does not overload `claim.pid` or closed O2/O3 schemas. Restart validates OS identity before terminating a surviving process and never requeues while the old process may still be live.

Structured output uses one coordinator-selected, pre-created result path. The coordinator rejects symlinks and resolved-path escape and computes byte count and digest itself. The subprocess receives an explicit allowlisted environment; production credentials are never inherited through `os.environ.copy()`.

## Review and verdict ingestion

The external reviewer contributes only an `opus_verdict` object. The coordinator loads its own enrolled packet and durably recorded worker result, assembles the replay bundle, supplies operator-owned reviewer trust, and calls `validate_replay_bundle`. This prevents a trusted reviewer from substituting a self-consistent packet/result bundle.

Reviewer identity must be present in the operator-owned trust registry and differ from the worker session. Automatic self-registration is forbidden. P5E uses a predeclared synthetic reviewer identity. Real reviewer enrollment remains an operator action.

A REVIEW-resume pass handles both a resting REVIEW packet without a verdict and a valid unjournaled verdict artifact. Deterministic review claims prevent duplicate reviewer invocation.

## Seals, REVISE, fallback, and promotion

Terminal seals bind the terminal journal event plus packet, result, verdict, and bundle digests where applicable. An identical existing seal is a no-op; a contradictory seal quarantines/fails closed. Seals are completed before dependent promotion.

REVISE preserves checkpoints, satisfied criteria, remaining criteria, and attempt accounting before requeue. Confirmed Kimi exhaustion uses only the accepted provider-evidence confirmation path. First fallback writes an immutable reassignment/checkpoint artifact and journals reassignment. A repeated Sonnet assignment or Sonnet unavailability quarantines the packet. Prior-session exhaustion evidence cannot authorize a new fallback.

## Concurrency proofs

Two distinct tests are required:

1. two top-level coordinators prove the singleton recovery lock admits one coordinator;
2. two lower-level claim attempts, intentionally below the singleton boundary, prove O_EXCL admits exactly one claim winner.

The second test is not described as a coordinator-contention test.

## Testing and commissioning

Every slice follows RED, observed failure, minimum GREEN, focused verification, all prior harness tests, and fresh independent Opus review. P5E uses disposable state roots and synthetic worker/reviewer adapters. Its report states that synthetic success proves orchestration plumbing, not real-provider safety.

`PLAN.md` and `rhemata-status.md` remain unchanged until final Opus `ACCEPT`; build and docs/records commits remain separate.
