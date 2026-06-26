-- Migration 052: guest_sessions table + increment_guest_query function
--
-- This migration documents a table and function that were applied directly
-- to the Supabase SQL editor during the June 2026 guest-metering work and
-- were never committed to a migration file
-- It is idempotent and safe to re-run against the live database
-- It does NOT modify existing data
--
-- RLS for this table (ENABLE ROW LEVEL SECURITY + the service-role policy)
-- lives in migration 037_rls_all_tables.sql -- do not duplicate it here
--
-- Created: 2026-06-26

-- Table: guest_sessions
-- One row per anonymous visitor, keyed by a client-generated UUID stored in
-- the browser's localStorage under the key "rhemata_anon_id"
-- query_count is incremented by increment_guest_query on each /chat call
CREATE TABLE IF NOT EXISTS guest_sessions (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  anon_id     text        NOT NULL,
  query_count integer     DEFAULT 0,
  created_at  timestamptz DEFAULT now(),
  last_seen   timestamptz DEFAULT now()
);

-- Unique constraint on anon_id
-- Added via a guarded DO block so re-running does not error if the
-- constraint already exists (as it does on the live database)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'guest_sessions_anon_id_key'
      AND conrelid = 'public.guest_sessions'::regclass
  ) THEN
    ALTER TABLE guest_sessions
      ADD CONSTRAINT guest_sessions_anon_id_key UNIQUE (anon_id);
  END IF;
END
$$;

-- Function: increment_guest_query
-- Called by the backend /chat endpoint for unauthenticated (guest) users
-- On first visit inserts a new row with query_count = 1
-- On subsequent visits increments query_count and updates last_seen
-- Returns the new query_count as a bare integer
-- SECURITY DEFINER allows the call to bypass RLS (table is service-role only)
-- Atomicity comes from the single upsert statement -- no SELECT FOR UPDATE needed
CREATE OR REPLACE FUNCTION public.increment_guest_query(p_anon_id text)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
DECLARE
  v_count int;
BEGIN
  INSERT INTO guest_sessions (anon_id, query_count, last_seen)
  VALUES (p_anon_id, 1, now())
  ON CONFLICT (anon_id) DO UPDATE
    SET query_count = guest_sessions.query_count + 1,
        last_seen = now()
  RETURNING query_count INTO v_count;

  RETURN v_count;
END;
$function$
