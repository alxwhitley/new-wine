-- Make the two unattributable sentinel docs honestly silent.
-- Decision (Alex, 2026-07-11): author/source genuinely unknown for both, so they remain
-- on the sentinel source and are never cited by name. citation_mode = silent_context means
-- retrieved + informs the answer, but no name attached.
--
-- So Great a Salvation: citable -> silent_context (was citable with no author/source to cite)
UPDATE documents
SET citation_mode = 'silent_context'
WHERE id = '9b9dbc39-b28b-4472-9434-167dddb2a2df';
--
-- The 59 One Another's (c9321a05-0d11-4d6c-855d-8ce97a38312f) is already silent_context.
-- No change needed -- recorded here for the decision trail.
