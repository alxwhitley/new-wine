-- Rename greek_word → original_word to support both Greek NT and Hebrew OT data
ALTER TABLE interlinear_words RENAME COLUMN greek_word TO original_word;

-- Add language column to distinguish Greek NT vs Hebrew OT words
ALTER TABLE interlinear_words ADD COLUMN language text NOT NULL DEFAULT 'greek';

-- Index on language for filtered queries
CREATE INDEX IF NOT EXISTS idx_interlinear_words_language ON interlinear_words (language);
