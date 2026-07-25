-- 068_deletion_requests.sql
-- Account deletion requests -- stub for the account panel's "Delete account"
-- action. Logs a request for manual admin follow-up. Does NOT delete any
-- data itself -- real cascading deletion is a future migration.
--
-- Backend uses SUPABASE_SERVICE_KEY (service_role, BYPASSRLS) for all writes.
-- RLS is defense-in-depth against anon-key access.


-- -- 1. deletion_requests ----------------------------------------------------

CREATE TABLE IF NOT EXISTS deletion_requests (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  email       text        NOT NULL,
  status      text        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'resolved')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

-- At most one pending request per user at a time
CREATE UNIQUE INDEX IF NOT EXISTS deletion_requests_one_pending_idx
  ON deletion_requests (user_id)
  WHERE status = 'pending';


-- -- 2. RLS --------------------------------------------------------------------
--
-- Pattern used throughout this project (see migration 038):
--   - service_role bypass covers all backend writes
--   - authenticated policies scope to auth.uid()
--   - anon role has no matching policy -- denied by default

ALTER TABLE deletion_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "deletion_requests: own rows read"
  ON deletion_requests FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "deletion_requests: own row insert"
  ON deletion_requests FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "deletion_requests: service role full access"
  ON deletion_requests FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
