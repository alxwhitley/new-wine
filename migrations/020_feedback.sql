-- Migration 020: Feedback table for chat answer ratings
-- Run in Supabase SQL Editor.
-- Created: 2026-05-22

CREATE TABLE feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid REFERENCES messages(id) ON DELETE CASCADE,
  user_id uuid,
  anon_id text,
  rating text NOT NULL CHECK (rating IN ('thumbs_up', 'thumbs_down')),
  comment text,
  question text NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- RLS
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

-- Users can insert their own rows
CREATE POLICY "Users can insert own feedback"
  ON feedback FOR INSERT
  WITH CHECK (
    auth.uid() = user_id
    OR user_id IS NULL  -- allow guest feedback
  );

-- Service role can read all
CREATE POLICY "Service role can read all feedback"
  ON feedback FOR SELECT
  USING (auth.role() = 'service_role');
