-- Migration 033: Add document_id to books table for linking to readable documents
ALTER TABLE books ADD COLUMN IF NOT EXISTS document_id uuid REFERENCES documents(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_books_document_id ON books(document_id);
