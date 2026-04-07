-- Migration 004: Create articles table for magazine browse/search
-- Run in Supabase SQL Editor
-- Created: 2026-04-06

CREATE TABLE IF NOT EXISTS articles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
  title text NOT NULL,
  author text,
  magazine text,
  issue text,
  date text,
  year int,
  month int,
  categories text[],
  keywords text[],
  scripture_refs text[],
  people_mentioned text[],
  summary text,
  word_count int,
  source_type text DEFAULT 'magazine',
  is_copyrighted bool DEFAULT true,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS articles_categories_idx
  ON articles USING GIN(categories);
CREATE INDEX IF NOT EXISTS articles_keywords_idx
  ON articles USING GIN(keywords);
CREATE INDEX IF NOT EXISTS articles_scripture_idx
  ON articles USING GIN(scripture_refs);
CREATE INDEX IF NOT EXISTS articles_people_idx
  ON articles USING GIN(people_mentioned);
CREATE INDEX IF NOT EXISTS articles_year_idx
  ON articles(year);
CREATE INDEX IF NOT EXISTS articles_fts_idx
  ON articles USING GIN(
    to_tsvector('english',
      coalesce(title,'') || ' ' ||
      coalesce(author,'') || ' ' ||
      coalesce(summary,'')
    )
  );
