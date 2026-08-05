-- Migration 081: generation_model_config -- one-row control plane for the
-- answer-generation model ID.
-- ====================================================================
-- A single shared knob: which Claude model ID every generation call site
-- uses -- the sync /chat answer stream, teacher cards (study.py), position
-- papers (house-voice), scripts/positions.py, and the async producer/worker
-- (scripts/answer_worker.py, via producer.py). Changing this row changes
-- the live model everywhere with no redeploy.
--
-- Deliberately its OWN table, not a column on async_answer_config:
-- async_answer_config's own docstring scopes it to "the async answer
-- path's control plane" specifically (pause, backpressure, rate ceilings,
-- spend ceiling, lease length). The generation model is a broader,
-- cross-cutting value that also governs the synchronous /chat path, teacher
-- cards, and position papers -- none of which touch async_answer_config at
-- all. Folding it in there would misname it.
--
-- Read pattern: NOT read fresh-every-call like async_answer_config's
-- load_config() (that function is only called once per worker poll tick,
-- so a fresh SELECT there is free). This value is read once per live
-- answer generation on the SYNC path too, at much higher call frequency,
-- so it goes through a 60-second in-process TTL cache instead -- the same
-- pattern backend/app/services/source_filter.py already uses for
-- get_disabled_filters(). See backend/app/services/llm_client.py's
-- get_generation_model().
--
-- No value-format validation beyond non-empty/non-whitespace: intentionally
-- no allow-list of "known good" model IDs (Alex's explicit call) -- an
-- unfamiliar value is not blocked. Malformed/missing/unreachable falls back
-- to llm_client.GENERATION_MODEL (the hardcoded default), logged when it
-- happens, never a failed request.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL, per Session Routing's
-- Database-write row -- see scripts/apply_migration_081.py.

CREATE TABLE IF NOT EXISTS generation_model_config (
    id          integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    model       text NOT NULL DEFAULT 'claude-sonnet-5',
    updated_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO generation_model_config (id, model) VALUES (1, 'claude-sonnet-5')
    ON CONFLICT (id) DO NOTHING;
