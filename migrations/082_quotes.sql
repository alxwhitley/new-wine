-- Migration 082: Quote rail schema (Project 3, manual-curation-only)
--
-- Three new tables plus one column added to chunks. Builds the hand-curated,
-- server-gated quote rail per CLAUDE.md Settled decisions #16/#17: an AI may
-- propose a quote candidate, never approve one -- every hard rule below is
-- enforced by a trigger, not application code, because the backend connects
-- with the service_role key and bypasses RLS on every write (see migration
-- 037's own note) -- RLS cannot be the enforcement layer here, only a
-- BEFORE-fire trigger can, since triggers run regardless of role.
--
-- quote_source_revisions: an immutable snapshot of exactly one chunk's text
-- at the moment a human captured it as a quote candidate. Quotes are
-- verified against this snapshot, not a live re-read of chunks -- a later
-- edit to a chunk must never retroactively change what an already-approved
-- quote is judged against.
--
-- document_quote_clearance: one row per document a human has affirmatively
-- reviewed and cleared as safe to source quotes from. Presence of a row is
-- the only thing that counts -- absence is not-cleared, full stop, never
-- inferred from "no known problem" (CLAUDE.md Settled decision #16: "a
-- source must be AFFIRMATIVELY cleared").
--
-- quotes: the record itself. status is draft/approved/revoked. Approving is
-- gated by four hard rules, all checked in one trigger fired on every
-- INSERT or UPDATE that sets status = 'approved':
--   1. approved_by must reference a currently-admin-role user (user_roles) --
--      never null, never a system/service placeholder. This is the
--      strongest boundary this architecture can express -- the backend is a
--      single service-role connection for every write path, automated or
--      human-triggered, so the database cannot cryptographically tell a
--      human click from a script with valid credentials apart. What it CAN
--      guarantee, permanently, is that the row names a real admin-role user
--      every time, never nothing and never a fabricated identity -- the
--      actual trust boundary is the app's existing require_admin_role
--      dependency (backend/app/auth.py), which alone determines what value
--      ever reaches this column.
--   2. the source document must have a document_quote_clearance row.
--   3. the source document's source_kind must not be 'commentary' --
--      permanent, hard exclude, not scoped to any one teacher.
--   4. quote_text must be an exact substring of its source revision's
--      captured passage_text -- fail-closed, a quote that cannot be found
--      is rejected, not passed through with a warning.
--
-- A second, earlier trigger on quote_source_revisions blocks capturing a
-- snapshot from a chunk already marked quote_ineligible_reason IS NOT NULL
-- -- see the chunks.quote_ineligible_reason column below, seeded in this
-- same migration for the one confirmed exclusion zone on record (Andrew
-- Murray's "The New Life", chunks 0-5: CCEL's own editorial front matter
-- plus a translator's note signed "J.P.L.", 1891 -- not Murray's words,
-- must never be sourced as a Murray quote -- docs/audits/
-- quote_rail_project3_audit_2026-08-06.md has the full chunk-by-chunk
-- evidence for this boundary).
--
-- Automated extraction (any inline/AI-candidate generation) is explicitly
-- OUT of this migration's scope -- there is no code path anywhere that can
-- set status = 'approved' without a real admin-role user_id attached.
--
-- Rollback (fully reversible, no data loss to any existing table):
--   DROP TABLE quotes
--   DROP TABLE document_quote_clearance
--   DROP TABLE quote_source_revisions
--   DROP FUNCTION enforce_quote_approval_gates()
--   DROP FUNCTION enforce_source_revision_eligibility()
--   ALTER TABLE chunks DROP COLUMN quote_ineligible_reason
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.


-- ── PART 1: chunk-level exclusion flag ───────────────────────────────────────

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS quote_ineligible_reason text;

COMMENT ON COLUMN chunks.quote_ineligible_reason IS
  'NULL = eligible. Non-null names a specific, permanent reason this chunk may never be captured as a quote source revision -- enforced by enforce_source_revision_eligibility().';

UPDATE chunks SET quote_ineligible_reason = 'ccel_editorial_description_not_teacher_authored'
WHERE id IN (
  '722b3730-e047-4f4d-b380-c752f95bac42', -- chunk_index 0
  'aa84b382-8585-45de-9fd8-cf58f60e8bd0', -- chunk_index 1
  'ab18ebce-117c-4356-87c1-a45f0119e051'  -- chunk_index 2
);

UPDATE chunks SET quote_ineligible_reason = 'translators_note_not_teacher_authored'
WHERE id IN (
  'e8f75476-6c20-47d9-bf54-a0576ab71158', -- chunk_index 3
  'c3f1de77-fbf8-4369-a2ed-7144283c2fec', -- chunk_index 4
  '8d53499b-0561-49bf-a660-64a652a8bde0'  -- chunk_index 5 (opens with the translator's signature before Murray's own Preface begins partway through -- excluded whole per the audit's conservative recommendation)
);


-- ── PART 2: quote_source_revisions ───────────────────────────────────────────

CREATE TABLE quote_source_revisions (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id      uuid        NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  passage_text  text        NOT NULL,
  captured_by   uuid        NOT NULL REFERENCES auth.users(id),
  captured_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_quote_source_revisions_chunk_id ON quote_source_revisions(chunk_id);

ALTER TABLE quote_source_revisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "quote_source_revisions: service role full access"
  ON quote_source_revisions FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

CREATE OR REPLACE FUNCTION enforce_source_revision_eligibility()
RETURNS trigger AS $$
DECLARE
  v_reason text;
BEGIN
  SELECT quote_ineligible_reason INTO v_reason FROM chunks WHERE id = NEW.chunk_id;
  IF v_reason IS NOT NULL THEN
    RAISE EXCEPTION 'quote_source_revisions: chunk % is permanently excluded from quote sourcing (%)', NEW.chunk_id, v_reason;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_source_revision_eligibility
  BEFORE INSERT ON quote_source_revisions
  FOR EACH ROW EXECUTE FUNCTION enforce_source_revision_eligibility();


-- ── PART 3: document_quote_clearance ─────────────────────────────────────────

CREATE TABLE document_quote_clearance (
  document_id  uuid        PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  cleared_by   uuid        NOT NULL REFERENCES auth.users(id),
  cleared_at   timestamptz NOT NULL DEFAULT now(),
  note         text        NOT NULL
);

ALTER TABLE document_quote_clearance ENABLE ROW LEVEL SECURITY;
CREATE POLICY "document_quote_clearance: service role full access"
  ON document_quote_clearance FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');


-- ── PART 4: quotes ────────────────────────────────────────────────────────────

CREATE TABLE quotes (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_revision_id  uuid        NOT NULL REFERENCES quote_source_revisions(id),
  teacher_source_id   uuid        NOT NULL REFERENCES sources(id),
  quote_text          text        NOT NULL,
  topic               text        NOT NULL,
  reviewer_note        text        NOT NULL,
  status              text        NOT NULL DEFAULT 'draft'
                                  CHECK (status IN ('draft', 'approved', 'revoked')),
  created_by          uuid        NOT NULL REFERENCES auth.users(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  approved_by         uuid        REFERENCES auth.users(id),
  approved_at         timestamptz,
  revoked_by          uuid        REFERENCES auth.users(id),
  revoked_at          timestamptz,
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  CHECK (status <> 'revoked' OR (revoked_by IS NOT NULL AND revoked_at IS NOT NULL))
);

CREATE INDEX idx_quotes_status ON quotes(status);
CREATE INDEX idx_quotes_source_revision_id ON quotes(source_revision_id);
CREATE INDEX idx_quotes_teacher_source_id ON quotes(teacher_source_id);

ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "quotes: service role full access"
  ON quotes FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

CREATE OR REPLACE FUNCTION enforce_quote_approval_gates()
RETURNS trigger AS $$
DECLARE
  v_document_id     uuid;
  v_source_kind     text;
  v_passage_text    text;
  v_is_admin        boolean;
  v_is_cleared      boolean;
BEGIN
  IF NEW.status <> 'approved' THEN
    RETURN NEW;
  END IF;

  -- Gate 1: approved_by must be a currently-admin-role user. Never null,
  -- never a system/service placeholder -- see this migration's header note
  -- on why this is the strongest boundary this architecture can express.
  IF NEW.approved_by IS NULL THEN
    RAISE EXCEPTION 'quotes: approved_by is required to approve a quote';
  END IF;
  SELECT EXISTS (
    SELECT 1 FROM user_roles WHERE user_id = NEW.approved_by AND role = 'admin'
  ) INTO v_is_admin;
  IF NOT v_is_admin THEN
    RAISE EXCEPTION 'quotes: approved_by (%) is not a currently-designated admin user', NEW.approved_by;
  END IF;

  -- Resolve the source document + its committed passage snapshot.
  SELECT c.document_id, d.source_kind, sr.passage_text
    INTO v_document_id, v_source_kind, v_passage_text
  FROM quote_source_revisions sr
  JOIN chunks c ON c.id = sr.chunk_id
  JOIN documents d ON d.id = c.document_id
  WHERE sr.id = NEW.source_revision_id;

  IF v_document_id IS NULL THEN
    RAISE EXCEPTION 'quotes: source_revision % does not resolve to a document', NEW.source_revision_id;
  END IF;

  -- Gate 2: commentary is a permanent, hard exclude -- never scoped to one teacher.
  IF v_source_kind = 'commentary' THEN
    RAISE EXCEPTION 'quotes: source document % is commentary-tagged -- commentaries may never be quoted', v_document_id;
  END IF;

  -- Gate 3: the source document must have been affirmatively cleared.
  SELECT EXISTS (
    SELECT 1 FROM document_quote_clearance WHERE document_id = v_document_id
  ) INTO v_is_cleared;
  IF NOT v_is_cleared THEN
    RAISE EXCEPTION 'quotes: source document % has not been affirmatively cleared for quoting', v_document_id;
  END IF;

  -- Gate 4: exact-substring match against the committed snapshot, fail-closed.
  IF position(NEW.quote_text IN v_passage_text) = 0 THEN
    RAISE EXCEPTION 'quotes: quote_text is not an exact substring of its captured source passage';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_quote_approval_gates
  BEFORE INSERT OR UPDATE ON quotes
  FOR EACH ROW
  WHEN (NEW.status = 'approved')
  EXECUTE FUNCTION enforce_quote_approval_gates();
