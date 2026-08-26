-- Migration 092: conversation-level cumulative usage signal
--
-- Long-conversation handoff nudge (docs/superpowers/specs/2026-08-26-long-
-- conversation-handoff.md), phase B. Adds a running counter on
-- `conversations`, mirroring the running-counter pattern already used by
-- `provider_rate_usage` (migration 078) rather than per-message columns --
-- cheaper to read, and this feature only ever needs the conversation-level
-- total, never a per-message breakdown.
--
-- Tokens are stored raw (not a pre-computed dollar amount) so cost is always
-- derived at read time via config.py's estimate_cost_usd(), the same
-- function every other cost figure in this codebase already goes through --
-- a stored dollar figure would silently drift if the pricing constants ever
-- change (they already have once, the 2026-08-31 introductory-rate expiry).
--
-- Purely additive: three new columns, all NOT NULL DEFAULT 0. No RLS change
-- needed -- conversations already has row-level policies (migration 037/
-- 039-style "own row" + service-role) and this only adds columns, not rows
-- or a new access path; the columns are read exclusively by
-- conversation_store.py over the service-role/direct-Postgres connection,
-- which already bypasses RLS for every other column on this table.
--
-- Rollback (fully reversible, no data loss to any existing column):
--   ALTER TABLE conversations
--     DROP COLUMN cumulative_input_tokens,
--     DROP COLUMN cumulative_output_tokens,
--     DROP COLUMN turn_count;
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS cumulative_input_tokens integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cumulative_output_tokens integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS turn_count integer NOT NULL DEFAULT 0;
