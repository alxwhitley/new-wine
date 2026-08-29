# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-29. **PLAN.md has zero active blockers.** The
2026-08-27→29 back-to-back completion queue
(`docs/superpowers/plans/2026-08-28-back-to-back-completion-queue.md`) is now
fully closed, including Packet 6 (this entry) — see Process measures below.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**2026-08-27 through 2026-08-29 ran the full six-packet back-to-back
completion queue.** Packets 2–6 completed their outcomes; Packet 1 (New Wine
A2 ingestion-ready) did not — see item 1.

1. **New Wine A2 — NOT ingestion-ready.** Two more real segmentation fixes
   landed this window (`d5420e3`, `4bad5b5`) but Issue 02-1973 still hasn't
   cleared the article gate end-to-end; recurrence is dominated by run-to-run
   model variance, not one deterministic gap (CLAUDE.md's New Wine Landmines
   entry has the full diagnostic trail). No database write occurred. This is
   Task 1.1's own permitted exit ("demonstrate no stable correctable pattern,
   return to Alex with the evidence"), not a queue failure.
2. **Search analytics — live in production.** Migration 093 applied,
   `ANALYTICS_HMAC_SECRET_V1` set on `rhemata`, finalizer
   (`search-analytics-finalizer`, `*/5 * * * *`) and retention
   (`search-analytics-retention`, `0 6 * * *`) running as verified Railway
   Cron Jobs. **Non-obvious setup trap:** a freshly `railway add`-ed cron
   service defaults to the Railpack builder (ignores this repo's
   `nixpacks.toml`, fails with `Script start.sh not found`) and inherits no
   other service's env vars — switch Builder to Nixpacks manually, use
   `/opt/venv/bin/python` in the start command, and copy env vars over by
   hand. **Explicitly skipped, Alex's decision:** the production smoke
   sequence (consent flow, one real answered question, dashboard
   field-allowlist check) — the feature's core privacy guarantee (no
   question wording stored) shipped **unverified**.
3. **Circular loading ring — shipped** (`0e4442a`), replacing the old
   answer-wait copy; browser-verified across desktop/mobile/reduced-motion.
4. **B4/B5 launch hardening — done.** Dependency fixes (Next.js, pdfplumber;
   starlette/fastapi accepted as-is, Alex's call). Account deletion made
   real, reconciled, idempotent (`760f253`), migration 094 applied — code is
   live, but real live-DB deletion verification is still blocked (below).
   Teacher-card metering confirmed already-guarded, now has real regression
   coverage. Three sensitive-logging leaks removed. A real unbounded
   `answer_jobs` content-retention gap closed (90-day purge). CORS/headers/
   secrets verified clean (gitleaks: 86 findings, all confirmed false
   positives).
5. **B6/B7 gate — ACCEPTed 2026-08-29.** Lint: 0 errors. Accessibility:
   0 axe/Lighthouse violations across all 7 core surfaces (16 real defects
   found and fixed, including a systemic `--primary` color-contrast conflict
   — full contrast-sweep math and the fix in CLAUDE.md's Landmines entry,
   not restated here). Observability: real `/health`/`/ready` endpoints,
   saved SQL for all 7 dashboard metrics, rollback triggers against a real
   latency baseline (p50 36.83s, p90 48.58s). Client-error reporting:
   Alex's explicit call to skip for beta launch. Task 5.4 attended
   rollout: 45 pending local commits pushed to `origin/main`; migrations 093
   (46/46 verified) and 094 (18/18 verified) applied; first-hour watch was a
   point-in-time snapshot (queue depth 0, failed jobs 0, no traffic yet) —
   full detail in `docs/audits/2026-08/b6_accessibility_pass_2026-08-28.md`
   and `docs/audits/2026-08/b6_observability_and_rollback_2026-08-28.md`.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Analytics smoke sequence never ran** — see item 2 above. Full sequence:
  `docs/audits/2026-08/search_analytics_rollout_packet_2026-08-28.md`
  Section 6. Any real logged-in account works (need not be disposable).
- **Live account-deletion verification is genuinely blocked, not skipped.**
  Only a mocked unit test exists (`scripts/test_account_deletion.py`,
  12/12). Needs Alex to create a real disposable test account first, then a
  real attended deletion against production (Session Routing hard rule).
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** remaining recurring failure is a large non-article dump
  absorbing part of "The Apostle" (`non_article_span_implausibly_large`),
  plus continued `article_implausibly_long`/title-bleed variance. Same
  method as the last two closed fixes.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual); staging source name still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `rhemata_readonly_analysis` has no grant
  on PII/user tables.

---

## Process measures — back-to-back completion queue close

- **Original outcome completion:** 4 of 5 named packets fully achieved
  their outcome (search analytics live, loading ring shipped, B4/B5 risks
  closed/accepted, B6/B7 ACCEPT). Packet 1 (New Wine A2 ingestion-ready) did
  not — permitted by its own exit criterion, carried forward as Scheduled.
- **Unplanned investigations started:** 1 — the in-page Discovery review
  browser extension (`tools/discovery-review-extension/`, commits `2af9e4d`
  through `5860dbf`, 2026-08-27), a full design/build/harden cycle outside
  the queue's five named packets. Built detail: CLAUDE.md's 2026-08-27
  Landmines entry.
- **Findings promoted to Blocker:** 0. PLAN.md's active blocker count held
  at 0 across the whole window; B6-F1 (the only recent Blocker-track item)
  closed 2026-08-26, before this queue began.
- **Active critical-path item count:** 0. Packet 6 was the last named
  critical-path item; nothing else from the queue's five packets remains
  open.

---

## Next single item

None on the critical path — the back-to-back queue is fully closed. Three
non-blocking threads remain, none competing for a critical-path slot:

- **New Wine A2 segmentation variance** (Scheduled, `docs/roadmap.md` A2) —
  segmentation-only diagnostic call, inspect raw spans/transcript, targeted
  instruction fix, live-validate.
- **Analytics production smoke sequence** — deferred, Alex's decision.
- **Live account-deletion verification** — blocked on Alex creating a
  disposable test account.
