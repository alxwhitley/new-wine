# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-27/28. **PLAN.md has zero active blockers.** New Wine
A2 is the live critical-path thread, still open.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**New Wine A2 — two distinct, live-validated segmentation fixes landed this
session (`d5420e3`, `4bad5b5`); Issue 02-1973 still hasn't cleared the
article gate end-to-end.** ~20 live Groq calls total across both fixes
(full-CLI attempts + cheap segmentation-only diagnostics, same method both
times: reproduce via a segmentation-only call against the cached transcript,
inspect the raw spans and actual transcript text directly, ship a targeted
`SEGMENTATION_INSTRUCTIONS` addition, live-validate, then run the full CLI).

1. **`d5420e3`** — the model was anchoring an article boundary on a bare
   page marker (page 23) rather than verifying the content after it was
   genuinely a new article's opening, so it mislabeled "The Apostle - God's
   Master Builder"'s own continuing content as "Keeping the Unity," shifting
   every downstream title by one slot. Confirmed against the issue's own
   table of contents ("KEEPING THE UNITY .24"). Post-fix: target-defect
   recurrence dropped from 4/6 to 1/4 real live attempts — reduced, not
   eliminated.
2. **`4bad5b5`** — the model correctly recognized the "New Wine Forum"
   reader Q&A column's opening, then mislabeled its own continuing content
   (16,788 chars) as three separate "advertisement" spans, each just over
   the 5,000-char named-category cap. Direct text inspection found zero
   commercial language in any of it — genuine column continuation
   (Basham/Prince dialogue on "slain in the Spirit"), not real ads. Post-fix:
   2 of 2 real live checks show zero fake-advertisement mislabeling; one
   correctly unified the whole column into a single 22,562-char span
   matching the ToC exactly ("NEW WINE FORUM .26").

Both fixes: 86 existing unit tests pass, no regressions. 4 further live
full-CLI attempts after both fixes still failed on other, already-documented
variance (`article_implausibly_long` x2, `non_article_span_implausibly_large`
x2 — a large non-article dump swallowing part of "The Apostle," unrelated to
either fix). One full-CLI attempt was user-interrupted mid-run (no error, no
partial write). A stretch of ~5 consecutive Cloudflare 524 timeouts from
Groq's own proxy occurred mid-session; checked Groq's public status page
(no active incident reported) and concluded it's call-latency variance
against the 120s proxy timeout at "high" segmentation reasoning (which can
generate 50k+ output tokens), not an outage — retries after brief backoff
consistently recovered. No database write occurred at any point this
session. Full detail: CLAUDE.md's New Wine landmine entry.

**Search analytics / corpus-gap dashboard — still repo-complete, locally
verified, UNMERGED, unchanged this session (docs/roadmap.md Horizon item
4).** Worktree `search-analytics-corpus-gap`, migration 093 written but not
applied. Needs Alex's review decision before anything further — see prior
session's entry (git history) for full detail.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Waiting on Alex:** search-analytics dashboard is built and verified but
  unmerged — needs a review decision, not more building.
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** the remaining recurring failure is a large non-article
  dump absorbing part of "The Apostle" article (`non_article_span_implausibly_large`),
  plus continued `article_implausibly_long`/title-bleed variance — none
  re-diagnosed with the same direct-inspection method yet (this session ran
  out of budget for it after landing the two confirmed fixes). Next: same
  method — a segmentation-only diagnostic call, inspect the actual raw spans
  and transcript text at the failure point, targeted instruction fix,
  live-validate. Production database ingest for this or any New Wine issue
  remains a separate, attended, explicitly approved operation regardless of
  how clean a review run gets.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual, but read any `scripts/test_*.py` before batch-running it);
  dependency/hardening follow-up (starlette+fastapi, pdfplumber+pdfminer,
  CSP, deferred Next.js major bump); staging source name still reads
  `"Vlad Savchuk (web staging)"`; Bonnke URL suspect; no retention/TTL logic
  for user data; `rhemata_readonly_analysis` has no grant on PII/user
  tables; full cascading account deletion still unbuilt.

---

## Next single item

**No active blocker.** New Wine A2 remains the live critical-path thread:
diagnose the large-non-article-dump recurrence
(`non_article_span_implausibly_large`) the same way this session closed the
two other gaps — a segmentation-only diagnostic call against the cached
transcript, direct inspection of the actual raw spans/text at the failure
point, a targeted instruction addition, live-validate before committing.
Real database ingest for this or any New Wine issue remains a separate,
attended, explicitly approved operation regardless of how clean a review run
gets.

Separately, not competing for the critical-path slot: Alex has a
repo-complete, verified search-analytics dashboard waiting for a merge/
rollout decision whenever there's time to review it.
