-- Migration 019: Admin source toggles table
-- Allows admin to enable/disable source categories at runtime.
-- Run in Supabase SQL Editor.
-- Created: 2026-05-22

CREATE TABLE source_toggles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_identifier text UNIQUE NOT NULL,
  identifier_type text NOT NULL,  -- 'source_kind', 'source_name', or 'global'
  label text NOT NULL,
  enabled boolean DEFAULT true NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- Seed rows
INSERT INTO source_toggles (source_identifier, identifier_type, label, enabled) VALUES
  ('word_study',        'source_kind',  'Precept Austin Word Studies',  true),
  ('sermon_transcript', 'source_kind',  'YouTube Sermons',              true),
  ('commentary',        'source_kind',  'Historical Commentaries',      true),
  ('magazine_article',  'source_kind',  'New Wine Magazine',            true),
  ('Derek Prince',      'source_name',  'Derek Prince Sermons',         true),
  ('copyrighted',       'global',       'Copyrighted Content',          true);

-- RLS: public can read, only service role can update
ALTER TABLE source_toggles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read source_toggles"
  ON source_toggles FOR SELECT
  USING (true);

CREATE POLICY "Service role can update source_toggles"
  ON source_toggles FOR UPDATE
  USING (auth.role() = 'service_role');

CREATE POLICY "Service role can insert source_toggles"
  ON source_toggles FOR INSERT
  WITH CHECK (auth.role() = 'service_role');
