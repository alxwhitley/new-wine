# Rhemata — Private-Beta Blocker Plan

> This is the only active work queue. Later work lives in `docs/roadmap.md`;
> completed and superseded reasoning lives in `docs/plan-archive.md`.

**Goal:** begin controlled web-article ingestion quickly without compromising
propositions, quotes, generated answers, or recoverability.

**Current item:** **W5–W6 — one quarantined article proof.** Attended,
human/production-only gate; the executable plan is
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

**Status:** DONE — merged to `main` 2026-08-18 (PR #1
`harness/quote-containment-and-staging`, closing commit `a8a7731`, merge
`923f1ed`). Quote-rail flag (default off), single-row `--row-id` claiming, the
staged web-article contract, and the zero-write preview all verified live
against the merged code. Full detail: CLAUDE.md Invariant 16 + the
quote-containment Landmines entry.

### W5–W6 — One quarantined article proof

**Status:** WAITING on Alex's source/production approval (W1–W4 prerequisite
is satisfied).

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

**Status:** W7's first bullet DONE — commit `82ec0f5`, 2026-08-18. Relevance is
now scored from each quote's own `quote_text` (not the inherited document
topic tag), tie-breaking is a strict deterministic `(score, id)` order, and
`create_and_approve_quote()` is idempotent on a repeat call. Covered by
`scripts/test_quote_passage_relevance.py`, including live evidence against
real corpus content (the old scoring's exact-tie defect reproduced, then
gone; real false positives now rejected, a real true positive still
selected). Quote rail stays off (`QUOTE_SELECTION_ENABLED` untouched).
**New, unverified finding (2026-08-18, `/code-review` run interrupted before
its adversarial-verify step):** the idempotency check is a non-atomic
SELECT-then-INSERT with no DB uniqueness constraint or lock backing it — a
genuine concurrent call could still duplicate a row. PLAUSIBLE, not
CONFIRMED; a future session should re-run verification and, if it holds,
harden it (advisory lock or a real unique index) before this path sees any
concurrent traffic.

- [ ] "Chosen teacher-scope rule" sub-item (plan doc Task 9 point 5): Alex
  still needs to choose the visible quote label/scope policy — a source/work
  title vs. a semantic topic tag. Everything else in the second bullet
  (false positives, true positives, same-label/same-teacher negatives, ties)
  is covered by the same test file above.
- [ ] Audit approved and pending quotes as untrusted legacy data. Re-enable only
  a small reviewed subset after Alex approves the label and teacher-scope policy.
- [ ] Prove a baptism regression, an article-supported answer, an honest no-support
  answer, exact retrieved chunk/citation IDs, no bad quote IDs, and a bounded
  teacher-card regression before making the article visible.

### Quote quality — no quality bar exists anywhere in the quote pipeline

**Status:** OPEN, not scoped. Required before the quote rail is re-enabled.

Finding, 2026-08-19: Alex read a 20-quote random sample
(docs/audits/quote_quality_sample_2026-08-19.md) and assessed roughly 20%
as quotes worth serving. The rest are grammatically complete but
substantively weak — mid-argument connective sentences, or sentences
referencing context the reader cannot see ("Verse 17, this is a wonderful
verse").

Root cause is by design, not a defect: when per-quote human approval was
removed 2026-08-08 (Settled decision #18), every replacement check was
deterministic — exact-substring match, speaker confirmation,
sentence-boundary/completeness, commentary exclusion, document clearance,
per-work cap. None of them assess whether a quote is worth reading.
Nothing in the pipeline ever has.

Required before the quote rail is re-enabled: a process for producing
quality quotes. Not scoped yet. Deliberately not solved this session —
Alex's explicit call to log it rather than chase it.

Two open sub-questions, both unresolved and not investigated:
(a) What selected the candidate spans in the first place — whether an LLM
proposed them (permitted under Settled decision #16) or a mechanical rule
did. This changes what the fix looks like and has not been checked.
(b) The boundary-proximity/sentence-completeness check (Settled decision
#18) did not catch a real failure in the sample: quote 7 (Derek Prince,
"The New Testament Evangelist") runs past the end of its own point and
swallows the opening sentence of the next section ("We come to the
seventh unity, one God and Father."). One confirmed case, cause unknown,
not investigated.

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
