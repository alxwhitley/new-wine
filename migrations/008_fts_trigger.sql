-- Migration 008: Auto-populate fts column on chunk insert/update
-- Required because fts is a plain nullable column (not generated)
-- due to Supabase maintenance_work_mem constraints.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-07

CREATE OR REPLACE FUNCTION chunks_fts_update() RETURNS trigger AS $$
BEGIN
  NEW.fts := to_tsvector('english', coalesce(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_fts_trigger ON chunks;

CREATE TRIGGER chunks_fts_trigger
  BEFORE INSERT OR UPDATE OF content
  ON chunks
  FOR EACH ROW
  EXECUTE FUNCTION chunks_fts_update();
