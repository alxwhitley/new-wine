-- Migration 045: Add visible column to sources
-- Visibility is the curation dial — independent of license_status.
-- DEFAULT false: future entities arrive hidden (fail-closed).
-- Existing corpus entities are seeded visible=true separately in Step 3b
-- so nothing disappears when the gate goes live in Step 4.
-- Created: 2026-06-23

ALTER TABLE sources ADD COLUMN visible boolean NOT NULL DEFAULT false;
