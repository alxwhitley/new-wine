-- Migration 042: add nullable image_url column to documents
-- Run in Supabase SQL Editor

ALTER TABLE documents ADD COLUMN IF NOT EXISTS image_url text;
