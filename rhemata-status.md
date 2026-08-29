# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-29. **PLAN.md has zero active blockers.** The B6/B7
release-candidate gate (`docs/superpowers/plans/2026-08-28-back-to-back-completion-queue.md`)
reached Task 5.4 (attended rollout) and closed it with **Alex's explicit
ACCEPT decision, 2026-08-29** — beta is open. Packet 6 (final session
records/roadmap update) is the only formally unclosed piece of that queue.

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
2. **Search analytics — live in production** (migration 093 applied, secret
   set, finalizer + retention cron jobs running — see Task 5.4 below). Smoke
   sequence deferred (Findings section).
3. **Circular loading ring — shipped** (`0e4442a`), replacing the old
   answer-wait copy; browser-verified across desktop/mobile/reduced-motion.
4. **B4/B5 launch hardening — done.** Dependency fixes (Next.js, pdfplumber;
   starlette/fastapi explicitly accepted as-is, Alex's call). Account
   deletion made real, reconciled, idempotent (`760f253`), migration 094
   applied — code is live, but see Findings: real deletion still
   unverified. Teacher-card metering confirmed already-guarded, now
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

**Task 5.4 — attended rollout, done, ACCEPTed 2026-08-29:**
- Pushed 45 local commits to `origin/main` (Railway + Vercel deploy on push;
  they were sitting unpushed since the prior session — confirmed live via a
  404 on `/health` before the push, 200 after).
- Migration 093 (search analytics) applied — 46/46 verified on a fresh
  connection. Migration 094 (`deletion_audit_log`) applied — 18/18 verified
  on a fresh connection.
- `ANALYTICS_HMAC_SECRET_V1` generated and set on `rhemata` only; service
  restarted to pick it up (confirmed via `/ready`).
- Two Railway Cron Job services created and verified running:
  `search-analytics-finalizer` (`*/5 * * * *`) and
  `search-analytics-retention` (`0 6 * * *`), both rooted at `/` with
  `/opt/venv/bin/python scripts/search_analytics_*.py` start commands.
  **Non-obvious setup trap, worth knowing before creating another Railway
  cron service in this project:** a freshly `railway add`-ed service
  defaults to the Railpack builder, which does not read this repo's
  `nixpacks.toml` and fails immediately (`Script start.sh not found`) —
  Builder must be manually switched to Nixpacks in Settings, AND the start
  command must use the venv path (`/opt/venv/bin/python`, not `python3`) to
  match where Nixpacks actually installs dependencies. Also: a new service
  does not inherit any other service's env vars — `SUPABASE_DB_URL` +
  `GROQ_API_KEY` (finalizer) and `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
  (retention) had to be copied over explicitly. Finalizer verified via
  several real 5-minute runs (clean zero-count result dict, zero
  failures); retention verified via its real 6am UTC firing
  (`{'purged': 0}`, expected).
- **Explicitly skipped, Alex's decision, not an oversight:** the analytics
  production smoke sequence (consent flow, one real answered question,
  dashboard field-allowlist check) — the feature's core privacy guarantee
  (no question wording stored anywhere) shipped to production
  **unverified**. Live account-deletion verification remains separately
  blocked (below), so that half of the smoke plan didn't run either.
- First-hour watch was a **point-in-time snapshot, not a continuous
  first-hour trace** (time passed during cron troubleshooting): queue
  depth 0, failed jobs 0, expired leases 0, finalizer backlog 0, no
  worker/latency activity in the last hour (expected — no real traffic
  yet). API 5xx rate was not checked (Railway-dashboard-only, no CLI/DB
  access to it from this session).

---

## Findings surfaced, not yet acted on

- **Analytics smoke sequence never ran — do this before trusting the
  feature's privacy guarantee.** Full sequence:
  `docs/audits/2026-08/search_analytics_rollout_packet_2026-08-28.md`
  Section 6. Any real logged-in account works (does not need to be
  disposable — that requirement is specific to account-deletion testing
  below).
- **Live account-deletion verification is genuinely blocked, not skipped.**
  Only a mocked unit test exists (`scripts/test_account_deletion.py`,
  12/12). The real test plan
  (`docs/audits/2026-08/b4_account_deletion_design_2026-08-28.md` Section 5)
  needs Alex to create a real designated (disposable) test account first,
  then a real, attended deletion against production — cannot be done
  autonomously (Session Routing hard rule).
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

**Packet 6 — final session records**, closing the back-to-back completion
queue: update `docs/roadmap.md` (replace stale A2 wording, mark completed
Horizon work), record process measures, one docs-only closeout commit.

Separately, not competing for the critical-path slot: the analytics smoke
sequence (deferred, not run — see above), the live account-deletion
verification blocked on Alex creating a disposable test account, and New
Wine A2's remaining segmentation variance.
