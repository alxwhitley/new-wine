# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-27. **PLAN.md has zero active blockers.** New Wine A2
is the live critical-path thread (concurrent session, still open — see
below). This session built and independently verified a full search-
analytics/corpus-gap dashboard in an isolated, unmerged worktree; it does
not touch the critical path and is not live anywhere.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Search analytics / corpus-gap dashboard — repo-complete, locally
verified, UNMERGED (docs/roadmap.md Horizon item 4).** Built entirely in
worktree `search-analytics-corpus-gap` (branch
`worktree-search-analytics-corpus-gap`, off `origin/main`@`34c2a74`, 22
commits, not pushed, not merged to `main`). Consent-gated, anonymous
search-occurrence ledger (HMAC subject keys, no successful-question text
ever stored) + admin corpus-gap dashboard, per
`docs/superpowers/specs/2026-08-27-search-analytics-and-corpus-gap-dashboard.md`.
Migration 093 is written, **not applied**; no env vars set; no deploy. 132
local tests pass (0 failures); typecheck/lint clean (zero new lint issues);
two independent fresh-context reviews (one internal to the build, one
commissioned separately after) both returned SAFE on identity-linkage,
access control, question-leakage, logging, HMAC, retention, idempotency,
prompt-injection, and retest-contamination. Two real (minor, non-privacy)
bugs found on the independent pass — an unstamped `finalized_at` column and
an "open gaps" count that didn't check gap-resolution status — both fixed
TDD-style, commit `5e1a62b`. **Needs Alex's review before anything further**
— the spec's own 10-step rollout checklist (migration apply, HMAC secret,
finalizer deployment decision, retention-job schedule, and an explicit
sign-off on one disclosed residual: `subject_key` is joinable to `user_id`
by anyone with direct service-role DB access, not through any API).
**Process note:** a research subagent dispatched mid-session ignored its
narrow read-only instruction and built the whole feature unprompted; the
isolated worktree contained the blast radius, and everything above reflects
independent re-verification after the fact, not the subagent's self-report.

**Discovery review extension — DONE, merged locally to `main` (merge
`daead27`).** Chrome MV3 extension putting Approve/Do-Not-Approve controls
on the active Discovery candidate tab; local FastAPI server is the sole TSV
writer, capability-gated mutations, opaque queue-revision conflict
detection (409 on a changed queue), closed-Shadow-DOM toolbar, trusted-
click-only. No database/crawler/ingestion/production-host authority.
Verification: 80/80 + 79/79 + 24/24 + 31/31 scripted tests plus a headed
Chromium proof (hostile clicks, cross-origin attempts, queue-conflict byte
preservation, malformed payloads, tab isolation/deactivation). Discovery
queue snapshot (2026-08-27): 118 candidates (111 unverified, 7 rejected);
Approved Sites 18 rows, 1 `approved=TRUE`. Alex's modified Discovery TSV
remains intentionally uncommitted.

**New Wine A2 — two real fixes shipped and live-validated (`d011fac`,
`ae37d3b`); Issue 02-1973 still hasn't cleared the article gate end-to-
end.** `non_article_span_implausibly_large` was traced to two articles
("Keeping the Unity," "New Wine Forum") being consistently misfiled as
non-article material — fixed via explicit instruction wording. A separate
`article_spans_overlap` false-positive was root-caused to an unsorted
comparison order and fixed to match the coverage check's existing pattern.
Neither fix closes the underlying recurrence: post-fix runs still hit a
fresh `non_article_span_implausibly_large`, an inconsistent semantic-
reviewer stage, and one new confirmed risk (a passing review once approved
an ad-bleed span, "Spiritual Potpourri," uncaught by any check). Full
detail: CLAUDE.md's New Wine landmine entry. No database write occurred.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Waiting on Alex:** search-analytics dashboard (see Current state) is
  built and verified but unmerged — needs a review decision, not more
  building. Its own parked findings: consent is enforced frontend-only, not
  backend; the classifier sends raw (pre-redaction) question text to Groq;
  re-resolving an already-resolved gap extends its retention window instead
  of no-op'ing; a future direct `auth.users` deletion (bypassing this
  feature's own `withdraw()`) would cascade-orphan `search_occurrences`
  rather than clean them up.
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** see Current state above — two fixes shipped, but Issue
  02-1973 still isn't through the article gate. Next: diagnose the
  reviewer-stage `article_failure_reasons_invalid` inconsistency and the
  Spiritual-Potpourri ad-bleed risk directly, same no-CLI method. Production
  database ingest for this or any New Wine issue remains a separate,
  attended, explicitly approved operation regardless of how clean a review
  run gets.
- **Parked:** the extension's JavaScript success validator treats a
  32-character whitespace capability/revision as syntactically long enough.
  The Python server still rejects it before mutation, so this is a diagnostic
  contract mismatch, not an authorization bypass.
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

**No active blocker.** New Wine A2 remains the live critical-path thread:
diagnose the semantic-reviewer stage's `article_failure_reasons_invalid`
inconsistency and the Spiritual-Potpourri ad-bleed risk directly (cheap —
OCR is fully cached), the same standalone no-CLI method used this session,
before running more blind CLI retries. Real database ingest for this or any
New Wine issue remains a separate, attended, explicitly approved operation
regardless of how clean a review run gets.

Separately, not competing for the critical-path slot: Alex has a
repo-complete, verified search-analytics dashboard waiting for a merge/
rollout decision (see Current state) whenever there's time to review it.
