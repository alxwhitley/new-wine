-- Migration 018: Create excerpts table for generated word study articles
-- Run in Supabase SQL Editor.
-- Created: 2026-05-22

CREATE TABLE excerpts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
  content text NOT NULL,
  generated_at timestamptz DEFAULT now(),
  model text NOT NULL,
  excerpt_type text NOT NULL DEFAULT 'word_study_article',
  UNIQUE(document_id, excerpt_type)
);

CREATE INDEX idx_excerpts_document_id ON excerpts(document_id);
