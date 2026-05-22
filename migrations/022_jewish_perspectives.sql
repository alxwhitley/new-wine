-- Migration 022: Jewish Perspective cache table
-- Run in Supabase SQL Editor.
-- Created: 2026-05-22

CREATE TABLE jewish_perspectives (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  verse_reference text UNIQUE NOT NULL,
  content jsonb NOT NULL,
  generated_at timestamptz DEFAULT now(),
  model text NOT NULL
);

CREATE INDEX idx_jewish_perspectives_verse ON jewish_perspectives (verse_reference);

ALTER TABLE jewish_perspectives ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read jewish_perspectives"
  ON jewish_perspectives FOR SELECT
  USING (true);

CREATE POLICY "Service role can insert jewish_perspectives"
  ON jewish_perspectives FOR INSERT
  WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "Service role can update jewish_perspectives"
  ON jewish_perspectives FOR UPDATE
  USING (auth.role() = 'service_role');
