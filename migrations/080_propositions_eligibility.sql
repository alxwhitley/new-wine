-- Migration 080: materialized "pass-both" eligibility signal for propositions
-- (position layer speed fix, PLAN.md #48 / step 2a, 2026-08-04).
--
-- The position-serving path's evidence gathering (scripts/positions.py's
-- gather_evidence/gather_evidence_corpus, via _is_eligible) needs to know
-- which propositions pass BOTH the closeness check and the citation-accuracy
-- check (scripts/eligible_statements.py's classify_eligibility(), the single
-- shared decision function both the whole-corpus compute and the lazy
-- per-candidate checker already use). Computing this whole-corpus is
-- CPU-bound and far too slow to run at question time (a document's full text
-- is trigram-checked against every one of its propositions) -- the serving
-- path's only viable form until now was a LAZY per-candidate checker
-- (EligibilityChecker) that pays this cost, live, on every question. This
-- column lets the serving path filter with a fast, indexed boolean instead.
--
-- eligible defaults to false and is backfilled by a one-time batch
-- (scripts/backfill_proposition_eligibility.py) that calls
-- compute_eligible_proposition_ids() -- REUSED VERBATIM, never re-derived --
-- so the materialized value can never diverge from what the live decision
-- function would say (the same fork hazard CLAUDE.md's Landmines warn about
-- for the book-name map's five hand-maintained copies).
--
-- KNOWN STALENESS, DISCLOSED NOT SOLVED BY THIS MIGRATION: a proposition
-- written after this backfill runs (any document ingested from here on)
-- defaults to eligible=false until a future backfill re-runs, and a later
-- fix to closeness_check.py/reference_grounding.py's decision logic (like
-- the BOOK_MAP fix eligible_statements.py's own docstring describes) will
-- not be reflected here until re-backfilled either. No refresh trigger
-- exists yet -- flagged for Alex (ties into Open Decision #14's refresh-
-- trigger question for positions themselves), not solved silently here.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL, per Session Routing's
-- Database-write row -- see scripts/apply_positions_migration_080.py.

ALTER TABLE propositions ADD COLUMN IF NOT EXISTS eligible boolean NOT NULL DEFAULT false;

-- Partial index: only eligible rows are ever selected by id at question time
-- (SELECT id::text FROM propositions WHERE eligible = true), so this is an
-- index-only scan over exactly the rows that matter, not the whole table.
CREATE INDEX IF NOT EXISTS propositions_eligible_idx ON propositions (id) WHERE eligible;
