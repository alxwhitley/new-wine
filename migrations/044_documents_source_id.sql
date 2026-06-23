-- Migration 044: Add source_id FK to documents
-- Links each document to its rights holder in the sources table (migration 043).
-- Column is nullable: all existing rows stay NULL. Backfilling is Step 3.
-- ON DELETE SET NULL: losing a source record orphans documents, never deletes them.
-- The Step 4 retrieval gate must treat copyrighted docs with source_id = NULL
-- as NOT retrievable (fail-closed) -- so anything missed in Step 3 defaults to OFF.
-- This migration is INERT: no existing behavior changes.
-- Created: 2026-06-23

ALTER TABLE documents
  ADD COLUMN source_id uuid REFERENCES sources(id) ON DELETE SET NULL;

CREATE INDEX idx_documents_source_id ON documents(source_id);
