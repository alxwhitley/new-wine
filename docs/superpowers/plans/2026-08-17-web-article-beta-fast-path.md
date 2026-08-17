# Web-Article Beta Fast Path — Implementation Plan

**Objective:** establish a controlled path from one approved web article to
reviewed propositions and trustworthy answers, while containing the current
quote-relevance defect and preventing accidental broad ingestion.

**Operating rule:** complete Tasks 1–4 back to back as one repository-only block
(about 3–4 hours). Stop at the checkpoint. Tasks 5–10 cross production or human
judgment gates and must be attended.

## Verified starting state

- Migration 088 is already applied. Queue row
  `8e8f23e0-7dc6-4057-aa4d-c07f1b607c99` completed an isolated processor proof
  into document `35b53381-2153-4936-a97b-641a20e29205` (two chunks, zero
  propositions because the source is public domain). This was not a deployed
  worker-service proof; do not reapply the migration.
- The web path can fetch `web_page + single + declared`, but its dry run stops
  before metadata, embeddings, and proposition extraction. Generic metadata
  currently classifies an article as `unknown` / `silent_context`.
- Quote selection embeds the inherited `quotes.topic`, not the quote passage.
  Nearly the whole Derek Prince quote corpus inherits a document tag, so the
  baptism screenshot is a systemic defect rather than a three-row anomaly.
- New propositions default to `eligible=false`; proposition extraction skips
  public-domain/owned sources. The first article must therefore use a cleared,
  hidden licensed/unlicensed staging source and an explicit eligibility step.

## Task 1 — Contain the quote rail

**Files:** `backend/app/services/quotes.py`,
`backend/app/services/async_answers/producer.py`, and new
`scripts/test_quote_selection_gate.py`.

1. Add `quote_selection_enabled(env: Mapping[str, str] = os.environ) -> bool`.
2. Default to disabled; only the exact documented true value enables selection.
3. Make the producer skip selection and emit no `quote_ids` when disabled. Keep
   stored rows untouched and preserve the selector behind the flag for repair.
4. Test absent/false/true values, prove disabled never calls the selector, and
   test answer serialization with no quote IDs.

**Stop:** default configuration cannot attach a quote; enabling preserves current
behavior. No deployment or environment change.

## Task 2 — Pin an isolated live worker run to one row

**Files:** `scripts/source_ingest_worker.py` and
`scripts/test_source_ingest_worker.py`.

1. Add `--row-id UUID`, valid only with `--once`; reject other combinations.
2. Thread `only_row_id` into `Worker.tick()` and the existing claim primitive.
3. A missing, uncleared, non-ready, or leased target returns no-claim and never
   falls through to another ready row.
4. Test two ready rows, malformed UUID, no match, uncleared target, and retries.

**Stop:** an attended proof has a mechanically enforced single-row blast radius.

## Task 3 — Define the staged web-article contract

**Files:** `scripts/source_ingest_queue/processor.py`,
`scripts/test_source_ingest_processor.py`, and a narrow source-resolution helper
only if necessary. Do not weaken canonical serving gates.

1. Accept only `web_page + single + declared`. Reject collections, inferred
   attribution, sentinels, and undecided retention.
2. Resolve an existing source and require explicit queue clearance.
3. Require a hidden source with license `licensed` or `unlicensed`; never create
   sources, aliases, permissions, or visibility automatically.
4. Set `source_kind=web_article` and `citation_mode=citable` explicitly without
   changing generic metadata behavior globally.
5. Preserve fetch/SSRF limits, immutable URL/hash/byte evidence, atomic writing,
   and exact accounting. Test every refusal boundary.

**Stop:** an article can be prepared for hidden staging without becoming
retrievable or broadening another pipeline.

## Task 4 — Build a full-compute, zero-write preview

**Files:** new `scripts/source_ingest_queue/preview.py`, new
`scripts/test_source_ingest_preview.py`, processor changes, and `.gitignore` if
the review directory is not already covered.

1. Separate computation from persistence so preview continues through metadata,
   chunks, embeddings, propositions, and quote-span proposals without writing.
2. Emit immutable JSON with row ID, URL, hash/bytes, source/teacher/license,
   metadata, chunks, propositions, prompt/model/fingerprint, eligibility=false,
   cost/token data when available, and quote proposals with surrounding passage.
3. Label quote spans `proposal`; never call approval or write quote rows.
4. Inject persistence/model boundaries. A DB double must fail on writes while the
   complete preview still succeeds.
5. Keep report identity deterministic for the same captured content.

**Run:** targeted preview, processor, worker, quote-gate, and answer-producer
tests, then one coherent verification pass.

**Repository-only checkpoint:** review diff and prove no production DB,
deployment, queue, visibility, or configuration changed. Commit code separately
from records. Stop and return to Alex.

## Task 5 — Human and production gate

Alex approves the exact URL, source/teacher, license basis, hidden staging,
quote-containment deployment, and the quote teacher scope. Recommendation:
quotes must belong to teachers actually represented/cited in the final answer,
not every teacher considered during retrieval. Verify a production answer has no
quote IDs before enqueueing anything.

## Task 6 — Preview and review the first article

Create or clear one row, capture once, and run the no-write preview from that
immutable body. Review every proposition beside its supporting passage for
meaning, attribution, scripture grounding, and voice. Review quote boundaries
separately and approve none. Reconcile counts, provenance, cost, and metadata.
Alex either accepts the preview or quarantines the article.

## Task 7 — One hidden, row-pinned write

Run exactly `--row-id`; reconcile worker accounting with fresh document, chunk,
proposition, and queue queries. Confirm all propositions remain ineligible. Prove
rerun idempotency and a scoped rollback procedure. Any mismatch or unexpected
retrievability quarantines the row and stops.

## Task 8 — Eligibility and answer release

Run canonical eligibility only for the new document, review passing/failing
propositions side by side, and promote only passing IDs. Test an article-supported
question with the exact retrieved chunk/citation, an honest no-support question,
the baptism regression, and a bounded teacher-card regression. Quotes stay off.
Only then may Alex approve source visibility.

## Task 9 — Repair quote relevance while disabled

1. Treat legacy `quotes.topic` as an untrusted display hint, not relevance proof;
   rank quote text and its supporting passage against the question.
2. Add deterministic ties and idempotent create/approve behavior.
3. Cover the three screenshot quote IDs, true positives, same-label and
   same-teacher negatives, considered-but-not-final teachers, and embedding ties.
4. Audit approved and pending rows, but do not make cleaning every legacy row a
   launch blocker. Re-enable a small reviewed subset first and retain the switch.
5. Alex chooses the visible label. A source/work title is safer than a semantic
   tag that falsely implies the quote directly answers the question.

## Task 10 — Recoverability and a bounded batch

Before multiple articles, establish authoritative backup/PITR and the safest
restore proof. Freeze a named manifest with URLs, hashes, clearance, expected
cost/counts, and rollback. Run a small resumable batch, reconcile every terminal
state, sample propositions/citations/answers, and explicitly accept or quarantine.

## Triggered and scheduled

- New Wine stays paused until an OCR candidate wins a blind benchmark on named
  severe-failure pages without degrading good controls, then Alex accepts it.
- Broad visible-default policy, general prompt refinement, broad claim-support
  work, and foundation audits are Scheduled. Promote only with direct evidence
  that they meet the Beta Critical Path interruption rule.
