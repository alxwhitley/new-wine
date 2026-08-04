-- 078_async_answer_path.sql
-- Project 1, Stage 1 -- the durable asynchronous answer path (INERT / additive).
--
-- This migration is purely additive. It creates three NEW tables and touches
-- nothing the live serving path reads or writes. The live /chat endpoint
-- (chat.py) is unchanged and remains the serving path. Nothing here is wired
-- into request routing.
--
-- Design (CLAUDE.md 2026-08-03 settled decision #14): one app, one managed
-- queue, one database, one scalable worker deployment. The queue IS a table in
-- the existing Supabase Postgres, claimed with SELECT ... FOR UPDATE SKIP
-- LOCKED. Capacity is a DIAL (more workers), never a rebuild.
--
-- NOTE (Invariant 9): no semicolons inside -- comments. Applied as one
-- multi-statement string by scripts/apply_async_answer_migration.py, verified
-- on a FRESH connection.

-- ====================================================================
-- answer_jobs -- durable queued generations + per-answer instrumentation
-- ====================================================================
-- A job is the unit of WORK/generation. Rows survive a worker crash or a
-- process restart (nothing about a job lives only in memory or in an HTTP
-- connection). Phase 4 instrumentation columns live on the same row so every
-- completed answer carries its own retrieved point IDs, model/prompt/policy
-- versions, timing, cost, and outcome.
CREATE TABLE IF NOT EXISTS answer_jobs (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Submission identity (idempotency). A resubmit carrying the same
    -- idempotency_key never creates a second job -- the UNIQUE constraint plus
    -- return-existing in jobs.enqueue() guarantee "a duplicate submission
    -- cannot produce duplicate work." Nullable: internal/synthetic submissions
    -- may omit it.
    idempotency_key      text UNIQUE,

    -- Content identity (single-flight + exact-match reuse, Phase 3). A
    -- deterministic hash of question + filters + evidence_version +
    -- prompt_version + policy_version. Two DIFFERENT submissions of the same
    -- content share one generation (single-flight) or reuse a fresh completed
    -- answer (reuse). Enforced structurally by answer_jobs_active_dedup_idx
    -- below -- at most one ACTIVE (queued|running) job per dedup_key.
    dedup_key            text NOT NULL,

    status               text NOT NULL DEFAULT 'queued'
                           CHECK (status IN ('queued','running','done','failed','canceled')),

    -- Request inputs (everything the producer needs to regenerate; a retry
    -- re-runs from these, so it re-runs the accuracy check by construction).
    question             text NOT NULL,
    filters              jsonb NOT NULL DEFAULT '{}'::jsonb,
    messages             jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_version     text NOT NULL,
    prompt_version       text NOT NULL,
    policy_version       text NOT NULL,

    -- Result (populated on completion).
    answer               text,
    citations            jsonb,
    verified_references  jsonb,
    outcome              text
                           CHECK (outcome IS NULL OR outcome IN
                             ('answered','refused_attribution','no_material','error')),

    -- Phase 4 instrumentation. retrieved_chunk_ids / retrieved_point_ids record
    -- exactly what the answer was built from; model/version columns pin the
    -- generation; the timing + cost + token columns are the cheap-now,
    -- unrecoverable-later signals both external reviewers flagged.
    retrieved_chunk_ids  jsonb,
    retrieved_point_ids  jsonb,
    model                text,
    input_tokens         integer,
    output_tokens        integer,
    cache_read_tokens    integer,
    cache_write_tokens   integer,
    cost_usd             numeric(12,6),

    -- Lifecycle / crash recovery. A running job carries a lease; when its
    -- worker dies the lease expires and the reaper requeues it (attempts++),
    -- so "a killed worker loses nothing." run_after carries retry backoff and
    -- rate-limit / spend deferral.
    attempts             integer NOT NULL DEFAULT 0,
    max_attempts         integer NOT NULL DEFAULT 3,
    worker_id            text,
    lease_expires_at     timestamptz,
    run_after            timestamptz NOT NULL DEFAULT now(),
    last_error           text,

    -- Reuse bookkeeping (audit only; single-flight/reuse both return an
    -- existing job id, so no alias table is needed).
    reused_from_job_id   uuid,

    -- Timing.
    created_at           timestamptz NOT NULL DEFAULT now(),
    queued_at            timestamptz NOT NULL DEFAULT now(),
    started_at           timestamptz,
    finished_at          timestamptz,
    updated_at           timestamptz NOT NULL DEFAULT now()
);

-- Claim index: workers pull the oldest ready queued job. Partial so the index
-- stays small as completed rows accumulate.
CREATE INDEX IF NOT EXISTS answer_jobs_claim_idx
    ON answer_jobs (run_after, created_at)
    WHERE status = 'queued';

-- Reaper index: find running jobs whose lease has expired (dead worker).
CREATE INDEX IF NOT EXISTS answer_jobs_lease_idx
    ON answer_jobs (lease_expires_at)
    WHERE status = 'running';

-- Single-flight enforcement, structural (not advisory). At most one ACTIVE
-- (queued or running) job may exist per dedup_key. A concurrent second
-- submission of identical content loses the insert race with a unique
-- violation and is routed to the existing active job by jobs.enqueue().
CREATE UNIQUE INDEX IF NOT EXISTS answer_jobs_active_dedup_idx
    ON answer_jobs (dedup_key)
    WHERE status IN ('queued','running');

-- Reuse lookup: the freshest completed answer for a content key (Phase 3).
CREATE INDEX IF NOT EXISTS answer_jobs_reuse_idx
    ON answer_jobs (dedup_key, finished_at DESC)
    WHERE status = 'done' AND outcome = 'answered';

-- ====================================================================
-- async_answer_config -- one-row control plane (the dials)
-- ====================================================================
-- Central, horizontally-shared knobs: pause switch, backpressure ceiling,
-- reuse TTL, provider rate ceilings (RPM / ITPM / OTPM), spend ceiling. Every
-- worker reads this row; changing a dial changes behaviour across the whole
-- worker fleet with no redeploy.
CREATE TABLE IF NOT EXISTS async_answer_config (
    id                 integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    paused             boolean NOT NULL DEFAULT false,
    -- Backpressure: submissions past this queue depth are rejected at enqueue
    -- (the queue absorbs bursts up to here; workers pull at their own rate).
    max_queue_depth    integer NOT NULL DEFAULT 5000,
    -- Phase 3 reuse: a completed answer is reusable for this many seconds.
    -- 0 disables reuse (conservative default). Single-flight does NOT depend
    -- on this -- it always collapses concurrent identical work.
    reuse_ttl_seconds  integer NOT NULL DEFAULT 0,
    -- Provider rate ceilings, per rolling minute. NULL = unlimited.
    rpm_limit          integer,
    itpm_limit         bigint,
    otpm_limit         bigint,
    -- Spend ceiling. NULL = no ceiling. When cumulative spend in the window
    -- reaches this, workers stop claiming and jobs stay queued (demonstrable
    -- halt in Phase 5).
    spend_ceiling_usd  numeric(14,4),
    spend_window       text NOT NULL DEFAULT 'rolling_24h'
                         CHECK (spend_window IN ('total','rolling_24h','rolling_1h')),
    -- Lease length. A running job whose lease expires is reclaimed by the
    -- reaper. Long enough to cover a normal generation (~70s) with headroom.
    lease_seconds      integer NOT NULL DEFAULT 300,
    updated_at         timestamptz NOT NULL DEFAULT now()
);

INSERT INTO async_answer_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- ====================================================================
-- provider_rate_usage -- rolling per-minute usage buckets
-- ====================================================================
-- A shared, horizontally-correct sliding-window limiter. Before a generation a
-- worker reserves against the current minute bucket (RPM/ITPM/OTPM); after the
-- call it reconciles estimated -> actual. Multiple workers coordinate through
-- row locks on the minute bucket.
CREATE TABLE IF NOT EXISTS provider_rate_usage (
    bucket_minute  timestamptz PRIMARY KEY,
    requests       integer NOT NULL DEFAULT 0,
    input_tokens   bigint  NOT NULL DEFAULT 0,
    output_tokens  bigint  NOT NULL DEFAULT 0,
    updated_at     timestamptz NOT NULL DEFAULT now()
);
