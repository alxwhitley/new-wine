CREATE OR REPLACE FUNCTION match_sermon_chunks_by_ref(
    query_embedding vector(1536),
    verse_ref text,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_index int,
    content text,
    title text,
    author text,
    source_kind text,
    citation_mode text,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        c.id,
        c.document_id,
        c.chunk_index,
        c.content,
        d.title,
        d.author,
        d.source_kind,
        d.citation_mode,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE verse_ref = ANY(c.bible_references)
      AND d.source_kind = 'sermon_transcript'
      AND d.citation_mode = 'citable'
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
$$;
