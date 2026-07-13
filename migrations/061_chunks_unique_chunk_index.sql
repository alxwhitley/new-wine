-- Migration 061: prevent duplicate chunk_index within a document
-- Adds a UNIQUE constraint on chunks(document_id, chunk_index). Forward-only.
--
-- Applied after a one-time live cleanup removed 9,168 pre-existing duplicate
-- rows across 186 documents (145 Precept Austin, 1 STEPBible, 40 Derek
-- Prince) -- see rhemata-status.md and PLAN.md's ground-truth log for the
-- cleanup record. The table previously had no uniqueness constraint at all
-- on (document_id, chunk_index) beyond the primary key on id, which is why
-- the duplication was possible and silent.
--
-- Side effect: makes ingest_lexicon.py's existing
-- `INSERT ... ON CONFLICT DO NOTHING` functional for the first time --
-- previously inert, since no constraint existed for a conflict to fire
-- against.

ALTER TABLE chunks
  ADD CONSTRAINT chunks_document_id_chunk_index_key UNIQUE (document_id, chunk_index);
