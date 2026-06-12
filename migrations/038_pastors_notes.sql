-- 038_pastors_notes.sql
-- Pastors' Notes — Phase 1: schema, indexes, RLS.
-- Run manually in the Supabase SQL Editor. Do not run via script.
--
-- Backend uses SUPABASE_SERVICE_KEY (service_role, BYPASSRLS) for all writes.
-- RLS is defense-in-depth against anon-key access.


-- ── 1. user_roles ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_roles (
  user_id      uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role         text        NOT NULL DEFAULT 'user'
                           CHECK (role IN ('user', 'contributor', 'admin')),
  display_name text        UNIQUE,
  granted_by   uuid        REFERENCES auth.users(id),
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Seed: grant admin role to the project owner. UUID looked up by email — not hardcoded.
INSERT INTO user_roles (user_id, role)
SELECT id, 'admin'
FROM auth.users
WHERE email = 'alxwhitley@gmail.com'
ON CONFLICT (user_id) DO UPDATE SET role = 'admin';


-- ── 2. contributor_requests ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS contributor_requests (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  message     text,
  status      text        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'approved', 'rejected', 'revoked')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  reviewed_by uuid        REFERENCES auth.users(id)
);

-- At most one pending request per user at a time
CREATE UNIQUE INDEX IF NOT EXISTS contributor_requests_one_pending_idx
  ON contributor_requests (user_id)
  WHERE status = 'pending';


-- ── 3. pastors_cards ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pastors_cards (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES auth.users(id),
  verse_id    text        NOT NULL,  -- format: JHN.1.1, matches verses table
  content     text        NOT NULL CHECK (char_length(content) BETWEEN 50 AND 2000),
  topic_tags  text[]      NOT NULL DEFAULT '{}',
  status      text        NOT NULL DEFAULT 'published'
                          CHECK (status IN ('published', 'removed')),
  embedding   vector(1536),          -- NULL for now; backfillable later
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pastors_cards_verse_status_idx
  ON pastors_cards (verse_id, status);

CREATE INDEX IF NOT EXISTS pastors_cards_user_idx
  ON pastors_cards (user_id);


-- ── 4. RLS ────────────────────────────────────────────────────────────────────
--
-- Pattern used throughout this project (see migration 037):
--   - service_role bypass covers all backend writes
--   - authenticated policies scope to auth.uid()
--   - anon role has no matching policy → denied by default

-- user_roles: each user can read only their own row; no anon access
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_roles: own row read"
  ON user_roles FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "user_roles: service role full access"
  ON user_roles FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');


-- contributor_requests: users can read/insert own rows; updates only via service role
ALTER TABLE contributor_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "contributor_requests: own rows read"
  ON contributor_requests FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "contributor_requests: own row insert"
  ON contributor_requests FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "contributor_requests: service role full access"
  ON contributor_requests FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');


-- pastors_cards: public read for published only; all writes through service role
ALTER TABLE pastors_cards ENABLE ROW LEVEL SECURITY;

CREATE POLICY "pastors_cards: public read published"
  ON pastors_cards FOR SELECT
  USING (status = 'published');

CREATE POLICY "pastors_cards: service role full access"
  ON pastors_cards FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
