-- Migration 050: source_aliases table + ingest resolution seed
-- Provides a normalized alias_key → source_id lookup for ingest scripts.
-- alias_key is lowercase + trimmed + single-space normalized so lookups are
-- case/whitespace-insensitive without runtime normalization at write time.
-- ON DELETE CASCADE: aliases are disposable — if a source is deleted, its
-- aliases go with it (unlike documents, which fall to the sentinel).
-- Created: 2026-06-25

-- ── PART 1: Table + index + RLS ──────────────────────────────────────────────

CREATE TABLE source_aliases (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  alias_key     text        NOT NULL UNIQUE,
  alias_display text,
  source_id     uuid        NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
  note          text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- The UNIQUE constraint on alias_key creates a B-tree index automatically.
-- No additional index is needed; confirmed: pg unique constraints always
-- back their constraint with an index (pg_indexes will show idx_source_aliases_alias_key).

-- RLS: ingest scripts use SUPABASE_SERVICE_KEY (bypasses RLS).
-- Gate is read-only for anonymous; write is service-role only.
ALTER TABLE source_aliases ENABLE ROW LEVEL SECURITY;

CREATE POLICY "source_aliases: service role full access"
  ON source_aliases FOR ALL
  USING  (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- ── PART 2: New source rows required by this seed ────────────────────────────
-- F.F. Bosworth (ff-bosworth) already exists as unlicensed/shown — not recreated.
-- NOTE: user spec said visibility='hidden' for Bosworth; existing row is 'shown'.
-- Not changed here — adjust separately if desired.

INSERT INTO sources (name, slug, license_status, visibility, notes)
VALUES (
  'An Unknown Christian',
  'an-unknown-christian',
  'public_domain',
  'shown',
  'Pen name used for The Kneeling Christian (c.1924). Author identity disputed but '
  'work is in the public domain. Created for sentinel-doc reassignment.'
);

-- ── PART 3: Alias seed ───────────────────────────────────────────────────────
-- All alias_key values are pre-normalized (lower + trim + single-space).
-- source_id resolved via subselect on slug — no hardcoded UUIDs.

INSERT INTO source_aliases (alias_key, alias_display, source_id, note) VALUES

  ('a.b. bruce', 'A.B. Bruce', (SELECT id FROM sources WHERE slug = 'ab-bruce'), 'from MATCHED review CSV'),
  ('a.j. gordon', 'A.J. Gordon', (SELECT id FROM sources WHERE slug = 'aj-gordon'), 'from MATCHED review CSV'),
  ('abraham kuyper', 'Abraham Kuyper', (SELECT id FROM sources WHERE slug = 'abraham-kuyper'), 'from MATCHED review CSV'),
  ('adam clarke''s commentary', 'Adam Clarke''s Commentary', (SELECT id FROM sources WHERE slug = 'adam-clarke'), 'from MATCHED review CSV'),
  ('andrew murray', 'Andrew Murray', (SELECT id FROM sources WHERE slug = 'andrew-murray'), 'from MATCHED review CSV'),
  ('bible study pdcst', 'Bible Study PDCST', (SELECT id FROM sources WHERE slug = 'bible-study-podcast'), 'from MATCHED review CSV'),
  ('bible study podcast', 'Bible Study Podcast', (SELECT id FROM sources WHERE slug = 'bible-study-podcast'), 'from MATCHED review CSV'),
  ('bosworth', 'Bosworth', (SELECT id FROM sources WHERE slug = 'ff-bosworth'), 'Surname-only; likely F.F. Bosworth (d.1958, unlicensed). F.F. Bosworth source pre-exists.'),
  ('brother lawrence', 'Brother Lawrence', (SELECT id FROM sources WHERE slug = 'brother-lawrence'), 'from MATCHED review CSV'),
  ('catherine booth', 'Catherine Booth', (SELECT id FROM sources WHERE slug = 'catherine-booth'), 'from MATCHED review CSV'),
  ('chapel library', 'Chapel Library', (SELECT id FROM sources WHERE slug = 'chapel-library'), 'from MATCHED review CSV'),
  ('charles g. finney', 'Charles G. Finney', (SELECT id FROM sources WHERE slug = 'charles-finney'), 'from MATCHED review CSV'),
  ('christ for the nations', 'Christ for the Nations', (SELECT id FROM sources WHERE slug = 'derek-prince'), 'Re-upload venue; Derek Prince holds rights'),
  ('christian classics ethereal library', 'Christian Classics Ethereal Library', (SELECT id FROM sources WHERE slug = 'ccel'), 'from MATCHED review CSV'),
  ('covenant harvest church/international student fellowship', 'Covenant Harvest Church/International Student Fellowship', (SELECT id FROM sources WHERE slug = 'covenant-harvest-church'), 'from MATCHED review CSV'),
  ('daniel kolenda', 'Daniel Kolenda', (SELECT id FROM sources WHERE slug = 'daniel-kolenda'), 'from MATCHED review CSV'),
  ('derek prince', 'Derek Prince', (SELECT id FROM sources WHERE slug = 'derek-prince'), 'from MATCHED review CSV'),
  ('derek prince ministries', 'Derek Prince Ministries', (SELECT id FROM sources WHERE slug = 'derek-prince'), 'from MATCHED review CSV'),
  ('doug kreighbaum', 'Doug Kreighbaum', (SELECT id FROM sources WHERE slug = 'doug-kreighbaum'), 'from MATCHED review CSV'),
  ('drawing near', 'Drawing Near', (SELECT id FROM sources WHERE slug = 'john-bevere'), 'from MATCHED review CSV'),
  ('e.m. bounds', 'E.M. Bounds', (SELECT id FROM sources WHERE slug = 'em-bounds'), 'from MATCHED review CSV'),
  ('good news church', 'Good News Church', (SELECT id FROM sources WHERE slug = 'derek-prince'), 'Re-upload venue; Derek Prince holds rights'),
  ('hannah smith', 'Hannah Smith', (SELECT id FROM sources WHERE slug = 'hannah-whitall-smith'), 'from MATCHED review CSV'),
  ('hannah whitall smith', 'Hannah Whitall Smith', (SELECT id FROM sources WHERE slug = 'hannah-whitall-smith'), 'from MATCHED review CSV'),
  ('historicalchristianfaith commentaries database', 'HistoricalChristianFaith Commentaries Database', (SELECT id FROM sources WHERE slug = 'historicalchristianfaith'), 'from MATCHED review CSV'),
  ('j.r. miller', 'J.R. Miller', (SELECT id FROM sources WHERE slug = 'jr-miller'), 'from MATCHED review CSV'),
  ('jamieson-fausset-brown commentary', 'Jamieson-Fausset-Brown Commentary', (SELECT id FROM sources WHERE slug = 'jamieson-fausset-brown'), 'from MATCHED review CSV'),
  ('john bevere', 'John Bevere', (SELECT id FROM sources WHERE slug = 'john-bevere'), 'from MATCHED review CSV'),
  ('john bevere tv', 'John Bevere TV', (SELECT id FROM sources WHERE slug = 'john-bevere'), 'from MATCHED review CSV'),
  ('john bevere, rick renner', 'John Bevere, Rick Renner', (SELECT id FROM sources WHERE slug = 'john-bevere'), 'Co-authored doc; primary rights holder = John Bevere'),
  ('john charles ryle', 'John Charles Ryle', (SELECT id FROM sources WHERE slug = 'jc-ryle'), 'from MATCHED review CSV'),
  ('john owen', 'John Owen', (SELECT id FROM sources WHERE slug = 'john-owen'), 'from MATCHED review CSV'),
  ('john wesley', 'John Wesley', (SELECT id FROM sources WHERE slug = 'john-wesley'), 'from MATCHED review CSV'),
  ('johnbeveretv', 'johnbeveretv', (SELECT id FROM sources WHERE slug = 'john-bevere'), 'from MATCHED review CSV'),
  ('jonathan edwards', 'Jonathan Edwards', (SELECT id FROM sources WHERE slug = 'jonathan-edwards'), 'from MATCHED review CSV'),
  ('matthew henry', 'Matthew Henry', (SELECT id FROM sources WHERE slug = 'matthew-henry'), 'Author name shorthand for Matthew Henry''s Commentary'),
  ('matthew henry''s commentary', 'Matthew Henry''s Commentary', (SELECT id FROM sources WHERE slug = 'matthew-henry'), 'from MATCHED review CSV'),
  ('muller', 'Muller', (SELECT id FROM sources WHERE slug = 'george-muller'), 'Surname-only variant; almost certainly George Müller (PD d.1898)'),
  ('na bible study pdcst', 'NA Bible Study PDCST', (SELECT id FROM sources WHERE slug = 'bible-study-podcast'), 'from MATCHED review CSV'),
  ('new wine magazine', 'New Wine Magazine', (SELECT id FROM sources WHERE slug = 'new-wine-magazine'), 'from MATCHED review CSV'),
  ('phoebe palmer', 'Phoebe Palmer', (SELECT id FROM sources WHERE slug = 'phoebe-palmer'), 'from MATCHED review CSV'),
  ('precept austin', 'Precept Austin', (SELECT id FROM sources WHERE slug = 'precept-austin'), 'from MATCHED review CSV'),
  ('prophetic equipping', 'Prophetic Equipping', (SELECT id FROM sources WHERE slug = 'prophetic-equipping'), 'from MATCHED review CSV'),
  ('r.a. torrey', 'R.A. Torrey', (SELECT id FROM sources WHERE slug = 'ra-torrey'), 'Source entity''s own canonical name'),
  ('reuben archer torrey', 'Reuben Archer Torrey', (SELECT id FROM sources WHERE slug = 'ra-torrey'), 'from MATCHED review CSV'),
  ('rhemata', 'Rhemata', (SELECT id FROM sources WHERE slug = 'rhemata'), 'from MATCHED review CSV'),
  ('ruth prince', 'Ruth Prince', (SELECT id FROM sources WHERE slug = 'ruth-prince'), 'Explicit alias: Ruth Prince entity is kept separate from Derek Prince'),
  ('sandals church', 'Sandals Church', (SELECT id FROM sources WHERE slug = 'john-bevere'), 'Host church; John Bevere holds rights'),
  ('smith wigglesworth', 'Smith Wigglesworth', (SELECT id FROM sources WHERE slug = 'smith-wigglesworth'), 'from MATCHED review CSV'),
  ('stepbible', 'STEPBible', (SELECT id FROM sources WHERE slug = 'stepbible'), 'from MATCHED review CSV'),
  ('the bible study podcast', 'The Bible Study Podcast', (SELECT id FROM sources WHERE slug = 'bible-study-podcast'), 'from MATCHED review CSV'),
  ('the crossroads', 'The Crossroads', (SELECT id FROM sources WHERE slug = 'derek-prince'), 'Re-upload venue; Derek Prince holds rights'),
  ('unknown christian', 'Unknown Christian', (SELECT id FROM sources WHERE slug = 'an-unknown-christian'), 'Author of The Kneeling Christian; PD anonymous classic'),
  ('william booth', 'William Booth', (SELECT id FROM sources WHERE slug = 'william-booth'), 'from MATCHED review CSV')
;


-- ── PART 4: Verification query (read-only; run after applying migration) ──────
-- SELECT s.name, count(*) AS alias_count
-- FROM source_aliases sa
-- JOIN sources s ON s.id = sa.source_id
-- GROUP BY s.name ORDER BY alias_count DESC, s.name;
