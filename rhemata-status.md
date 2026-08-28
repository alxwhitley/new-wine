# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-28. **PLAN.md has zero active blockers.** The B6/B7
release-candidate gate (`docs/superpowers/plans/2026-08-28-back-to-back-completion-queue.md`)
is the live critical-path thread: Tasks 5.1–5.3 done, Task 5.4 (attended
rollout) is next.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**2026-08-27/28 session ran the full six-packet back-to-back completion
queue.** Packets 1–4 done or explicitly closed; Packet 5 (B6/B7 gate) done
through Task 5.3; Task 5.4 (attended rollout) and Packet 6 (this close) are
what's left.

1. **New Wine A2 — NOT ingestion-ready.** Two real segmentation fixes landed
   (`d5420e3`, `4bad5b5`) but Issue 02-1973 still hasn't cleared the article
   gate end-to-end; recurring failure modes remain (see CLAUDE.md's New Wine
   Landmines entry for full diagnostic detail). No database write occurred.
2. **Search analytics — merged to `main`** (`d636173`), migration 093 **not
   applied**. Alex's policy decisions are made (privacy accepted as-is,
   finalizer on a timer, daily retention, frontend-only quiet-skip consent).
   Rollout instructions written:
   `docs/audits/2026-08/search_analytics_rollout_packet_2026-08-28.md`.
3. **Circular loading ring — shipped** (`0e4442a`), replacing the old
   answer-wait copy; browser-verified across desktop/mobile/reduced-motion.
4. **B4/B5 launch hardening — done.** Dependency fixes (Next.js, pdfplumber;
   starlette/fastapi explicitly accepted as-is, Alex's call). Account
   deletion made real, reconciled, idempotent (`760f253`) — **code is
   complete but migration 094 (`deletion_audit_log`) is NOT applied**, so
   this isn't live yet. Teacher-card metering confirmed already-guarded, now
   has real regression coverage. Three sensitive-logging leaks removed
   (JWT prefixes, raw guest IPs, question text). A real unbounded
   `answer_jobs` content-retention gap closed (90-day purge, isolated-fixture
   proven). CORS/headers/secrets verified clean (gitleaks: 86 findings, all
   confirmed false positives).
5. **B6/B7 gate — Tasks 5.1–5.3 done.** Lint: 0 errors (25 fixed, real bugs
   found along the way — a ref-during-render, an impure `Math.random()`, a
   stale-dependency bug). Accessibility: axe/Lighthouse scan **0 violations**
   across all 7 core surfaces (Home, Study, Library, Consent gate, Account
   settings, Admin analytics, Sources) — 16 real defects found and fixed,
   including a systemic `--primary` color-contrast conflict (see below) and
   a consent gate that had no dialog semantics at all. Observability: real
   `/health`/`/ready` endpoints added and verified against production; saved
   SQL for all 7 dashboard metrics (5 verified live, 1 needs migration 093);
   concrete rollback triggers using real latency baseline (p50 36.83s, p90
   48.58s); rollback steps per component documented. Client-error reporting:
   Alex's explicit call to skip it for beta launch. Backup/RPO/RTO: already
   closed 2026-08-19 (`docs/audits/2026-08/w9_recoverability_inventory_2026-08-19.md`)
   — a first-draft claim that this was unconfirmed was wrong and corrected
   same session (`ef89f47`).
   Full detail: `docs/audits/2026-08/b6_accessibility_pass_2026-08-28.md`,
   `docs/audits/2026-08/b6_observability_and_rollback_2026-08-28.md`.
6. **The `--primary` brand-color conflict (worth knowing before touching it
   again):** the app's gold token is used three conflicting ways (white
   button text, dark button text, plain link text on dark backgrounds) — no
   single lightness value satisfies WCAG AA in all three. Fixed by flipping
   `--primary-foreground` to a dark shade instead of darkening `--primary`
   itself; `--primary` is untouched. Full contrast-sweep math in the
   accessibility audit doc above.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Two migrations pending, both need Task 5.4's attended rollout:**
  093 (search analytics tables) and 094 (`deletion_audit_log` +
  `deletion_requests` schema widening — account deletion isn't live without
  this).
- **Live account-deletion verification is genuinely blocked, not skipped.**
  Only a mocked unit test exists (`scripts/test_account_deletion.py`,
  12/12). The real test plan
  (`docs/audits/2026-08/b4_account_deletion_design_2026-08-28.md` Section 5)
  needs Alex to create a real designated test account first, then a real,
  attended deletion against production — cannot be done autonomously (Session
  Routing hard rule).
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** the remaining recurring failure is a large non-article
  dump absorbing part of "The Apostle" article
  (`non_article_span_implausibly_large`), plus continued
  `article_implausibly_long`/title-bleed variance — same method as the two
  closed fixes: segmentation-only diagnostic call, direct inspection of raw
  spans/transcript text, targeted instruction fix, live-validate.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual — read any `scripts/test_*.py` before batch-running it);
  staging source name still reads `"Vlad Savchuk (web staging)"`; Bonnke URL
  suspect; `rhemata_readonly_analysis` has no grant on PII/user tables.

---

## Next single item

**Task 5.4 — the attended production rollout** (`docs/superpowers/plans/2026-08-28-back-to-back-completion-queue.md`).
Get explicit approval for the exact action list, then: apply migrations 093
+ 094, set `ANALYTICS_HMAC_SECRET_V1` on `rhemata` only, configure
finalizer/retention schedules, deploy backend/worker/frontend, verify
liveness/readiness, run the analytics + core-journey smoke sequence (not a
magazine ingest), watch the first hour against the documented rollback
triggers, record ACCEPT/HOLD/ROLLBACK, open the beta only on ACCEPT. Then
Packet 6 (final session records) closes the queue.

Separately, not competing for the critical-path slot: New Wine A2's
remaining segmentation variance, and the live account-deletion verification
blocked on Alex creating a test account.
