-- Migration 064: teacher_profiles table for SP4 (teacher card content) +
-- seed data for the 9 teachers whose bios currently live only in two
-- hardcoded, inconsistent frontend arrays (frontend/app/library/authors/page.tsx
-- AUTHORS, frontend/app/library/page.tsx AUTHOR_DATA -- same 9 names, AUTHORS'
-- bio field used here since AUTHOR_DATA has a different field, specialty,
-- instead).
--
-- Row existence = curated: a teacher's underline only ever renders live if
-- their source_id has a row here (see
-- docs/superpowers/specs/2026-07-18-sp4-teacher-cards-design.md). No new
-- teacher may be added by any path except this table -- there is no admin UI
-- for this, by deliberate scope decision.
--
-- All 9 names confirmed resolvable via source_aliases as of the 2026-07-18
-- SP4 pre-build data fix (5 of these 9 had no source_aliases row at all
-- before that fix -- see rhemata-status.md's "SP4 pre-build data fix"
-- section). Do not run this migration before confirming that fix is live
-- (SELECT count(*) FROM source_aliases WHERE alias_key IN
-- ('bob mumford','ern baxter','charles simpson','don basham','oswald j. smith')
-- should return 5).
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

CREATE TABLE teacher_profiles (
  source_id   uuid PRIMARY KEY REFERENCES sources(id),
  bio         text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE teacher_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "teacher_profiles: service role full access"
  ON teacher_profiles FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Seed data: resolves each name to source_id via source_aliases (same
-- normalize_alias_key contract -- lowercase + trim + collapse whitespace --
-- app/services/source_resolver.py). ON CONFLICT makes this idempotent.

INSERT INTO teacher_profiles (source_id, bio)
SELECT sa.source_id, v.bio
FROM (VALUES
  ('derek prince', 'Cambridge-educated philosopher turned Bible teacher, Prince founded Derek Prince Ministries after a wartime conversion and became one of the most widely translated charismatic teachers of the 20th century, known especially for his work on deliverance, healing, and the Holy Spirit.'),
  ('bob mumford', 'Bible teacher and co-founder of New Wine Magazine, Mumford is known for his Kingdom of God teaching and his role in the charismatic renewal, still living and ministering through Lifechangers.'),
  ('ern baxter', 'Canadian Pentecostal preacher regarded as one of the greatest orators of the 20th century, Baxter served as Bible teacher for William Branham''s crusades and delivered his landmark "Thy Kingdom Come" message to 5,000 leaders in Kansas City.'),
  ('charles simpson', 'Baptist-turned-charismatic pastor from Mobile, Alabama who co-founded New Wine Magazine in 1969 and became a key leader in the charismatic renewal, known for his pastoral teaching on covenant community and spiritual authority.'),
  ('don basham', 'Bible teacher and author who pioneered deliverance ministry in the charismatic movement, Basham served as editor of New Wine Magazine from 1975-1981 and was known for his accessible writing on the Holy Spirit and spiritual warfare.'),
  ('john bevere', 'Co-founder of Messenger International and bestselling author of The Bait of Satan and The Awe of God, Bevere is known globally for his bold teachings on the fear of the Lord, spiritual authority, and uncompromising discipleship.'),
  ('michael brown', 'Scholar, apologist, and radio host with a PhD from NYU, Brown is a leading charismatic voice on the Jewish roots of Christianity, revival, and cultural apologetics, and has authored over 40 books.'),
  ('jack deere', 'Former Dallas Seminary professor of Old Testament who became a charismatic theologian after encountering the gifts through John Wimber; best known for Surprised by the Power of the Spirit, a landmark defense of continuationism.'),
  ('oswald j. smith', 'Canadian pastor, hymn writer, and missions statesman who founded The People''s Church in Toronto; preached 12,000 sermons in 80 countries and was described by Billy Graham as "the greatest missionary statesman of our time."')
) AS v(alias_key, bio)
JOIN source_aliases sa ON sa.alias_key = v.alias_key
ON CONFLICT (source_id) DO NOTHING;
