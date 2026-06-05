ALTER TABLE documents ADD COLUMN IF NOT EXISTS era text;
ALTER TABLE books ADD COLUMN IF NOT EXISTS era text;
CREATE INDEX IF NOT EXISTS idx_documents_era ON documents(era);
CREATE INDEX IF NOT EXISTS idx_books_era ON books(era);
