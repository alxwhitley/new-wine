# Corpus Quality Measurement — Phase 1 Report (2026-07-24)

Read-only measurement. No deletions, no visibility changes, no writes to any table.

## Scope

- In-scope documents scored: **1641**
- Excluded: the Precept Austin source (`698e0596-a9c6-4890-958d-9199f1b8f762`), per standing source-level exclusion.
- All other documents in the corpus are in scope, including 4 STEPBible lexicon/background documents — see caveat below.

## Methodology — signal sets actually used

No LLM calls this phase. All three dimensions are computed from countable, deterministic signals only.

**1. Attribution risk** (higher = more likely the single-teacher attribution is wrong or incomplete)
- Title contains a guest/second-speaker indicator (`w/`, `ft.`/`feat.`, "interview", "panel", "Q&A", "conversation with", "guest", "talks with", `& Firstname Lastname`) → +3
- Title contains "with Firstname Lastname" (weaker pattern, only scored if the above didn't already fire) → +2
- Opening ~300 words contain guest-introduction language ("our guest", "please welcome", "joining me/us", "my guest today", "welcome to the show/podcast", "today's guest", "special guest") → +2 per distinct phrase, capped at +6
- Source is classified a **multi-voice channel** rather than a single-teacher archive or book → +3. Classification is source-level and countable: ≥3 documents, ≥3 distinct non-null `author` values, and <50% of the source's documents have `author == source_name` → multi-voice channel. ≥80% match rate, or `source_type == 'book'` → single-teacher archive. Otherwise ambiguous (no bonus).

**2. Signal density** (packaging_score; higher = more packaging relative to teaching)
- Platform/CTA/greeting language density per 1000 words ("subscribe", "link in the description", "hit the bell", "welcome back", "let's pray", "before we get started", "follow us on", "sign up", "donate", "click the link", "smash that", URLs, etc. — 27-phrase list)
- + 40 × sentence-repetition rate (exact-duplicate sentences ≥4 words, as a fraction of all sentences ≥4 words)
- − scripture-reference density per 1000 words (from `documents.bible_references`, already extracted corpus-wide; capped at 15 so very citation-dense documents don't runaway-dominate the credit)

**3. Text integrity** (integrity_score; higher = more integrity problems)
- Document does not end on terminal punctuation → +25
- Non-word/non-standard-punctuation character ratio × 400
- Missing chunk-index gaps × 6 per gap (0 found corpus-wide — see caveat)
- Near-empty-chunk ratio (chunks <40 chars) × 30
- Repeated-non-digit-character-run rate (runs of 5+, per 10,000 chars, floored at a 2,000-char denominator) × 3 — digits are excluded because some sources (STEPBible verse-code citations) legitimately contain long digit runs that are not scan/OCR garbage; this was caught as a false-positive class during verification and fixed before this report was built (see caveats).

**Near-duplicates** (reported separately, not folded into the three scores): 5-word-shingle MinHash (48 hash functions, deterministic seed), compared pairwise **within the same source only** — cross-source comparison was out of scope for this pass. Similarity ≥0.5 reported as a candidate; ≥0.85 as likely-duplicate.

**Composite score** (used only to rank the worst/middle/best lists): each dimension's raw score is converted to a 0–100 percentile rank across the 1,641 in-scope documents, then the three percentile ranks are averaged unweighted. This is a methodology choice, not specified by the original brief — a document that is extremely bad on one axis and fine on the other two will rank as moderately bad overall, not catastrophically bad. The per-dimension distributions below are the way to see axis-specific worst cases.

## Caveats found during verification — read before trusting the numbers

- **A real scoring bug was caught and fixed before this report was generated.** The first version of the repeated-character-run signal matched digit runs, which fired systematically on HistoricalChristianFaith's internal verse-reference codes (e.g. `revelation 5000001`) — a citation format, not scan garbage. It also used a raw count instead of a length-normalized rate, which let the corpus's handful of 1–2 million-word documents dominate the "worst integrity" list purely by being long. Both fixed (digits excluded from the pattern; rate-per-10k-chars with a length floor) before any of the numbers below were generated. Flagged here per this project's standing practice of reporting bugs found and fixed in-session rather than smoothing over them.
- **The 4 STEPBible lexicon/background documents (`source_type='background'`) are structurally different from teaching content** and several signals don't cleanly apply to them: they are one-entry-per-chunk reference databases (10,258 chunks / 420,949 words for the Hebrew lexicon alone), so "ends without terminal punctuation" fires trivially (a dictionary entry doesn't end in a period) and scripture-reference density is meaningless (a lexicon entry isn't a scripture citation). Their integrity/packaging scores should not be read the same way as a sermon's.
- **HistoricalChristianFaith Commentaries Database documents vary in length by five orders of magnitude** — from a single ~150-character cross-reference stub (`Anselm of Laon`) to a 2.66-million-word collected-works dump (`Thomas Aquinas`, 7,657 chunks). "One document" is not a consistent unit of content for this source. Scores for this source's documents should be read per-document, not assumed comparable to a sermon transcript.
- **A genuine, actionable ingestion-pipeline finding, not just a low score:** 29 of the 33 documents carrying `source_name = 'New Wine Magazine'` (this is the entire `magazine_article` population) end their stored text with a leaked JSON/markdown code-fence artifact — literally `"\n}\n\`\`\`` or `"\n}` — from the Gemini/Groq extraction pipeline (`extract_magazine.py`). The article text itself reads fine; only the last few characters of the last chunk carry the artifact. This is a well-scoped, mechanically fixable defect (strip the trailing pattern and re-ingest, or patch the approved `.md` source files), not a content-quality problem. It is a large part of why New Wine Magazine articles cluster at the top of the worst-overall list below — worth fixing on its own before re-running any future pass, since it will otherwise keep re-flagging clean content.
- **A second, separate, corpus-wide ingestion-pipeline finding, verified directly against the DB (not just the JSON snippet — the JSON's stored 120-char tail undercounted this by more than half):** at least 19 public-domain books end their stored text with a leaked CCEL website artifact — either an ebook-store promo footer ("Visit the Kindle store or see http://www.ccel.org/...") or a bare "Index of Scripture References" page-number dump, sometimes just a trailing bare page number with no other text. This is NOT limited to the 13 documents whose `source_id` resolves to the "Christian Classics Ethereal Library" source row — it also hits books correctly attributed to their real individual author (Andrew Murray ×4, E.M. Bounds ×4, Charles G. Finney ×2, John Wesley ×1, Brother Lawrence ×1, R.A. Torrey ×1, An Unknown Christian ×1), because all of them were scraped through the same CCEL pipeline (`scripts/scrape_ccel.py` / `download_ccel.py`) regardless of which source they ultimately resolved to. Confirmed affected titles: *The School of Obedience*, *Prayer and Praying Men*, *Purpose in Prayer*, *Absolute Surrender*, *The Weapon of Prayer*, *The Two Covenants*, *The Deeper Christian Life*, *The Reality of Prayer*, *How To Pray*, *The True Vine*, *The Journal of John Wesley*, *Lectures to Professing Christians*, *The Kneeling Christian*, *Power From On High*, *With Christ in the School of Prayer*, *The Practice of the Presence of God*, *The Essentials of Prayer*, *Sermons on Several Occasions*, *The Necessity of Prayer*. At least one more (E.M. Bounds' *Power Through Prayer*) shows the same bare-trailing-page-number pattern and is very likely the same root cause, not separately confirmed. Same fix shape as the New Wine finding: strip the trailing pattern, re-ingest.
- **The multi-voice-channel classification (attribution-risk signal #4) conflates two different risks and should not be read as "this source has the Savchuk/Bevere co-host problem."** It fires whenever a source has ≥3 distinct non-null `author` values and a low author/source-name match rate — true both for a channel with real, uncredited co-speakers (the risk this signal is meant to catch) AND for a library/anthology source that correctly attributes each document to its own real author but groups them under one umbrella source row (Christian Classics Ethereal Library, HistoricalChristianFaith Commentaries Database, New Wine Magazine's un-resolved articles). For the latter group the underlying `author` field is very likely already correct — grouping under one source is a cataloging fact, not an attribution error. This signal cannot currently tell the two cases apart from countable signals alone; 18 of the 40 documents in the worst-overall list below are flagged **only** via this bonus, and most of those are anthology/library documents, not genuine guest-speaker risk. Treat this as the weakest of the four attribution-risk signals and verify manually before acting on it for any given source.
- **One single-chunk document (`CLF Church` — "Prophetic Equipping via Zoom", 102 words) contains no teaching content at all** — its stored text is a Zoom meeting link and passcode, nothing else. This is the single most severe finding in the corpus by a different kind of severity than a score number conveys: it isn't a badly-scored teaching document, it's not a teaching document.
- **Near-duplicate detection is scoped to within-source pairs only.** A document near-duplicate across two different sources (e.g. the same sermon re-uploaded under a slightly different channel/source) would not be caught by this pass.
- **Zero chunk-index gaps found corpus-wide.** Migration 061's `UNIQUE(document_id, chunk_index)` constraint (closed 2026-07-13 per PLAN.md) appears to hold; this signal currently contributes nothing to any score but is kept for future-proofing.

## Grouped results — by material type (`source_type`)

User's suggested categories map onto this corpus's actual `source_type` values as: transcript → `sermon`; book → `book`; article → `paper`/`position_paper`; magazine → `magazine_article`. `commentary` and `background` (lexicon) are large enough in this corpus (493 and 4 docs) to warrant their own rows rather than folding into "other".

### Attribution risk

| Material type | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Sermon transcript | 1038 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 3.0 | 6 |
| Commentary | 493 | 0 | 0.0 | 0.0 | 3.0 | 3.0 | 3.0 | 3 |
| Book | 55 | 0 | 0.0 | 0.0 | 0.0 | 1.5 | 3.0 | 3 |
| Magazine article | 33 | 0 | 0.0 | 0.0 | 0.0 | 3.0 | 3.0 | 3 |
| Paper | 10 | 0 | 0.0 | 3.0 | 3.0 | 3.0 | 3.0 | 3 |
| Other | 4 | 0 | 0.9 | 2.25 | 3.0 | 3.0 | 3.0 | 3 |
| Background / lexicon | 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Position paper | 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Manual | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### Signal density (packaging)

| Material type | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Sermon transcript | 1038 | -15.0 | 0.0 | 1.48 | 2.99 | 4.22 | 5.32 | 24.43 |
| Commentary | 493 | -15.0 | -9.8 | -1.42 | -0.04 | 0.73 | 4.0 | 26.74 |
| Book | 55 | -9.51 | -6.12 | 1.94 | 3.69 | 4.89 | 5.43 | 6.94 |
| Magazine article | 33 | -12.27 | -8.34 | -0.21 | 1.7 | 3.09 | 4.6 | 6.71 |
| Paper | 10 | -13.86 | -13.25 | -11.8 | -8.25 | -6.81 | -4.55 | 1.57 |
| Other | 4 | -15.0 | -10.5 | -3.75 | 2.66 | 13.8 | 29.05 | 39.22 |
| Background / lexicon | 4 | 0.28 | 0.36 | 0.47 | 0.59 | 2.14 | 4.83 | 6.62 |
| Position paper | 3 | -5.83 | -5.15 | -4.12 | -2.42 | -1.51 | -0.96 | -0.59 |
| Manual | 1 | -6.32 | -6.32 | -6.32 | -6.32 | -6.32 | -6.32 | -6.32 |

### Text integrity problems

| Material type | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Sermon transcript | 1038 | 0.0 | 0.0 | 0.0 | 2.71 | 4.02 | 4.95 | 29.65 |
| Commentary | 493 | 0.0 | 0.0 | 0.08 | 0.34 | 1.44 | 26.94 | 32.0 |
| Book | 55 | 3.17 | 25.03 | 25.22 | 26.22 | 26.92 | 27.67 | 72.68 |
| Magazine article | 33 | 1.2 | 7.37 | 26.68 | 27.63 | 28.77 | 28.83 | 30.92 |
| Paper | 10 | 0.16 | 0.24 | 5.04 | 24.78 | 26.77 | 26.98 | 27.92 |
| Other | 4 | 2.26 | 9.08 | 19.31 | 25.66 | 30.36 | 37.65 | 42.51 |
| Background / lexicon | 4 | 6.03 | 9.79 | 15.45 | 18.94 | 22.98 | 29.65 | 34.09 |
| Position paper | 3 | 2.59 | 2.98 | 3.58 | 4.57 | 18.22 | 26.41 | 31.88 |
| Manual | 1 | 26.51 | 26.51 | 26.51 | 26.51 | 26.51 | 26.51 | 26.51 |

### Composite (0-100 percentile avg)

| Material type | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Sermon transcript | 1038 | 5.12 | 31.57 | 41.53 | 51.34 | 59.33 | 66.46 | 90.51 |
| Commentary | 493 | 17.46 | 29.13 | 37.85 | 45.71 | 55.73 | 66.26 | 84.47 |
| Book | 55 | 22.76 | 51.83 | 59.46 | 68.58 | 79.86 | 84.59 | 92.56 |
| Magazine article | 33 | 35.59 | 45.97 | 54.19 | 65.67 | 79.67 | 92.77 | 93.82 |
| Paper | 10 | 37.07 | 44.14 | 48.83 | 57.86 | 64.54 | 65.3 | 68.7 |
| Other | 4 | 42.13 | 47.69 | 56.04 | 63.74 | 72.8 | 83.57 | 90.75 |
| Background / lexicon | 4 | 44.72 | 45.28 | 46.12 | 50.56 | 61.51 | 74.07 | 82.44 |
| Position paper | 3 | 31.32 | 34.49 | 39.25 | 47.17 | 48.91 | 49.95 | 50.65 |
| Manual | 1 | 51.5 | 51.5 | 51.5 | 51.5 | 51.5 | 51.5 | 51.5 |

## Grouped results — by source

23 sources have ≥3 in-scope documents (shown as distributions below); 26 sources have 1-2 documents (listed individually after, since a distribution over 1-2 points isn't meaningful).

### Attribution risk

| Source | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Derek Prince | 495 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3 |
| HistoricalChristianFaith Commentaries Database | 307 | 3 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 3 |
| John Bevere | 220 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3 |
| Vlad Savchuk | 126 | 3 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 3 |
| Leonard Ravenhill | 117 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3 |
| Matthew Henry | 65 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Jamieson, Fausset & Brown | 65 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Adam Clarke | 56 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Zac Poonen | 50 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3 |
| CLF Church | 18 | 3 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 6 |
| New Wine Magazine | 15 | 3 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 3 |
| Christian Classics Ethereal Library | 13 | 3 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 3 |
| Daniel Kolenda | 11 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 2 |
| Andrew Murray | 7 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Doug Kreighbaum | 7 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Jack Deere | 6 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.5 | 3 |
| Carter Conlon | 6 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| E.M. Bounds | 5 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| STEPBible | 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Charles Simpson | 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Bob Mumford | 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Jonathan Edwards | 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| Rhemata | 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 |

### Signal density (packaging)

| Source | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Derek Prince | 495 | -13.54 | 0.8 | 1.6 | 2.7 | 3.55 | 4.33 | 5.71 |
| HistoricalChristianFaith Commentaries Database | 307 | -15.0 | -15.0 | -7.13 | 0.0 | 2.74 | 5.86 | 26.74 |
| John Bevere | 220 | -9.04 | -0.66 | 1.42 | 3.43 | 4.72 | 5.5 | 13.98 |
| Vlad Savchuk | 126 | -4.73 | 0.1 | 2.26 | 4.48 | 5.88 | 6.55 | 16.43 |
| Leonard Ravenhill | 117 | -15.0 | 0.0 | 0.0 | 2.45 | 4.05 | 5.99 | 14.61 |
| Matthew Henry | 65 | -2.31 | -0.39 | -0.24 | -0.04 | 0.04 | 0.07 | 0.15 |
| Jamieson, Fausset & Brown | 65 | -0.89 | -0.38 | -0.15 | -0.05 | -0.02 | 0.01 | 0.18 |
| Adam Clarke | 56 | -1.42 | -0.35 | -0.15 | -0.03 | 0.03 | 0.07 | 0.16 |
| Zac Poonen | 50 | -3.02 | -0.52 | 2.08 | 3.51 | 4.73 | 6.07 | 24.43 |
| CLF Church | 18 | -15.0 | -13.38 | -9.87 | -5.41 | -2.2 | 2.14 | 39.22 |
| New Wine Magazine | 15 | -11.67 | -5.18 | 0.1 | 2.22 | 4.52 | 4.73 | 5.39 |
| Christian Classics Ethereal Library | 13 | 2.06 | 3.21 | 3.9 | 4.62 | 5.0 | 5.53 | 5.89 |
| Daniel Kolenda | 11 | 0.41 | 2.51 | 3.08 | 3.61 | 4.6 | 5.17 | 5.31 |
| Andrew Murray | 7 | -9.12 | -1.72 | 3.43 | 3.97 | 4.62 | 4.81 | 4.9 |
| Doug Kreighbaum | 7 | -9.51 | -9.4 | -8.07 | -6.48 | -5.68 | -3.72 | -1.74 |
| Jack Deere | 6 | 3.33 | 3.42 | 3.81 | 4.83 | 4.97 | 5.02 | 5.07 |
| Carter Conlon | 6 | 4.56 | 4.78 | 5.01 | 5.11 | 5.24 | 5.35 | 5.43 |
| E.M. Bounds | 5 | 3.94 | 4.24 | 4.69 | 4.75 | 4.9 | 5.6 | 6.07 |
| STEPBible | 4 | 0.28 | 0.36 | 0.47 | 0.59 | 2.14 | 4.83 | 6.62 |
| Charles Simpson | 4 | -12.27 | -8.36 | -2.49 | 1.93 | 3.24 | 3.51 | 3.69 |
| Bob Mumford | 4 | -2.55 | -1.55 | -0.06 | 1.08 | 1.56 | 1.87 | 2.08 |
| Jonathan Edwards | 3 | -0.85 | -0.36 | 0.38 | 1.6 | 3.04 | 3.9 | 4.48 |
| Rhemata | 3 | -5.83 | -5.15 | -4.12 | -2.42 | -1.51 | -0.96 | -0.59 |

### Text integrity problems

| Source | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Derek Prince | 495 | 0.0 | 2.71 | 3.24 | 3.75 | 4.3 | 4.8 | 29.65 |
| HistoricalChristianFaith Commentaries Database | 307 | 0.0 | 0.0 | 0.0 | 0.18 | 0.54 | 1.21 | 25.89 |
| John Bevere | 220 | 0.0 | 0.0 | 0.0 | 0.0 | 0.27 | 25.01 | 25.14 |
| Vlad Savchuk | 126 | 0.0 | 0.0 | 0.0 | 0.0 | 0.03 | 0.07 | 25.01 |
| Leonard Ravenhill | 117 | 0.0 | 0.0 | 0.0 | 0.0 | 0.04 | 25.0 | 25.07 |
| Matthew Henry | 65 | 0.1 | 0.18 | 0.22 | 0.28 | 0.33 | 0.5 | 25.34 |
| Jamieson, Fausset & Brown | 65 | 1.45 | 26.59 | 26.95 | 27.25 | 27.6 | 28.16 | 32.0 |
| Adam Clarke | 56 | 0.87 | 1.05 | 1.17 | 1.49 | 1.96 | 2.51 | 27.32 |
| Zac Poonen | 50 | 0.0 | 0.0 | 0.0 | 0.01 | 0.04 | 0.09 | 0.44 |
| CLF Church | 18 | 0.16 | 0.84 | 1.98 | 16.52 | 26.71 | 27.36 | 42.51 |
| New Wine Magazine | 15 | 26.6 | 27.11 | 27.34 | 27.63 | 28.69 | 28.87 | 30.92 |
| Christian Classics Ethereal Library | 13 | 25.02 | 25.03 | 25.06 | 25.61 | 26.73 | 26.74 | 26.96 |
| Daniel Kolenda | 11 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.03 | 25.0 |
| Andrew Murray | 7 | 25.14 | 25.67 | 26.34 | 26.71 | 26.84 | 27.1 | 27.44 |
| Doug Kreighbaum | 7 | 25.67 | 26.13 | 26.47 | 26.75 | 27.31 | 27.83 | 27.95 |
| Jack Deere | 6 | 0.0 | 0.0 | 0.0 | 0.01 | 0.09 | 12.56 | 25.0 |
| Carter Conlon | 6 | 0.0 | 0.0 | 0.0 | 0.01 | 0.01 | 0.03 | 0.04 |
| E.M. Bounds | 5 | 25.03 | 25.49 | 26.16 | 26.45 | 26.7 | 26.94 | 27.1 |
| STEPBible | 4 | 6.03 | 9.79 | 15.45 | 18.94 | 22.98 | 29.65 | 34.09 |
| Charles Simpson | 4 | 26.31 | 26.42 | 26.58 | 27.7 | 28.75 | 28.78 | 28.8 |
| Bob Mumford | 4 | 2.12 | 9.96 | 21.73 | 28.48 | 29.03 | 29.64 | 30.04 |
| Jonathan Edwards | 3 | 25.15 | 25.3 | 25.53 | 25.91 | 26.07 | 26.16 | 26.22 |
| Rhemata | 3 | 2.59 | 2.98 | 3.58 | 4.57 | 18.22 | 26.41 | 31.88 |

### Composite (0-100 percentile avg)

| Source | n | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|---|
| Derek Prince | 495 | 25.71 | 41.06 | 46.83 | 53.48 | 59.87 | 65.78 | 80.67 |
| HistoricalChristianFaith Commentaries Database | 307 | 23.96 | 32.74 | 41.72 | 50.18 | 60.02 | 69.92 | 84.47 |
| John Bevere | 220 | 9.29 | 23.15 | 33.86 | 44.06 | 55.76 | 63.53 | 83.84 |
| Vlad Savchuk | 126 | 34.65 | 43.06 | 52.02 | 62.23 | 67.66 | 71.36 | 90.51 |
| Leonard Ravenhill | 117 | 5.45 | 14.09 | 26.91 | 40.37 | 49.82 | 58.35 | 68.84 |
| Matthew Henry | 65 | 17.46 | 23.9 | 27.54 | 29.74 | 38.13 | 41.23 | 57.89 |
| Jamieson, Fausset & Brown | 65 | 30.61 | 41.18 | 43.96 | 47.93 | 54.86 | 58.49 | 66.38 |
| Adam Clarke | 56 | 25.3 | 29.43 | 33.56 | 39.12 | 44.14 | 46.31 | 56.91 |
| Zac Poonen | 50 | 5.12 | 23.4 | 31.0 | 42.49 | 51.17 | 58.32 | 62.17 |
| CLF Church | 18 | 37.07 | 44.08 | 51.63 | 60.2 | 64.54 | 69.87 | 90.75 |
| New Wine Magazine | 15 | 59.86 | 65.72 | 69.91 | 80.93 | 92.02 | 93.59 | 93.82 |
| Christian Classics Ethereal Library | 13 | 71.75 | 77.68 | 83.31 | 83.74 | 86.85 | 87.88 | 92.56 |
| Daniel Kolenda | 11 | 24.82 | 28.82 | 31.64 | 38.41 | 53.22 | 57.58 | 59.27 |
| Andrew Murray | 7 | 46.52 | 54.79 | 61.53 | 63.52 | 69.59 | 71.97 | 74.04 |
| Doug Kreighbaum | 7 | 49.25 | 50.6 | 51.66 | 51.85 | 54.43 | 55.05 | 55.22 |
| Jack Deere | 6 | 40.55 | 41.05 | 44.9 | 55.24 | 56.34 | 64.11 | 71.61 |
| Carter Conlon | 6 | 39.23 | 40.43 | 42.05 | 44.36 | 48.33 | 51.75 | 54.21 |
| E.M. Bounds | 5 | 61.08 | 62.45 | 64.51 | 79.57 | 80.16 | 80.87 | 81.34 |
| STEPBible | 4 | 44.72 | 45.28 | 46.12 | 50.56 | 61.51 | 74.07 | 82.44 |
| Charles Simpson | 4 | 53.23 | 53.52 | 53.95 | 59.89 | 66.12 | 67.07 | 67.7 |
| Bob Mumford | 4 | 45.16 | 46.85 | 49.4 | 53.59 | 60.06 | 66.73 | 71.18 |
| Jonathan Edwards | 3 | 40.83 | 45.05 | 51.37 | 61.91 | 62.5 | 62.85 | 63.09 |
| Rhemata | 3 | 31.32 | 34.49 | 39.25 | 47.17 | 48.91 | 49.95 | 50.65 |

### Small sources (1-2 documents) — raw composite scores, not a distribution

| Source | Document | Composite |
|---|---|---|
| A.B. Bruce | The Training of the Twelve | 58.6 |
| A.J. Gordon | The Twofold Life | 70.7 |
| Abraham Kuyper | The Work of the Holy Spirit | 22.8 |
| An Unknown Christian | The Kneeling Christian | 62.0 |
| Brother Lawrence | The Practice of the Presence of God | 80.4 |
| Catherine Booth | Aggressive Christianity | 71.3 |
| Chapel Library | Profiting from the Word | 53.8 |
| Charles G. Finney | Lectures to Professing Christians | 73.2 |
| Charles G. Finney | Power From On High | 73.8 |
| Covenant Harvest Church | Foundation Stones for New Believers | 57.4 |
| Don Basham | Lord of the Dollar? | 55.1 |
| Don Basham | The Servant | 62.7 |
| Ern Baxter | Christ's Eternal Lordship | 35.6 |
| Ern Baxter | What Makes God Angry? | 56.7 |
| F.F. Bosworth | Christ the Healer | 66.5 |
| George Müller | Autobiography | 60.9 |
| George Müller | How God Answers Prayer | 75.2 |
| Hannah Whitall Smith | Every-day Religion | 51.6 |
| Hannah Whitall Smith | The God of All Comfort | 76.5 |
| J.C. Ryle | Holiness: Its Nature, Hindrances, Difficulties, and Roots | 54.9 |
| J.R. Miller | Marriage Altar | 66.8 |
| John Owen | Pneumatologia | 57.7 |
| John Wesley | Sermons on Several Occasions | 79.3 |
| Michael Brown | What is the baptism of the Holy Spirit (with Dr. Michael Bro | 26.2 |
| Michael Brown | Dr. Brown Responds to Phil Johnson's Strange Fire Message (P | 54.6 |
| Oswald J. Smith | A Man Who Met His Lord | 74.7 |
| Phoebe Palmer | The Way of Holiness | 52.3 |
| R.A. Torrey | How To Pray | 61.1 |
| Ruth Prince | The Call Of God | 47.9 |
| Ruth Prince | A Woman Prepares For Marriage (Ruth Prince) | 54.8 |
| Smith Wigglesworth | Complete Salvation and How To Receive It - Part 2 | 39.1 |
| Unassigned — needs source | So Great a Salvation | 33.3 |
| Unassigned — needs source | The 59 “One Another’s” of the NT | 48.0 |
| William Booth | In Darkest England | 78.8 |

## Suspected duplicates (separate list)

Within-source MinHash candidates, similarity ≥0.5. These are a separate, easier decision from the quality scores above.

| Similarity | Source | Title A | Title B |
|---|---|---|---|
| 0.958 (likely duplicate) | Leonard Ravenhill | Something Is Missing In The Church by Leonard Ravenhill | (Sermon Clip) Something is Missing by Leonard Ravenhill |
| 0.917 (likely duplicate) | John Bevere | The Keys to Finishing Well in Life | The Keys to Finishing Well in Life |
| 0.896 (likely duplicate) | John Bevere | The Fear of the Lord Is My Treasure | The Fear of the Lord Is My Treasure |
| 0.833 (candidate) | HistoricalChristianFaith Commentaries Database | Adamnan | Adamnán of Iona |
| 0.792 (candidate) | John Bevere | What You Do Now Impacts Your Children | What You Do Now Impacts Your Children |
| 0.750 (candidate) | John Bevere | Getting Wisdom Is the Best Thing We Can Do | Getting Wisdom Is the Best Thing We Can Do |
| 0.688 (candidate) | John Bevere | The Most Powerful Scripture for Believers | The Most Powerful Scripture for Believers |
| 0.604 (candidate) | John Bevere | God Has Made Your Calling beyond Your Natural Ability | God Has Made Your Calling beyond Your Natural Ability |
| 0.604 (candidate) | John Bevere | Successful Living | Successful Living |
| 0.542 (candidate) | John Bevere | Indicators of Your Calling | Indicators of Your Calling |
| 0.542 (candidate) | John Bevere | Why You Are Not Experiencing the Presence of God | Why You Are Not Experiencing the Presence of God |
| 0.542 (candidate) | John Bevere | How to Embrace Biblical Stewardship for a Fulfilling Li | How to Embrace Biblical Stewardship for a Fulfilling Li |
| 0.521 (candidate) | John Bevere | What Do You Want Your Legacy to Be? | What Do You Want Your Legacy to Be? |
| 0.500 (candidate) | John Bevere | Embrace Your Unique Talents and Flourish | Embrace Your Unique Talents and Flourish |

## 40 worst-scoring documents overall

**Before reading this list: 17 of these 40 (8 CCEL-pipeline, 9 New-Wine-pipeline) are explained by the two known ingestion-pipeline bugs above, and 18 more are flagged only via the multi-voice-channel classification caveat above (mostly anthology/library sources, not confirmed guest-speaker risk).** Only **5** of the 40 are not explained by either caveat — those are the ones most worth reading closely.

- **93.8** — *DEATH IS DEATH AND DEATH HURTS* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~2201 words; attributed to a multi-voice channel, not a single-teacher archive; 19% of sentences are exact repeats.
- **93.7** — *THE GOSPEL OF GOD'S GOVERNMENT* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~4290 words; attributed to a multi-voice channel, not a single-teacher archive; 15% of sentences are exact repeats.
- **93.5** — *The Sinner’s Place* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~1913 words; attributed to a multi-voice channel, not a single-teacher archive.
- **93.3** — *The Privilege of Serving* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~4213 words; attributed to a multi-voice channel, not a single-teacher archive; 15% of sentences are exact repeats.
- **92.6** — *Christian Nurture* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~135899 words; attributed to a multi-voice channel, not a single-teacher archive; 15% of sentences are exact repeats.
- **90.8** — *THE VULNERABILITY OF LEADERSHIP* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~521 words; attributed to a multi-voice channel, not a single-teacher archive.
- **90.8** — *Prophetic Equipping via Zoom* (CLF Church, Other) — 4.4% non-word/garbled characters; ~39 platform/cta phrases per 1000 words; ends without terminal punctuation at ~102 words.
- **90.5** — *This Is the Enemy’s Last Attack Before Your Next Level* (Vlad Savchuk, Sermon transcript) — Ends without terminal punctuation at ~11640 words; attributed to a multi-voice channel, not a single-teacher archive.
- **88.2** — *Your Battle Ends Here | This Is How You Should Fight Your Battles* (Vlad Savchuk, Sermon transcript) — Ends without terminal punctuation at ~17628 words; attributed to a multi-voice channel, not a single-teacher archive; 17% of sentences are exact repeats.
- **87.9** — *The Journal of John Wesley* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~196192 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **87.7** — *Quiet Talks on Prayer* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~65069 words; attributed to a multi-voice channel, not a single-teacher archive; 15% of sentences are exact repeats.
- **87.7** — *This May Frustrate You - But You Need to Hear It* (Vlad Savchuk, Sermon transcript) — Ends without terminal punctuation at ~7254 words; attributed to a multi-voice channel, not a single-teacher archive.
- **87.2** — *ARE YOU CONTROLLED BY THE "PARTY SPIRIT"?* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~1740 words; attributed to a multi-voice channel, not a single-teacher archive; 12% of sentences are exact repeats.
- **86.8** — *Lectures on Revivals of Religion* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~246490 words; attributed to a multi-voice channel, not a single-teacher archive; 16% of sentences are exact repeats.
- **86.5** — *The Secret of Guidance* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~37297 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **85.9** — *How to Win the War on Porn | Your Porn Battle Plan* (Vlad Savchuk, Sermon transcript) — Ends without terminal punctuation at ~5433 words; attributed to a multi-voice channel, not a single-teacher archive; 13% of sentences are exact repeats.
- **85.8** — *A Prisoner of Hope* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~5977 words; attributed to a multi-voice channel, not a single-teacher archive; 12% of sentences are exact repeats.
- **85.2** — *The Weapon of Prayer* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~47948 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **84.5** — *Arator* (HistoricalChristianFaith Commentaries Database, Commentary) — Attributed to a multi-voice channel, not a single-teacher archive; 13% of sentences are exact repeats.
- **83.8** — *Only ONE Thing Will Keep You Ready for His Return* (John Bevere, Sermon transcript) — Ends without terminal punctuation at ~7854 words; 23% of sentences are exact repeats.
- **83.7** — *The Way Into the Holiest* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~99008 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **83.7** — *Absolute Surrender* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~43916 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **83.4** — *Purpose in Prayer* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~43811 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **83.3** — *The Lord's Table* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~28042 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **83.2** — *JRR Tolkien* (HistoricalChristianFaith Commentaries Database, Commentary) — 56% of sentences are exact repeats; attributed to a multi-voice channel, not a single-teacher archive.
- **82.4** — *LSJ Greek Lexicon (TFLSJ) — Entries 0-5624* (STEPBible, Background / lexicon) — 4.6% non-word/garbled characters; 17% of sentences are exact repeats; near-zero scripture references.
- **82.0** — *Symeon the New Theologian* (HistoricalChristianFaith Commentaries Database, Commentary) — 42% of sentences are exact repeats; attributed to a multi-voice channel, not a single-teacher archive.
- **81.3** — *The Necessity of Prayer* (E.M. Bounds, Book) — Ends without terminal punctuation at ~40054 words; 15% of sentences are exact repeats.
- **81.2** — *Epiphanius of Salamis* (HistoricalChristianFaith Commentaries Database, Commentary) — 33% of sentences are exact repeats; attributed to a multi-voice channel, not a single-teacher archive.
- **80.9** — *THE PLACE OF TRANFORMATION* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~2040 words; attributed to a multi-voice channel, not a single-teacher archive.
- **80.7** — *Immersion in the Spirit* (Derek Prince, Sermon transcript) — Ends without terminal punctuation at ~12049 words; 16% of sentences are exact repeats.
- **80.6** — *Quiet Talks on Power* (Christian Classics Ethereal Library, Book) — Ends without terminal punctuation at ~59025 words; attributed to a multi-voice channel, not a single-teacher archive; 14% of sentences are exact repeats.
- **80.4** — *The Practice of the Presence of God* (Brother Lawrence, Book) — Ends without terminal punctuation at ~15205 words; 14% of sentences are exact repeats; near-zero scripture references.
- **80.2** — *Power Through Prayer* (E.M. Bounds, Book) — Ends without terminal punctuation at ~27392 words; 16% of sentences are exact repeats.
- **80.1** — *Asterius of Cappadocia* (HistoricalChristianFaith Commentaries Database, Commentary) — Attributed to a multi-voice channel, not a single-teacher archive; 16% of sentences are exact repeats.
- **79.7** — *Swords Into Plowshares* (New Wine Magazine, Magazine article) — Ends without terminal punctuation at ~3266 words; attributed to a multi-voice channel, not a single-teacher archive.
- **79.7** — *Curses - Cure - Part 2* (Derek Prince, Sermon transcript) — Ends without terminal punctuation at ~6407 words; 15% of sentences are exact repeats.
- **79.6** — *The Essentials of Prayer* (E.M. Bounds, Book) — Ends without terminal punctuation at ~41698 words; 15% of sentences are exact repeats.
- **79.4** — *Clement of Rome* (HistoricalChristianFaith Commentaries Database, Commentary) — 44% of sentences are exact repeats; attributed to a multi-voice channel, not a single-teacher archive.
- **79.3** — *Sermons on Several Occasions* (John Wesley, Book) — Ends without terminal punctuation at ~800012 words; 12% of sentences are exact repeats.

## Random sample of 15 from the middle (composite 40-60 band, n=861, seed=42)

- **58.3** — *Do You Feel Spiritually Stuck?* (John Bevere, Sermon transcript) — 3615-word document; 1.1 scripture refs/1000w.
- **57.3** — *The Spirit Of Antichrist* (Derek Prince, Sermon transcript) — 8098-word document; 1.9 scripture refs/1000w.
- **57.1** — *Processing Your Prophecy* (CLF Church, Sermon transcript) — 1893-word document; 4.8 scripture refs/1000w.
- **57.1** — *Be Perfect - Part 1* (Derek Prince, Sermon transcript) — 7721-word document; 3.0 scripture refs/1000w.
- **56.8** — *Jamieson-Fausset-Brown Commentary - Daniel* (Jamieson, Fausset & Brown, Commentary) — 37770-word document; 0.0 scripture refs/1000w.
- **54.4** — *Deliverance And Demonology* (Derek Prince, Sermon transcript) — 2311-word document; 59.7 scripture refs/1000w.
- **53.4** — *Servanthood* (Derek Prince, Sermon transcript) — 8048-word document; 2.6 scripture refs/1000w.
- **53.1** — *How To Face The Last Days Without Fear* (Derek Prince, Sermon transcript) — 8430-word document; 3.1 scripture refs/1000w.
- **50.2** — *Arius* (HistoricalChristianFaith Commentaries Database, Commentary) — 92-word document; no notable flags on any dimension.
- **47.7** — *Ticonius* (HistoricalChristianFaith Commentaries Database, Commentary) — 17679-word document; 5.4 scripture refs/1000w.
- **46.5** — *The Ark Of God by Leonard Ravenhill* (Leonard Ravenhill, Sermon transcript) — 7002-word document; 0.6 scripture refs/1000w.
- **45.5** — *Maximus the Confessor* (HistoricalChristianFaith Commentaries Database, Commentary) — 3155-word document; 6.3 scripture refs/1000w.
- **45.0** — *(Compilation) The Cup - Part 1 by Leonard Ravenhill* (Leonard Ravenhill, Sermon transcript) — 328-word document; no notable flags on any dimension.
- **44.0** — *The 7 Women Every Christian Man Should RUN From* (Vlad Savchuk, Sermon transcript) — 3880-word document; 6.2 scripture refs/1000w.
- **41.4** — *Would You like to Be a Friend of God?* (John Bevere, Sermon transcript) — 719-word document; 1.4 scripture refs/1000w.

## 15 best-scoring documents overall

- **5.1** — *God Will Never Let You Down but Will Help You by Zac Poonen* (Zac Poonen, Sermon transcript) — 1667-word document: ends cleanly, near-zero platform/CTA language, 4.2 scripture refs/1000w, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **5.5** — *Romans 7 by Leonard Ravenhill* (Leonard Ravenhill, Sermon transcript) — 203-word document: ends cleanly, near-zero platform/CTA language, 19.7 scripture refs/1000w, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **8.0** — *Reviving Biblical Truths in Today's America by Leonard Ravenhill #shor* (Leonard Ravenhill, Sermon transcript) — 130-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **8.8** — *(clip) Lord, Teach Us to Pray by Leonard Ravenhill* (Leonard Ravenhill, Sermon transcript) — 404-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **9.3** — *Discover the Secret to Experiencing God's Presence* (John Bevere, Sermon transcript) — 596-word document: ends cleanly, near-zero platform/CTA language, 6.7 scripture refs/1000w, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **9.4** — *Experience the Wisdom of 40 Years in One Book!* (John Bevere, Sermon transcript) — 784-word document: ends cleanly, near-zero platform/CTA language, 3.8 scripture refs/1000w, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **9.6** — *Helping One Another in Christ’s Body by Zac Poonen* (Zac Poonen, Sermon transcript) — 820-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **9.7** — *New Covenant Fasting by Zac Poonen* (Zac Poonen, Sermon transcript) — 4021-word document: ends cleanly, near-zero platform/CTA language, 5.7 scripture refs/1000w, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **10.2** — *Wealthy Christians vs Eternal Riches by Leonard Ravenhill #shorts* (Leonard Ravenhill, Sermon transcript) — 111-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **10.6** — *(Audio Sermon Clip) Being Still Before the Lord by Leonard Ravenhill* (Leonard Ravenhill, Sermon transcript) — 237-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **10.8** — *Experiencing the Power of Resurrection of Christ in Us by Leonard Rave* (Leonard Ravenhill, Sermon transcript) — 127-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **11.1** — *The Power of Baptism: Dying to the World Above by Leonard Ravenhill #s* (Leonard Ravenhill, Sermon transcript) — 132-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **11.2** — *Don't Miss Out: How to Claim Your Full Reward — John Bevere* (John Bevere, Sermon transcript) — 425-word document: ends cleanly, near-zero platform/CTA language, 4.7 scripture refs/1000w, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **11.6** — *"The Devil Accuses Martin Luther" - Leonard Ravenhill* (Leonard Ravenhill, Sermon transcript) — 182-word document: ends cleanly, near-zero platform/CTA language, 5.5 scripture refs/1000w, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
- **11.8** — *The Secret to Elevating Your Thoughts, Intentions, and Actions* (John Bevere, Sermon transcript) — 712-word document: ends cleanly, near-zero platform/CTA language, no chunk-index gaps, clean text, no scan artifacts, single-teacher attribution.
