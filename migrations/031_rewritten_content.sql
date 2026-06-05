ALTER TABLE chunks ADD COLUMN IF NOT EXISTS rewritten_content text;
CREATE INDEX IF NOT EXISTS idx_chunks_rewritten ON chunks((rewritten_content IS NOT NULL));

ALTER TABLE documents ADD COLUMN IF NOT EXISTS rewrite_status text DEFAULT 'pending';
-- values: 'pending' | 'complete' | 'failed'
