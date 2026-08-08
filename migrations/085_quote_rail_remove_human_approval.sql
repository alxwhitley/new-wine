-- Migration 085: quote rail -- remove the human-approval gate, add a
-- speaker-confirmation gate in its place, add the acceptance/refusal log.
--
-- REVERSES part of migration 082's design, on Alex's explicit decision
-- (2026-08-08, CLAUDE.md "Settled product decisions (2026-08-08)" --
-- per-quote human review did not scale). Migration 082's header claimed
-- "there is no code path anywhere that can set status = 'approved' without
-- a real admin-role user_id attached" -- that guarantee is intentionally
-- retired by this migration. What replaces it is not a weaker version of
-- the same guarantee; it is a different one: a candidate is approved when,
-- and only when, it passes every remaining deterministic check, human or
-- not. None of these checks are LLM/AI judgment calls -- same posture as
-- the exact-substring check they extend.
--
-- enforce_quote_approval_gates() changes:
--   REMOVED -- Gate 1 (approved_by must reference a currently-admin-role
--     user). approved_by/created_by remain NOT NULL FK columns (table-level
--     CHECK + FK, unchanged) -- so every row still names a real
--     authenticated caller for provenance, it just no longer has to be
--     checked as "currently admin" for the row to become approved.
--   UNCHANGED -- commentary exclusion, document-clearance requirement,
--     exact-substring match against the immutable snapshot.
--   ADDED -- speaker-confirmation gate: the source document's source_id
--     must equal the quote's teacher_source_id. This is the concrete,
--     checkable form the "speaker not positively confirmed" rule takes for
--     this architecture: these are written, already-attributed documents
--     (not diarized audio), so "who really said this" reduces to "does the
--     attributed teacher match the document this text actually came from" --
--     the exact gap that let a strong-content-match get attributed without
--     ID confirmation in the Savchuk case (CLAUDE.md Landmines). The admin
--     UI lets a curator pick ANY confirmed teacher from a dropdown
--     independent of which teacher's documents are being browsed -- nothing
--     upstream of this trigger enforced that the two agree.
--
-- Boundary-proximity / sentence-completeness (the other new tightening
-- rule) is deliberately NOT duplicated here -- it stays Python-only, in
-- backend/app/services/quote_verifier.py, the same accepted narrower
-- boundary already used for the per-work quote-text cap
-- (services/quotes.py's _enforce_quote_cap docstring). There is exactly one
-- write path (create_and_approve_quote()) and it always runs that check
-- before this trigger ever fires.
--
-- quote_verification_log: a record, not a review queue -- nobody reads this
-- routinely. One row per create_and_approve_quote() call, capturing enough
-- to reconstruct which rule accepted or refused a candidate if a bad quote
-- ever surfaces. Written from Python (a refusal never reaches an INSERT on
-- `quotes` at all, so the DB trigger cannot be where this is logged).
--
-- Rollback (fully reversible, no data loss to any existing table):
--   DROP TABLE quote_verification_log
--   -- then re-apply migration 082's original enforce_quote_approval_gates()
--   -- definition verbatim to restore Gate 1 and drop the speaker gate.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools
-- (Session Routing: database-write session, plain script path).


-- ── PART 1: quote_verification_log ───────────────────────────────────────────

CREATE TABLE quote_verification_log (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id              uuid        REFERENCES chunks(id),
  document_id           uuid        REFERENCES documents(id),
  teacher_source_id     uuid        REFERENCES sources(id),
  candidate_quote_text  text        NOT NULL,
  decision              text        NOT NULL CHECK (decision IN ('accepted', 'refused')),
  rule                  text        NOT NULL,
  reason                text,
  submitted_by          uuid        REFERENCES auth.users(id),
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_quote_verification_log_decision ON quote_verification_log(decision);
CREATE INDEX idx_quote_verification_log_chunk_id ON quote_verification_log(chunk_id);
CREATE INDEX idx_quote_verification_log_created_at ON quote_verification_log(created_at);

COMMENT ON TABLE quote_verification_log IS
  'Every quote-candidate decision, accepted or refused, since the human-approval gate was removed (migration 085, 2026-08-08). Not a review queue -- a reconstruction record.';

ALTER TABLE quote_verification_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "quote_verification_log: service role full access"
  ON quote_verification_log FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');


-- ── PART 2: enforce_quote_approval_gates() -- drop Gate 1, add speaker gate ──

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

  IF NEW.approved_by IS NULL THEN
    RAISE EXCEPTION 'quotes: approved_by is required to approve a quote';
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

  -- Gate (new, migration 085): the attributed teacher must be the document's
  -- own source -- a strong content match is not confirmation (the Savchuk
  -- case this rule exists for). No human catches a mismatched dropdown
  -- selection now, so this is structural, not a UI default.
  IF v_document_source_id IS DISTINCT FROM NEW.teacher_source_id THEN
    RAISE EXCEPTION 'quotes: teacher_source_id % does not match the source document''s own source_id % -- speaker not positively confirmed', NEW.teacher_source_id, v_document_source_id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
