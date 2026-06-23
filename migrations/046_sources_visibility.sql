-- Migration 046: Replace sources.visible (boolean) with sources.visibility (text)
-- Behavior-neutral: reshapes the column, changes nothing about what is served.
-- DEFAULT 'hidden' preserves the fail-closed guarantee: future entities arrive
-- hidden until explicitly shown. All 40 existing entities migrate to 'shown'.
-- Created: 2026-06-23

ALTER TABLE sources
  ADD COLUMN visibility text NOT NULL DEFAULT 'hidden'
    CHECK (visibility IN ('shown', 'hidden'));

UPDATE sources
  SET visibility = CASE WHEN visible THEN 'shown' ELSE 'hidden' END;

ALTER TABLE sources DROP COLUMN visible;
