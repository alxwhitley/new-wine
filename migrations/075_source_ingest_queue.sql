-- 075_source_ingest_queue.sql
-- Source ingest queue -- admin submits candidate source URLs for future
-- fetching/ingestion. This migration is TABLE + RLS ONLY. No fetching or
-- ingestion logic exists yet; rows sit here until a future session builds
-- the runner that consumes them.
--
-- Backend uses SUPABASE_SERVICE_KEY (service_role, BYPASSRLS) for all writes.
-- RLS is defense-in-depth against anon-key access.


-- ── 1. source_ingest_queue ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS source_ingest_queue (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  url                   text        NOT NULL,
  source_format         text        NOT NULL
                                    CHECK (source_format IN ('web_page', 'pdf')),
  source_scope          text        NOT NULL
                                    CHECK (source_scope IN ('single', 'collection')),
  -- Teacher name to credit. NULL when attribution_mode = 'per_item' (no single
  -- name applies to every item this row will produce).
  attribute_to          text,
  -- 'declared' = attribute_to applies to everything from this row.
  -- 'per_item' = author must be detected per item at ingest time.
  attribution_mode      text        NOT NULL
                                    CHECK (attribution_mode IN ('declared', 'per_item')),
  -- What a future ingestion run should do when an item's author can't be
  -- resolved. NEVER add a value meaning "proceed unnamed" -- nothing enters
  -- the corpus without a named voice (hard product invariant).
  on_unknown_author     text        NOT NULL DEFAULT 'flag'
                                    CHECK (on_unknown_author IN ('flag', 'skip')),
  -- Deliberately UNSET. Alex has not decided whether raw source text is
  -- retained alongside propositions. Future ingestion code must treat NULL
  -- as "not yet decided -- stop and ask", never as false. Do not default
  -- this true or false.
  retain_original_text  boolean     DEFAULT NULL,
  status                text        NOT NULL DEFAULT 'waiting'
                                    CHECK (status IN ('waiting', 'running', 'done', 'failed', 'needs_attention')),
  flag_reason           text,
  -- Future ingestion code must process ONLY rows where this is true. Lets
  -- permission-track and blocked sources sit in the queue safely.
  cleared_to_run        boolean     NOT NULL DEFAULT false,
  notes                 text,
  submitted_by          uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS source_ingest_queue_status_idx
  ON source_ingest_queue (status);

CREATE INDEX IF NOT EXISTS source_ingest_queue_cleared_to_run_idx
  ON source_ingest_queue (cleared_to_run);


-- ── 2. source_ingest_domain_memory ────────────────────────────────────────────
-- Per-domain author prefill: domain -> last used attribute_to + attribution_mode.
-- A separate tiny table, not a derived query over source_ingest_queue, because
-- the backend already extracts the domain from the URL at insert time (needed
-- to key this table); a derived query would instead have to re-parse the
-- domain out of every historical `url` value at read time -- unindexable and
-- slower as the queue grows, for the same information this upsert already has
-- on hand. One row per domain also means "prefill" is a single indexed
-- equality lookup, not a most-recent-row scan over unbounded queue history.

CREATE TABLE IF NOT EXISTS source_ingest_domain_memory (
  domain            text        PRIMARY KEY,
  attribute_to      text,
  attribution_mode  text        NOT NULL
                                CHECK (attribution_mode IN ('declared', 'per_item')),
  updated_at        timestamptz NOT NULL DEFAULT now()
);


-- ── 3. RLS ────────────────────────────────────────────────────────────────────
--
-- Pattern mirrored from contributor_requests / deletion_requests (migrations
-- 038, 068): own-row read/insert, service-role full access, no anon policy.
-- Admin listing/actions in the backend always go through the service-role
-- client (require_admin_role gate) -- these authenticated-role policies are
-- defense-in-depth, not the real access control.

ALTER TABLE source_ingest_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "source_ingest_queue: own rows read"
  ON source_ingest_queue FOR SELECT
  USING (auth.uid() = submitted_by);

CREATE POLICY "source_ingest_queue: own row insert"
  ON source_ingest_queue FOR INSERT
  WITH CHECK (auth.uid() = submitted_by);

CREATE POLICY "source_ingest_queue: service role full access"
  ON source_ingest_queue FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');


-- source_ingest_domain_memory has no owning user -- service-role only,
-- mirroring the `sources` table's RLS posture (ARCHITECTURE.md: "RLS
-- service-role"). No anon or authenticated policy at all -- both denied.

ALTER TABLE source_ingest_domain_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY "source_ingest_domain_memory: service role full access"
  ON source_ingest_domain_memory FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
