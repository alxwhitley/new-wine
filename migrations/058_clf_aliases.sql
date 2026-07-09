-- 058_clf_aliases.sql
-- Adds two source_aliases rows pointing at CLF Church
-- (29bfe81f-a150-4e43-baac-042e366fb4b3, owned/shown)
--
--   'alex whitley' — author-key so Alex's personal sermons/papers resolve
--                    at ingest time instead of falling to the sentinel
--   'clf church'   — source_name-key that CLAUDE.md claimed migration 050
--                    seeded but the live DB never had (doc/DB mismatch,
--                    found 2026-07-03)
--
-- Deliberately does NOT touch the Rhemata source or its 'rhemata' alias.
-- Idempotent via ON CONFLICT DO NOTHING on the alias_key UNIQUE constraint.
-- Keys are pre-normalized per source_resolver.normalize_alias_key
-- (lowercase, trimmed, single-spaced).

INSERT INTO source_aliases (alias_key, alias_display, source_id, note)
VALUES
  ('alex whitley', 'Alex Whitley',
   '29bfe81f-a150-4e43-baac-042e366fb4b3',
   'Author-key for Alex Whitley original content (migration 058)'),
  ('clf church', 'CLF Church',
   '29bfe81f-a150-4e43-baac-042e366fb4b3',
   'Source-name key, closes migration 050 doc/DB mismatch (migration 058)')
ON CONFLICT (alias_key) DO NOTHING;
