-- Migration 086: allow 'pending' status on quotes
--
-- The quote rail originally supported draft / approved / revoked.  Curation
-- workflows need an explicit 'pending' state for machine-extracted candidates
-- that have passed the verifier but are awaiting human review before they may
-- be served.  Adding 'pending' does not change any existing row and does not
-- weaken the approval gates: the DB trigger still fires only when status is
-- set to 'approved', and resolve_quote() still returns only approved quotes.

ALTER TABLE quotes
  DROP CONSTRAINT IF EXISTS quotes_status_check;

ALTER TABLE quotes
  ADD CONSTRAINT quotes_status_check
  CHECK (status IN ('draft', 'pending', 'approved', 'revoked'));
