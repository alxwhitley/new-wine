# Rhemata — Private-Beta Blocker Plan

> This file is the only active work queue. It contains only work that must close
> before the private beta can advance. Later work lives in `docs/roadmap.md`;
> completed and superseded reasoning lives in `docs/plan-archive.md`.

**Goal:** reach an ingestion-ready platform, then complete the product and corpus
tracks required for a private-beta launch candidate in October 2026.

**Current item:** **F2 recoverability**. Only one blocker may be in progress.

## Working boundary

- Follow the Beta Critical Path and Anti-Zeno rules in `AGENTS.md`.
- A discovery does not enter this file automatically. Alex must promote it under
  the Blocker rule with concrete beta harm, evidence, affected surface, and the
  smallest closure condition.
- Scheduled, Triggered, and Parked work belongs in `docs/roadmap.md` and does not
  authorize work during a blocker session.
- `CLAUDE.md` owns product invariants and landmines. `ARCHITECTURE.md` owns current
  implementation detail. `rhemata-status.md` owns point-in-time session state.
- Production database writes remain attended, explicitly approved operations in
  the primary Codex session. They never run through a subagent or coordinator.

## Frozen blocker order

### F2 — Recoverability

**Status:** IN PROGRESS

Close when both are true:

- [ ] Record authoritative Supabase backup/PITR status, retention, restore
  granularity, owner, RTO/RPO, and exclusions.
- [ ] Test the safest available restore scope. If full-project disaster restore
  cannot be proven, Alex explicitly accepts, upgrades, or defers the gap.

Already closed: production-relevant dependency pins, backend/worker Python
parity, and clean-environment backend/admin-auth smoke coverage. Evidence:
`docs/audits/deps_pin_pydantic_starlette_2026-08-14.md` and
`docs/audits/nixpacks_python_parity_2026-08-14.md`.

**Audit boundary:** authoritative recovery facts, the safest permitted restore
proof, and the two criteria above. Adjacent Supabase, schema, deployment, or
harness findings are classified and do not expand the session.

### F3 — Ingestion-default contract

**Status:** WAITING FOR ALEX, then queued after F2.

Alex first decides whether private beta itself is the Tier-1-to-Tier-2 trip
line. Policy and evidence are in:

- `docs/audits/f3_visible_default_policy_2026-08-17.md`
- `docs/audits/f3_visible_default_evidence_2026-08-17.md`

Close when all are true:

- [ ] Newly registered source classes follow the approved visible-default rule;
  sentinel, unresolved-alias, empty-shell, and Tier-2 exceptions are explicit.
- [ ] Schema and registration paths agree without weakening license,
  retrievability, or serving gates.
- [ ] One dry run and one isolated real registration pass through the actual
  chokepoint and reconcile source/document/chunk/proposition state.
- [ ] `ARCHITECTURE.md` records the approved policy and actual implementation.

The orphaned admin PDF-upload endpoint is an Alex-accepted named exception, not
an unlabeled bypass or an implicit repair task.

### F4 — Pre-benchmark quality decisions

**Status:** QUEUED after F3.

Close when Alex makes both decisions:

- [ ] **Claim-support residual risk:** accept it, retain a narrow deterministic
  check, or define evidence sufficient to reopen work. Do not build a sixth
  probabilistic judge by default. The existing reference verifier closes
  teacher-name misattribution, not substantive claim-support risk.
- [ ] **System-prompt review timing:** decide whether review is required at the
  ingestion-ready benchmark or before private-beta expansion.

Quote hardening is already closed. Evidence:
`docs/audits/stabilization_track_1_2026-08-15.md`.

### F6 — Ingestion-ready verdict

**Status:** QUEUED after F4.

Close with a recorded PASS or HUMAN_REQUIRED verdict against this fixed gate:

- [ ] **Correctness:** served-answer invariants and ranked failure-mode controls
  hold; the accepted orphaned admin PDF endpoint exception is named explicitly.
- [ ] **Ingestion:** shared chokepoint, dry run, isolated-item proof, accounting,
  and reconciliation are operational.
- [ ] **Recoverability:** F2 is closed or Alex explicitly accepts the residual.
- [ ] **Operability:** dependencies reproduce and failures are diagnosable.
- [ ] **Records:** `PLAN.md`, `CLAUDE.md`, `ARCHITECTURE.md`, and
  `rhemata-status.md` agree in a separate docs-only close.

Historical custom-harness evidence is sufficient and requires no further work.
Passing F6 freezes foundation work as the default activity. Later engineering
must serve the named beta tracks in `docs/roadmap.md` or repair a demonstrated
regression promoted under the Blocker rule.

## What happens after F6

The product track (B1-B7) and corpus track (A1-A6) begin concurrently under
their contracts in `docs/roadmap.md`. Migration 088 remains a separately
approved production database-write session inside the applicable phase.

The launch candidate exists only when the product release candidate, corpus
acceptance gate, current F6 recheck, live census, representative answer/evidence
review, and Alex's deployment/audience approval all pass. This later work is
Scheduled, not authorized by the current blocker queue.

## Session close

Record only:

1. whether the original outcome and acceptance criteria passed;
2. discoveries classified as Blocker, Scheduled, Triggered, or Parked;
3. any scope change Alex explicitly approved; and
4. the next single blocker.

Track four process measures: original outcome completed, unplanned
investigations started, findings promoted to Blocker, and active blocker count.
Healthy target: completed, zero, rare, and one.
