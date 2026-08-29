# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-29. **PLAN.md has zero active blockers.** This
session fixed a real provenance bug (commit `9a9ecf0`), ran a second live
Opus 5 test (article review, not segmentation), and found part of that
review's own "missing content" complaint was a false positive. New Wine A2
is still not ingestion-ready — Alex is deliberately pausing this track.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**New Wine A2 remains NOT ingestion-ready. Alex is deliberately holding this
track — no next step selected.** Earlier same-day work (two more refuted
redesigns, a zero-cost Grok-collaborative design pressure-test, a first live
Opus 5 segmentation test that passed real gates) is recorded in
`docs/audits/2026-08/new_wine_free_checks_2026-08-29.md` and
`docs/audits/2026-08/new_wine_opus_segmentation_e2e_test_2026-08-29.md` — not
restated here. This session's own work:

1. **Fixed: `segmentation_model`/`reviewer_model` false provenance stamp**
   (commit `9a9ecf0`). `segment_articles()`/`review_articles_against_issue()`
   hardcoded `ARTICLE_MODEL` regardless of which client actually ran the
   call — found live in the segmentation test above.
   `StructuredOutputClient` now requires a `.model` attribute; both stages
   stamp from `client.model`. Mutation-proven: 3 new tests in
   `test_magazine_article_review.py`, one specifically proving the existing
   lineage check was previously trivially-passing. Full detail: CLAUDE.md
   Landmines.
2. **Live-tested: Opus 5 reviewing its own Opus 5 segmentation of Issue
   02-1973 QUARANTINED the issue.** $0.6288 of an Alex-approved $3.00
   ceiling spent (a zero-cost dry-run request-size estimate ran first). 9 of
   10 articles failed verdict. Real, substantive complaints, NOT resolved
   this session: both interrupted articles (Health and Healing, The
   Apostle) flagged as *wrongly split* — contradicts how the earlier
   segmentation test's audit doc characterized that same split as correct;
   several page-marker-past-true-end complaints, the exact defect class the
   free-check design work targeted.
3. **Independently verified: 2 of the review's "missing substantive span"
   complaints are FALSE POSITIVES**, not real content gaps. Both flagged
   spans (a Letters-to-the-Editor department, a conference ad) are fully
   present, correctly classified as `non_article_spans`, zero coverage gap
   either side. The reviewer appears to compare only against `articles`,
   not the full `articles + non_article_spans` partition. Recorded as a
   standing CLAUDE.md Landmine — do not trust this complaint type without
   checking `non_article_spans` first.
4. **Real ingestion is not possible yet — three gates, not one.** (a)
   Article review has never legitimately passed for this issue by any
   model — every real attempt quarantined, plus one apparent "pass" that
   was a now-closed bug (a single fake article spanning the whole issue).
   (b) Opus isn't wired into the real pipeline
   (`review_magazine_issue.py` still hardcodes gpt-oss-120b); both Opus
   tests used one-off bypass scripts, not the real orchestration. (c)
   Proposition extraction/review has never been attempted for this issue —
   unreachable until article review passes. Even clearing all three, a
   real DB write remains a separate, attended, explicitly-approved step by
   standing project rule.

Full trail: `docs/audits/2026-08/new_wine_opus_review_e2e_test_2026-08-29.md`.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Live account-deletion verification** — genuinely blocked, needs Alex to
  create a real disposable test account first (Session Routing hard rule).
- **Analytics production smoke sequence** — deferred, Alex's explicit
  decision, not run.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual); staging source name still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `rhemata_readonly_analysis` has no grant
  on PII/user tables.

---

## Next single item

**New Wine A2 — Alex is deliberately holding this track; no next step
selected.** Real options on the table when resumed, none pre-selected:
- Verify the two still-unchecked review-complaint classes (split-article
  disagreement, marker-placement) against the raw transcript, the same way
  the missing-spans complaint was checked, before weighing either as
  evidence for the v1.4 redesign question.
- Implement the v1.4 design (folio hatch, marker-exclusion, resume
  placement) in `articles.py` for real — still verified on paper/
  free-checks only.
- Wire an alternate-model path into the real pipeline if Opus is to be
  seriously evaluated, rather than continuing via one-off bypass scripts.
- Get article/jump counts from ≥2 more transcripts (still zero beyond
  Issue 02-1973) before any corpus-wide cost decision.

**Do NOT spend further live-call budget on any of these without a fresh,
named ceiling** — the $3 approved 2026-08-29 for article review is spent
($0.63 of it) and does not carry forward, same as the earlier segmentation
ceiling.
