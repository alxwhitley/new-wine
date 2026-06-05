CREATE TABLE books (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  title text NOT NULL,
  author text NOT NULL,
  description text,
  topic_tags text[] DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

CREATE INDEX idx_books_author ON books(author);
CREATE INDEX idx_books_topic_tags ON books USING GIN(topic_tags);
