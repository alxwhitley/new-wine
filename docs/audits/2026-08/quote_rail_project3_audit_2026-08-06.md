# Project 3 (Quote Rail) — Discovery Audit, Andrew Murray + Derek Prince

**Date:** 2026-08-06
**Type:** Read-only audit. No writes, no migrations, no schema changes, no new
extraction. `conn.set_session(readonly=True)` was used for every DB query in
this pass.
**Scope:** Confirmed teachers only — Andrew Murray, Derek Prince — per Alex's
instruction. Corpus material for both is taken as given to be written work,
not transcripts (per Alex, not re-verified) — **except where §2 below reports
a direct schema-level conflict with that premise for Derek Prince**, which is
reported as a finding, not a re-verification of the underlying claim.

---

## 1. Andrew Murray — corpus inventory

**Source row:** `sources.id = d26f77e7-6ce0-4311-991b-03d9900a6045`, name
`Andrew Murray`, `license_status = public_domain`, `visibility = shown`. One
alias (`andrew murray` → this source). No name-collision risk found (unlike
Prince, below).

**10 documents, all `source_kind = 'book'` / `source_type = 'book'`** —
consistent with "written work." All ingested from local PDFs
(`sources/documents/murray_*.pdf`); 3 of the 10 carry `source = "Christian
Classics Ethereal Library"` (CCEL), meaning they include CCEL's own editorial
front matter ahead of Murray's text (see §3 — confirmed for one of the three,
not checked for the other two).

| Title | Propositions | Chunks | CCEL-sourced |
|---|---:|---:|:---:|
| Absolute Surrender | 0 | 124 | yes |
| The Deeper Christian Life | 0 | 82 | |
| The Lord's Table | 149 | 78 | yes |
| The Master's Indwelling | 0 | 144 | |
| **The New Life: Words of God for Young Disciples** | 408 | 249 | |
| The School of Obedience | 0 | 90 | |
| The True Vine | 165 | 70 | |
| The Two Covenants | 0 | 154 | yes |
| Waiting On God! | 176 | 104 | |
| With Christ in the School of Prayer | 0 | 257 | |

**6 of the 10 books have zero propositions** despite having chunks — they
were never run through `extract_propositions()` (or yielded nothing). This
matters for scoping quote review: if quote candidates are sourced from the
propositions layer, only 4 books are currently populated; if sourced from raw
chunk/`full_text` content (as the old `extract_book_quotes.py` did — see
§4), all 10 are available regardless of proposition status. `full_text` is
NULL for all 10 Murray documents (pre-dates the `documents.full_text`
chokepoint addition) — chunks are the only stored text for this teacher.

No `document_work_groups` membership for any Murray document — none of the
10 are split-work series.

---

## 2. Derek Prince — corpus inventory

**Source row:** `sources.id = 17be391b-d025-4178-8543-3e84da675c5d`, name
`Derek Prince`, `license_status = unlicensed`, `visibility = shown`. 4
aliases (`derek prince`, `derek prince ministries`, `christ for the
nations`, `good news church`) — the latter two are re-upload venues, Derek
Prince holds rights per the alias notes.

**Name-collision risk, reconciled:** A `sources` row for **Ruth Prince**
(Derek Prince's late wife) exists separately
(`9e535915-620c-4b42-8173-b5f66d7ccc1a`), with her own alias
(`ruth prince`) explicitly noted in migration 050 as "kept separate from
Derek Prince." An author-substring search for `%prince%` picks up 2
documents attributed to her (`A Woman Prepares For Marriage (Ruth Prince)`,
`The Call Of God`) — **these are correctly excluded from the Derek Prince
set below; they are a different person with her own source row.**

**496 documents attributed to Derek Prince** (by `source_id`, Ruth Prince's
2 excluded):

| `source_kind` / `source_type` | Count |
|---|---:|
| `sermon_transcript` / `sermon` | 491 |
| `magazine_article` / `magazine_article` | 5 |

**Finding — conflicts with the stated premise that all corpus material for
both teachers is written work, not transcripts:** 491 of the 496 Derek
Prince documents are tagged in the database's own classification as
`source_kind = 'sermon_transcript'`, `source_type = 'sermon'`. All but 2 of
these resolve to `www.derekprince.com/sermons/<n>` URLs, and every sampled
`file_path` matches a media-catalog naming pattern
(`MA-4093-100-ENG.txt`, `MV-4356-100-ENG.txt`, etc.) consistent with
transcribed audio/video sermon recordings, not originally-written text. This
is not a re-verification of whether the transcripts are accurate — no audio
was checked, per instruction — it is a direct report of what the corpus's
own `source_kind`/`source_type` metadata says about how this material
originated. It is squarely relevant to Project 3 because CLAUDE.md's own
quote-eligibility rule (Settled decision #16) makes "auto-transcript" status
the central eligibility question: *"auto-transcripts are ineligible unless a
human checked the passage against the audio."* **See the decision list in
the plain-English summary.**

The remaining **5 documents are `magazine_article`** — no `url`, no
`file_path`, but carry `year`/`issue` metadata (e.g. `issue = "01-1978"`),
consistent with a print newsletter/magazine, structurally distinct from the
sermon-transcript set and plausibly genuinely written material. Not
independently confirmed either way — flagged, not resolved.

**Split-work series:** 86 of the 496 documents (17.3%) belong to a
`document_work_groups` multi-part series — 21 distinct groups: seventeen
2-part series, one 20-part series ("The Roman Pilgrimage"), one 21-document
chapter-by-chapter series through Hebrews ("Analysis of Hebrews"), and two
5-recording "five deliverances from Galatians" groupings. This grouping
mechanism exists (migration 071) but, per that migration's own comment, is
explicitly not wired into any consumer yet — nothing in the quote-rail
design currently reads it. Relevant to Project 3's "cumulative unique
approved-quote text per work is capped AT APPROVAL TIME" rule (Settled
decision #16) once "work" needs to mean the underlying teaching, not each
split document.

---

## 3. Andrew Murray — "The New Life" translator's-note location

**Document:** `9fb66238-fe97-47da-88df-56f3e4b5602d`, "The New Life: Words
of God for Young Disciples." 249 chunks, 408 live propositions (already
reduced from 411 by the 2026-08-01 remediation recorded in CLAUDE.md —
confirmed still holding).

Read the first 8 chunks directly (full content, not previews) to locate
exact boundaries:

| `chunk_index` | Content |
|---:|---|
| 0–2 | CCEL's own editorial front matter — a third-party "Description" of the book written by CCEL staff, the table of contents, and CCEL's copyright/distribution boilerplate. **Not Murray's words, and not the translator's note either** — a third category. |
| 3 | Title page repeat, then the **Translator's Note** begins ("A glance at the pages of this little work will show...") |
| 4 | Translator's Note continues, ends **"...Translator's Note / J.P.L. / Abbroath, September 1891 / 3"** — signed and dated by the translator (initials "J.P.L.") |
| 5 | Opens with the tail-end repeat of the Translator's Note signature (chunk overlap), then **Murray's own Preface begins** ("In intercourse with young converts, I have very frequently longed...", first person, matches Murray's authorial voice) |
| 6–7 | Preface continues — genuinely Murray's own writing |

**Recommended exclusion boundary for quote sourcing:** `chunk_index` 0
through 5 inclusive. Chunks 0–2 are CCEL's editorial description (not
Murray, not the translator), chunks 3–4 are the Translator's Note proper,
and chunk 5 opens with a short repeated fragment of the translator's
signature before Murray's real Preface starts partway through it — excluding
the whole chunk is the conservative choice consistent with CLAUDE.md's "no
words trimmed" quote rule (trimming mid-chunk to rescue the Preface fragment
would itself be a targeted edit of stored content, which the codebase
avoids elsewhere for exactly this fragility reason). **Murray's own authored
content begins cleanly at `chunk_index = 6`.**

This is a different, additional problem from the already-fixed
proposition-level issue (411→408, CLAUDE.md) — that fix removed 3
proposition rows; it did not and does not touch the underlying chunk text,
which still contains the full CCEL description + Translator's Note verbatim.
Any quote-sourcing pass that reads chunks or `full_text` directly (as the
old `extract_book_quotes.py` did) would re-encounter this problem
independently of the proposition-layer fix.

**Not checked, flagged only:** whether the other 2 CCEL-sourced Murray books
(Absolute Surrender, The Two Covenants) have the same kind of non-Murray
front matter. Both currently have 0 propositions, so this issue hasn't
surfaced through that layer for them the way it did for The New Life — but a
chunk-level read (the same method used above) was not performed for these
two in this pass, since the task scoped this check to the one book with the
already-documented issue.

---

## 4. Existing quote infrastructure — what's actually there vs. what PLAN.md's old track describes

**Confirmed: nothing usable for the current (2026-08-03/08-06) manual-approval
design exists yet.** Specifically:

- **`book_quotes` table (migration 034, `CREATE TABLE book_quotes(id,
  document_id, quote_text, quote_index, created_at)`).** Live row count:
  **0**. This is the table PLAN.md's own version history (v4→v5, Jul 8)
  records as "confirmed 0 live rows and retired" — confirmed still true
  live. It has no verification/provenance columns of any kind (no
  content-hash, no source-span pointer, no approval state) — it could not
  satisfy Settled decision #16's rules even if populated.
- **`scripts/extract_book_quotes.py`** — a working script, but it is the
  **old, fully-automated design PLAN.md's 2026-08-03 build-plan reset
  explicitly superseded**: it calls Claude Haiku and asks it to freely
  generate 5 "quotable passages" from a batch of Murray book text, validates
  only length/format (100–600 chars, doesn't start with a digit, doesn't
  contain a short list of boilerplate strings), and inserts straight into
  the retired `book_quotes` table. **No verification that the model's output
  is an exact substring of the source text at all** — this is precisely the
  unenforceable shape Settled decision #17 rules out ("a quote cannot be
  fabricated because the model never generates one" is not a claim this
  script could ever support). It targets Murray only (hardcoded `author
  ILIKE '%murray%'`), has never been run against Prince. Not wired to
  anything live; not a starting point for Project 3 as currently decided.
- **No new quotes table exists.** Highest applied migration is `081` (env
  var/model config); nothing between `034` and `081` touches quotes.
  PLAN.md's own "Q1 — table + gate" item (`#21`, from the pre-2026-08-03
  staged plan) was never executed, and that whole staged plan (`#21`–`#25`)
  is itself superseded — the replacement ("minimal-records, content-hash-now,
  MANUAL-approval-only rail") has not been designed or built either. There
  is currently no schema, no gate, no tool for the plan actually in force.
- **`backend/app/routers/library.py:102-119`** (`GET /library/book/{doc_id}`,
  behind `require_user` auth) reads `book_quotes` first, falls back to raw
  chunks if empty — since `book_quotes` is empty for every document, this
  endpoint is currently always serving the raw-chunks fallback, unfiltered,
  for any authenticated user opening a book page. Pre-existing, not
  introduced by this audit; noted because it's the one live code path that
  already touches book content in a quote-adjacent way.
- **`scripts/closeness_check.py`** (the wording-similarity gate originally
  built for a different, since-retired proposition-closeness project) exists
  and is functional but explicitly dormant — CLAUDE.md's Landmines section
  records it as "parked by Alex's decision," not switched on anywhere. It
  could plausibly be reused for a future exact-substring/near-duplicate
  verifier (Settled decision #16/#17's "verified-quote component"), but that
  is a design decision for a later session, not something already wired in.

**Commentary gate check (task step 4):** `documents.source_kind` for every
Prince and Murray document is `sermon_transcript`, `magazine_article`, or
`book` — **zero rows tagged `commentary` for either teacher.** Clean; no
commentary material has entered either corpus subset.

---

## 5. Query method note

All queries ran with `psycopg2` against `SUPABASE_DB_URL` (from
`backend/app/.env`), session set `readonly=True, autocommit=True` before any
query executed — the connection itself could not have performed a write.
Author-field reconciliation followed the same pattern used elsewhere in this
repo (`scripts/source_resolver.py`'s source_name/author dual-path): matched
on `sources`/`source_aliases` canonical rows first, cross-checked against a
raw `documents.author ILIKE` sweep to catch anything not linked by
`source_id`, and manually reconciled the one collision found (Ruth Prince).
