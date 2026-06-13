-- 039_user_usage.sql
-- Per-user weekly query metering — Phase 2 billing foundation.
-- Run manually in the Supabase SQL Editor. Do not run via script.
--
-- Replaces the per-day hardcoded constant (user_daily_usage + increment_user_daily_query,
-- migration 014). The old table is left intact; the /chat endpoint no longer writes to it.
--
-- weekly_limit is stored per-user so Phase 2 can raise it per subscription tier
-- without a code change. Default 50/week for all new rows.
--
-- Backend uses SUPABASE_SERVICE_KEY (service_role, BYPASSRLS) for all writes
-- via SECURITY DEFINER RPCs. RLS is defence-in-depth against anon-key access.


-- ── 1. user_usage ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_usage (
  user_id       uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  query_count   int         NOT NULL DEFAULT 0,
  week_start    date        NOT NULL DEFAULT (date_trunc('week', now())::date),
  weekly_limit  int         NOT NULL DEFAULT 50,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- ── 2. RLS ────────────────────────────────────────────────────────────────────

ALTER TABLE user_usage ENABLE ROW LEVEL SECURITY;

-- Authenticated users can read their own row only (for GET /usage via anon key)
CREATE POLICY "user_usage: own row read"
  ON user_usage FOR SELECT
  USING (auth.uid() = user_id);

-- All writes go through SECURITY DEFINER RPCs running under service_role context
CREATE POLICY "user_usage: service role full access"
  ON user_usage FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');


-- ── 3. increment_user_query ───────────────────────────────────────────────────
--
-- Atomic single-statement upsert: INSERT on first call, increment on same
-- week, reset to 1 on new week. Two concurrent calls at count=49 will
-- serialize on the PK conflict; both return their final count correctly.
--
-- Returns (query_count, weekly_limit, week_start) AFTER the operation.
-- Caller compares query_count > weekly_limit to enforce the hard stop.
--
-- NOTE: date_trunc('week', now()) returns Monday in ISO 8601 (Postgres default).

CREATE OR REPLACE FUNCTION increment_user_query(p_user_id uuid)
RETURNS TABLE(query_count int, weekly_limit int, week_start date)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_monday date := date_trunc('week', now())::date;
  v_count  int;
  v_limit  int;
BEGIN
  INSERT INTO user_usage AS u (user_id, query_count, week_start, weekly_limit)
  VALUES (p_user_id, 1, v_monday, 50)
  ON CONFLICT (user_id) DO UPDATE
    SET
      query_count = CASE
                      WHEN u.week_start = v_monday THEN u.query_count + 1
                      ELSE 1
                    END,
      week_start  = v_monday,
      updated_at  = now()
  RETURNING u.query_count, u.weekly_limit
  INTO v_count, v_limit;

  RETURN QUERY SELECT v_count, v_limit, v_monday;
END;
$$;


-- ── 4. get_user_usage ─────────────────────────────────────────────────────────
--
-- Non-incrementing read for GET /usage (page-load circle before first query).
-- Applies week-rollover: if stored week_start is stale, returns count=0 for
-- the new week — matching what increment_user_query would set on next call.

CREATE OR REPLACE FUNCTION get_user_usage(p_user_id uuid)
RETURNS TABLE(query_count int, weekly_limit int, week_start date)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_monday  date := date_trunc('week', now())::date;
  v_row     user_usage%ROWTYPE;
BEGIN
  SELECT * INTO v_row FROM user_usage WHERE user_id = p_user_id;

  IF NOT FOUND THEN
    -- No row yet: new user, zero queries this week
    RETURN QUERY SELECT 0::int, 50::int, v_monday;
  ELSIF v_row.week_start != v_monday THEN
    -- Stale week: effective count is 0 (new week, no queries yet)
    RETURN QUERY SELECT 0::int, v_row.weekly_limit, v_monday;
  ELSE
    RETURN QUERY SELECT v_row.query_count, v_row.weekly_limit, v_row.week_start;
  END IF;
END;
$$;
