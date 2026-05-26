ALTER TABLE chunks ADD COLUMN IF NOT EXISTS bible_references text[] DEFAULT '{}';
CREATE INDEX IF NOT EXISTS chunks_bible_references_gin ON chunks USING GIN (bible_references);
