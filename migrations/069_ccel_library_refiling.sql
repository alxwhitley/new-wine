-- 069_ccel_library_refiling.sql
-- Re-files the 13 documents that were attributed to "Christian Classics
-- Ethereal Library" (a distributor/platform, not a person) onto their real
-- named authors, per the front-matter evidence established in the
-- 2026-07-25 read-only attribution audit (PLAN.md #44).
--
-- 8 named authors across the 13 documents. 5 already had their own
-- source-level entry in the corpus, reused as-is:
--   Andrew Murray, Charles G. Finney, E.M. Bounds, John Wesley, R.A. Torrey
-- 3 needed a new entry, created below following the same pattern as every
-- other existing single-teacher public-domain source (license_status
-- public_domain, visibility shown, no permission fields):
--   Horace Bushnell, Samuel Dickey Gordon, F.B. Meyer
--
-- Torrey note: his front matter labels him "(Translator)," not author.
-- Alex's ruling: a cataloguing error inherited from the source website --
-- filed as his own work, not reopened here.
--
-- Bushnell note: Christian Nurture is deleted in the very next migration
-- (070) by Alex's explicit ruling (see that file and PLAN.md #44 for the
-- reason). His source entry is created here so step one stays uniform and
-- the deletion is recorded against a real named source -- but deliberately
-- gets NO matching name-lookup entry (unlike Gordon and Meyer below), since
-- a lookup pointing at a source about to be removed would either dangle or
-- silently re-admit his material on a future ingest.
--
-- Attribution change only. Nothing deleted, trimmed, merged, or
-- reprocessed -- every document's own text and chunk/statement counts are
-- untouched by this migration.
--
-- Executed and verified live 2026-07-25 (fresh reads confirmed the intended
-- end state before this file was written): Andrew Murray 10, Charles G.
-- Finney 3, E.M. Bounds 7, John Wesley 2, R.A. Torrey 2, Horace Bushnell 1,
-- Samuel Dickey Gordon 2, F.B. Meyer 2 -- 13 documents moved, library source
-- holds 0.

INSERT INTO sources (id, name, slug, license_status, visibility)
VALUES
  ('42b66a72-b10b-470e-866b-7b3af5c02ee2', 'Horace Bushnell', 'horace-bushnell', 'public_domain', 'shown'),
  ('ab5ea9ce-9818-40e0-adf4-0fcb2432253e', 'Samuel Dickey Gordon', 'samuel-dickey-gordon', 'public_domain', 'shown'),
  ('94599d56-a373-4ef9-920c-0b0cd563eaf3', 'F.B. Meyer', 'fb-meyer', 'public_domain', 'shown')
ON CONFLICT (id) DO NOTHING;

INSERT INTO source_aliases (alias_key, alias_display, source_id, note)
VALUES
  ('samuel dickey gordon', 'Samuel Dickey Gordon', 'ab5ea9ce-9818-40e0-adf4-0fcb2432253e',
   'Migration 069 -- library re-filing, corpus cleanup #44'),
  ('f.b. meyer', 'F.B. Meyer', '94599d56-a373-4ef9-920c-0b0cd563eaf3',
   'Migration 069 -- library re-filing, corpus cleanup #44')
ON CONFLICT (alias_key) DO NOTHING;

-- Reused existing sources
UPDATE documents SET source_id = 'd26f77e7-6ce0-4311-991b-03d9900a6045' WHERE title = 'Absolute Surrender';               -- Andrew Murray
UPDATE documents SET source_id = 'd26f77e7-6ce0-4311-991b-03d9900a6045' WHERE title = 'The Lord''s Table';                -- Andrew Murray
UPDATE documents SET source_id = 'd26f77e7-6ce0-4311-991b-03d9900a6045' WHERE title = 'The Two Covenants';                -- Andrew Murray
UPDATE documents SET source_id = 'd2714d54-7b38-4073-8bcc-4f5bb2582ef7' WHERE title = 'Lectures on Revivals of Religion'; -- Charles G. Finney
UPDATE documents SET source_id = '49eb3ee1-26ad-4a24-86c9-aebaaee2eef6' WHERE title = 'Purpose in Prayer';                -- E.M. Bounds
UPDATE documents SET source_id = '49eb3ee1-26ad-4a24-86c9-aebaaee2eef6' WHERE title = 'The Weapon of Prayer';             -- E.M. Bounds
UPDATE documents SET source_id = '1ff35bfc-fc8c-4385-bf06-5818eca7aba7' WHERE title = 'The Journal of John Wesley';       -- John Wesley
UPDATE documents SET source_id = '6b996e24-5947-4597-ad84-5becd6bba6e3' WHERE title = 'The Person and Work of The Holy Spirit'; -- R.A. Torrey

-- Newly created sources
UPDATE documents SET source_id = '42b66a72-b10b-470e-866b-7b3af5c02ee2' WHERE title = 'Christian Nurture';                -- Horace Bushnell
UPDATE documents SET source_id = 'ab5ea9ce-9818-40e0-adf4-0fcb2432253e' WHERE title = 'Quiet Talks on Power';             -- Samuel Dickey Gordon
UPDATE documents SET source_id = 'ab5ea9ce-9818-40e0-adf4-0fcb2432253e' WHERE title = 'Quiet Talks on Prayer';            -- Samuel Dickey Gordon
UPDATE documents SET source_id = '94599d56-a373-4ef9-920c-0b0cd563eaf3' WHERE title = 'The Secret of Guidance';           -- F.B. Meyer
UPDATE documents SET source_id = '94599d56-a373-4ef9-920c-0b0cd563eaf3' WHERE title = 'The Way Into the Holiest';         -- F.B. Meyer
