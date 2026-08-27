-- 091_teacher_specific_routing_flag.sql
-- B6-F1 production-activation switch for the named-teacher source-boundary
-- correction (docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md).
-- Alex reviewed the two named_teacher_deliverance blind pairs and recorded
-- ACCEPT 2026-08-26 (PLAN.md B6-F1) -- but the mechanism itself
-- (backend/app/services/async_answers/producer.py's experimental_teacher_
-- routing parameter, merged in fc87041) still has no production caller: the
-- one real caller, scripts/answer_worker.py, never passes it. This migration
-- only ADDS the switch -- it does NOT flip it on. Flipping it is a separate,
-- attended Database-write session per CLAUDE.md Session Routing.
--
-- Mirrors migration 079's async_answer_config.serving_enabled pattern
-- exactly: a single boolean column on the existing singleton config row
-- (id=1), read fresh by answer_worker.py's load_config(db) every tick --
-- flip it with one UPDATE, flip back the same way, no redeploy required
-- either direction. Default false -- production behaviour is completely
-- unchanged until this column is explicitly set true.
--
-- Invariant 9: no semicolons inside -- comments.

ALTER TABLE async_answer_config
  ADD COLUMN IF NOT EXISTS experimental_teacher_routing_enabled boolean NOT NULL DEFAULT false;
