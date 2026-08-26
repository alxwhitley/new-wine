# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-25 (New Wine Issue 02-1973 paid no-write review;
terminal artifacts validated locally, no deployment or database write).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md` remains at **0 active blockers**. This session completed the
scheduled A2 New Wine no-write benchmark; no production deploy, database
write, or source-file move occurred.

**Issue 02-1973 terminal result: quarantined.** The accepted OCR split used
Gemini `gemini-3.7-flash` for initial OCR and `gemini-3.6-flash` for page
review plus at most one repair. All 32 pages passed; page 15 required the
single repair for a reading-order error. Groq `openai/gpt-oss-120b` then
produced 17 lineage-bound article candidates whose text and source pages
were derived locally from verified spans.

Fresh whole-issue article review blocked the issue before propositions. It
found the omitted `THE APOSTLE—GOD'S MASTER BUILDER` article and missing
continuations in two Health and Healing candidates. Reconciliation:
32 pages, 17 reviewed article candidates, 0 propositions, 0 writes. The
validated artifacts remain local-only and intentionally untracked under
`docs/audits/2026-08/new_wine_issue_02_1973_review_2026-08-25_retry_13/`
because the Git remote is public; OCR/article/decision envelope hashes and
lineage all revalidated. Measured
terminal-artifact cost was $0.26839185 including the reused OCR manifest;
the conservative cumulative bound across diagnostic attempts was
$1.08638205, below Alex's $1.25 ceiling.

Provider hardening and cost reductions are committed through `b18c6ca`:
bounded diagnostics, constrained Gemini thinking, sufficient structured
output envelopes, zero hidden retries, exact transcript-derived article
text/page lineage, safe filenames, and Groq-strict review schemas.

---

## Findings surfaced, not yet acted on

- **Scheduled A2:** correct the three article-coverage findings locally and
  rerun the no-write article/proposition gates. The present quarantine is
  the desired safety result, not authorization for ingestion.
- The article review's two `missing_substantive_spans` point at page markers
  immediately before the omitted continuations; the failed article records
  independently identify the missing page content. Improve span precision
  only if needed during the scheduled correction; it does not weaken the
  current quarantine.

---

## Next single item

Review the quarantined Issue 02-1973 article boundaries, correct the omitted
Derek Prince article and two continuations, then rerun the local no-write
article/proposition gates. Database-write approval remains a separate later
decision. Session measures: original outcome completed; unplanned
investigations 0; findings promoted to Blocker 0; active blockers 0.
