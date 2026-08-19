# Book Document Structure — Read-Only Diagnostic

Read-only diagnostic. Connection: `rhemata_readonly_analysis` only.
Asserted `current_user = rhemata_readonly_analysis` before any query.
No changes to any file, database row, plan, or documentation file.
No proposals or recommendations. This report is input to a decision Alex has not made yet.

---

## Executive summary

**No structural information about book body boundaries is recorded in the database.** A book document is a flat run of text chunks ordered by `chunk_index`, with no field, column, table, or metadata that marks where front matter ends, where the quotable body begins, where chapters divide, or where back matter begins. The only existing mechanism that distinguishes body from apparatus is a per-chunk `quote_ineligible_reason` column that has been manually populated for 66 chunks across 10 of 53 book documents — all 10 are Andrew Murray books. The remaining 43 book documents have zero apparatus flagging.

Chapter-scoped extraction was built and proven live, but it is extraction-time only: chapter boundaries are computed, used to scope per-chunk proposition extraction, and then discarded. Nothing about chapter structure is persisted. The production backfill never used the chapter-scoped path at all — it called the single-call `process_document()` for every document including books.

A numeral-heading chapter detector (`detect_book_chapters()`) exists in the codebase but has zero production callers. It found a confident-wrong-answer failure mode twice during development, only one of which has a clean fix. It is not wired into any ingestion or extraction path.

---

## 1. What structural information is recorded per document

**Nothing that marks chapters, sections, front matter, or body boundaries.**

The `chunks` table has these columns:
- `id`, `document_id`, `content`, `embedding`, `chunk_index`, `created_at`
- `fts` (tsvector), `bible_references` (text array)
- `rewritten_content` (paraphrase text, populated for 142 of 25,064 book chunks)
- `quote_ineligible_reason` (text, populated for 66 of 25,064 book chunks — see section 4)

There is no `chapter_index`, `chapter_label`, `section`, `is_front_matter`, `is_body`, `is_back_matter`, or any analogous field. A chunk knows its ordinal position (`chunk_index`) and its text (`content`). That is all.

The `documents` table has `full_text` (text) and `ingest_completed_at` (timestamp), but:
- `full_text` is NULL for all 53 book documents. The original full book text is not stored — only the chunks.
- `ingest_completed_at` is NULL corpus-wide (a known landmine, recorded in AGENTS.md).

The `books` table has `id`, `title`, `author`, `description`, `topic_tags`, `created_at`, `era`, `document_id` — no chapter structure.

The `proposition_chunks` table is a link table with columns `(proposition_id, chunk_id)` — it connects propositions to chunks but carries no chapter or structural metadata.

**Chapter information is not stored as a field, not inferable from any recorded structure, and not present anywhere in the schema.** It can only be computed at read time by re-running the chapter detector against the chunk text — the same detection that has the regression history described in section 5.

---

## 2. How book documents got ingested, and whether that path preserved structure

Two ingestion paths exist in the codebase. Only one was used in production. Neither preserved structure.

### Path A: `process_document()` — the production path (single-call)

This is the path that actually ran. Both `shared_ingest.py` (the main ingestion module) and `run_full_backfill.py` (the corpus backfill) call `propositions.process_document()` for every document, including books. Neither checks `source_type == 'book'` or routes to the book-specific path.

`process_document()` feeds the ENTIRE document text to the model in a single LLM call. The text is reconstructed from chunks by `"\n".join()` — a flat concatenation with no structure (confirmed in `run_full_backfill.py:128-138` and `shared_ingest.py`). Chapter boundaries are never computed on this path. The known limitation: this path structurally breaks on book-length documents (the `max_tokens=8192` ceiling compresses or truncates long books — a documented finding from the 2026-08-02 backfill).

### Path B: `process_book_document()` / `_extract_and_store_book_chapters()` — the chapter-scoped path (built, proven, never used in production)

This path was built in commit `d7c46f5` (2026-07-31). It calls `split_book_into_chapters()` to detect chapter boundaries, then runs `extract_propositions()` once per chapter (multi-call), then `store_propositions()` once per chapter with `clear_existing=False`. A front/back-matter classifier (`is_front_back_matter()`) skips title-page/index/table-of-contents-shaped spans before they reach the model.

This path **computes chapter structure at extraction time and discards it**. The reconciliation dict returned by `_extract_and_store_book_chapters()` contains `chapters_skipped_front_matter`, `per_chapter` outcomes (label, word_count, outcome per chapter), and other diagnostics — but this dict is returned to the caller, logged, and never persisted. `store_propositions()` signature is `(conn, document_id, propositions, embed_fn, prompt_version, chunk_ids=None, clear_existing=True)` — it accepts a flat list of `chunk_ids` but no chapter label, chapter index, or body/apparatus flag. The chapter structure is used to scope which chunks go to which extraction call, and then it is gone.

**Production callers of `process_book_document()` / `_extract_and_store_book_chapters()`: zero.** The function appears only in `scripts/propositions.py` (definition) and `scripts/test_propositions_book_chapters.py` + `scripts/test_propositions_book_numeral_detection.py` (tests). AGENTS.md records that 2 books were extracted via the multi-call path on 2026-08-02, but that was done by a now-deleted one-off script, not by any current production code. The backfill (`run_full_backfill.py`) used `process_document()` for all 515 documents it processed, including books.

### What this means for structure preservation

Even if Path B had been used in production, it would not have persisted structure. The chapter boundaries are ephemeral — computed, used for extraction scoping, discarded. A book processed through Path B today has the same flat chunk run in the database as a book processed through Path A. You cannot tell from the database which path a book went through, or whether its chapters were ever detected.

---

## 3. Per-document: chunk count and chunk-0 content

All 53 book documents (`source_type='book'`), ordered by source name then title. Chunk 0 is the first chunk by `chunk_index`. The observation is whether chunk 0 contains front matter (CCEL catalog boilerplate, table of contents, translator's note, publisher information, OCR garbage from scanned title pages) versus starting directly in the author's text.

| # | Source | Title | Chunks | Chunk 0 observation |
|---|--------|-------|--------|---------------------|
| 1 | A.B. Bruce | The Training of the Twelve | 774 | CCEL catalog boilerplate (Author(s), Publisher, Description) |
| 2 | A.J. Gordon | The Twofold Life | 2 | Google Books scan preamble ("digital copy of a book...") |
| 3 | Abraham Kuyper | The Work of the Holy Spirit | 49 | CCEL catalog boilerplate |
| 4 | An Unknown Christian | The Kneeling Christian | 148 | CCEL catalog boilerplate |
| 5 | Andrew Murray | Absolute Surrender | 124 | CCEL catalog boilerplate |
| 6 | Andrew Murray | The Deeper Christian Life | 82 | CCEL catalog boilerplate |
| 7 | Andrew Murray | The Lord's Table | 78 | CCEL catalog boilerplate |
| 8 | Andrew Murray | The Master's Indwelling | 144 | CCEL catalog boilerplate |
| 9 | Andrew Murray | The New Life | 249 | CCEL catalog boilerplate + table of contents (lists "Translator's Note 2") |
| 10 | Andrew Murray | The School of Obedience | 90 | CCEL catalog boilerplate |
| 11 | Andrew Murray | The True Vine | 70 | CCEL catalog boilerplate |
| 12 | Andrew Murray | The Two Covenants | 154 | CCEL catalog boilerplate |
| 13 | Andrew Murray | Waiting On God! | 104 | CCEL catalog boilerplate |
| 14 | Andrew Murray | With Christ in the School of Prayer | 257 | CCEL catalog boilerplate |
| 15 | Brother Lawrence | The Practice of the Presence of God | 43 | CCEL catalog boilerplate |
| 16 | Catherine Booth | Aggressive Christianity | 188 | OCR garbage from scanned title page (garbled characters) |
| 17 | Chapel Library | Profiting from the Word | 142 | Publisher information ("Published by Chapel Library...") |
| 18 | Charles G. Finney | Lectures on Revivals of Religion | 681 | CCEL catalog boilerplate |
| 19 | Charles G. Finney | Lectures to Professing Christians | 479 | CCEL catalog boilerplate |
| 20 | Charles G. Finney | Power From On High | 107 | CCEL catalog boilerplate |
| 21 | CLF Church | Foundations of Healthy Church Life | 99 | Appears to start in content (NT Wright quote, then "Nine Passionate Pursuits") |
| 22 | Covenant Harvest Church | Foundation Stones for New Believers | 93 | Table of contents |
| 23 | Doug Kreighbaum | Essentials For New Disciples | 163 | Title + table of contents |
| 24 | Doug Kreighbaum | Manual Systematic Theology | 423 | Title + table of contents |
| 25 | Doug Kreighbaum | Maturing in God | 62 | Title + table of contents |
| 26 | Doug Kreighbaum | Ministry of God's Word | 52 | Title + table of contents (inline) |
| 27 | E.M. Bounds | Power Through Prayer | 79 | CCEL catalog boilerplate |
| 28 | E.M. Bounds | Prayer and Praying Men | 129 | CCEL catalog boilerplate |
| 29 | E.M. Bounds | Purpose in Prayer | 121 | CCEL catalog boilerplate |
| 30 | E.M. Bounds | The Essentials of Prayer | 121 | CCEL catalog boilerplate |
| 31 | E.M. Bounds | The Necessity of Prayer | 120 | CCEL catalog boilerplate |
| 32 | E.M. Bounds | The Reality of Prayer | 116 | CCEL catalog boilerplate |
| 33 | E.M. Bounds | The Weapon of Prayer | 135 | CCEL catalog boilerplate |
| 34 | F.B. Meyer | The Secret of Guidance | 105 | CCEL catalog boilerplate |
| 35 | F.B. Meyer | The Way Into the Holiest | 291 | CCEL catalog boilerplate |
| 36 | F.F. Bosworth | Christ the Healer | 256 | Table of contents (lists "FOREWORD", "AUTHOR'S PREFACE", sermons) |
| 37 | George Müller | Autobiography | 462 | OCR garbage from scanned title page (Internet Archive digitization) |
| 38 | George Müller | How God Answers Prayer | 118 | OCR garbage from scanned title page (library stamp) |
| 39 | Hannah Whitall Smith | Every-day Religion | 294 | Scanned title page (title, author, publisher, year) |
| 40 | Hannah Whitall Smith | The God of All Comfort | 2 | Google Books scan preamble |
| 41 | J.C. Ryle | Holiness | 592 | CCEL catalog boilerplate |
| 42 | John Owen | Pneumatologia | 2296 | CCEL catalog boilerplate |
| 43 | John Wesley | Sermons on Several Occasions | 2323 | CCEL catalog boilerplate |
| 44 | John Wesley | The Journal of John Wesley | 564 | CCEL catalog boilerplate |
| 45 | Jonathan Edwards | Religious Affections | 581 | CCEL catalog boilerplate |
| 46 | Jonathan Edwards | The Works of Jonathan Edwards, Vol. 1 | 4922 | CCEL catalog boilerplate |
| 47 | Jonathan Edwards | The Works of Jonathan Edwards, Vol. 2 | 5186 | CCEL catalog boilerplate |
| 48 | Phoebe Palmer | The Way of Holiness | 287 | OCR garbage from scanned title page |
| 49 | R.A. Torrey | How To Pray | 96 | CCEL catalog boilerplate |
| 50 | R.A. Torrey | The Person and Work of The Holy Spirit | 238 | CCEL catalog boilerplate + table of contents (lists "Chapter I. The Personality of the Holy Spirit") |
| 51 | Samuel Dickey Gordon | Quiet Talks on Power | 168 | CCEL catalog boilerplate + table of contents |
| 52 | Samuel Dickey Gordon | Quiet Talks on Prayer | 183 | CCEL catalog boilerplate |
| 53 | William Booth | In Darkest England | 422 | OCR garbage from scanned title page |

**Observation:** Of 53 book documents, chunk 0 contains front matter (CCEL boilerplate, scanned title page, table of contents, or OCR garbage) in at least 50. Two CLF/Covenant Harvest documents (#21, #22) may start closer to content, but #22 opens with a table of contents and #21 opens with a front-matter epigraph. No book document unambiguously starts in the author's body text at chunk 0. The front matter typically spans the first 2-4 chunks (roughly 3,000-8,000 characters) before the author's text begins.

---

## 4. Whether anything exists today that distinguishes body text from apparatus

**One column, manually populated, covering 10 of 53 book documents.**

The `chunks.quote_ineligible_reason` column is the only field in the schema that distinguishes body from apparatus. It is a free-text column (no enum constraint) populated per-chunk. As of this query:

- **66 book chunks** (of 25,064 total book chunks) carry a `quote_ineligible_reason` value.
- **10 book documents** (of 53) have at least one flagged chunk. All 10 are Andrew Murray books.
- **43 book documents** have zero flagged chunks — every chunk is treated as body by default.

The distinct reason values and their counts (across all chunks, not only books):

| Reason | Count |
|--------|-------|
| `ccel_editorial_front_matter_not_teacher_authored` | 32 |
| `third_party_quotation_george_muller_not_teacher_authored` | 17 |
| `scripture_index_auto_generated_not_teacher_authored` | 7 |
| `ccel_editorial_description_not_teacher_authored` | 3 |
| `translators_note_not_teacher_authored` | 3 |
| `guest_speaker_not_derek_prince_authored` | 2 |
| `ccel_related_books_advertisement_not_teacher_authored` | 2 |
| `catechism_and_worship_manual_quotation_not_teacher_authored` | 2 |
| (non-book: `the_bride_prepares_herself`appendix) | 1 |

**What this column does not cover:**
- No chunk in any non-Murray book is flagged. E.M. Bounds, Charles Finney, John Wesley, Jonathan Edwards, J.C. Ryle, John Owen, F.B. Meyer, R.A. Torrey, S.D. Gordon, Brother Lawrence, A.B. Bruce, Abraham Kuyper, An Unknown Christian, Catherine Booth, Phoebe Palmer, William Booth, George Müller, Hannah Whitall Smith, F.F. Bosworth, Doug Kreighbaum, Chapel Library, CLF Church, Covenant Harvest Church, A.J. Gordon — zero flagged chunks across all of these, despite many having the same CCEL catalog boilerplate in chunk 0.
- No mechanism flags inline footnotes (the `-- Translator` notes inside Murray's *The New Life* and *The Lord's Table* that the contamination pull found). The `translators_note_not_teacher_authored` flag covers only the standalone translator's-note *block* in chunks 3-5 of *The New Life*, not the 7 inline footnotes embedded mid-body.
- No mechanism flags back matter (scripture indexes, related-books advertisements) for any book except those Murray books where it was manually applied.
- No schema-level constraint, enum, or automated process maintains this column. It appears to have been populated by one-off manual or script-based passes against Murray books only.

**Nothing else in the schema or ingestion code flags footnotes, headers, front matter, or non-body content.** The ingestion code (`shared_ingest.py`, `run_full_backfill.py`) does not set `quote_ineligible_reason`. The chapter-scoped extraction path (`_extract_and_store_book_chapters()`) classifies front/back matter via `is_front_back_matter()` but only uses that classification to skip extraction — it does not write to `quote_ineligible_reason` or any other persistent field.

---

## 5. State of the existing numeral-heading chapter detector

### Where it lives

`detect_book_chapters()` is defined at `scripts/propositions.py:3296`. It is a pure function (no DB, no LLM, no network) that takes `ordered_chunks: List[Tuple[str, str]]` and returns a `BookStructureResult` (status, chapters list, split_method, diagnostics dict).

### What it does

It combines two detection strategies:

1. **Repeat-marker detector** (`split_book_into_chapters()`, already committed and production-used): detects chapters by finding lines that repeat verbatim twice — the table-of-contents entry and the chapter heading itself. Works for books whose TOC lists chapter titles that then appear again as headings. Returns spans with `split_method="title_repeat_boundary"`.

2. **Numeral-heading detector** (`_detect_numeral_heading_sequence()`, new in `8d6b7bc`): detects chapters by finding a sequence of roman-numeral or bare "Chapter N" headings (e.g. "I. The Importance of Prayer", "II. ...", "III. ...") without requiring a TOC repeat. Uses a dynamic-programming objective to select the best chain of headings. Returns spans with `split_method="numeral_heading_boundary"`.

The decision logic (in order): if numeral-detector is confident AND N > R → "numeral_detected"; elif R >= 3 → "repeat_detected" (returns repeat-detector result verbatim); elif numeral-detector is confident → "numeral_detected"; else → "needs_eyeball" (chapters=None).

### Callers

**Zero production callers.** The function is called only from `scripts/test_propositions_book_numeral_detection.py` (a test file). It is never called from:
- `process_book_document()` or `_extract_and_store_book_chapters()` (which use `split_book_into_chapters()` directly, bypassing `detect_book_chapters()` entirely)
- `shared_ingest.py` (which calls `process_document()`, not the book path at all)
- `run_full_backfill.py` (which also calls `process_document()`)
- Any other script

### The two prior regressions

From the commit message of `8d6b7bc` (2026-08-05):

> "it found a confident-wrong-answer failure mode twice during development, only one of which has a clean fix. Committing now on Alex's explicit confirmation, to preserve the work in history; wiring it in is a separate, deliberate future decision."

The two failure modes, recovered from the test file (`test_propositions_book_numeral_detection.py`):

**Regression 1 — Torrey "How To Pray" (chapter I resolves to a TOC line, not the real heading):**
Chapter I resolves to offset 6155 — the book's own table-of-contents restatement line ("I. The Importance of Prayer", a standalone TOC entry) — instead of the real "CHAPTER I" / "THE IMPORTANCE OF PRAYER" heading at offset 6830. Root cause: the TOC line satisfies all 5 discriminators (including discriminator 5, "followed by real prose", only because a later TOC line in the same listing happens to wrap to >=50 chars — a pre-existing weakness). The TOC line sits 675 characters earlier than the real heading, giving the spurious chain a marginally larger overall span, which Fix B's span-weighted DP objective prefers. Chapters II-XII (11 of 12) are unaffected. **Not fixed** — fixing requires touching the discriminator-5 logic, which was out of scope.

**Regression 2 — Murray "The School of Obedience" (nested subsection headings preferred over chapter headings):**
The numeral detector's isolated behavior prefers a tightly-clustered roman-numeral SUB-SECTION heading sequence (e.g. "I. FAITH SEES IT.", "II. FAITH DESIRES IT." inside chapter VI) over the correctly-spread chapter sequence, because length-tie + min-max-gap systematically prefers tightly-clustered subsections. This book is rescued only because the repeat detector (R=10, >= 3) wins first via the "elif R >= 3: repeat_detected" branch, so the flawed numeral chain is never used. **Not fixed** — "do not redesign" instruction. A future book with the same nested-subsection shape but without repeat-detector rescue would not be saved.

### Additional regression in `is_front_back_matter()` (commit `8e251c8`, 2026-07-31)

Two independent bugs in the front/back-matter classifier (not in `detect_book_chapters()` itself, but in the function that any chapter detection path depends on to separate body from apparatus):

**(a) Third-party editorial front matter had no signal:** translator's/editor's notes, introductions credited to someone other than the book's own author, were extracted and stored as if they were the credited author's own teaching. Fixed via `_has_third_party_byline()` detector + `_MATTER_LABEL_APPARATUS` set.

**(b) Roman-numeral arm miscounted common words:** `_digit_token_ratio()`'s roman-numeral arm miscounted the capitalized pronoun "I" and ordinary lowercase words spelled entirely from IVXLCDM (e.g. "did", "mid") as roman-numeral locators, pushing genuine short chapters over the digit-ratio threshold and wrongly excluding them as front/back matter. Fixed by requiring lowercase-in-original-text and a round-trip-valid roman numeral.

---

## Bottom line

A book in this corpus is a flat run of text chunks with no recorded structure. The database does not know where a book's body begins or ends, where its chapters divide, or which chunks are apparatus. The only existing body/apparatus distinction is a manually-populated column covering 10 of 53 books. The chapter detection code that could compute boundaries exists but is unwired, and its own development found two confident-wrong-answer failure modes, only one of which is rescued (by a different detector winning first), and neither of which is fixed. The production extraction path never used chapter-scoped extraction at all.

---

## Connection and write confirmation

- **Read-only role used throughout:** `rhemata_readonly_analysis`, confirmed by `SELECT current_user` before any query.
- **Database writes this session:** zero.
- **Files modified this session:** zero (this report file is the only output).
- **Commits created:** zero.
