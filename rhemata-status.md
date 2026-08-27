# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-27. **PLAN.md has zero active blockers.** This session
fixed a UI regression, committed a stray migration, and did substantial New
Wine A2 pipeline work (below) — see docs/roadmap.md's A2 entry for the
roadmap-level pointer.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Chat input focus ring — DONE, live (commit `a26d1f6`).** Removed the
mouse-focus ring on the prompt capsule (a prior session's uncommitted fix);
verified live in the running dev server before pushing.

**Migration 091 + B6-F1 routing-flag scripts — committed (commit `2e6bde1`).**
Already live in production from a prior session; only the repo record was
missing. No new DB write — brings the repo in sync with already-applied state.

**New Wine A2 — substantial progress, Issue 02-1973 still not cleared
end-to-end.** Root-caused and fixed the original defect (segmentation
silently stopped 54% through the 32-page issue at low reasoning, no error),
then found and fixed five further defects through live validation the same
day, each unit-tested before moving on (9 commits, `37e2746`..`683b973`,
213/214 tests passing — the one failure is a pre-existing, unrelated
PyMuPDF/venv environment quirk, confirmed via `git stash` to predate this
session):
- Deterministic full-coverage check (`article_coverage_incomplete`) — the
  original fix.
- `non_article_spans`: non-article content now has an explicit home instead
  of becoming a silent gap.
- Three rounds of size/fraction caps, each closing a gaming pattern the
  model found live in direct response to the previous fix: dumping real
  articles into oversized `other_non_article` spans, then oversized NAMED
  categories, then spread across many spans under the per-span cap
  (closed with an aggregate 40%-of-issue cap) — then, most seriously, one
  giant article covering the whole issue, which slipped past the semantic
  reviewer too (`_MAX_ARTICLE_CHARS` closes this).
- Reasoning raised low→medium→high; instructions strengthened to require
  fine-grained decomposition, not just full coverage.
- `letters_to_editor` category added + `other_non_article` cap widened
  2,000→2,500, found via a direct diagnostic call (bypassing the CLI,
  reusing the cached OCR transcript) that showed an otherwise-correct
  11-article segmentation being rejected only for two legitimate spans with
  nowhere good to go.
- Per-page OCR result cache (`local/magazine_review_ocr_page_cache.json`,
  gitignored) — pure efficiency, no safety-rule change. All 32 pages of
  this issue are now cached; a retry costs $0 in OCR.

**21 live attempts run today** against the real Issue 02-1973 PDF. 14
reached real segmentation output; the rest failed earlier on OCR content,
provider rate limits, empty/refused model output, or connection errors —
infra noise, not a code gap. Confirmed cost from decision files that
recorded it: **$0.87** — a known floor, not the true total: the pipeline
doesn't record cost from a call that raised after being billed, so real
spend is likely closer to $1.2–1.5. Of the $3 validation headroom Alex set
this session, this is well within budget.

**Not yet resolved:** `non_article_span_implausibly_large` is still firing
on most recent attempts (6 of the last 8 that reached segmentation, v14
onward) even after the `letters_to_editor`/cap-widening fix. Unlike the
`article_implausibly_long` recurrence earlier (fully resolved by the
reasoning bump + instruction fix), this one hasn't yet had its own
diagnostic pass post-fix — v20/v21's exact offending spans are unknown (no
manifest persists when `segment_articles()` rejects). Next session should
run the same diagnostic method used for the `letters_to_editor` fix (a
standalone segmentation-only call reusing the cached transcript, no CLI, no
new OCR cost — see the script pattern in commit `683b973`'s message) before
assuming these are all false positives worth loosening a cap for; some may
be genuine catches.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** see Current state above — Issue 02-1973 isn't through
  the article gate yet. Production database ingest for this or any New
  Wine issue remains a separate, attended, explicitly approved operation
  regardless of how clean a review run gets.
- **Triggered**: JWKS unknown-`kid` rate limit — residual belongs at the
  edge.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual, but read any `scripts/test_*.py` before batch-running it);
  dependency/hardening follow-up (starlette+fastapi, pdfplumber+pdfminer,
  CSP, deferred Next.js major bump); staging source name still reads
  `"Vlad Savchuk (web staging)"`; Bonnke URL suspect; no retention/TTL logic
  for user data; `rhemata_readonly_analysis` has no grant on PII/user
  tables; full cascading account deletion still unbuilt; New Wine review
  pipeline's cost-reporting gap (noted above) is a real observability nit,
  not fixed this session.

---

## Next single item

**No active blocker.** New Wine A2 is the live thread: diagnose the
`non_article_span_implausibly_large` recurrence directly (cheap — OCR is
fully cached) before running more blind CLI retries. Real database ingest
for this or any New Wine issue remains a separate, attended, explicitly
approved operation regardless of how clean a review run gets.
