-- 072_complete_salvation_refiling.sql
-- Re-files "Complete Salvation and How To Receive It - Part 2" from
-- "Smith Wigglesworth" onto "Derek Prince" -- Alex's explicit ruling
-- (2026-07-25 bulk-linking-apply session): this is Derek Prince's own
-- teaching, mis-filed under Smith Wigglesworth. Confirmed by reading the
-- document's own opening text before this migration was written: it
-- continues directly from "Part 1" (already correctly filed under Derek
-- Prince) -- "We're continuing now with the theme 'Complete Salvation and
-- How To Receive It.' In the previous session I explained..." -- and Smith
-- Wigglesworth otherwise has exactly zero other documents in this corpus
-- (confirmed live the same session), so this was the only document under
-- his name, not one of several.
--
-- The document carried zero extracted statements at the time of this
-- migration -- confirmed live before this write -- so nothing is lost or
-- moved at the statement level, only the attribution. This re-filing is
-- separate from, and does not itself link, the two "Complete Salvation"
-- parts as one work -- that linking is deliberately held back until this
-- re-filing is settled and verified (see rhemata-status.md /
-- PLAN.md #44).

UPDATE documents SET source_id = '17be391b-d025-4178-8543-3e84da675c5d'  -- Derek Prince
WHERE id = '083b2f3e-4b06-4b61-9b73-72bdf86b8d45'  -- "Complete Salvation and How To Receive It - Part 2"
  AND source_id = 'edc31423-3918-4e4a-86dd-a30f0acd6707';  -- was Smith Wigglesworth
