# Stabilization and Beta Readiness Program Design

**Date:** 2026-08-15

**Status:** Approved in chat for written specification

## Purpose

Move Rhemata toward the October 2026 private beta by finishing the highest-value
operational verification, correctness, roadmap, and product work without
mistaking optional autonomous-harness work for a launch dependency.

The program preserves the product's ranked failure modes: theological error is
the worst outcome, teacher misrepresentation is second, and generic answers are
third. It also preserves the hard separation between repo-only harness work and
production database writes.

## Operating decision

The standing harness mode is supervised, one worker at a time, with an
independent reviewer. The synthetic coordinator remains built and tested, but
its missing real-provider adapter is not part of this program. No unattended
multi-provider run, real-provider adapter, or deferred safety fence is built
unless Alex separately reopens that work.

Every repo change uses the repository's existing session routing:

- read-only diagnostics run directly;
- repo-only multi-step builds use an isolated executor/reviewer packet;
- trivial mechanical edits run directly;
- governed records and other docs are committed separately from builds;
- production database writes run only in a separately authorized plain-script
  session after a dry run and single-item proof where applicable.

## Program structure

### Track 1: Stabilize and establish current truth

First establish what is deployed and what the live evidence says.

1. Push the already-reviewed local records commit.
2. Confirm Railway backend, Railway worker, and Vercel deployment revisions.
3. Smoke-test the newly gated corpus surfaces and teacher-card behavior.
4. Re-run the Prince quote rejection-reason diagnostic using read-only access.
5. Reproduce the stale stored-position evidence test and classify the mismatch.
6. Diagnose the missing teacher names in the deliverance answer from evidence
   retrieval through generation and rendering.
7. Reconcile the original F5 trace against the four subsequently fixed serving
   bypasses and produce an authoritative remaining list.

Track 1 produces evidence and classifications, not speculative fixes. Any
finding that requires a code change becomes a bounded Track 2 packet. Any
finding that requires a production write becomes a Track 3 decision boundary.

### Track 2: Fix proven repo defects

Implement only defects demonstrated by Track 1 or already supported by current
evidence. Each behavior change starts with a discriminating failing test and is
independently reviewed before integration.

Expected work includes:

- correcting or retiring stale stored-position assertions;
- repairing the deliverance attribution path at the actual failure point;
- resolving correctness-relevant F5 bypasses not already accepted or deferred;
- deciding and, if approved, correcting teacher-card refusal copy;
- correcting stale harness constitution wording;
- reducing recurring harness friction only where a bounded, reproducible fix
  exists.

Build commits and documentation commits remain separate. Answer-path changes
receive the stronger review appropriate to user-facing accuracy risk.

### Track 3: Resolve decisions and isolated data work

Prepare evidence for the remaining owner decisions without inferring Alex's
authority. This track includes:

- merge-or-retire decisions for accepted probe branches;
- Trail and Brooks review/visibility disposition;
- human review of the 18 chapter-boundary proposals;
- `pending` versus `draft` quote-status consolidation;
- Decision 23 quote hardening;
- the `jewish_perspectives` table decision.

No doctrinal, licensing, destructive, migration, or production-write decision
is inferred from this specification. When Alex authorizes a production change,
it runs as its own plain-script session with exact targets, rollback posture,
and reconciliation.

### Track 4: Complete launch-critical product work

After the foundation findings are closed or explicitly accepted, proceed in
this order:

1. Answer integrity and attribution blockers.
2. Position-paper residuals and source/teacher metadata defects.
3. Guest-to-account flow, authentication calls to action, and v4 proposition
   work.
4. Admin notifications required by position refresh.
5. Measured full-answer latency reduction without weakening verification.
6. Private-beta journey, accessibility, security, and production smoke passes.

The existing F6 and B1-B7 roadmap gates remain authoritative. This program does
not silently mark them complete or bypass their evidence requirements.

## Checkpoints

### Checkpoint A: Stabilization evidence

- Deployed revisions are known for all three services.
- The new serving guards have production smoke evidence.
- Prince rejection reasons are quantified or the exact remaining blocker is
  recorded.
- The stale test and deliverance attribution issue have reproducible causes.
- The F5 remaining-bypass list is reconciled and authoritative.

### Checkpoint B: Correctness closure

- Every Track 2 fix has a discriminating regression test.
- Independent review records `ACCEPT` with reproduced evidence.
- Production smoke checks confirm user-facing fixes.
- Canonical records are corrected in a separate docs-only close.

### Checkpoint C: Decision and data closure

- Each owner decision is accepted, deferred with a trigger, or rejected.
- Every authorized production write has dry-run or exact-target evidence,
  execution accounting, and independent live reconciliation.
- No database write was executed through the agent harness.

### Checkpoint D: Beta readiness

- F6 remains valid against the release revision.
- B7 and the corpus-track acceptance gate pass.
- Launch blockers have evidence-backed closure or explicit owner acceptance.
- Alex retains final deployment and private-beta audience approval.

## Failure handling

- An executor's self-report is never sufficient evidence for instruction
  compliance or correctness.
- Repeated harness classifier misfires are reformulated once; a three-turn
  no-progress pattern aborts to the permitted plain path and is recorded.
- Turn counts are planning estimates, not safety boundaries. Hard wall-clock,
  process, output, and attempt limits remain the enforceable controls.
- Any contradiction between an explicit instruction and observed evidence is
  surfaced to Alex rather than resolved unilaterally.
- Unrelated user files, including `Temporary-assets/`, remain untouched.

## Explicit non-goals

- Real-provider coordinator adapters.
- Unattended multi-provider execution.
- A new safety-fence subsystem without its recorded trigger.
- A sixth probabilistic claim-support judge.
- A pre-launch 100-user load test.
- Production database writes through executor/reviewer agents.
- Reopening settled theological, quote, source, or product decisions without
  new evidence and Alex's explicit ruling.
