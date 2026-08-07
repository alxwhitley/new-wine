-- Migration 083: quote rail live-answer wiring support (Project 3 -> async
-- answer path).
--
-- Adds ONE column: answer_jobs.quote_ids. This is the only schema change the
-- wiring needs -- selection is a deterministic runtime query
-- (app.services.quotes.select_quotes_for_answer) and resolution already
-- exists (migration 082's quotes_service.resolve_quote(), the single
-- resolution point). No quote TEXT is ever stored here or anywhere else on
-- this path -- only quote ids travel, per CLAUDE.md Settled decision #16/#17
-- ("generated answers carry quote IDs, never text... resolved through the
-- single existing resolution point at render time").
--
-- Wired into the ASYNC path only (backend/app/services/async_answers/
-- producer.py) -- chat.py, the old synchronous path, is deliberately left
-- byte-identical this session. See CLAUDE.md's new landmine on this: the
-- sync path remains a live, silently-reachable fallback (network errors,
-- mode-cache staleness, rollback), so a quote appearing on an answer is
-- accepted as best-effort, not guaranteed, depending on which path served
-- it. This is a recorded product decision, not an oversight to "complete"
-- by wiring chat.py later without checking first.
--
-- The per-teacher/per-work cumulative-quote-text cap (Settled decision #16)
-- needs NO new column -- it is computed at approval time from existing
-- tables (quotes -> quote_source_revisions -> chunks -> document_id),
-- enforced in app.services.quotes.create_and_approve_quote(). That
-- enforcement is application-level only, not a DB trigger, unlike migration
-- 082's four hard gates -- see create_and_approve_quote()'s own docstring
-- for why that's an accepted, narrower boundary for this particular rule.
--
-- Rollback (fully reversible, no data loss to any existing table):
--   ALTER TABLE answer_jobs DROP COLUMN quote_ids
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

ALTER TABLE answer_jobs ADD COLUMN IF NOT EXISTS quote_ids jsonb;

COMMENT ON COLUMN answer_jobs.quote_ids IS
  'List of approved quote ids selected for this answer (Project 3 wiring, async path only, migration 083). Quote TEXT is never stored here -- resolved at render time via quotes_service.resolve_quote(), the single resolution point (migration 082). NULL/empty for the overwhelming majority of answers (no matching approved quote, or fewer than 3 quotes exist corpus-wide as of this migration); also always empty when outcome != answered (position_paper / refused_attribution / no_material never carry a quote -- selection runs only after verify_references, on a non-refused answer).';
