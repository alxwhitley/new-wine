-- Migration 094: Deletion audit log (Packet 4, Task 4.2 of the 2026-08-28
-- back-to-back completion queue -- account deletion is being made real).
--
-- deletion_requests.user_id CASCADEs when the referenced auth.users row is
-- deleted, so the request row that started a deletion disappears along with
-- the account it was about. Without a separate record, there would be no
-- queryable proof a deletion ever happened -- a real gap the 2026-08-19
-- scope audit already flagged (docs/audits/2026-08/b4_account_deletion_scope_2026-08-19.md).
--
-- deleted_user_id and original_request_id are deliberately plain uuid
-- columns with NO foreign key -- by the time this row is written, both the
-- account and the original request row are already gone. This table is the
-- one thing that survives: an email address and three timestamps, nothing
-- else. resolved_by DOES keep a real FK to auth.users, since the admin who
-- performed the deletion is expected to still have an account.
--
-- Deletion is fail-closed on resolution, not on the Auth API call alone --
-- outcome only becomes 'resolved' after every owned table is re-queried and
-- confirmed empty (backend/app/services/account_deletion.py); a 'failed'
-- row still records what was attempted, with a reason, so a retry has
-- something to reconcile against.
--
-- Same posture as migration 093: RLS-enabled, service-role-only. The
-- Contributors admin tab reads this table for resolved/failed deletion
-- history alongside deletion_requests for pending rows.
--
-- Also widens deletion_requests.status's existing CHECK
-- (deletion_requests_status_check, confirmed live today: only 'pending'
-- and 'resolved' were ever permitted) to add 'failed' -- the
-- terminal-but-retryable state a deletion attempt reaches when the Auth
-- API call or post-delete reconciliation doesn't succeed, distinct from
-- 'resolved' per this queue's own boundary that a request may not become
-- resolved while owned data or the Auth account still exists.
--
-- Rollback (fully reversible, no data loss to any existing table):
--   DROP TABLE deletion_audit_log
--   ALTER TABLE deletion_requests DROP CONSTRAINT deletion_requests_status_check
--   ALTER TABLE deletion_requests ADD CONSTRAINT deletion_requests_status_check
--     CHECK (status = ANY (ARRAY['pending'::text, 'resolved'::text]))
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.
-- Invariant 9: no semicolons inside -- comments.


CREATE TABLE deletion_audit_log (
  id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  original_request_id  uuid        NOT NULL,
  deleted_user_id      uuid        NOT NULL,
  email                text        NOT NULL,
  requested_at         timestamptz NOT NULL,
  resolved_at          timestamptz NOT NULL,
  resolved_by          uuid        NOT NULL REFERENCES auth.users(id),
  outcome              text        NOT NULL CHECK (outcome IN ('resolved', 'failed')),
  reconciliation       jsonb       NOT NULL,
  failure_reason       text
);

ALTER TABLE deletion_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "deletion_audit_log: service role full access"
  ON deletion_audit_log FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
REVOKE ALL ON TABLE deletion_audit_log FROM anon, authenticated;

CREATE INDEX deletion_audit_log_deleted_user_id_idx ON deletion_audit_log (deleted_user_id);


-- ── PART 2: widen deletion_requests.status, add a failure reason ───────────

ALTER TABLE deletion_requests DROP CONSTRAINT deletion_requests_status_check;
ALTER TABLE deletion_requests ADD CONSTRAINT deletion_requests_status_check
  CHECK (status = ANY (ARRAY['pending'::text, 'resolved'::text, 'failed'::text]));

ALTER TABLE deletion_requests ADD COLUMN failure_reason text;
