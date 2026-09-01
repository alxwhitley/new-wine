-- Migration 097: versioned source-passage policy classifications
--
-- Internal metadata only. This migration does not register sources, ingest
-- content, change source visibility, or wire retrieval and answer generation.
-- Classification history is retained while its chunk exists. A current row
-- may only be demoted to non-current and every other update or delete fails.
--
-- Rollback requires an attended decision because dropping the table destroys
-- policy history. No rollback command is embedded in this migration.

CREATE TABLE source_passage_policy_versions (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id              uuid        NOT NULL REFERENCES chunks (id) ON DELETE RESTRICT,
  policy_class          text        NOT NULL,
  protected_topic_keys  text[]      NOT NULL DEFAULT '{}',
  issue_key             text,
  viewpoint_key         text,
  classifier_kind       text        NOT NULL,
  rule_version          text        NOT NULL,
  model                 text,
  prompt_fingerprint    text,
  reason_codes          text[]      NOT NULL,
  is_current            boolean     NOT NULL DEFAULT true,
  created_at            timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT source_passage_policy_versions_policy_class_check CHECK (
    policy_class IN ('general_context', 'orthodox_viewpoint', 'protected_spirit_filled', 'mixed', 'uncertain')
  ),
  CONSTRAINT source_passage_policy_versions_classifier_kind_check CHECK (
    classifier_kind IN ('deterministic', 'model')
  ),
  CONSTRAINT source_passage_policy_versions_classifier_metadata_check CHECK (
    (
      classifier_kind = 'deterministic'
      AND model IS NULL
      AND prompt_fingerprint IS NULL
    )
    OR
    (
      classifier_kind = 'model'
      AND model IS NOT NULL
      AND btrim(model) <> ''
      AND prompt_fingerprint IS NOT NULL
      AND btrim(prompt_fingerprint) <> ''
    )
  ),
  CONSTRAINT source_passage_policy_versions_rule_version_check CHECK (
    btrim(rule_version) <> ''
  ),
  CONSTRAINT source_passage_policy_versions_reason_codes_check CHECK (
    cardinality(reason_codes) > 0
    AND array_position(reason_codes, NULL) IS NULL
  ),
  CONSTRAINT source_passage_policy_versions_protected_topics_check CHECK (
    array_position(protected_topic_keys, NULL) IS NULL
    AND protected_topic_keys <@ ARRAY[
      'continuation_of_gifts',
      'tongues',
      'baptism_holy_spirit',
      'divine_healing',
      'healing_mechanics',
      'apostolic_authority',
      'modern_apostles_and_prophets',
      'prophetic_accountability',
      'deliverance_spiritual_warfare',
      'anointing_impartation_manifestations',
      'hearing_god_and_revelation',
      'revival_signs_and_wonders'
    ]::text[]
  ),
  CONSTRAINT source_passage_policy_versions_issue_key_check CHECK (
    issue_key IS NULL OR issue_key ~ '^[a-z][a-z0-9_]*$'
  ),
  CONSTRAINT source_passage_policy_versions_viewpoint_key_check CHECK (
    viewpoint_key IS NULL OR viewpoint_key ~ '^[a-z][a-z0-9_]*$'
  ),
  CONSTRAINT source_passage_policy_versions_policy_metadata_check CHECK (
    (
      policy_class = 'general_context'
      AND cardinality(protected_topic_keys) = 0
      AND issue_key IS NULL
      AND viewpoint_key IS NULL
    )
    OR
    (
      policy_class = 'orthodox_viewpoint'
      AND cardinality(protected_topic_keys) = 0
      AND issue_key IS NOT NULL
      AND viewpoint_key IS NOT NULL
    )
    OR
    (
      policy_class = 'protected_spirit_filled'
      AND cardinality(protected_topic_keys) > 0
      AND issue_key IS NULL
      AND viewpoint_key IS NULL
    )
    OR
    (
      policy_class IN ('mixed', 'uncertain')
      AND issue_key IS NULL
      AND viewpoint_key IS NULL
    )
  )
);

CREATE INDEX source_passage_policy_versions_chunk_id_idx
  ON source_passage_policy_versions (chunk_id);

CREATE UNIQUE INDEX source_passage_policy_versions_one_current_idx
  ON source_passage_policy_versions (chunk_id)
  WHERE is_current;

CREATE OR REPLACE FUNCTION enforce_source_passage_policy_history()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'UPDATE'
     AND OLD.is_current
     AND NOT NEW.is_current
     AND NEW.id IS NOT DISTINCT FROM OLD.id
     AND NEW.chunk_id IS NOT DISTINCT FROM OLD.chunk_id
     AND NEW.policy_class IS NOT DISTINCT FROM OLD.policy_class
     AND NEW.protected_topic_keys IS NOT DISTINCT FROM OLD.protected_topic_keys
     AND NEW.issue_key IS NOT DISTINCT FROM OLD.issue_key
     AND NEW.viewpoint_key IS NOT DISTINCT FROM OLD.viewpoint_key
     AND NEW.classifier_kind IS NOT DISTINCT FROM OLD.classifier_kind
     AND NEW.rule_version IS NOT DISTINCT FROM OLD.rule_version
     AND NEW.model IS NOT DISTINCT FROM OLD.model
     AND NEW.prompt_fingerprint IS NOT DISTINCT FROM OLD.prompt_fingerprint
     AND NEW.reason_codes IS NOT DISTINCT FROM OLD.reason_codes
     AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
  THEN
    RETURN NEW;
  END IF;

  RAISE EXCEPTION 'source_passage_policy_versions history rows are append-only';
END;
$$ LANGUAGE plpgsql SET search_path = '';

CREATE TRIGGER source_passage_policy_versions_append_only
  BEFORE UPDATE OR DELETE ON source_passage_policy_versions
  FOR EACH ROW EXECUTE FUNCTION enforce_source_passage_policy_history();

ALTER TABLE source_passage_policy_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "source_passage_policy_versions: service role read"
  ON source_passage_policy_versions FOR SELECT TO service_role
  USING (true);

CREATE POLICY "source_passage_policy_versions: service role insert"
  ON source_passage_policy_versions FOR INSERT TO service_role
  WITH CHECK (true);

CREATE POLICY "source_passage_policy_versions: service role demote current"
  ON source_passage_policy_versions FOR UPDATE TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "source_passage_policy_versions: analysis read"
  ON source_passage_policy_versions FOR SELECT TO newwine_readonly_analysis
  USING (true);

REVOKE ALL ON source_passage_policy_versions FROM anon, authenticated;
REVOKE ALL ON source_passage_policy_versions FROM service_role;
GRANT SELECT, INSERT, UPDATE ON source_passage_policy_versions TO service_role;
GRANT SELECT ON source_passage_policy_versions TO newwine_readonly_analysis;

REVOKE ALL ON FUNCTION enforce_source_passage_policy_history() FROM PUBLIC, anon, authenticated;
