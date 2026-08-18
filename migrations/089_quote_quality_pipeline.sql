-- 089_quote_quality_pipeline.sql
-- Passage-level topic ids + quality pipeline provenance + selection eligibility
-- for the quote-quality rebuild (Settled #29 —
-- docs/superpowers/specs/2026-08-19-quote-quality-and-topic-design.md).
--
-- Legacy rows (quality_pipeline_version IS NULL) are marked
-- selection_eligible=false. While QUOTE_SELECTION_ENABLED is off they are
-- already unserved. This makes live-but-unserved into explicitly
-- unselectable before any attended re-enable.
--
-- No semicolon inside -- comments (Invariant 9).
-- Do not re-apply blindly — use scripts/apply_migration_089.py --apply.


ALTER TABLE quotes
  ADD COLUMN IF NOT EXISTS topic_ids text[],
  ADD COLUMN IF NOT EXISTS quality_pipeline_version text,
  ADD COLUMN IF NOT EXISTS selection_eligible boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN quotes.topic_ids IS
  'Passage-level taxonomy tags from scripts/taxonomy.py VALID_TAGS. NULL on legacy rows that inherited documents.topic_tags[0] into topic only.';

COMMENT ON COLUMN quotes.quality_pipeline_version IS
  'NULL = legacy / pre-quality-pipeline. Non-null (e.g. quote_quality_v1) = produced under the Settled #29 propose+quality+verify path.';

COMMENT ON COLUMN quotes.selection_eligible IS
  'When false, select_quotes_for_answer must ignore the row even if status=approved. Legacy backfill sets false where quality_pipeline_version IS NULL.';

-- Explicit: legacy corpus is not the v1 serving set.
UPDATE quotes
SET selection_eligible = false
WHERE quality_pipeline_version IS NULL
  AND selection_eligible IS DISTINCT FROM false;

CREATE INDEX IF NOT EXISTS quotes_selection_eligible_idx
  ON quotes (selection_eligible)
  WHERE status = 'approved' AND selection_eligible = true;

CREATE INDEX IF NOT EXISTS quotes_quality_pipeline_version_idx
  ON quotes (quality_pipeline_version)
  WHERE quality_pipeline_version IS NOT NULL;
