-- Migration 014: Daily query limit for authenticated users
-- Tracks query count per user per day, resets at midnight UTC

CREATE TABLE IF NOT EXISTS user_daily_usage (
    user_id UUID NOT NULL,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    query_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, usage_date)
);

-- RLS: users can only see their own usage
ALTER TABLE user_daily_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own usage"
    ON user_daily_usage FOR SELECT
    USING (auth.uid() = user_id);

-- Function: increment and return today's count for a user
CREATE OR REPLACE FUNCTION increment_user_daily_query(p_user_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    current_count INTEGER;
BEGIN
    INSERT INTO user_daily_usage (user_id, usage_date, query_count)
    VALUES (p_user_id, CURRENT_DATE, 1)
    ON CONFLICT (user_id, usage_date)
    DO UPDATE SET query_count = user_daily_usage.query_count + 1
    RETURNING query_count INTO current_count;

    RETURN current_count;
END;
$$;
