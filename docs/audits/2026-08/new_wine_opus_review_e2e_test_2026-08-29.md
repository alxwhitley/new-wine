# New Wine A2 — Opus 5 Article-Completeness Review, Live End-to-End Test, 2026-08-29

**Status: real, budget-approved live spend. Alex approved a $3.00 ceiling for
this specific test**, following a zero-cost dry-run request-size estimate
(`new_wine_opus_review_cost_estimate_2026-08-29.py`: ~81,551 input tokens
estimated, $0.41-$2.01 projected depending on output length). **Actual spend:
$0.6288 of $3.00** ($0.0140 dummy mechanics + $0.6148 real review call).
$2.3712 unspent. No database write. No file promotion.

This is the stage the 2026-08-29 segmentation test explicitly did not attempt
(see `docs/audits/2026-08/new_wine_opus_segmentation_e2e_test_2026-08-29.md`,
"What this does not prove" — article review requires the same model per the
lineage check, cost unknown at the time). It is also the first live exercise
of that same session's `segmentation_model`/`reviewer_model` provenance fix
(commit `9a9ecf0`) on a real Opus-produced manifest.

## What actually ran

`local/2026-08/new_wine_opus_review_e2e_test_2026-08-29.py` — not a
modification to `scripts/magazine_review/articles.py`. `ARTICLE_MODEL` stays
`"openai/gpt-oss-120b"`.

1. **Zero-cost manifest reconstruction.** The real 10-article manifest Opus 5
   produced in the 2026-08-29 segmentation test
   (`new_wine_opus_e2e_segmentation_result_2026-08-29.json`) was replayed
   through the real, unmodified `articles.segment_articles()` via a client
   that echoes the saved result with no network call — so the manifest is a
   byte-accurate reconstruction, `segmentation_model` correctly reading
   `"claude-opus-5"` (proving the provenance fix works on this real data,
   not just the synthetic fixtures in `scripts/test_magazine_article_review.py`).
2. **Dummy mechanics test against the REAL review schema.** The segmentation
   test's schema never exercised `anyOf: [{type: string}, {type: null}]`
   (the review schema's `failure_reasons` nullable-string-per-field shape) —
   a genuinely new JSON Schema construct for Claude's converter, not yet
   proven to round-trip. Cost: $0.0140 (in=1,693, out=221). Round-tripped
   correctly.
3. **Real review call.** `effort: "medium"`, matching production's
   `REVIEW_REASONING`, `max_tokens=64000`, via the real, unmodified
   `articles.review_articles_against_issue()`.

**Deliberate, disclosed gate bypass, not a workaround of a bug:**
`_validate_manifest_lineage()`'s `manifest.segmentation_model != ARTICLE_MODEL`
check (the fix this same session added) is designed to reject ANY manifest
not produced by the exact configured `ARTICLE_MODEL` — by construction, this
makes it structurally impossible to test "Opus reviews its own Opus
segmentation" without bypassing this one field. The script stamps
`segmentation_model=ARTICLE_MODEL` via `dataclasses.replace()` solely to pass
this one gate, then restores the real value (`"claude-opus-5"`) before saving
any result. Every other gate — article_set_hash reconciliation, identity/
prompt-fingerprint binding, semantic verdict validation, issue-coverage
consistency — ran for real, unmodified.

## Result: REVIEW QUARANTINED THE ISSUE

```
status: quarantined
issue_coverage_complete: False
missing_articles: []
missing_substantive_spans: 2
quarantine_reasons: 17
verdict: False on 9 of 10 articles (only "Editorial" passed clean)
```

Real usage: `input_tokens=96,886, output_tokens=5,216`, cost `$0.6148`.
(The zero-cost estimate's ~81,551-token projection undercounted the real
input by ~19% — the `len(text)//3` heuristic is a rougher approximation than
its "conservative overestimate" framing suggested; output landed far below
segmentation's 53,125, consistent with `medium` vs `high` reasoning effort
and a much smaller response schema.)

**The dominant failure pattern is not noise — it is a real, substantive
disagreement between what segmentation produced and what review considers
correct, concentrated on exactly the hardest cases:**

- **Both interrupted articles (Health and Healing, The Apostle) are flagged
  as WRONGLY split.** Review's own words: "The single Derek Prince feature is
  broken into two separate article records at the '(Continued on page 6)'
  jump; the continuation ... is filed as a distinct article rather than
  joined to this one, so the jump-line transition is not reconstituted."
  Same complaint, independently, for The Apostle's split around the page-22
  conference sidebar. This is the exact opposite verdict from how the
  segmentation test's own audit doc characterized this behavior ("Health and
  Healing's interruption — split into two real spans... correctly") — that
  characterization was against the CURRENTLY SHIPPED schema's design (one
  flat `ArticleRecord` per span, interruptions necessarily represented as two
  sibling records), which review is now treating as a defect rather than the
  intended shape. Both stages are Opus 5; this is not a capability gap
  between models, it's the same model disagreeing with itself across two
  different roles on what "correct" segmentation of an interrupted article
  even means.
- **CORRECTED, same-day follow-up — both "missing substantive spans" are
  reviewer false positives, not segmentation gaps.** Independently checked
  against the real transcript and the real segmentation result: the page-4
  "Letters to the Editor" department (flagged span [7733:11573)) is fully
  covered, contiguous, zero gap, by 10 real `non_article_spans` at
  [7716:11590) — category `letters_to_editor`, each an accurately-described
  individual reader letter (spot-checked the first: a real letter signed
  "E.T., Florida," matching its stored reason verbatim). The boxed
  "TEACHING CONFERENCE COMES TO LOS ANGELES" item (flagged span
  [79636:80864)) is fully covered, contiguous, zero gap, by one
  `non_article_span` at the identical range — category `advertisement`,
  and the raw text confirms it genuinely is one: a paid conference (Bob
  Mumford/Don Basham/Derek Prince as speakers, $10/$20 registration, a
  mailing address), exactly satisfying the `advertisement` category's own
  bar. Both spans sit flush against their neighboring articles on both
  sides — zero gap either side, consistent with the original "zero gate
  failures" result. **Review's complaint appears to compare only against
  `manifest.articles`, not the full `articles + non_article_spans`
  partition the schema's coverage design actually uses** — it is flagging
  correctly-classified non-article content as "missing" rather than
  catching a real gap. This narrows the real, substantive part of this
  review's quarantine to the split-article and marker-placement complaints
  above; the "missing substantive spans" reason should not be weighted as
  evidence of an actual content gap in this issue.
- **Several page-marker-carried-past-the-true-end complaints** (Bible Study,
  The Call of Love, Keeping the Unity, New Wine Forum, Nature of Obedience) —
  a `=== PAGE N ===` marker landing a few sentences past where review
  believes the article actually ends. This is exactly the class of defect
  the free-check protocol's "jump-line detector" and "marker-exclusion"
  design work (`new_wine_free_checks_2026-08-29.md`) was aimed at — direct,
  new evidence that this defect class is real and recurring on this issue,
  independent of which model segments it.

## What this does and does not prove

**Proves:**
- The 2026-08-29 `segmentation_model`/`reviewer_model` provenance fix works
  correctly against real (not just fixture) data: the reconstructed manifest
  honestly carries `"claude-opus-5"`, and the lineage gate correctly refused
  to let review proceed without the disclosed bypass above.
- Claude's schema converter accepts the review schema's `anyOf`/`null`
  shape — a previously untested JSON Schema construct.
- Opus 5 CAN run the review stage end-to-end through the real production
  validation path at a real, now-measured cost ($0.61 for this issue, well
  under the worst-case $2.01 projection) — cost is not a blocker for further
  testing.

**Does not prove:**
- That this issue is actually ingestion-ready, or that Opus's review verdict
  is itself correct. Of the 17 quarantine reasons, 2 (the "missing
  substantive spans") are now independently confirmed FALSE POSITIVES (see
  the correction above); the split-article and marker-placement complaints
  remain unverified against the raw transcript in this session. Review being
  Opus 5 reviewing Opus 5's own output could mean either "a real,
  self-consistent quality bar the shipped gpt-oss pipeline never reached" or
  "Opus applying a stricter standard than the shipped schema is designed to
  satisfy" — this result does not distinguish between those, and the
  confirmed false positive on the coverage-style complaints is a reason for
  caution before trusting the rest of the review verdict at face value.
- Anything about gpt-oss-120b reviewing an Opus-segmented manifest, or Opus
  reviewing a gpt-oss-segmented manifest — this was a same-model-both-stages
  test only.
- That the "split interrupted articles into two records" shape is wrong —
  that is the CURRENTLY SHIPPED design (`author: str`, one `ArticleRecord`
  per span), and this session's earlier free-check work
  (`new_wine_free_checks_2026-08-29.md`) already found real, unresolved
  design tension around exactly this (the v1.4 jump-resolution algorithm,
  unimplemented). This result is a second, independent data point feeding
  that same open question, not a new one.
- Reliability at any particular rate — n=1 for the review stage specifically.

## What this adds to the open "next single item" list

`rhemata-status.md`'s three listed options (implement v1.4; test article
review with Opus; get counts from more transcripts) are no longer
independent — this result ties options 1 and 2 together directly: the
review stage's own complaints (interrupted-article splitting, marker
placement past the true end) are largely the same failure classes the v1.4
design (folio hatch, marker-exclusion, jump-resolution) was built to
address. Testing article review in isolation surfaced evidence relevant to
whether the shipped schema or the v1.4 redesign is the right target, not
just a review-stage cost/capability data point.

## Artifacts

- Scripts: `local/2026-08/new_wine_opus_review_cost_estimate_2026-08-29.py`
  (zero-cost estimate), `local/2026-08/new_wine_opus_review_e2e_test_2026-08-29.py`
  (live test)
- Raw result: `local/2026-08/new_wine_opus_e2e_review_result_2026-08-29.json`
- All gitignored under `local/` per existing convention; this document is
  the durable record.
