-- Migration 057: IP-based rate limit on NEW guest session creation
--
-- Problem (S3): increment_guest_query keys purely on the client-supplied
-- anon_id (localStorage value). A client can send a fresh UUID on every
-- request, resetting the 6-query guest limit indefinitely -- unbounded
-- Groq/OpenAI/Cohere spend via the unauthenticated /chat path.
--
-- Fix: cap how many NEW guest_sessions rows can be created from the same IP
-- within a rolling window. This targets the actual exploit (rapid anon_id
-- rotation) without capping total lifetime activity per IP, which would
-- false-positive-block legitimate shared-network users (this app serves a
-- church congregation -- many real visitors plausibly share one IP on
-- church wifi during a service). An existing anon_id incrementing its own
-- query_count is never affected by this check.
--
-- Chosen over IP-based total-count limiting (false-positives on shared
-- wifi) and a server-set cookie replacing anon_id (would need a frontend
-- credentials:include change and a cross-origin SameSite=None cookie,
-- which Safari's ITP is known to restrict -- a real risk for a
-- likely iOS-heavy user base). No new infra: Postgres only.
--
-- Run manually in the Supabase SQL editor.

ALTER TABLE guest_sessions ADD COLUMN IF NOT EXISTS ip_address text;

CREATE INDEX IF NOT EXISTS idx_guest_sessions_ip_created
  ON guest_sessions (ip_address, created_at);

-- CREATE OR REPLACE with a different parameter list creates a NEW overload
-- rather than replacing the old one (Postgres function identity includes
-- the signature) -- drop the old single-arg version explicitly, otherwise
-- both overloads exist and PostgREST's overload resolution gets ambiguous.
DROP FUNCTION IF EXISTS public.increment_guest_query(text);

-- Tunable starting point, not derived from real traffic data -- revisit
-- once production guest volume is observed. 20 new sessions/hour/IP still
-- caps worst-case abuse at 20 x GUEST_QUERY_LIMIT free queries/hour/IP
-- (vs. unlimited today) while giving real headroom for a shared-wifi
-- scenario (many distinct genuine visitors, each creating ONE session).
CREATE OR REPLACE FUNCTION public.increment_guest_query(p_anon_id text, p_ip_address text DEFAULT NULL)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
DECLARE
  v_count int;
  v_existing_id uuid;
  v_recent_sessions_from_ip int;
  v_max_new_sessions_per_hour CONSTANT int := 20;
BEGIN
  SELECT id INTO v_existing_id FROM guest_sessions WHERE anon_id = p_anon_id;

  IF v_existing_id IS NULL AND p_ip_address IS NOT NULL THEN
    SELECT count(*) INTO v_recent_sessions_from_ip
    FROM guest_sessions
    WHERE ip_address = p_ip_address
      AND created_at > now() - interval '1 hour';

    IF v_recent_sessions_from_ip >= v_max_new_sessions_per_hour THEN
      RETURN -1; -- sentinel: too many new guest sessions from this IP recently
    END IF;
  END IF;

  INSERT INTO guest_sessions (anon_id, ip_address, query_count, last_seen)
  VALUES (p_anon_id, p_ip_address, 1, now())
  ON CONFLICT (anon_id) DO UPDATE
    SET query_count = guest_sessions.query_count + 1,
        last_seen = now()
  RETURNING query_count INTO v_count;

  RETURN v_count;
END;
$function$
