-- Migration 034: Book quotes table for extracted quotable passages
CREATE TABLE book_quotes (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
  quote_text text NOT NULL,
  quote_index int NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX idx_book_quotes_document_id ON book_quotes(document_id);
