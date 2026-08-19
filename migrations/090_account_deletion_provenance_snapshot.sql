-- 090_account_deletion_provenance_snapshot.sql
-- Unblocks real account deletion for the 4 tables whose actor-tracking FK to
-- auth.users has no ON DELETE action (defaults NO ACTION) -- confirmed live
-- 2026-08-19 (docs/audits/2026-08/b4_account_deletion_scope_2026-08-19.md):
-- deleting either of the 2 real accounts referenced across quotes/
-- quote_source_revisions/document_quote_clearance today would raise a live
-- FK-violation error, not "isn't built yet."
--
-- Design (Alex's explicit choice, 2026-08-19, chosen over a sentinel
-- "deleted user" account or CASCADE): snapshot + nullable FK. Each affected
-- actor column gets a companion *_email snapshot, captured by the
-- application at write time going forward (backend/app/auth.py's new
-- resolve_user_email(), wired into backend/app/services/quotes.py and
-- backend/app/routers/pastors_notes.py -- same commit as this migration).
-- This migration adds the columns and backfills existing rows from
-- auth.users. The live FK itself becomes ON DELETE SET NULL. This preserves
-- WHO did something as a permanent, readable fact even after the account is
-- gone (a real email, not a synthetic identity) -- deliberate, because these
-- 4 tables record actions on shared PRODUCT state (an approved quote, a
-- document's quote-clearance, a pastor's published card), not private
-- personal data. saved_words/study_pins/conversations correctly CASCADE-
-- delete already (migrations 038/039) and are UNCHANGED by this migration.
--
-- DEPLOY ORDERING: this migration and the application code that populates
-- the new *_email columns must ship together. created_by_email /
-- captured_by_email / cleared_by_email / author_email are NOT NULL going
-- forward -- old backend code running against the new schema would fail
-- every new quote/card/clearance write with a NOT-NULL violation until the
-- code deploy lands. approved_by_email / revoked_by_email stay nullable
-- (mirroring approved_by/revoked_by themselves), so they don't force this.
--
-- quotes.approved_by needed more than a column change: enforce_quote_
-- approval_gates() (082, tightened 085) and the quotes_check CHECK
-- constraint both unconditionally reject a NULL approved_by on any row
-- with status='approved' -- including the FK's own SET NULL action, which
-- is itself an UPDATE. Both are narrowed here to only require a real
-- approved_by at the moment a row TRANSITIONS into 'approved' (INSERT, or
-- UPDATE from a non-approved status); once a row is already approved,
-- later clearing approved_by (only ever via this FK's cascade in practice)
-- is now permitted. approved_at (the timestamp) stays required
-- unconditionally either way -- only the actor pointer becomes nullable
-- post-approval, not the fact that approval happened. Gate 2 (commentary),
-- Gate 3 (clearance), Gate 4 (exact-substring), and the speaker-
-- confirmation gate are BYTE-IDENTICAL to migration 085's version, not
-- touched. Same narrowing applied to quotes_check1 (revoked_by) for
-- symmetry, though no trigger logic reads revoked_by today.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools
-- (Session Routing: database-write session, plain script path, attended).
--
-- Rollback (fully reversible -- the *_email columns are purely additive and
-- can safely stay even on rollback if preferred):
--   ALTER TABLE pastors_cards DROP CONSTRAINT pastors_cards_user_id_fkey;
--   ALTER TABLE pastors_cards ALTER COLUMN user_id SET NOT NULL;
--   ALTER TABLE pastors_cards ADD CONSTRAINT pastors_cards_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id);
--   -- (repeat the DROP/ADD FK + SET NOT NULL pattern for
--   -- quote_source_revisions.captured_by, document_quote_clearance.cleared_by,
--   -- and quotes.created_by, then re-apply migration 085's
--   -- enforce_quote_approval_gates() definition verbatim and restore
--   -- quotes_check/quotes_check1 to their original AND-based form.)


-- ── PART 1: pastors_cards ───────────────────────────────────────────────────

ALTER TABLE pastors_cards ADD COLUMN author_email text;

UPDATE pastors_cards
SET author_email = (SELECT email FROM auth.users WHERE id = pastors_cards.user_id)
WHERE author_email IS NULL;

ALTER TABLE pastors_cards ALTER COLUMN author_email SET NOT NULL;

ALTER TABLE pastors_cards DROP CONSTRAINT pastors_cards_user_id_fkey;
ALTER TABLE pastors_cards ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE pastors_cards ADD CONSTRAINT pastors_cards_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;


-- ── PART 2: quote_source_revisions ──────────────────────────────────────────

ALTER TABLE quote_source_revisions ADD COLUMN captured_by_email text;

UPDATE quote_source_revisions
SET captured_by_email = (SELECT email FROM auth.users WHERE id = quote_source_revisions.captured_by)
WHERE captured_by_email IS NULL;

ALTER TABLE quote_source_revisions ALTER COLUMN captured_by_email SET NOT NULL;

ALTER TABLE quote_source_revisions DROP CONSTRAINT quote_source_revisions_captured_by_fkey;
ALTER TABLE quote_source_revisions ALTER COLUMN captured_by DROP NOT NULL;
ALTER TABLE quote_source_revisions ADD CONSTRAINT quote_source_revisions_captured_by_fkey
  FOREIGN KEY (captured_by) REFERENCES auth.users(id) ON DELETE SET NULL;


-- ── PART 3: document_quote_clearance ────────────────────────────────────────

ALTER TABLE document_quote_clearance ADD COLUMN cleared_by_email text;

UPDATE document_quote_clearance
SET cleared_by_email = (SELECT email FROM auth.users WHERE id = document_quote_clearance.cleared_by)
WHERE cleared_by_email IS NULL;

ALTER TABLE document_quote_clearance ALTER COLUMN cleared_by_email SET NOT NULL;

ALTER TABLE document_quote_clearance DROP CONSTRAINT document_quote_clearance_cleared_by_fkey;
ALTER TABLE document_quote_clearance ALTER COLUMN cleared_by DROP NOT NULL;
ALTER TABLE document_quote_clearance ADD CONSTRAINT document_quote_clearance_cleared_by_fkey
  FOREIGN KEY (cleared_by) REFERENCES auth.users(id) ON DELETE SET NULL;


-- ── PART 4: quotes ───────────────────────────────────────────────────────────

ALTER TABLE quotes ADD COLUMN created_by_email text;
ALTER TABLE quotes ADD COLUMN approved_by_email text;
ALTER TABLE quotes ADD COLUMN revoked_by_email text;

UPDATE quotes
SET created_by_email = (SELECT email FROM auth.users WHERE id = quotes.created_by)
WHERE created_by_email IS NULL;

UPDATE quotes
SET approved_by_email = (SELECT email FROM auth.users WHERE id = quotes.approved_by)
WHERE approved_by IS NOT NULL AND approved_by_email IS NULL;

UPDATE quotes
SET revoked_by_email = (SELECT email FROM auth.users WHERE id = quotes.revoked_by)
WHERE revoked_by IS NOT NULL AND revoked_by_email IS NULL;

ALTER TABLE quotes ALTER COLUMN created_by_email SET NOT NULL;
-- approved_by_email / revoked_by_email stay nullable at the column level --
-- mirroring approved_by/revoked_by themselves (a draft/never-revoked quote
-- has neither).

ALTER TABLE quotes DROP CONSTRAINT quotes_created_by_fkey;
ALTER TABLE quotes ALTER COLUMN created_by DROP NOT NULL;
ALTER TABLE quotes ADD CONSTRAINT quotes_created_by_fkey
  FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE SET NULL;

ALTER TABLE quotes DROP CONSTRAINT quotes_approved_by_fkey;
ALTER TABLE quotes ADD CONSTRAINT quotes_approved_by_fkey
  FOREIGN KEY (approved_by) REFERENCES auth.users(id) ON DELETE SET NULL;

ALTER TABLE quotes DROP CONSTRAINT quotes_revoked_by_fkey;
ALTER TABLE quotes ADD CONSTRAINT quotes_revoked_by_fkey
  FOREIGN KEY (revoked_by) REFERENCES auth.users(id) ON DELETE SET NULL;

-- Narrow both status CHECKs: require the TIMESTAMP unconditionally, but no
-- longer require the ACTOR pointer to survive forever -- the *_email
-- snapshot is now the permanent record of who, once the live account is
-- gone.
ALTER TABLE quotes DROP CONSTRAINT quotes_check;
ALTER TABLE quotes ADD CONSTRAINT quotes_check
  CHECK (status <> 'approved' OR approved_at IS NOT NULL);

ALTER TABLE quotes DROP CONSTRAINT quotes_check1;
ALTER TABLE quotes ADD CONSTRAINT quotes_check1
  CHECK (status <> 'revoked' OR revoked_at IS NOT NULL);

-- Narrow enforce_quote_approval_gates(): approved_by is still required at
-- the moment a row TRANSITIONS into 'approved' (fresh INSERT, or UPDATE
-- from a non-approved status) -- an already-approved row having approved_by
-- cleared later (only ever by this migration's own FK cascade in practice)
-- no longer re-raises. Gates 2-4 and the speaker-confirmation gate are
-- byte-identical to migration 085's version, not touched. The trigger
-- itself (trg_enforce_quote_approval_gates, WHEN (NEW.status = 'approved'))
-- is unchanged -- only CREATE OR REPLACE on the function body, same
-- mechanism migration 085 used.
CREATE OR REPLACE FUNCTION enforce_quote_approval_gates()
RETURNS trigger AS $$
DECLARE
  v_document_id       uuid;
  v_document_source_id uuid;
  v_source_kind        text;
  v_passage_text        text;
  v_is_cleared          boolean;
BEGIN
  IF NEW.status <> 'approved' THEN
    RETURN NEW;
  END IF;

  IF TG_OP = 'INSERT' THEN
    IF NEW.approved_by IS NULL THEN
      RAISE EXCEPTION 'quotes: approved_by is required to approve a quote';
    END IF;
  ELSIF OLD.status IS DISTINCT FROM 'approved' THEN
    IF NEW.approved_by IS NULL THEN
      RAISE EXCEPTION 'quotes: approved_by is required to approve a quote';
    END IF;
  END IF;

  -- Resolve the source document + its committed passage snapshot.
  SELECT c.document_id, d.source_kind, d.source_id, sr.passage_text
    INTO v_document_id, v_source_kind, v_document_source_id, v_passage_text
  FROM quote_source_revisions sr
  JOIN chunks c ON c.id = sr.chunk_id
  JOIN documents d ON d.id = c.document_id
  WHERE sr.id = NEW.source_revision_id;

  IF v_document_id IS NULL THEN
    RAISE EXCEPTION 'quotes: source_revision % does not resolve to a document', NEW.source_revision_id;
  END IF;

  -- Gate: commentary is a permanent, hard exclude -- never scoped to one teacher.
  IF v_source_kind = 'commentary' THEN
    RAISE EXCEPTION 'quotes: source document % is commentary-tagged -- commentaries may never be quoted', v_document_id;
  END IF;

  -- Gate: the source document must have been affirmatively cleared.
  SELECT EXISTS (
    SELECT 1 FROM document_quote_clearance WHERE document_id = v_document_id
  ) INTO v_is_cleared;
  IF NOT v_is_cleared THEN
    RAISE EXCEPTION 'quotes: source document % has not been affirmatively cleared for quoting', v_document_id;
  END IF;

  -- Gate: exact-substring match against the committed snapshot, fail-closed.
  IF position(NEW.quote_text IN v_passage_text) = 0 THEN
    RAISE EXCEPTION 'quotes: quote_text is not an exact substring of its captured source passage';
  END IF;

  -- Gate: the attributed teacher must be the document's own source -- a
  -- strong content match is not confirmation (the Savchuk case this rule
  -- exists for).
  IF v_document_source_id IS DISTINCT FROM NEW.teacher_source_id THEN
    RAISE EXCEPTION 'quotes: teacher_source_id % does not match the source document''s own source_id % -- speaker not positively confirmed', NEW.teacher_source_id, v_document_source_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
