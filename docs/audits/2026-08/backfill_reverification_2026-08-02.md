# Backfill Re-verification — is "781 unlicensed docs / 91% Prince+Bevere" real?

**Date:** 2026-08-02
**Session type:** read-only diagnostic / audit (plain/direct terminal path per
CLAUDE.md Session Routing). **Zero DB writes** — the Postgres session was forced
read-only at the connection level (`psycopg2 set_session(readonly=True)`, verified
by a rejected write probe: *"cannot execute CREATE TABLE in a read-only
transaction"*). Every query SELECT-only. No corpus mutation, no extraction run.
**Method:** counts re-derived live from `SUPABASE_DB_URL`, classified by the ACTUAL
extraction gate read out of `scripts/propositions.py::process_document`. All counts
below are live as of this date; treat any figure in PLAN.md / memory as stale.

---

## Verdict (up front)

- **The "781 unlicensed documents need statements" figure is stale and materially
  wrong for the current corpus. The real genuine-backfill set is 7 documents.**
- **The "91% Derek Prince and Bevere" claim is false now.** Of the 7, Derek Prince
  is 3 (43%) and John Bevere is **0** — all of Bevere's documents already have
  propositions.
- **The mass backfill has already run** (the 2026-07-30 #49 run): **850 unlicensed
  documents now carry propositions.** The 781 figure predates that run *and* the
  later Precept-Austin ingestion — it describes a corpus state that no longer
  exists.
- **The 7 residual docs are not an untouched backlog — they are the known failures
  from that run** (their profile matches the documented "7 still-failing: 5
  JSON-escaping defect + 2 book-length"). A naive re-run will *not* fix them:
  the 2 books structurally cannot go through the standard single-call path, and
  the 5 sermons hit an intermittent JSON-escaping defect that is a code problem,
  not a coverage gap.
- **Cost is negligible (~$0.35, well under the $50 ceiling)** — extraction runs on
  Groq Llama-3.3-70b, not Claude.
- **What should change how it runs:** do not schedule a mass backfill (it's done);
  do not let Precept Austin (2,176 word-studies, deliberately locked out) or the
  public-domain material get swept in; treat the 7 as targeted fix-and-retry work.

---

## 1. Total documents (live)

| Metric | Live count |
|---|---|
| Total documents | **3,595** |
| Total propositions | 10,622 |
| Documents with ≥1 proposition | 857 |
| Documents with **zero** propositions | **2,738** |

(857 + 2,738 = 3,595.) Documents→propositions link on `propositions.document_id`
(NOT NULL FK, `ON DELETE CASCADE`, migration 051).

## 2. Documents with zero propositions, by source

**2,738 total**, across 34 distinct sources. Top 15:

| Source | License | Zero-prop docs |
|---|---|---|
| Precept Austin | unlicensed | **2,176** |
| HistoricalChristianFaith Commentaries | public_domain | 307 |
| Jamieson, Fausset & Brown | public_domain | 65 |
| Matthew Henry | public_domain | 65 |
| Adam Clarke | public_domain | 56 |
| CLF Church | owned | 15 |
| Andrew Murray | public_domain | 6 |
| E.M. Bounds | public_domain | 6 |
| STEPBible | public_domain | 4 |
| Rhemata | owned | 3 |
| Charles G. Finney | public_domain | 3 |
| Jonathan Edwards | public_domain | 3 |
| **Derek Prince** | **unlicensed** | **3** |
| R.A. Torrey | public_domain | 2 |
| George Müller | public_domain | 2 |

Long tail: 19 more sources, **22 docs** total. The count is dominated by Precept
Austin (79%) and public-domain commentaries.

## 3. Classification by the ACTUAL extraction gate — and the Prince+Bevere check

`process_document` gates in this order: (1) Precept Austin → locked out;
(2) `license_status NOT IN ('licensed','unlicensed')` → skipped (public_domain /
owned / missing); (3) `word_count < 50` → too thin. Only what survives all three
is genuine backfill. (Note: no `licensed` sources exist live — only `owned`,
`public_domain`, `unlicensed` — so the gate effectively means "unlicensed".)

| Bucket | Docs | Backfill? |
|---|---|---|
| **EXCLUDED: Precept Austin (locked out)** | 2,176 | No — deliberate |
| **EXCLUDED: public_domain/owned (license gate)** | 514 | No — deliberate |
| **BOOK-PATH: public_domain/owned BOOKS** | 41 | Separate workstream |
| **GENUINE BACKFILL (process_document path)** | **5** | **Yes** |
| **GENUINE BACKFILL (book-length, needs book path)** | **2** | **Yes, but hard** |

**Genuine backfill = 7 documents.** By source:

| Source | Docs | Words | ≥50w eligible |
|---|---|---|---|
| Derek Prince | 3 | 28,242 | 3 |
| Daniel Kolenda | 1 | 12,073 | 1 |
| Vlad Savchuk | 1 | 7,989 | 1 |
| Doug Kreighbaum (book) | 1 | 139,659 | 1 |
| F.F. Bosworth (book) | 1 | 90,842 | 1 |
| **Total** | **7** | **278,805** | **7** |

**"91% Prince and Bevere" → FALSE.** Prince = 3/7 = **43%**; Bevere = **0** (all
Bevere docs already have propositions). The claim was plausibly true pre-backfill
(Prince + Bevere were the bulk of the unlicensed corpus) but does not survive
re-derivation.

**Sanity cross-check:** documents *with* propositions split unlicensed 850 /
public_domain 7 — i.e. the backfill did hit the unlicensed corpus (850 done), and
the 7 public-domain-with-props are the already-run book-path books. This is
internally consistent with the documented "850/857 eligible" #49 accounting.

## 4. Exclusions, separated with reasons (NOT folded into the backfill count)

- **Precept Austin — 2,176 docs** (all `word_study`; 1,779 citable + 397
  silent_context). Locked out of the propositions layer by name
  (`PRECEPT_AUSTIN_SOURCE_ID`), a standing decision. Never attempted; never
  should be. **Not backfill.**
- **Public-domain / owned non-book — 514 docs**: 493 `commentary`
  (HistoricalChristianFaith, Jamieson-Fausset-Brown, Matthew Henry, Adam Clarke),
  8 `sermon_transcript`, 6 `paper`, 4 `lexicon` (STEPBible), 3 `position_paper`.
  Skipped by the license gate (already servable verbatim); commentaries and
  lexicons are additionally excluded from answers by ruling (settled decision #5).
  **Not backfill.**
- **Public-domain BOOKS — 41 docs** (E.M. Bounds 6, Andrew Murray 6, Finney 3,
  Edwards 3, Hannah Whitall Smith 2, Müller 2, Torrey 2, S.D. Gordon 2, F.B. Meyer
  2, and 22 singletons). These are eligible via the *book path*
  (`process_book_document`), a **separate, partially-built workstream** — the
  committed title-repeat path reliably covers only ~8 of 53 book documents
  (CLAUDE.md Landmines, PLAN.md #50). **Not part of the "781 unlicensed" backfill.**
- **Sentinel-source (orphaned) docs — 0.** No documents have fallen to the
  "Unassigned — needs source" sentinel; no orphan cleanup is implicated.
- **`is_copyrighted` / `citation_mode`** were checked and do **not** gate
  extraction (the gate keys on `sources.license_status` only); `silent_context`
  documents still get propositions if unlicensed, so citation-mode is not an
  exclusion reason here.
- **Deleted-but-not-purged:** the `documents` table has **no** soft-delete /
  status column, so this class does not exist at the document level — deletes are
  hard (cascade to propositions).

## 5. Attempted-and-produced-zero vs never-attempted

**The database does not record proposition-extraction attempts.** There is no
status column and no log table; `documents.ingest_completed_at` is **uniformly
NULL across the entire corpus** (both the 2,738 zero-prop and the 857
with-prop docs), so it is useless as a proxy. This is stated plainly per the task.

What can be said:
- **The 2,731 excluded docs were never attempted, correctly** — they are gated out
  *before* the model is called (`skipped_precept_austin` / `skipped_licensed`).
- **The 7 genuine-backfill docs were (by strong inference) attempted and failed,
  not never-attempted.** They are substantial, well-formed documents from teachers
  whose *other* documents were all processed in the 850-doc run; their count and
  makeup (5 sermons + 2 books) match the documented "7 still-failing" from the
  2026-07-30 run (5 JSON-escaping defect, 2 book-length). This means **a plain
  re-run silently will not help them**: the failure is a code defect (JSON escaping)
  and a structural gap (book length), not a missing pass. *Caveat: this is an
  inference from the run accounting + document profile; the DB itself cannot
  prove attempt-vs-error for any single row.*

## 6. Spot-read of the 7 (is the material worth extracting?)

All 7 are genuine, substantial, **non-duplicate** (no already-propositionized doc
shares any of their titles), non-junk content:

| Source | Kind | Words | Title | Character |
|---|---|---|---|---|
| Daniel Kolenda | sermon | 12,073 | *Cessationism 9 (The Pagan Origins)* | full sermon |
| Derek Prince | sermon | 5,824 | *Mary: The Pattern Mother* | full sermon |
| Derek Prince | sermon | 10,957 | *Seven Ways To Keep Your Deliverance* | full sermon |
| Derek Prince | sermon | 11,461 | *Who Are The Israel Of God?* | full sermon |
| Vlad Savchuk | sermon | 7,989 | *God Decides When. Not You.* | full sermon |
| Doug Kreighbaum | book | 139,659 | *Manual Systematic Theology* | full book |
| F.F. Bosworth | book | 90,842 | *Christ the Healer* | full book (classic) |

The 5 sermons are exactly the kind of teacher material the propositions layer
exists for; the 2 books are substantial doctrinal works. **The material is worth
extracting** — the question is not *worth* but *how* (see §5/verdict).

## 7. Cost of extracting the genuine backfill

**Extraction model = Groq `llama-3.3-70b-versatile`** (NOT Claude —
`EXTRACTION_MODEL` in `propositions.py`), `max_tokens=8192` per call, one call per
document (normal path) or per chapter (book path).

Per-document basis (Groq ≈ $0.59/M input, $0.79/M output — approximate published
rates; embeddings via OpenAI `text-embedding-3-small` at $0.02/M, negligible):

| Set | Words | ≈ input tok | ≈ cost |
|---|---|---|---|
| 5 sermons | 48,304 | ~64k | ~$0.06 (~$0.01/doc) |
| 2 books (chapter-path) | 230,501 | ~307k | ~$0.28 (~$0.14/book) |
| **Total** | **278,805** | **~371k** | **≈ $0.35** |

**Well under the $50 ceiling** — by two orders of magnitude. Cost is not a
constraint here and the order of magnitude is robust to any reasonable Groq-pricing
variance.

## 8. Runtime, interruptibility, resumability

- **Runtime:** Groq is fast. The 5 sermons ≈ 5 calls, ~1–2 min. The 2 books via
  the chapter path ≈ dozens of calls + per-proposition embeddings, ~20–40 min.
  Total under ~1 hour *if it could run end-to-end* (see caveat).
- **Interruptible & resumable: yes, safely.** `run_full_backfill.py` selects
  documents that *currently* have zero propositions and is documented crash-safe /
  resumable; `store_propositions()` is per-document DELETE-then-insert (idempotent
  per doc), so interrupting between documents leaves completed docs intact and a
  resume re-selects only the still-empty ones. No partial-write corruption risk.
- **Caveat that dominates runtime:** the standard backfill
  (`run_full_backfill` → `process_document`, single-call `max_tokens=8192`)
  **cannot process the 2 books** — that is the documented book-length gap; they
  require `process_book_document`, and only if they are title-repeat books (8/53
  covered) or via the deliberately-uncommitted numeral detector (zero production
  callers, a known confident-wrong failure mode). So the 2 books are not a
  "run it" item at all without per-book verification.

---

## Verdict

1. **Is the backfill genuinely needed?** The *mass* backfill implied by "781
   unlicensed documents" is **not needed — it already ran** (850 unlicensed docs
   done, 2026-07-30). What remains is **7 documents**, and they are the **known
   residual failures** of that run, not a fresh backlog.
2. **Is the number materially different from 781?** **Yes, drastically — 7, not
   781.** The 2,738 zero-proposition docs are 99.7% deliberate exclusions (2,176
   Precept Austin locked out; 514 public-domain/owned skipped; 41 public-domain
   books on a separate path). The 781 figure is stale on two counts (pre-backfill,
   and pre-Precept-Austin ingestion).
3. **Is "91% Prince and Bevere" correct?** **No.** Prince = 43%, Bevere = 0% of
   the genuine 7.
4. **Anything that should change how it runs?**
   - **Do not schedule a mass backfill.** It is complete. Point any run only at the
     7 residual documents, never at "all zero-proposition docs" (that would target
     2,176 locked-out Precept Austin word-studies and 514 public-domain docs).
   - **The 5 sermons need the JSON-escaping defect handled**, not just a re-run —
     a plain retry may succeed intermittently but the defect is a code problem
     (present in v3/v3.1 alike). Treat as fix-then-retry, cheap (~$0.06).
   - **The 2 books need the book path** and per-book verification; the standard
     single-call backfill will fail on them by construction. They are not a
     "run the backfill" item.
   - **Cost is a non-issue** (~$0.35); the constraint is code-readiness, not budget.

**Bottom line: the backfill is done. The "781 / 91% Prince+Bevere" number should be
retired. What's left is a 7-document fix-and-retry task — 5 sermons blocked on the
JSON-escaping defect and 2 books blocked on the book-length path — not a
corpus-scale run.**
