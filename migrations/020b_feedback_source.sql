-- Migration 020b: Add source_type and source_document_id to feedback table
-- Run in Supabase SQL Editor after 020_feedback.sql.
-- Created: 2026-05-22

ALTER TABLE feedback
  ADD COLUMN source_type text,
  ADD COLUMN source_document_id uuid REFERENCES documents(id) ON DELETE SET NULL;
