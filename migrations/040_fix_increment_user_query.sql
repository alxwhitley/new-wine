-- 040_fix_increment_user_query.sql
-- Fix: conditional increment — rejected requests must not move the counter.
--
-- Problem with 039: the upsert always incremented before the caller checked
-- count > limit, so a 51st request wrote count=51 to the DB then got a 429.
-- The counter drifted unbounded past the limit.
--
-- Fix: move the limit check INTO the RPC. The function holds a row-level lock
-- (SELECT ... FOR UPDATE) between reading the current count and deciding
-- whether to write. Two concurrent 50th-query calls will serialize on that
-- lock: the first increments to 50 (allowed), the second reads 50, computes
-- 51 > 50, and returns without writing (blocked). Counter never exceeds limit.
--
-- New return shape: adds `allowed boolean` so the handler branches on that
-- flag instead of re-deriving count > limit. The 429 body now uses the
-- returned count directly (no -1 needed — count is AT limit, not over it).
--
-- get_user_usage is unchanged — it already handles stale-week rollover correctly.

-- Must drop first: Postgres won't replace a function whose return type changes.
DROP FUNCTION IF EXISTS increment_user_query(uuid);

CREATE OR REPLACE FUNCTION increment_user_query(p_user_id uuid)
RETURNS TABLE(query_count int, weekly_limit int, week_start date, allowed boolean)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_monday    date := date_trunc('week', now())::date;
  v_count     int;
  v_limit     int;
  v_ws        date;
  v_new_count int;
BEGIN
  -- Ensure a row exists without overwriting real data.
  -- count=0 is a safe sentinel for a brand-new user; Case 2 below treats it
  -- as 0+1=1 which is always ≤ the default limit of 50.
  INSERT INTO user_usage (user_id, query_count, week_start, weekly_limit)
  VALUES (p_user_id, 0, v_monday, 50)
  ON CONFLICT (user_id) DO NOTHING;

  -- Acquire exclusive row lock. No concurrent call can read or write this row
  -- between here and the UPDATE below (or the no-op return on block).
  SELECT u.query_count, u.weekly_limit, u.week_start
  INTO   v_count, v_limit, v_ws
  FROM   user_usage u
  WHERE  u.user_id = p_user_id
  FOR UPDATE;

  -- Case 1: week has rolled over — always allowed, atomically reset to 1.
  IF v_ws != v_monday THEN
    UPDATE user_usage
       SET query_count = 1, week_start = v_monday, updated_at = now()
     WHERE user_id = p_user_id;
    RETURN QUERY SELECT 1::int, v_limit, v_monday, true;
    RETURN;
  END IF;

  -- Case 2: same week — only write if the post-increment count stays ≤ limit.
  v_new_count := v_count + 1;
  IF v_new_count <= v_limit THEN
    -- Allowed: write the increment.
    UPDATE user_usage
       SET query_count = v_new_count, updated_at = now()
     WHERE user_id = p_user_id;
    RETURN QUERY SELECT v_new_count, v_limit, v_ws, true;
  ELSE
    -- Blocked: return current count (at limit) without any write.
    RETURN QUERY SELECT v_count, v_limit, v_ws, false;
  END IF;
END;
$$;
