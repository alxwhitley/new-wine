# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-27. **PLAN.md has zero active blockers.** New Wine A2
is the live critical-path thread, still open.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**New Wine A2 — root cause of the recurring `foreign_article_title_in_span`
failure diagnosed and partially fixed, commit `d5420e3`; Issue 02-1973 still
hasn't cleared the article gate end-to-end.** 13 live Groq calls this
session (11 full-CLI attempts, 2 segmentation-only diagnostics). Pre-fix: 6
real (non-infra) full-CLI attempts, 0 clean passes — 4 hit
`foreign_article_title_in_span`, 2 hit `article_implausibly_long`. Diagnosed
via a segmentation-only call plus direct transcript/table-of-contents
inspection: the model was drawing "The Apostle - God's Master Builder"'s end
boundary right after a bare page marker (page 23) and labeling the
continuation "Keeping the Unity" — but that text is mid-sentence apostleship
content running to the same article's own page-23 footer; the real "Keeping
the Unity" heading (confirmed against the issue's own table of contents,
"KEEPING THE UNITY .24") sits ~5,800 chars later, shifting every downstream
title by one slot. Fixed by telling `SEGMENTATION_INSTRUCTIONS` not to
anchor a boundary on a bare page marker and not to mistake an in-article
all-caps subheading for a new article's title (`d5420e3`,
`scripts/magazine_review/articles.py`). Validated: 86 existing unit tests
still pass; 4 further live checks post-fix — 1 clean segmentation pass with
the correct 3-way split (Apostle / Keeping the Unity / Forum), 1 recurrence
of the same defect, 2 hit unrelated pre-existing guardrails
(`coverage_spans_overlap`, `non_article_span_implausibly_large`) instead.
Target-defect recurrence dropped (1/4 vs 4/6 pre-fix) but is not eliminated
— confirms CLAUDE.md's standing conclusion that this is model variance at
"high" segmentation reasoning, not one deterministic gap. No database write
occurred. Full detail: CLAUDE.md's New Wine landmine entry.

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
- **Scheduled A2:** two remaining guardrails still fire on live attempts
  against Issue 02-1973 — `coverage_spans_overlap` (page-marker spans
  double-booked inside an article's own continuous span) and
  `non_article_span_implausibly_large` (recurrence, cause not yet
  re-diagnosed post-fix). Next: same segmentation-only diagnostic method
  used this session (cheap, no CLI/OCR cost) against whichever of these
  recurs most. Production database ingest for this or any New Wine issue
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
diagnose the next-most-common remaining guardrail
(`non_article_span_implausibly_large` or `coverage_spans_overlap`) the same
way this session closed the title-bleed gap — a segmentation-only
diagnostic call against the cached transcript, direct transcript
inspection, a targeted instruction addition, live-validate before
committing. Real database ingest for this or any New Wine issue remains a
separate, attended, explicitly approved operation regardless of how clean a
review run gets.

Separately, not competing for the critical-path slot: Alex has a
repo-complete, verified search-analytics dashboard waiting for a merge/
rollout decision whenever there's time to review it.
