-- 041_pastors_notes_approval.sql
-- Pre-publish moderation gate for Pastors' Notes.
-- Run manually in the Supabase SQL Editor. Do not run via script.
--
-- What this migration does:
--   1. Adds 'pending' to the pastors_cards status CHECK constraint.
--   2. Adds RLS policy so authenticated users can read their own pending cards.
--      (Service_role bypasses RLS for all backend writes — this is defense-in-depth.)
--   3. Creates get_user_emails RPC (CREATE OR REPLACE — safe if already exists).
--
-- Lock proof:
--   - Public/anon SELECT: "pastors_cards: public read published" USING (status='published')
--     → pending rows are invisible to any unauthenticated anon-key request.
--   - Authenticated contributor: new policy USING (auth.uid()=user_id AND status='pending')
--     → a contributor can read only their own pending rows.
--   - Admin backend reads: service_role BYPASSRLS → all rows visible (used by /pending endpoint).
--   - The application-layer GET /cards endpoint enforces these same rules independently
--     of RLS, so there is dual enforcement.


-- ── 1. Extend status CHECK to include 'pending' ───────────────────────────────

ALTER TABLE pastors_cards DROP CONSTRAINT IF EXISTS pastors_cards_status_check;

ALTER TABLE pastors_cards
  ADD CONSTRAINT pastors_cards_status_check
  CHECK (status IN ('published', 'pending', 'removed'));


-- ── 2. RLS: authenticated users may read their own pending cards ──────────────

CREATE POLICY "pastors_cards: own pending read"
  ON pastors_cards FOR SELECT
  USING (auth.uid() = user_id AND status = 'pending');


-- ── 3. get_user_emails RPC ────────────────────────────────────────────────────
-- Called by /pastors-notes/requests and /pastors-notes/contributors to resolve
-- emails from auth.users. Safe to run whether or not it already exists.

CREATE OR REPLACE FUNCTION public.get_user_emails(user_ids uuid[])
RETURNS TABLE(id uuid, email text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id, email::text FROM auth.users WHERE id = ANY(user_ids);
$$;

GRANT EXECUTE ON FUNCTION public.get_user_emails(uuid[]) TO service_role;
