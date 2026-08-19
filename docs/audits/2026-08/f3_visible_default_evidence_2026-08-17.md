# F3 visible-default policy — supporting evidence (2026-08-17)

Read-only evidence gathered for the F3 written-policy exit criterion
(PLAN.md, "F3 — Finish the ingestion-default contract"). **This file is
evidence only. The policy it supports is a RECOMMENDATION to Alex and has
not been approved.** Nothing here was written to the database; every query
below ran on a `psycopg2` connection opened with
`conn.set_session(readonly=True)`.

---

## 1. Schema facts (from `information_schema`, live)

| Column | Default | Notes |
|---|---|---|
| `sources.visibility` | `'hidden'::text` | NOT NULL, `CHECK (visibility IN ('shown','hidden'))` — set by `migrations/046_sources_visibility.sql:8`; never altered since |
| `sources.license_status` | `'unlicensed'::text` | NOT NULL |
| `sources.retrievable` | (none) | `GENERATED ALWAYS AS (license_status = ANY (ARRAY['public_domain','owned','licensed']))` — **the expression contains no `visibility` term**, so no visibility-default change can affect it |

`documents.source_id` DEFAULT is the sentinel
`267a09ac-76f3-43fb-901f-3015aef88e22`, FK `ON DELETE SET DEFAULT`
(`migrations/049_seal_null_source_id.sql:78`, `:90`).

`app_settings` `safe_mode` = `off` at census time.

## 2. Live source census (75 rows)

| license_status | visibility | count |
|---|---|---|
| owned | shown | 2 |
| public_domain | shown | 28 |
| public_domain | hidden | 2 |
| unlicensed | shown | 32 |
| unlicensed | hidden | 11 |

**Only ONE hidden row is doing real gate work.** Of the 13 `hidden` rows:

- **Sentinel** (`Unassigned — needs source`, unlicensed) — holds 2 real
  documents (34 chunks, 32 propositions total; `author` NULL,
  `citation_mode='silent_context'`, created 2026-05-27 by migration 049's
  orphan backfill): `So Great a Salvation` (29 chunks / 17 props) and
  `The 59 "One Another's" of the NT` (5 chunks / 15 props). Its `hidden`
  flag is the only thing keeping those out of retrieval.
- **2 public_domain rows with content** — Robert Trail (`Concerning
  Sanctification`, 7 chunks), Thomas Brooks (`The Necessity of Holiness`,
  6 chunks). Invariant 2's gate serves `public_domain` on its **first arm**,
  which ignores `visibility` entirely — so these are **already served**
  and their `hidden` flag is inert.
- **10 unlicensed empty shells** (zero documents): Jesus Image, Kathryn
  Kuhlman, Keith Green, Mark Virkler, Paris Reidhead, R.T. Kendall, Randy
  Clark, Roberts Liardon, Sam Storms, T. Austin-Sparks. Four of these
  (Kuhlman, Green, Reidhead, Austin-Sparks) are SermonIndex-derived.

## 3. Empty shells already exist in BOTH visibility states

24 sources have zero documents: 10 unlicensed/hidden, 13 unlicensed/shown
(A.W. Tozer, Andrew Wommack, Art Katz, Bill Johnson, Craig Keener, David
Pawson, David Wilkerson, Duncan Campbell, Frank Bartleman, Gabriel Heights,
John Bevere, Prophetic Equipping, Smith Wigglesworth), 1 public_domain/shown
(Christian Classics Ethereal Library).

Neither group serves anything. Invariant 2's gate is evaluated per-document
via `d.source_id`; a source with zero documents contributes zero rows to
every retrieval RPC regardless of its visibility. **An empty shell's
`visibility` value is behaviourally inert.**

## 4. Unlicensed + shown sources holding content (Tier-1→Tier-2 re-review queue)

19 sources, by document count: Precept Austin 2,176 · Derek Prince 496 ·
Vlad Savchuk 126 · Leonard Ravenhill 117 · Zac Poonen 50 · New Wine Magazine
15 · Daniel Kolenda 11 · Doug Kreighbaum 9 · Jack Deere 6 · Carter Conlon 6 ·
Bob Mumford 4 · Charles Simpson 4 · Don Basham 2 · Michael Brown 2 · Ruth
Prince 2 · Ern Baxter 2 · F.F. Bosworth 1 · Covenant Harvest Church 1 ·
Oswald J. Smith 1.

## 5. Code inventory — who can create a `sources` row

Exhaustive grep for `INSERT INTO sources` / `table("sources").insert` across
`backend/` and `scripts/`:

| Path | Writes `visibility` as | Note |
|---|---|---|
| `scripts/register_youtube_source.py:113-114` | `'unlicensed', 'hidden'` | hardcoded literal |
| `scripts/register_sermonindex_speakers.py:99-100` | `'unlicensed', 'hidden'` | hardcoded literal |
| `scripts/register_bill_johnson_gabriel_heights.py:118-119` | `'unlicensed', 'hidden'` | hardcoded literal |
| `scripts/register_jesus_image.py:64-65` | `'unlicensed', 'hidden'` | hardcoded literal |
| `scripts/register_ryle_ch21_extracts_2026-08-09.py:137-138` | `'public_domain', 'hidden'` | hardcoded literal; its own docstring (`:14`, `:186`) claims `hidden` keeps the rows out of serving — **false for `public_domain`**, see §2 |
| `migrations/050_source_aliases.sql:38`, `migrations/069_ccel_library_refiling.sql:37` | explicit | seed rows |
| **No backend endpoint** | — | no FastAPI route inserts a `sources` row |

**No caller relies on the column DEFAULT.** All five scripts name
`visibility` explicitly.

`scripts/shared_ingest.py::ingest_document()` never creates a `sources`
row — it resolves one. `scripts/apply_migration_084.py:204`'s
`INSERT INTO sources DEFAULT VALUES` is a readonly-role rejection probe,
not a registration path.

## 6. Existing guards that a default flip must not disturb

- `scripts/shared_ingest.py:317` `SilentSentinelRefused`; `:372`
  `allow_sentinel: bool = False`; `:514-516` raises on resolver MISS.
  Callers: `scripts/ingest.py:453,571,573`, `scripts/ingest_magazine.py:242`,
  `scripts/source_ingest_queue/processor.py:347`.
- `backend/app/routers/admin.py:428-429` and `:450-451` — sentinel hard-403
  on both the visibility and license-status PATCH routes.
- `backend/app/services/source_resolver.py:25-49` `is_source_servable()` —
  the canonical Python mirror of Invariant 2; reads `safe_mode` fresh per call.
- `scripts/source_ingest_queue/processor.py:219-227` — queue runner refuses a
  non-servable declared source (`AttentionRequired("source_not_servable")`),
  and per Invariant 16 never creates sources/aliases or changes visibility.

## 7. The accepted chokepoint bypass depends on the sentinel staying hidden

`backend/app/routers/ingest.py:146-153` inserts a `documents` row with **no
`source_id` key at all** — it relies on the column DEFAULT, i.e. the
sentinel. That is why the bypass Alex explicitly accepted on 2026-08-15 is
currently harmless: anything it creates lands `unlicensed`/`hidden` and
cannot be served. **That containment is a side effect of the sentinel's
visibility, not an independent guard.**

## 8. `hidden` does not conceal a document's existence

`backend/app/routers/corpus_inventory.py` (unauthenticated, Alex's explicit
2026-08-17 decision) serves `author, title, url` for **every** document with
no license/visibility filter. `visibility` is a content-serving dial only;
it has never been a bibliographic-secrecy control.

## 9. Reproducing this census

The three read-only scripts used are in this session's scratchpad, not the
repo. Each opened `psycopg2.connect(SUPABASE_DB_URL)` with
`set_session(readonly=True, autocommit=True)` and issued only `SELECT`s
against `sources`, `documents`, `chunks`, `propositions`, `app_settings`,
and `information_schema.columns`. Counts are live as of 2026-08-17 and will
drift — re-run rather than cite these numbers later.
