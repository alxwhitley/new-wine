-- 070_clf_church_refiling.sql
-- Re-files two documents from "CLF Church" (institutional attribution) onto
-- "Doug Kreighbaum" (the named teacher whose other material substantially
-- overlaps with these two), per the 2026-07-25 duplicate-storage audit
-- (PLAN.md #44). Both institutional copies carried zero extracted
-- statements at the time of this migration -- confirmed live before this
-- write -- so nothing is lost or moved at the statement level, only the
-- attribution.
--
-- Open risk, recorded here and in PLAN.md: these two documents still exist
-- as separate rows from the material they overlap with. If either is
-- processed by the backfill before a duplicate re-check runs against
-- Kreighbaum's other work, it could generate new duplicate statements. Not
-- resolved by this migration -- flagged for whoever runs the backfill.

UPDATE documents SET source_id = 'f872b446-ce49-4b00-96c7-deb807b5a438'  -- Doug Kreighbaum
WHERE title = 'The Holy Spirit' AND source_id = '29bfe81f-a150-4e43-baac-042e366fb4b3';  -- was CLF Church

UPDATE documents SET source_id = 'f872b446-ce49-4b00-96c7-deb807b5a438'  -- Doug Kreighbaum
WHERE title = 'RESTORATION OF BIBLICAL DEACONS' AND source_id = '29bfe81f-a150-4e43-baac-042e366fb4b3';  -- was CLF Church
