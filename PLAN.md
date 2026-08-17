# Rhemata — Private-Beta Blocker Plan

> This is the only active work queue. Later work lives in `docs/roadmap.md`;
> completed and superseded reasoning lives in `docs/plan-archive.md`.

**Goal:** begin controlled web-article ingestion quickly without compromising
propositions, quotes, generated answers, or recoverability.

**Current item:** **W1–W4 repository-only safety block.** The executable plan is
`docs/superpowers/plans/2026-08-17-web-article-beta-fast-path.md`.

## Governing boundary

- A new finding interrupts this queue only if it can plausibly cause theological
  error, teacher misrepresentation, data loss, a security/privacy breach, or
  failure of the core beta journey. Everything else is classified Scheduled,
  Triggered, or Parked in `docs/roadmap.md`.
- Audits and implementation tasks use named files, acceptance tests, and a stop
  condition. Adjacent findings are recorded; they do not expand the session.
- Repository-only work may run back to back. Production database writes,
  deployments, source-visibility changes, and quote-rail re-enablement are
  attended gates requiring Alex's explicit approval.
- Every write path follows dry run → one isolated hidden proof → reconciliation
  → explicit release → bounded batch. No general worker may claim an unrelated
  row during the isolated proof.

## Active blocker sequence

### W1–W4 — Safe web-article runway

**Status:** IN PROGRESS — repository-only, approximately 3–4 hours.

- [ ] Add a reversible quote-rail flag, default off, with answer-path regression
  coverage. This contains the systemic topic-label/retrieval defect without
  deleting or relabeling production quotes.
- [ ] Add an explicit live `--row-id` worker target so an attended proof cannot
  claim another cleared row.
- [ ] Define the first web-article contract: `web_page + single + declared`, an
  existing non-sentinel source, explicit clearance, licensed/unlicensed hidden
  staging, `source_kind=web_article`, and `citation_mode=citable`.
- [ ] Extend preview mode through metadata, chunks, embeddings, propositions,
  provenance, and structural quote proposals while proving zero database writes.
- [ ] Stop for code review and verification. Do not deploy, enqueue, ingest, or
  change production configuration in this block.

### W5–W6 — One quarantined article proof

**Status:** WAITING on W1–W4 and Alex's source/production approval.

- [ ] Alex selects the exact article, confirms teacher/source and clearance, and
  approves deploying quote containment.
- [ ] Run the full no-write preview and review every proposed proposition beside
  its source passage; proposals remain ineligible and quotes remain proposals.
- [ ] Execute exactly one row-pinned write into a hidden source; reconcile
  attempted/stored/skipped/errored plus document/chunk/proposition state.
- [ ] Prove rerun idempotency and a row-level rollback procedure before release.
- [ ] Promote only propositions that pass the canonical eligibility checks;
  keep the article hidden until answer-integrity review passes.

### W7–W8 — Quote and answer integrity

**Status:** QUEUED after the quarantined proof; quote rail stays off.

- [ ] Replace inherited document-first-tag matching with quote/passage relevance,
  deterministic tie-breaking, and idempotent quote creation.
- [ ] Test the three demonstrated false positives, true positives, same-label and
  same-teacher negatives, ties, and the chosen teacher-scope rule.
- [ ] Audit approved and pending quotes as untrusted legacy data. Re-enable only
  a small reviewed subset after Alex approves the label and teacher-scope policy.
- [ ] Prove a baptism regression, an article-supported answer, an honest no-support
  answer, exact retrieved chunk/citation IDs, no bad quote IDs, and a bounded
  teacher-card regression before making the article visible.

### W9 — Recoverability and first small batch

**Status:** QUEUED after W8.

- [ ] Record authoritative Supabase backup/PITR retention, restore granularity,
  owner, RTO/RPO, and exclusions; prove the safest available restore scope or
  record Alex's explicit acceptance.
- [ ] Run one named, costed, resumable web-article batch with immutable inputs,
  logs, hard reconciliation, quality sampling, and an explicit release decision.

## Explicitly outside this finish line

- **Triggered:** New Wine PDF ingestion resumes only when a candidate OCR model
  wins a blind side-by-side test on named severe-failure pages without degrading
  good control pages, and Alex accepts the result.
- **Scheduled:** broad visible-default policy, general system-prompt review,
  broad claim-support refinement, product B1–B7, and remaining corpus A1–A6.
- Migration 088 is already applied. Its isolated processor proof completed on
  queue row `8e8f23e0-7dc6-4057-aa4d-c07f1b607c99`; never reapply it.

## Session close

Record only the original outcome, its acceptance result, classified discoveries,
Alex-approved scope changes, and the next single item. Track: original outcome
completed, unplanned investigations started, findings promoted to Blocker, and
active blocker count. Healthy target: completed, zero, rare, and one.
