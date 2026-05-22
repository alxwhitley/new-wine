-- Migration 021: Add individual commentary author toggles
-- Run in Supabase SQL Editor after 019_admin_source_toggles.sql.
-- Created: 2026-05-22

INSERT INTO source_toggles (source_identifier, identifier_type, label, enabled)
VALUES
  ('Matthew Henry', 'source_name', 'Matthew Henry Commentary', true),
  ('Adam Clarke', 'source_name', 'Adam Clarke Commentary', true),
  ('Jamieson, Fausset & Brown', 'source_name', 'Jamieson-Fausset-Brown Commentary', true)
ON CONFLICT (source_identifier) DO NOTHING;
