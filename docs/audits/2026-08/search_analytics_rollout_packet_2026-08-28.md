# Search Analytics — Packet 5 Rollout Instructions

**Prepared:** 2026-08-28, Packet 2 (Task 2.3) of the back-to-back completion
queue (`docs/superpowers/plans/2026-08-28-back-to-back-completion-queue.md`).
Nothing in this document has been executed — no migration applied, no
secret set, no deploy, no scheduler created. It exists so Packet 5 can run
the attended rollout without reconstructing these steps from memory.

Design spec: `docs/superpowers/specs/2026-08-27-search-analytics-and-corpus-gap-dashboard.md`.
Code merged onto `main`: commit `d636173` (+ `5b98e0a`, `73c82f1` — the
retention CLI wrapper and a dry-run-verify crash fix added while preparing
this packet).

## Decisions Alex already made (Packet 2, Task 2.1 — do not re-ask)

1. **Privacy boundary:** accepted as-is. Anonymous through the dashboard,
   the API, and `anon`/`authenticated` Postgres roles; correlatable by
   direct service-role database access (the same access Alex already has
   for routine maintenance).
2. **Finalizer runtime:** scheduled/timer, not an always-on worker service.
3. **Retention runtime:** once daily.
4. **Consent enforcement:** frontend-only (quiet skip for a non-consented
   authenticated user; no backend hard-block).

## 1. Migration 093

**Verify (dry-run, safe, already re-run live 2026-08-28 read-only against
production — confirms migration is NOT applied: 0 passed / 46 failed,
every table/column/RLS/grant check correctly absent):**

```
python3.12 scripts/apply_migration_093.py
```

**Apply (Packet 5's attended action):**

```
python3.12 scripts/apply_migration_093.py --apply
```

This runs the same verify pass immediately after applying, on the same
connection. **Re-run the plain verify command again afterward on a fresh
connection** (a second, separate invocation) to confirm the result holds
independent of the apply script's own transaction — this is the standing
"verify on a fresh connection" discipline (Invariant 9's SQL-comment
lesson exists for exactly this class of migration risk).

Expected post-apply result: 46/46 pass — 3 tables exist, each with RLS
enabled, a service_role policy, and no grant to `anon`/`authenticated`;
all listed columns present on each table.

## 2. Secret

**Correction to the design spec:** the spec's rollout checklist (item 3)
says to set `ANALYTICS_HMAC_SECRET_V1` on both `rhemata` and
`answer-worker`. Verified live 2026-08-28 by grepping the actual code: only
`backend/app/services/search_analytics/subject_key.py` reads this env var,
and it's only ever called from `async_chat.py` (submit path) and the
`consent`/`gaps`/`occurrences` services — all backend (`rhemata`) code.
`scripts/answer_worker.py` never imports anything from `search_analytics`.
**Set the secret on `rhemata` only.** Setting it on `answer-worker` too is
harmless but unnecessary secret sprawl — Alex's call if they want it there
defensively anyway.

- Generate a long random value (e.g. `openssl rand -hex 32`).
- Set `ANALYTICS_HMAC_SECRET_V1` on Railway service `rhemata`.
- Never print or log the value. Confirm it's set via the Railway dashboard
  or `railway variables` output, not by echoing it in a script or chat.

## 3. Finalizer — scheduled, not a worker service

`scripts/search_analytics_finalizer.py` already runs exactly one
finalization pass and exits — it was built for this from the start
("Safe to invoke repeatedly (e.g. via cron)"), so Alex's "run on a timer"
decision needs a scheduler, not new code.

```
python3.12 scripts/search_analytics_finalizer.py
```

**Packet 5 needs to decide the exact cadence and where the schedule runs**
(a Railway Cron Job hitting this script, or an external scheduler with
`railway run`). Suggested starting cadence: **every 5 minutes** — frequent
enough that a `no_material` gap is diagnosable soon after it happens
(the product goal), infrequent enough to keep it cheap (Groq
`openai/gpt-oss-120b`, one classification call per not-yet-classified job
per pass). Not yet approved — flag this cadence to Alex explicitly at the
Packet 5 gate rather than assuming it.

## 4. Retention — daily

New this session: `scripts/search_analytics_retention.py` (commit
`5b98e0a`), matching the finalizer wrapper's shape exactly.

```
python3.12 scripts/search_analytics_retention.py
```

Schedule once daily (e.g. a Railway Cron Job, any time of day — the purge
condition is `text_purge_at <= now()`, not tied to a specific hour).

## 5. Deploy

Deploy the reviewed backend (`rhemata`) and frontend revisions containing
commits `d636173`/`5b98e0a`/`73c82f1`. The answer-worker image is unaffected
by this feature (see Section 2) and does not need a redeploy for analytics
specifically, though it may already need one for unrelated queued Packet 4/5
work by the time Packet 5 actually runs — check the release revision at
that time, don't assume this note is still current.

## 6. Production smoke sequence

Run in order, after migration + secret + deploy, before opening beta:

1. **Consent flow:** log in as the designated test account. Confirm the
   consent modal renders and blocks (no close/backdrop-dismiss). `PUT
   /analytics/consent` with the current `CURRENT_POLICY_VERSION`; confirm
   `GET /analytics/consent` reflects current, non-withdrawn acknowledgment.
2. **One answered occurrence:** submit one real question as the consented
   test account. After the answer completes, run one finalizer pass
   (`python3.12 scripts/search_analytics_finalizer.py`) and confirm via
   `GET /admin/analytics/summary` that the monitored-search count
   increments. **Directly query `search_occurrences` for that row and
   confirm no question wording is stored anywhere on it** — this is the
   feature's core privacy guarantee; verify it, don't just trust the
   schema.
3. **Dashboard field allowlist:** load the admin Analytics tab; confirm
   only summary counts, the ranked topic bar chart (with an accessible
   `<table>` equivalent), and — on a gap row — the *redacted* question
   text ever render. No `subject_key`, no account identifier, no
   unredacted question text anywhere in the response payloads (check the
   network tab, not just the rendered UI).
4. **Controlled `no_material` case (attended production write — separate
   approval, per the queue's own attended-gates list):** only if Alex
   explicitly approves a controlled `no_material` production write at the
   Packet 5 gate. If approved: submit one question guaranteed to return
   `no_material`, finalize it, confirm a `search_gap_details` row appears
   with `redacted_question` populated and no direct identifiers in it.
5. **Retest/resolve:** from the admin panel, retest the gap row created in
   step 4 (or an existing open gap if step 4 wasn't run). Confirm `POST
   .../retests` enqueues a real job and stamps `retest_occurrence_id`.
   Once that retest's outcome is not `no_material`, confirm `PATCH
   .../resolve` succeeds; confirm it's rejected before that.
6. **Purge metadata (no need to wait 30 real days):** confirm
   `scripts/search_analytics_retention.py` runs cleanly against production
   with zero purges expected (nothing will be past its 30-day
   `text_purge_at` yet) — this only proves the job runs without error
   against the live schema, not the actual purge behavior, which is
   already covered by `scripts/test_analytics_retention.py`'s fixtures.

**Do not use a magazine ingest as this smoke test** (per the queue's own
explicit instruction) — the above sequence is the actual analytics/core-
journey smoke.

## 7. Rollback

**Triggers:** any security/privacy defect found in production (e.g.
question wording appearing somewhere it shouldn't); a new client error on
the core chat journey traceable to this feature; the finalizer or
retention job failing repeatedly rather than gracefully skipping.

**Posture:** this is additive, not a replacement of any existing path —
rolling back means disabling collection and finalization, never dropping
data:

- Revert the `rhemata`/frontend deploy to the prior revision. The prior
  revision has no analytics code at all, so this alone stops new
  consent-gate prompts and new occurrence rows.
- Stop invoking the finalizer and retention scheduled jobs (pause/delete
  the Railway Cron Job, or whatever scheduler Packet 5 sets up).
- **Do not drop or truncate `analytics_consent`, `search_occurrences`, or
  `search_gap_details`.** Preserve all rows for an attended decision;
  only Alex approves actual deletion of already-collected analytics data.
- Migration 093 itself does not need to be rolled back to stop the
  feature — the tables sitting inert with no application code reading or
  writing them is a safe paused state, not a live risk (RLS + no `anon`/
  `authenticated` grants mean they're not reachable via PostgREST even
  while idle).

## Still open for Packet 5 to decide, not this packet

- Exact finalizer cadence (5-minute suggestion above, unapproved).
- Which scheduler mechanism Railway rollout actually uses for the two cron
  jobs (finalizer, retention).
- Whether the controlled `no_material` smoke write (step 4) is approved.
