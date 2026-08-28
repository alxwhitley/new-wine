# B6 Task 5.3 — Observability, dashboards, and rollback plan

Part of the back-to-back completion queue, Packet 5 (B6/B7 release-candidate
gate). Prepares Task 5.4's attended rollout; makes no production change by
itself. All SQL below is read-only and safe to run any time.

**Verification status:** queries 2–6 (queue depth, failed jobs, expired
leases, worker heartbeat, latency) were run read-only against the real
production database this session and returned sane results consistent with
a currently-quiet system (0 queued, 0 failed, 0 expired leases, no recent
worker activity, no completions in the last hour to compute percentiles
from). Query 7 (finalizer backlog) correctly failed with `relation
"search_occurrences" does not exist` — expected, since migration 093 hasn't
been applied yet (Task 5.4). Re-verify query 7 once that migration lands.

## Liveness and readiness

Two new endpoints on the backend (`backend/app/main.py`, commit pending),
neither authenticated (matches the existing public `/` root), neither
returns secrets or exception detail:

- `GET /health` — liveness only. Returns `{"status": "ok"}` if the process
  can serve HTTP at all. No dependency I/O.
- `GET /ready` — readiness. Opens a real, short-lived connection to Postgres
  (`SELECT 1`, via the same `async_answers.db.connect()` already used by the
  answer worker) and confirms the six API keys every answer path depends on
  are present (`SUPABASE_URL`, `SUPABASE_DB_URL`, `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `COHERE_API_KEY`, `GROQ_API_KEY`). Returns `200
  {"status": "ok", "checks": {...}}` when every check passes, `503
  {"status": "not_ready", "checks": {...}}` naming which check(s) failed
  when one doesn't. Deliberately does NOT call Anthropic/OpenAI/Cohere/Groq
  live — this is polled on an interval, and a real provider call on every
  poll would be slow, non-free, and adds nothing a presence check doesn't
  already catch (a provider outage belongs in the answer path's own error
  handling, not this probe).

Verified locally: `/health` returns 200 immediately; `/ready` genuinely
reached the production Supabase pooler (`database: true`) and correctly
flagged a real gap in this dev machine's `.env` (`cohere_api_key: false`,
503) — proof the check does real work, not a hardcoded 200.

**Deliberately not changed:** `backend/railway.toml`'s `healthcheckPath` is
still `/` (Railway's own deploy-gating healthcheck), not `/ready`. Pointing
Railway's DEPLOY gate at a stricter check that includes a live DB round-trip
adds a new way for a transient hiccup (e.g. pooler cold start) to make
Railway consider a good deploy "failed" and roll it back — a repo-only prep
task is the wrong place to introduce that risk. `/health` and `/ready` are
additive, meant for manual/external polling and the Task 5.4 first-hour
watch. If Alex wants Railway's own deploy gate to use `/ready` instead, that
is a one-line `healthcheckPath` change to make deliberately during the
attended Task 5.4 rollout, not a byproduct of this prep session.

The worker (`scripts/answer_worker.py`) has no HTTP server, so it has no
liveness endpoint of its own — its "is it alive" signal is the worker
heartbeat query below (a recently-claimed or recently-finished job).

## Dashboards / saved queries

No dashboard tool (Grafana, Datadog, etc.) exists in this stack today —
confirmed by grep, nothing in `requirements.txt`/`package.json`. Per the
task's own "dashboards OR saved queries" framing, these are saved SQL
queries against the live Supabase Postgres (`rhemata_readonly_analysis` role
or the Supabase SQL Editor), each returning a live current value plus enough
context to act on it. Every query is read-only.

### 1. API 5xx rate

Not queryable from Postgres — this is Railway request-level data, and no
Railway MCP/API access exists in this environment. **Source of truth:
Railway dashboard → `rhemata` service → Observability tab** (HTTP status
breakdown over time). Check this manually during the Task 5.4 first-hour
watch; no saved query substitutes for it.

### 2. Answer queue depth

```sql
SELECT count(*) AS queued_jobs
FROM answer_jobs
WHERE status = 'queued';
```

Baseline: near 0 outside a burst (backpressure ceiling is
`async_answer_config.max_queue_depth`, default 5000 — a value approaching
that means submissions are about to start being rejected).

### 3. Failed jobs (recent)

```sql
SELECT id, question, last_error, attempts, max_attempts, finished_at
FROM answer_jobs
WHERE status = 'failed'
  AND finished_at > now() - interval '1 hour'
ORDER BY finished_at DESC;
```

Baseline: rare. A cluster of rows sharing the same `last_error` text is the
actionable signal, not the raw count.

### 4. Expired leases (dead-worker detection)

```sql
SELECT id, worker_id, started_at, lease_expires_at
FROM answer_jobs
WHERE status = 'running'
  AND lease_expires_at < now();
```

Should always return 0 rows — the reaper reclaims these automatically
(requeues, `attempts++`). A nonzero, growing count means the reaper itself
isn't running, not just that one worker died.

### 5. Worker heartbeat

No dedicated heartbeat table exists; derived from job activity instead —
accurate because a worker with nothing to claim still ticks its polling loop
and would pick up a job within one interval if one existed.

```sql
SELECT
  worker_id,
  max(started_at) AS last_claim,
  now() - max(started_at) AS since_last_claim
FROM answer_jobs
WHERE started_at > now() - interval '1 hour'
GROUP BY worker_id
ORDER BY last_claim DESC;
```

No rows in the last several minutes during a period with queued jobs = no
live worker. (Zero rows during a period with an EMPTY queue is normal, not
a signal — check query #2 alongside this one.)

### 6. p50 / p95 answer latency

```sql
SELECT
  percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM finished_at - started_at)) AS p50_seconds,
  percentile_cont(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM finished_at - started_at)) AS p90_seconds,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM finished_at - started_at)) AS p95_seconds,
  count(*) AS n
FROM answer_jobs
WHERE status = 'done'
  AND outcome = 'answered'
  AND finished_at > now() - interval '1 hour';
```

**Recorded baseline** (`docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`,
the `effort_medium_v1` change live in production since 2026-08-27): median
producer time **36.83 s**, p90 **48.58 s** (12-case paired benchmark, not a
live-traffic p95 — no live p95 figure exists yet since there hasn't been
real traffic since this change shipped). Treat p90 as the closest available
reference for the p95-based rollback trigger below until real traffic
produces a genuine p95.

### 7. Analytics-finalizer backlog

```sql
SELECT count(DISTINCT o.job_id) AS jobs_with_pending_classification
FROM search_occurrences o
JOIN answer_jobs j ON j.id = o.job_id
WHERE o.classification_status = 'pending'
  AND j.status = 'done';
```

Baseline: near 0 between finalizer runs, briefly nonzero right after a burst
of completed jobs, should drain to 0 within one finalizer interval (see
Task 5.4 for the chosen cadence).

## Hold / rollback triggers

Concrete, not just the task's own template language:

| Trigger | Threshold | Source |
|---|---|---|
| Security/privacy defect or data-integrity failure | Any confirmed instance | — |
| New client error affecting the core journey (ask → answer) | Any new, reproducible instance not present before this rollout | Direct user report or manual spot-check only — no automated client-error reporting exists (Alex's decision, see below: skipped for beta launch) |
| API 5xx rate | More than 2× the pre-rollout baseline rate | Railway Observability tab |
| p95 answer latency | More than 50% above the recorded p90 baseline of 48.58 s, i.e. **above ~73 s** sustained (not one outlier job) | Query #6 above |

Any single trigger firing during the Task 5.4 first-hour watch means HOLD
(stop opening the beta further) at minimum; a security/privacy or
data-integrity trigger means ROLLBACK regardless of the others.

## Rollback steps by component

- **Frontend (Vercel):** redeploy the previous production deployment from
  the Vercel dashboard ("Promote to Production" on the prior deployment), or
  `vercel rollback` from the CLI if available. No data involved — instant
  and fully reversible.
- **Backend (Railway `rhemata`):** redeploy the previous successful
  deployment from Railway's dashboard (Deployments tab → previous → Redeploy),
  or roll back to the prior git commit and let Railway's GitHub-triggered
  deploy pick it up. `backend/railway.toml`'s `restartPolicyMaxRetries = 3`
  already limits automatic crash-restart attempts before Railway stops
  retrying on its own.
- **Answer worker (Railway `answer-worker`):** same redeploy mechanism as
  the backend, independent service — rolling the worker back does not
  require rolling the backend back, and vice versa, since they deploy from
  the same repo but as separate Railway services.
- **Analytics finalizer:** stop the scheduled run (Alex's approved shape is
  a timer, not an always-on worker — see Packet 2 rollout instructions,
  `docs/audits/2026-08/search_analytics_rollout_packet_2026-08-28.md`).
  Stopping it is fully safe and reversible: unclassified `search_occurrences`
  rows simply stay `classification_status='pending'` and get picked up
  whenever the finalizer resumes — no data is lost by pausing it.
- **Retention scheduler:** same posture — stopping the daily retention run
  is safe; it only means eligible rows aren't purged yet, not that anything
  incorrect happens. Resuming it later picks up exactly where it left off
  (idempotent `UPDATE ... WHERE <cutoff> AND NOT already-purged` shape).
- **Migration 093 (search analytics tables):** additive-only, matching every
  other migration in this repo's convention (`CREATE TABLE IF NOT EXISTS`,
  no `ALTER`/`DROP` on existing tables). A rollback does NOT mean reversing
  the migration — dropping the new tables would destroy already-collected
  analytics data for no reason, since the tables being unused by disabled
  application code is already a safe, inert state. If a rollback is needed,
  the correct action is: stop the finalizer/retention schedules and redeploy
  the previous backend/frontend versions; leave migration 093's tables in
  place, dormant.

## Backups / RPO / RTO

**Correction:** this section originally said the backup/RPO/RTO posture was
unconfirmed and needed a fresh Alex dashboard check before Task 5.4. That was
wrong — a real, dated, dashboard-sourced inventory already exists and was
already closed by Alex's explicit acceptance:
`docs/audits/2026-08/w9_recoverability_inventory_2026-08-19.md` (PLAN.md's
W9 entry). Should have been checked before writing the paragraph below;
correcting here rather than leaving it standing, per this repo's own "repo
wins over chat premises" discipline.

**Authoritative posture (2026-08-19, closed):** scheduled daily physical
backups enabled, PITR disabled, 7 daily restore points visible (~10.6 GB DB).
Implied RPO ~24h worst case (writes since the last midnight-UTC backup).
Implied RTO unverified — no timed project-level restore has been run; Alex
explicitly accepted this as unproven rather than requiring a drill. A
smaller-scope restore (single document, 9-table footprint including
embeddings) was separately proven 2026-07-24
(`scripts/export_restore_document.py`) — a full project-level restore
remains the unproven piece. Nothing about this session's changes (search
analytics, observability endpoints, accessibility fixes) alters this
posture or reopens the question. The task's "if practical" non-production
export/restore round trip was already judged not required to close this —
Alex's 2026-08-19 acceptance covers it. No further action needed before
Task 5.4 on this specific item.

## Client-error reporting — decision needed before this task is complete

No error-tracking service exists in this codebase today (no Sentry or
equivalent — confirmed by grep). Two real options, both of which count as
"a new external service or new collection" per the governing rule for this
task, so both need Alex's explicit privacy approval before either is built:

1. **A hosted error-tracking service** (e.g. Sentry): richer tooling
   (stack traces, session replay, alerting) but sends client error data
   (URL, browser info, and whatever the error touches) to a third party.
2. **A minimal self-hosted endpoint**: the frontend POSTs an error summary
   (message, URL, timestamp — no stack trace unless explicitly added) to a
   new backend route that logs it; stored only in this project's own
   database/logs, nothing leaves this infrastructure, but it's still a new
   collection of client-side data that didn't exist before.

**Decided 2026-08-28 (Alex): skip client-error reporting for beta launch.**
Neither option is being built. Beta ships with no visibility into
client-side errors beyond the browser's own console and direct user
reports. Recorded as a deliberate, known gap — not an oversight — and a
real candidate for a later session once the beta has real usage to justify
the added collection (self-built) or the third-party data flow (Sentry).
