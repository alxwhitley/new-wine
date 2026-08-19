# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close — pre-beta research pass, two
production fixes shipped and deployed, one live migration applied).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md`'s private-beta blocker queue stayed empty all session (still **0**
active blockers) — this session's work came from `docs/roadmap.md`'s
Scheduled B1-B7/A1-A6 tracks instead, via ad hoc read-only research, not a
formal blocker promotion.

**1. Five parallel read-only research forks**, each logging to
`docs/audits/2026-08/` (commit `0de185d`): product-contract-vs-code gap
check (B1/B2), account-deletion table/FK scope (B4), security/privacy/abuse
code-reading snapshot (B5), a live corpus census (A1), and verification of
two suspect Discovery-tab ingestion URLs.

**2. Fixed a real B5 finding same session** (commit `f14c7e1`): `GET
/study/teacher/{source_id}` (`get_teacher_card()`) had zero query metering
before its live Anthropic generation — any authenticated user could loop it
for unlimited free generations. Now shares `enforce_query_limit()` with
`/async-chat/submit` (same weekly quota pool, not a separate limit). Three
fake-DB regression tests updated for the RPC-call bookkeeping this changes;
`test_debate_topics.py`'s live Tier B section updated to use a real test
account (not run this session — real cost/DB writes).

**3. Fixed a real B4 finding same session, migration + code** (commit
`25d2625`, migration **090 applied to production, verified 28/28**):
`pastors_cards.user_id`, `quotes.{created_by,approved_by,revoked_by}`,
`quote_source_revisions.captured_by`, `document_quote_clearance.cleared_by`
all referenced `auth.users` with `NO ACTION` — deleting either of the 2 real
admin accounts referenced across these tables would have raised a live
FK-violation error. Fixed via Alex's chosen design: each actor column gets a
NOT-NULL `*_email` snapshot captured at write time
(`app.auth.resolve_user_email()`), the FK becomes `ON DELETE SET NULL`, and
`quotes.approved_by`'s CHECK + `enforce_quote_approval_gates()` trigger were
narrowed to only require a real `approved_by` at the moment a row
transitions into `'approved'` (gates 2-4 + speaker-confirmation untouched).
Deploy-ordered correctly: code pushed to `origin/main` in the same session
right after the migration, so the previously-deployed backend's window of
failing new quote/card/clearance writes (NOT NULL violation) should be
closed once Railway's auto-deploy completes — **not independently confirmed
this session; verify the `rhemata` Railway deployment succeeded before
trusting new quote/pastors-card/clearance writes.**

**4. Fixed two stale doc claims** (commit `5e0511d`): POSITIONING.md said
verbatim quoting was "not live yet" (it's been live since earlier the same
day); PRODUCT.md still named John Bevere as an example covered teacher
(pulled from marketing 2026-08-06, zero corpus docs).

All 4 commits pushed to `origin/main`: `0de185d`, `5e0511d`, `f14c7e1`,
`25d2625`.

---

## Findings surfaced this session, not yet acted on

- **A1 census**: Bill Johnson, Randy Clark, and Craig Keener each have a
  `sources` row but **zero documents** — contradicts the prior session's
  ingestion-spreadsheet cross-check, which only confirmed the row exists.
  CLF Church (15 docs) and Rhemata's own content (9 docs) have **zero
  eligible propositions** — first-party material sitting unprocessed, not a
  corpus-acquisition gap.
- **Reinhard Bonnke's** Discovery-tab URL (`reinhardbonnke.com`) has an
  expired TLS cert and no corroboration from CfaN's own site — don't ingest
  from it as-is. **Darlene Cunningham's** URL has the same unverified-
  personal-domain pattern and was never checked (flagged in passing, out of
  original scope).
- B5 snapshot: no retention/TTL logic anywhere for user data; CORS
  `allow_origins` value not traced to its actual source; no dependency or
  security-header scan run. `/corpus-inventory/export`'s public,
  unauthenticated endpoint reconfirmed as Alex's existing accepted
  exception, not a new gap.
- B4 audit: `rhemata_readonly_analysis` has no grant on any PII table
  (conversations, messages, saved_words, etc.) — row counts there need an
  attended service-role session. Also observed live this session: the role
  *can* `CREATE TEMP TABLE` (ordinary Postgres default privilege, session-
  local, not a real write hole on any real table — confirmed, not a gap).
- Full cascading account deletion (the Supabase Admin API call + snapshot
  ordering) is still **not built** — migration 090 only removed the
  database-level blocker; `POST /account/delete-request` is still a stub.

---

## Next single item

Confirm the Railway `rhemata` deploy from this session's push succeeded
(builder has drifted before — see CLAUDE.md Landmines) before trusting new
quote/pastors-card/clearance writes in production. After that: Alex's call
among the surfaced findings above, or pick up `docs/roadmap.md`'s remaining
B1/B4/B5 scope. Active blocker count **0**.
