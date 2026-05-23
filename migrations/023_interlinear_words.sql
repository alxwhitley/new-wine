-- Interlinear word data for Greek NT (from TAGNT / STEPBible)
CREATE TABLE IF NOT EXISTS interlinear_words (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    verse_id text NOT NULL,
    word_position integer NOT NULL,
    greek_word text NOT NULL,
    transliteration text,
    strongs_number text,
    english_gloss text,
    morphology text,
    created_at timestamptz DEFAULT now(),
    UNIQUE (verse_id, word_position)
);

CREATE INDEX IF NOT EXISTS idx_interlinear_words_verse_id ON interlinear_words (verse_id);

-- RLS: public read, service role insert
ALTER TABLE interlinear_words ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read interlinear words"
    ON interlinear_words FOR SELECT
    USING (true);

CREATE POLICY "Service role can insert interlinear words"
    ON interlinear_words FOR INSERT
    WITH CHECK (true);
