-- Migration 067: propositions provenance columns
-- Records what actually produced each proposition row, so a future
-- fabrication sweep is a lookup instead of a manual text search and git
-- archaeology (as required for the 2026-07-23 leak diagnostic).
--
-- Three columns, all nullable -- existing rows have no provenance and must
-- not be blocked by a NOT NULL constraint. Existing rows get an explicit
-- legacy marker in a follow-up UPDATE (Phase 4), not in this migration --
-- this migration only adds the columns.
--
-- prompt_version    -- human-chosen label for which named revision of the
--                       extraction instructions was used ("v3", "v4", etc).
--                       Manually maintained by whoever edits the prompt.
--                       Convenient for scanning results, but NOT trusted
--                       for investigation on its own -- see prompt_fingerprint.
-- prompt_fingerprint -- SHA-256 hex digest of the exact, complete instruction
--                       text actually used for that specific call (the full
--                       template selected for that call, before any per-
--                       document or per-teacher substitution is filled in --
--                       so calls sharing one batch's instructions share one
--                       fingerprint, regardless of which teacher or content
--                       type routed to that template). Computed automatically
--                       at generation time, never hand-maintained, so it
--                       cannot drift out of sync with the real wording the
--                       way prompt_version already has (the sentence-
--                       structure fix and the terminology-rename pass both
--                       kept the "v4" label while the actual wording changed
--                       twice). Authoritative over prompt_version whenever
--                       the two disagree.
-- model             -- literal model identifier the call was made to (e.g.
--                       llama-3.3-70b-versatile). Records what was
--                       REQUESTED, not a guarantee of what code actually
--                       ran behind that name on the provider's side --
--                       a provider can change a model's behavior without
--                       changing its name.
-- Created: 2026-07-23

ALTER TABLE propositions
  ADD COLUMN IF NOT EXISTS prompt_version text,
  ADD COLUMN IF NOT EXISTS prompt_fingerprint text,
  ADD COLUMN IF NOT EXISTS model text;

-- Indexes for the investigative use case this exists for: "find everything
-- that came from this specific instruction version" (prompt_fingerprint,
-- the authoritative key) and "find everything labeled this way" (
-- prompt_version, for quick scanning). Table is small today (~2,400 rows)
-- but will grow through the pending backfill.
CREATE INDEX IF NOT EXISTS propositions_prompt_fingerprint_idx
  ON propositions (prompt_fingerprint);

CREATE INDEX IF NOT EXISTS propositions_prompt_version_idx
  ON propositions (prompt_version);
