# Rhemata — Live Status

Point-in-time state only. Overwritten each session. Never durable truth.
Corpus counts are not recorded here — query live.

Last verified: 2026-08-01 (live-DB corrections + Wesley's Journal real
write — see the entry immediately below).

---

## Live-DB corrections (Translator's Note misattribution, missing "VII. Saturday") + Wesley's Journal real write (session state, 2026-08-01)

Continuation of the 2026-07-31 chapter-scoped-extraction session below —
this session picked up its two disclosed-but-unresolved items (the
byline/apparatus/digit-ratio fix sitting uncommitted; the two live
imperfections it found in already-written books) and closed both, then
used the corrected pipeline for a new real write. Three ordered pieces,
routed per CLAUDE.md's Session Routing table: read-only diagnostic
(plain/direct terminal) → DB corrections + fix commit (plain-script/
DB-write, hard rule, harness never used) → Wesley's Journal real write
(same DB-write path). All DB claims below are from fresh, independent
queries run *after* each write, on a separate connection from the one
that performed the write — not the writing script's own self-report.

**Piece 1 — fix (a)/(b) committed, `8e251c8`.** The third-party-byline
detector (`_has_third_party_byline()`), the `_MATTER_LABEL_APPARATUS`
exact-match label set, and the tightened `_digit_token_ratio()`
roman-numeral arm — all built and proven against real Wesley/True Vine
fixtures in the prior 2026-07-31 session, sitting uncommitted — are now
committed. `_roman_to_int()`/`_int_to_roman()` (fix (b)'s own dependency,
originally introduced alongside the still-unwired numeral-heading
detector) were relocated earlier in the file, next to their real caller,
rather than committed in their original location — this was necessary,
not cosmetic: committing the file as originally structured would have
either duplicated these two functions or left fix (b) referencing
undefined names, since the numeral-heading detector itself (Piece 4 of
the 2026-07-31 entry — `_select_numeral_chain()`,
`_detect_numeral_heading_sequence()`, `detect_book_chapters()`, etc.)
stays deliberately uncommitted, unchanged, zero production callers,
exactly as that session decided. Verified by diffing the relocated
working tree against the original uncommitted version with comments
stripped: byte-identical apart from the move. Both `test_propositions_book_chapters.py`
(committed alongside, includes a fix for a `LONG_STRETCH_WORD_THRESHOLD`
assertion left stale by the already-committed `b4ab601`) and the separate,
still-uncommitted `test_propositions_book_numeral_detection.py` pass in
full against the post-commit working tree.

**Piece 2 — "The New Life" (Andrew Murray): Translator's Note
misattribution corrected, 411 → 408 propositions.** Diagnostic: split the
live document fresh via `split_book_into_chapters()` and confirmed
`is_front_back_matter("Translator's Note", text, author="Andrew Murray")`
now returns `(True, "editorial_apparatus")`. Its 3 `chunk_ids` were
joined against live `propositions`/`proposition_chunks` — 13 candidates
came back, not 3, because one boundary chunk is shared with the
following "Preface" chapter (chunk-linking is a per-extraction-call
cartesian product, so a shared chunk pulls in the neighbor's rows too).
Disambiguated per-candidate by fetching each one's own FULL chunk set:
propositions at `proposition_index` 1–3 link *only* to Translator's Note
chunks (content directly matches the note's own text — "reading a
chapter... every Sabbath evening" etc.); indices 4–13 link to all 6 of
Preface's chunks and their content directly matches real, genuine Murray
Preface prose ("I have confined myself... The first is the Word of
God..."), confirmed by reading the actual Preface span. Deleted exactly
the 3 ids (`52bb4190-e7ed-4213-97e5-89c6035a033f`,
`9887240b-0cd8-4235-94ec-517a30547577`,
`30453763-a478-4907-83f3-183ce92208ef`) — `proposition_chunks` rows
cascade-deleted automatically (migration 074's `ON DELETE CASCADE`).
Independently re-verified on a fresh connection: count is 408, the 3 ids
are gone, 0 orphaned `proposition_chunks` rows, the 10 genuine Preface
rows (spot-checked indices 4 and 13) are untouched, and the remaining
`proposition_index` sequence is a clean 4..411 (408 rows, no gaps other
than the 3 removed).

**Piece 3 — "The Lord's Table" (Andrew Murray): missing "VII. Saturday"
added, 148 → 149 propositions.** Diagnostic: the real "VII. Saturday"
span (57 words — the title-repeat marker produces two spans here, 57w
and a 9w trailing stub; only the 57w one clears `MIN_SUBSTANTIVE_WORD_COUNT`)
now classifies `is_front_back_matter() -> (False, "")` under the fixed
digit-ratio arm (previously misfired on the repeated uppercase "VII" +
page-number tokens). Confirmed genuinely absent from the live DB: the 11
propositions sharing a boundary chunk with either "VII. Saturday" span
all disambiguate, by the same full-chunk-set method as Piece 2, to the
neighboring "VI. Friday Morning: Faith" (5 rows) and "Saturday Morning:
Self-Surrender" (6 rows) chapters — zero rows are strictly linked to
"VII. Saturday"'s own chunks. Extracted via `extract_propositions()` on
just that 57-word span (`speaker="Andrew Murray"`, `prompt_version="v3.1"`,
matching every existing row's own provenance) — 1 proposition returned,
stored via `store_propositions(..., clear_existing=False)` at
`proposition_index=149` with `chunk_ids` set to the span's own two
chunks. Independently re-verified on a fresh connection: count is 149,
the new row's `prompt_version`/chunk links are correct, and the full
`proposition_index` sequence is an unbroken 1..149.

**Piece 4 — John Wesley's "The Journal of John Wesley": first real
write, storage ENABLED, 1,249 propositions, $0.3698.** Public-domain
source (CCEL) — `process_book_document()`'s own license gate would skip
it, so this called the gate-free `_extract_and_store_book_chapters()`
directly, the same disclosed, scoped bypass already used and documented
for every other public-domain book write (the 2026-07-31 entry's Piece
3). Reconciliation: 381 chapters attempted, 362 stored, 4 empty, 4
errored, 1 skipped_thin, 10 skipped_front_matter, 1,249 propositions
stored (reconciliation bucket-sum asserted internally, matches the
module's own invariant). The 4 errored chapters ("Life on Board,"
"Remarkable Service at Gwennap," "Beaten by the Mob," "Field-preaching
Expedient") are genuine content chapters hit by the pre-existing,
occasionally-deterministic JSON-escaping defect (ARCHITECTURE.md,
present in v3 and v3.1 alike, unrelated to and not fixed by this
session's work) — not a new regression; the 2026-07-31 storage-disabled
dry run hit 2 different chapters with the same underlying defect, not 4,
consistent with "occasionally-deterministic."

Independently re-verified on a fresh connection (re-deriving chapter
structure itself via `split_book_into_chapters()`, not trusting the
run's own returned reconciliation):
- Live count: 1,249, all with `prompt_version="v3.1"`, all with
  `>=1 proposition_chunks` link, 0 rows with any NULL provenance field.
- All 5 target front-matter sections independently confirmed to have
  **zero** propositions strictly linked to their own (non-boundary-shared)
  chunks: `EDITOR'S NOTE` (`editorial_apparatus`), `INTRODUCTION`
  (`third_party_byline`), `AN APPRECIATION OF JOHN WESLEY'S JOURNAL`
  (`third_party_byline`), `BIOGRAPHICAL SKETCH` (`editorial_apparatus`),
  `WESLEY'S LAST HOURS` (`third_party_byline`) — matching the prior
  session's storage-disabled proof exactly, now confirmed on a real write.
- Both previously-lost genuine diary entries ("Wesley's Defenders,"
  "Wesley Discusses Old Sermons") now have real, on-topic propositions —
  content directly matches each entry's own real subject matter (a mob-
  violence episode and the loyalty of Wesley's companions during it; a
  reflection on his seventy-fifth birthday and on why his sermon-writing
  hadn't changed over forty years, respectively) — not spot-checked
  against exact calendar dates, which this session did not verify.
- Cost: 372 real Groq calls, 538,086 input / 66,245 output tokens,
  $0.3698 (tiktoken cl100k_base on the real captured text of every call)
  — essentially identical to the prior session's dry-run estimate
  ($0.3698 there too), as expected since both ran the same prompt against
  the same text. Well under the $50 per-run approval threshold.
- Density: 1,249 propositions / ~197,500 words ≈ 6.3 per 1,000 words —
  far above the whole-document single-call baseline (~1.3/1,000 median,
  per the 2026-07-31 truncation-check entry below), consistent with
  Piece 1 of the 2026-07-31 entry's own finding that chapter-scoped
  extraction produces "dramatically richer output" than a single
  whole-book call.

**No git commit exists for Piece 4's real write itself** — matches this
repo's own established convention for DB-write-only sessions (neither
the 2026-07-30 508-document backfill nor the 2026-07-31 6-book real write
has a corresponding commit; the database is the durable record, this
entry is the pointer). The full run/verification JSON record is at
gitignored `book_chapter_live_proof_review/wesley_journal_real_write.json`
(companion to the prior session's storage-disabled
`wesley_journal_live_proof_v2.json`) — local-only, not for git history,
same rationale as every other proof-review directory in `.gitignore`.

**State of the repo at session close:** one commit landed (`8e251c8`),
from a confirmed-working build (full `test_propositions_book_chapters.py`
suite passing against the exact committed file). The numeral-heading
detector (Piece 4 of the 2026-07-31 entry below) is untouched and remains
uncommitted, zero production callers — this session neither wired it nor
changed its logic, only relocated two small helper functions it also
happens to depend on. CLAUDE.md's Landmines section is updated in place
(not silently deleted) to mark the two live imperfections and the byline
detector's commit status as corrected, pointing back to this entry.

---

## Chapter-scoped book extraction: built, proven, first real write (session state, 2026-07-31, several sessions same day)

Continuation of the two 2026-07-31 read-only diagnostics below (book-length
extraction truncation check + the corpus-wide chapter-detection scan they
led to). Mixed routing per CLAUDE.md's Session Routing table across five
ordered pieces: harness for the two repo-only builds; plain-script/DB-write
for the one real write; plain/direct terminal for the three read-only
diagnostics/proofs. Full evidentiary trail (per-agent reports, artifact
JSONL files, real query output) lives in this session's own transcript and
in gitignored `book_chapter_live_proof_review/*.json` — this entry is the
pointer plus the decisions, not a re-derivation of the evidence.

**Piece 1 — chapter-scoped extraction + front/back-matter classifier,
SHIPPED, commit `d7c46f5`.** New `propositions.py` functions
(`split_book_into_chapters()`, `_extract_and_store_book_chapters()`,
`process_book_document()`, `is_front_back_matter()`) give book-length
documents a structure-first, multi-call extraction path instead of the old
single-call-per-document design — the fix for the book-length gap PLAN.md
#17 named unresolved. `process_document()` and `store_propositions()`'s
default path are unchanged (`store_propositions()` gained one additive
`clear_existing` parameter, default preserves prior behavior exactly).
Front/back-matter spans (title pages, indexes, CCEL metadata blocks) are
classified and skipped BEFORE the model is ever called, not filtered after.
Live-proven, storage disabled throughout proving, on Andrew Murray's "The
True Vine" and E.M. Bounds' "Power Through Prayer": chapter-scoped
extraction produced dramatically richer output than the old whole-book
call on the same book (True Vine: 169 propositions across 31 real chapters
vs. 14 propositions from a single whole-book call that read as a
compressed verse-by-verse gloss of John 15, not an extraction of Murray's
actual arguments).

**Piece 2 — `LONG_STRETCH_WORD_THRESHOLD` 3000→6000, SHIPPED, commit
`b4ab601`.** Isolated one-constant fix: detected chapters between 3,000
and 6,000 words were being needlessly re-split into disconnected
"(untitled continuation)" fragments even though the real per-call
extraction ceiling (`SAFE_CHAPTER_WORD_CEILING`) is 6,000. Verified live
against 32 real chapters across 4 books that no longer fragment, and that
True Vine/Power Through Prayer's own proven span counts (38/22) are
unaffected (neither book has a chapter over 3,000 words).

**Piece 3 — first real write: 6 public-domain books, storage ENABLED.**
Andrew Murray's "The New Life" (411 propositions), "Waiting On God!" (176),
"The True Vine" (165), "The Lord's Table" (148); Brother Lawrence's "The
Practice of the Presence of God" (121); E.M. Bounds' "Power Through Prayer"
(131) — **1,152 propositions total, real cost $0.35, zero errors.**
Reconciliation for all 6 books reconciles exactly
(attempted = stored + front_matter + thin + empty + errored, no
exceptions) and was independently re-verified against the live DB on a
fresh connection, not taken from the extraction function's own return
values. Confirmed zero writes to any document outside the 6 named, and
zero writes to the two explicitly excluded books ("The Two Covenants" —
known pre-existing bug, see below; "The Journal of John Wesley" — proven
separately, see Piece 5). Every one of the 1,152 rows carries correct
`prompt_version='v3.1'`/fingerprint/model provenance.

**Piece 4 — numeral-heading chapter detector: BUILT, REVIEWED, NOT WIRED,
still uncommitted — deliberate decision, not an oversight.** A second
detection strategy (`detect_book_chapters()`, `_detect_numeral_heading_sequence()`)
was built to cover books whose chapters don't repeat their own titles
(roman-numeral headings like Andrew Murray's "The Master's Indwelling," or
bare "Chapter N" headings) — the old repeated-title-only detector cleanly
handles only 8 of the corpus's 53 book documents (15%). Went through three
full fix-and-reverify cycles: the first design produced a confident-wrong
answer on Doug Kreighbaum's "Manual Systematic Theology" (a 5-point
scripture-chapter outline mistaken for the book's real structure, covering
2.5% of the book) — fixed via a document-span-floor guard. The fix's own
re-verification then found a SECOND, different confident-wrong-answer
mechanism the guard doesn't catch: Charles Finney's "Lectures on Revivals
of Religion" chains together Finney's own scattered rhetorical outline
markers across most of the book's width (spanFrac ~97%, passing every
guard) instead of finding the real 22 "Lecture N" headings, which neither
detector pattern recognizes. **Decision: ship only the safe repeated-title
detector (already in Piece 1) + Piece 2's threshold fix to production; do
NOT wire the numeral detector.** Confirmed separately and importantly:
`detect_book_chapters()` currently has ZERO non-test callers anywhere in
the repo — the numeral-detector build has had no effect on any book ever
actually processed, so nothing is at risk from these findings today. If
picked up again, the honest fix is per-book TOC verification before
trusting a result, not another internal confidence guard — two rounds of
narrow guard-patching each produced a new regression elsewhere (Torrey,
Bounds' "Purpose in Prayer") without closing the underlying gap. Also
found (informational, not a defect this thread is scoped to fix): all 4
Jonathan Edwards/Owen/Wesley-Sermons/Ryle-scale "never-repeats-title"
books remain entirely unaddressed by either detector; a real, pre-existing
`split_book_into_chapters()` bug silently merges Andrew Murray's "The Two
Covenants"' real Chapter I into its Introduction (unrelated to the numeral
work, not touched, not fixed — this is why "The Two Covenants" is
excluded from every real write and every proof this session).

**Piece 5 — Wesley's "Journal" (197,501 words, the largest book tested):
storage-disabled proof found a real attribution-integrity defect,
FIXED (byline detector + digit-ratio fix), re-proven, still
uncommitted.** Structural proof was strong (373 real, coherent,
editor-titled excerpts, none near the extraction ceiling — max span 3,914
words). But this CCEL edition wraps the journal in genuine third-party
essays (an editor's note, a biographical sketch, an introduction "by the
Rev. Hugh Price Hughes," and "An Appreciation of John Wesley's Journal" by
Augustine Birrell) that the existing front/back-matter classifier didn't
catch — all 4 went to extraction and produced propositions stamped "John
Wesley teaches..." for content that was demonstrably the editor's/Hughes's/
Birrell's own words, verified against the real source text. **Fixed**: a
new byline detector (`_has_third_party_byline()` — a short line-start "by
[Name]" whose name shares no token with the document's known author) plus
an exact-match editorial-apparatus label set, checked before the existing
classifier's protections. Re-run confirmed all 4 sections now correctly
excluded before the model is ever called (instrumented proof, not just a
relabeled bucket), plus a bonus 5th genuine catch ("WESLEY'S LAST HOURS,"
opens "BY ONE WHO WAS PRESENT," a real anonymous eyewitness account, not
Wesley's own writing). **A real, disclosed limitation, not hardened this
session:** the byline detector's mechanism is broader than "recognize a
named person" — it fires on any short "By [phrase]" line that doesn't
share words with the author, confirmed it would also fire on "By faith
alone" or "By the grace of God." No false positive occurred on Wesley, but
this is unproven beyond the one book tested — a genuine content span
opening with a short "By..." epigraph or hymn line is a real, live risk
for the next book, not hardened here. A separate, real digit-ratio bug was
also fixed in the same pass (the "is this an index page" heuristic was
miscounting the pronoun "I" and words like "did" as roman numerals,
wrongly excluding two genuine short Wesley diary entries) — both now
correctly produce real propositions on re-run.

**Two real, already-live imperfections surfaced by re-running the fixed
classifier against every book that already has real propositions (10
books checked, not just the 6 written this session — 4 more from an
earlier Doug Kreighbaum/Covenant Harvest backfill also carry live
propositions). Neither is fixed this session — Alex's call whether either
is worth a small supplemental re-extraction:**
- **"The New Life" (411 live propositions) contains a misattribution.** A
  670-word Translator's Note — genuinely someone else writing about Murray
  in the third person ("its honoured author") — was extracted and stored
  as if it were Andrew Murray's own teaching, before this session's byline
  fix existed. A handful of the 411 live propositions are affected.
- **"The Lord's Table" (148 live propositions) is missing real content.**
  "VII. Saturday" (~57 words of genuine Murray devotional text) was wrongly
  excluded by the pre-fix digit-ratio bug before the book was written for
  real; it never reached the model, so no propositions exist for it.

**Corpus-wide detection coverage, for context on how far this reaches.**
Only 8 of 53 book documents detect cleanly via the safe, production
repeated-title detector alone (15%). The (unwired) numeral detector's own
corpus scan found it would raise that to 21-23/53 if ever wired and
trusted — but the same scan is what surfaced the Kreighbaum and Finney
confident-wrong cases, so that number is explicitly NOT a "ready" count.
28 books already have real, live propositions or were proven this session
(the 6 written + True Vine, which was among them, + Power Through Prayer +
Wesley's dry-run-only proof); the rest of the corpus's public-domain books
remain untouched, gated behind the still-open detector-hardening and
per-book-verification questions above.

**State of the repo at session close:** two commits landed (`d7c46f5`,
`b4ab601`), both isolated, both from confirmed-working builds. Everything
else — the byline detector, the digit-ratio fix, the numeral-heading
detector — sits uncommitted in the working tree, reviewed and proven but
deliberately held for Alex's decision on next steps (harden-and-wire the
numeral detector vs. leave it as a documented-but-inert capability;
whether to correct the two live-DB imperfections above; which further
books, if any, get a real write next). Zero DB writes occurred anywhere in
this session outside Piece 3's 6 named books, confirmed independently at
every step.

---

## Full propositions backfill (licensed/unlicensed corpus) — generation resumed (session state, 2026-07-30)

(**generation resumed and the propositions
backfill actually ran this session — corrects the 2026-07-29 header's own
"generation has not resumed" framing, which is now stale, not wrong-when-
written.** Three ordered pieces, all plain-script/DB-write path per
CLAUDE.md's Session Routing table: (1) a 25-doc proving batch on the
unmodified v3 prompt, measuring the "the author" defect at real scale for
the first time (90.1% of propositions, corrected word-boundary count); (2)
an isolated named-teacher fix (`EXTRACTION_PROMPT_V3_1`) — v3's exact
wording with only the naming mechanism grafted in, proven on a second
25-doc batch to drop that rate to 0.0% with no length/structure drift; (3)
the full remaining-corpus run on that proven v3.1 path, 515 documents, 508
succeeded. **Corpus-wide as of this session: 850/857 eligible documents now
have propositions (was ~343/857 at the start of today), 5,592 of those
propositions stamped `v3.1`, 222 stamped `v3`, 2,409 legacy rows still
`legacy_unknown` (untouched, unaffected) — so CLAUDE.md's Landmines line "no
live proposition row has real provenance" is now corrected in place, not
still true.** 7 documents remain unprocessed — 5 hit an already-known
JSON-escaping model quirk (confirmed pre-existing in v3 too, not caused by
this session's prompt change), 2 are a newly-discovered gap: book-length
documents (`source_type='book'`, 90K/140K words) structurally break the
current single-call, `max_tokens=8192` extraction design. Full detail
below and PLAN.md #17/#49.)
Records reconciled: 2026-07-23 (fix commit `0e2f32c` for the textarea-focus-blocks-panel bug — logged as a bullet inside the "Study Panel geometry v3" section below, not its own heading. Previously pointed to this by a numeric offset ("six below the new one") that silently went stale the moment a new entry was prepended above it — fixed to a name-based reference instead of re-guessing a new number that would just rot the same way next session).

---

## Two read-only diagnostics: historical-commentary attribution/copyright audit, book-extraction truncation check (session state, 2026-07-31)

Two independent read-only sessions, zero DB writes, zero code changes — plain/direct terminal path per CLAUDE.md's Session Routing table. This entry is the pointer; full evidence for item 1 lives in the audit file below, and for item 2 in this session's own chat transcript (no file was written for it, per that task's own explicit instruction).

**1. Historical commentary attribution/copyright audit — full report: `docs/audits/historical_commentary_attribution_and_copyright_audit_2026-07-31.md`.** Re-opens Open blockers #15/#16 below (both updated in place, not superseded — the underlying questions are still genuinely unresolved).

- **citation_mode:** confirmed fresh via live query — all 307 HistoricalChristianFaith documents currently have `citation_mode='silent_context'`, matching #15's own original wording below (re-read carefully, #15 already stated the live value as silent_context, not citable — the framing this audit's task brief used, "DB says citable but behaves silent," does not match #15's actual text and does not match today's live state either). Root cause of the code/DB mismatch traced: the now-deleted `ingest_commentaries.py` importer hardcoded `citation_mode='citable'` at insert time, in every version across its full git history, confirmed by reading the deleted file at each commit. **No migration, commit, or script anywhere in this repo performs the correction to `silent_context`** — searched migrations/*.sql, `git log -S`, and the `documents` table itself (no `updated_at` column to date it). Someone corrected this, correctly, outside the migration convention, with no audit trail. Not urgent, but the gap itself — an undocumented direct DB change — is worth knowing about.
- **New finding, not previously known:** license_status/visibility live on the `sources` table only — one row for this entire 307-document collection (`license_status='public_domain'`, `visibility='shown'`), with no per-document or per-author override anywhere in the schema. Three authors in this set are not safely public domain under a life-plus-70 baseline: **C.S. Lewis** (d. 1963, protected to ~2033), **J.R.R. Tolkien** (d. 1973, protected to ~2043), and **Douglas Wilson** (living author, b. 1953) — all three currently sit under the same blanket `public_domain`/`shown` record as every ancient/medieval author in the set. G.K. Chesterton (d. 1936) and J.B. Lightfoot (d. 1889) were also individually checked and already clear life-plus-70.
- **New finding:** Study Mode's commentary browsing panel (`backend/app/routers/study.py`, confirmed by its own code comment) structurally ignores `citation_mode` and always displays the author name for `source_kind='commentary'` results — confirmed rendered in the frontend too (`commentary-accordion-row.tsx:62`). This is the one path where the citation_mode correction above provides no protection at all, by design.
- **Not resolved by this session** (read-only, no DB/code changes): five open questions are logged in the audit file for Alex — the per-source-only license model, whether to pull the three flagged authors from retrieval now (the existing `source_toggles` "Historical Commentaries" switch is one immediate lever, already confirmed `enabled=True`), scope of further author verification, whether to trace the undocumented citation_mode change further, and a minor "Adamnan"/"Adamnán of Iona" duplicate-author cleanup.

**2. Book-length extraction truncation check — no file written, per that task's explicit instruction; findings recorded here instead.** Follow-up to PLAN.md #17's open book-length gap (2 of the item's 7 unprocessed documents from the 2026-07-30 backfill). Question: do book-length documents show a broader, silent under-extraction pattern beyond the two known hard failures?

**Confirmed: no.** 46 of 53 `source_type='book'` documents (including all 10 of Andrew Murray's) are `license_status='public_domain'` or `owned` — the propositions gate skips these entirely by design, so their 0-proposition counts are expected behavior, not evidence of any bug. The only population the gate ever attempts is the 6 `unlicensed` books. Of those: the 2 known failures (Bosworth "Christ the Healer," 90,842 words; Kreighbaum "Manual Systematic Theology," 139,659 words) are confirmed clean total errors in the real backfill log (`backfill_run_review/full_backfill_log.jsonl`) — `result: "error"` on both first attempt and retry, zero stored either time, not a partial/truncated success. The other 4 (Kreighbaum's "Essentials For New Disciples"/"Maturing in God"/"Ministry of God's Word," and the anonymous "Foundation Stones for New Believers") succeeded with genuine full-document coverage: their propositions-per-1000-words (0.65–1.47) sit at or near the median for unlicensed non-book documents (1.32, IQR 0.98–2.49, n=3025); the top 10 corpus-wide proposition counts show a smooth natural decline (40, 36, 30, 27, 25, 24...) with no ceiling-clustering signature; and — the strongest evidence — reading the actual proposition text against each book's own structure shows the LAST proposition in all three checked books topically matches the book's own final ~1% of content (e.g. "Foundation Stones for New Believers"'s last proposition, about eternity, matches its literal last chunk's Ecclesiastes 3:11 citation). **No re-extraction of any existing book is warranted.** The risk surface for PLAN.md #17's book-length gap remains exactly the 2 already-known documents, unchanged in scope — see PLAN.md #17 for the corresponding update.

---

## Records-cleanup pass: Item 3/4 state corrected, Open Decision #20 held (session state, 2026-07-30, later same day)

Docs/records-only session — read PLAN.md and this file fresh before writing, per this session's own instruction, rather than blind-applying a prepared list. Full detail lives in PLAN.md; this is the pointer plus one correction that belongs here because it directly concerns the section immediately below.

**Correction, flagged rather than silently rewritten:** the section below ("Position layer Item 3 shipped; review repairs gate Item 4") states Item 4 must wait for three repairs from a post-commit review. That did not hold — **Item 4 (the standing premise-correction instruction) shipped anyway, commit `94b1ee7`,** directly after Item 3, without those three repairs confirmed landed first. See PLAN.md's Item 3/Item 4 roadmap entries for the full reconciliation.

**Update (2026-07-30, later same day, commits `d023a69`/`d0f2404`): all three named repairs are now done** — deduplicated prompt templates (one shared `BASE_TEMPLATE`), the "verbatim stated" wording corrected to "explicitly state," and regression tests added (`scripts/test_positions.py`). The section below has been updated in place to reflect this rather than left stale. Full detail: `docs/audits/item3_item4_repairs_2026-07-30.md`. **Not part of this repair slice, still genuinely unmade:** the explicit accepted/rejected boundary table for matcher variants ("predestined," "predestinate," "Calvin on election," "unconditional-election") named in the section below. **One more variant, from an independent parallel review (Codex, 2026-07-30, later same day):** "Reformed doctrine of election" also doesn't trigger tension mode today — confirmed directly against the live code. Same open decision, more completely enumerated, still unmade.

**Also for the record:** Item 3's tension-mode exception is a narrow, one-off carve-out for the Calvinism/predestination topic family only — not general "contested topic" infrastructure. No future session should assume a general mechanism for doctrinally-contested topics exists in this codebase.

**Separately:** a fifth attempt at an automated output-stage verification guard (Open Decision #20) was built, tested, and held the same day — nothing shipped, `scripts/positions.py`/`scripts/generate_teacher_positions.py` are at clean HEAD. Full record in PLAN.md Open Decision #20; not duplicated here.

---

## Position layer Item 3 shipped; review repairs complete (session state, 2026-07-30; repairs landed later the same day, see update below)

Item 3's narrow Calvinism/predestination tension-mode exception is committed at `b9f9a45`. Matching topics use `TENSION_MODE_PROMPT` with `position_tension_v1`; ordinary topics keep `POSITION_PROMPT` with `position_v1`. The same selector drives generation and stored provenance. No database rows were written by this item or the review described here.

A subsequent read-only adversarial review found three repairs required before Item 4 begins: deduplicate the two complete prompt templates so later standing instructions cannot drift between ordinary and tension modes; replace the tension prompt's “verbatim stated” exception with an evidence-level “explicitly states” rule because the generator sees already-paraphrased propositions, not verbatim source text; and add durable regression tests for selection, exact prompt parity/difference, and stored version/fingerprint. Matcher boundaries also remain deliberately unresolved rather than silently widened: bare “election” is intentionally excluded, while “predestined,” “predestinate,” “Calvin on election,” and hyphenated “unconditional-election” are currently excluded without an explicit accept/reject ruling.

**Next position-layer step:** repair and test Item 3 as above, then implement Item 4's premise-correction standing instruction against the shared prompt structure. Do not add Item 4 to only one of the current duplicated templates. **Update (2026-07-30, later same day, commits `d023a69`/`d0f2404`): done.** The two prompt templates are now deduplicated into one shared `BASE_TEMPLATE`; the "verbatim stated" wording is now "explicitly state" (`TENSION_MODE_PROMPT_VERSION` bumped to `position_tension_v3`); `scripts/test_positions.py` adds regression coverage for both the tension-mode trigger/selection and the shared-paragraph identity. The matcher-variant accept/reject boundary table named above was not part of this repair slice and remains unmade. A real-data check found the wording fix does not measurably change the Calvinism/predestination over-confidence behavior itself — that stays open, tracked at PLAN.md Open Decision #20. Full detail: `docs/audits/item3_item4_repairs_2026-07-30.md`.

---

## Records-only session: no-oracle reframe + position-layer three-source design (session state, 2026-07-30)

Docs/records-only session per CLAUDE.md's Session Routing table — chat proposed, terminal committed; zero code touched, zero DB writes. Writes: `CLAUDE.md`, `PLAN.md` (bumped to v5.3), `POSITIONING.md`. This entry is the pointer; full text lives in those files, not duplicated here.

**Decisions recorded, all Alex's explicit calls from this session:**
- **No-oracle rule reframed, not deleted.** Was absolute ("Rhemata never speaks except to attribute a named teacher"); now a strong default with two sanctioned own-voice exceptions. `POSITIONING.md` Section 5 ("Not an oracle"), Section 9 (Chat guardrail), and Section 10 (Guardrail 2) updated to state the exceptions explicitly. Guardrail 1 ("never speaks as God, for God, or about what God is 'saying'") stays untouched and absolute — the reframe is about attribution, not about claiming revelation.
- **Position Papers — new sanctioned house-voice category.** Hand-authored by Alex, scripture-backed, one per charismatic pillar. Served `silent_context` — unattributed, uncited, not labeled to the user as a "Position Paper." The two pre-existing example files (`sources/documents/baptism_of_the_holy_spirit.md`, `sources/documents/speaking_in_tongues.md`) are the canonical tone/structure/depth model. **Scope capped deliberately:** charismatic pillars only; core Christian-basics topics (Trinity, salvation, nature of scripture) are explicitly out of scope — teacher citation already covers them. Authoring the remaining pillars is unscheduled future work.
- **Machine-generated live fallback may also speak in its own voice**, but every such answer must carry the disclaimer "Rhemata can make mistakes. Please let us know if you see any." — Position Papers never carry it.
- **Position-synthesizing layer (PLAN.md track PL) reframed from two answer sources to three:** (a) Position Papers, (b) teacher/corpus positions (unchanged design), (c) machine-generated fallback (own voice + disclaimer). New build dependency added to #48: the fallback must log/tag each answer's topic, feeding a future real-usage-driven queue for which topic gets a Position Paper next — no topics pre-named, per the existing Open Decision #16 posture.
- **2026-07-29 closeness-check retirement reconciled into PLAN.md.** That decision (gate retired in code via `CLOSENESS_CHECK_RETIRED = True`; retroactive triage of the 213 flagged/held items abandoned as accepted risk after only the 139-item fast pile was triaged) had previously been recorded only in this file's "Retroactive closeness-check triage" entry below — PLAN.md's #45–#47 language still read as if the review were open. Now reconciled: #45 marked retired with a full note, #46 marked moot-for-production, #47's header/closing updated to point at the retirement rather than "findings NOT RESOLVED." The "Ingestion policy, effective 2026-07-25" paragraph (which gated new-ingest propositions on #45 existing) is marked superseded — #45 was retired rather than turned on, and fresh ingests generate propositions via the v3.1 path same as the backfill.
- **CLAUDE.md Invariant 13 updated.** The backfill precondition for corpus-wide positions ("a decision not yet made") is now judged SATISFIED — Alex's explicit call, given 850/857 documents backfilled and the 7 remaining failures understood (known JSON-escaping bug + book-length extraction gap, PLAN.md #17). This does NOT make corpus-wide positions buildable today: the `positions.kind` CHECK constraint, the application-level refusal, and Open Decision #13 (scope-boundary ownership) are all still in place/open.
- **Backfill milestone confirmed complete, this session's numbers matched against PLAN.md #17/#49 and the prior 2026-07-30 entries below:** 850/857 eligible documents have propositions, 5,357 new rows via v3.1, 7 unprocessed (5 JSON-escaping, 2 book-length).
- **Stale ~781 backfill-target figure — checked, already corrected.** Live-grepped every root `.md` file: the only two files mentioning "781" are `PLAN.md` (line ~288, already annotated "stale, predates the Bevere deletion") and this file (the two entries below dated 2026-07-28/30, already annotated as corrected to 564, plus one historical mention inside the 2026-07-25 Bevere-risk finding further below, left as-is since it accurately describes the count *at the moment that finding was made*, before the deletion). No uncorrected/uncaveated "781" exists anywhere in the durable records as of this session.

**Flagged for Alex, not resolved this session — three literal customer-facing copy strings still state the old absolute claim and were deliberately NOT rewritten unilaterally:**
1. `POSITIONING.md` Section 1 (the one-liner): "...never from an averaged, anonymous AI voice..."
2. `POSITIONING.md` Section 7, Messaging Pillar 1: "Every answer comes from a named teacher you can verify — never from an anonymous AI voice."
3. `POSITIONING.md`'s "15-Second Version": "it never answers in its own voice."

All three now overstate the rule now that Position Papers and the disclaimed machine fallback exist. Section 5/9/10 (the governing rules) were reframed directly since they're product rules, not ad copy — these three are the literal external-facing lines, and picking new wording that stays punchy without re-opening the oracle framing is a copy decision, not a records one.

---

## Full propositions backfill run — 508/515 documents, corpus-wide 850/857 (session state, 2026-07-30)

Plain-script/DB-write path throughout, per CLAUDE.md's Session Routing
table's hard rule (any DB write, harness never used). Three pieces in one
continuous session; each is its own dated sub-entry below, newest first.
`scripts/backfill_propositions.py` and `scripts/run_full_backfill.py` are
new, committed; `scripts/propositions.py`/`scripts/shared_ingest.py` carry
the actual prompt/wiring change (next sub-entry). Zero code touched in this
top entry — this is the full-scale run only.

**Live-queried, not assumed: 515 documents were the real remaining backfill
set** (zero propositions, `license_status` licensed/unlicensed, not Precept
Austin) at run time — re-derived fresh, not reused from an earlier day's
stale count. Ran via `scripts/run_full_backfill.py`: sequential (no
concurrency, matching every other ingest script in this repo), one document
at a time, on the v3.1 named-teacher path. Crash-safety was load-bearing,
not theoretical: every result is appended to a gitignored JSONL log
(`backfill_run_review/full_backfill_log.jsonl`) immediately, fsync'd, and a
background-task monitoring hiccup mid-run (the wait-loop watching the
process got killed independently of the process itself — see below) proved
the design's real value, not just its intent.

**Result, verified against `propositions` table row counts directly, not
the script's own printed summary:** 508 of 515 documents got propositions —
**5,357 new rows**, range **3–40 per document**, mean **10.5**. Script-
reported counts vs actual DB counts: **0 mismatches** across all 515.
Every one of the 5,357 rows carries `prompt_version='v3.1'`, a correct
fingerprint, `model='llama-3.3-70b-versatile'` — 0 exceptions. Zero
documents produced a legitimate empty result (`no_propositions`/
`too_thin_to_extract`) — every document that succeeded had real extractable
content, unlike some earlier proving-batch runs.

**Cost: $4.19 actual**, computed from real word volume observed during the
run (4.61M input words, 217K output words of generated propositions) at the
confirmed Groq rates ($0.59/M in, $0.79/M out) — close to the $4.50–5
pre-run estimate, disclosed to Alex before the run started per CLAUDE.md's
per-item-cost rule. Comfortably under the $50 ceiling.

**7 documents still fail after one retry pass each — two distinct causes,
not conflated:**
- **5 are the already-known JSON-escaping defect**, root-caused in the
  prior sub-entry below: the model occasionally emits an unescaped quote
  inside a nested scripture quotation, breaking strict `json.loads()`
  parsing. All five are normal length (5.8K–12K words), same
  `"Expecting ',' delimiter"` signature: Daniel Kolenda "Cessationism 9
  (The Pagan Origins)", Derek Prince "Mary: The Pattern Mother", Derek
  Prince "Seven Ways To Keep Your Deliverance", Derek Prince "Who Are The
  Israel Of God?", and Vlad Savchuk "God Decides When. Not You." — the
  same document that failed identically, deterministically, in the prior
  sub-entry's proving batch; confirmed again here as still deterministic at
  `temperature=0.2` (identical failure on the retry, not intermittent).
- **2 are a genuinely new finding, never exercised by either proving
  batch (max ~11.8K words tested there): book-length documents.** Bosworth
  "Christ the Healer" (90,842 words, 256 chunks) and Doug Kreighbaum
  "Manual Systematic Theology" (139,659 words, 423 chunks) — both
  legitimately `source_type='book'`, confirmed by direct query, not a
  mis-filed/duplicated-content data error. Kreighbaum's failed with a hard
  Groq 400 ("Please reduce the length of the messages or completion");
  Bosworth's failed with malformed trailing JSON, almost certainly the same
  underlying cause. **Root cause: `extract_propositions()` sends the
  entire reconstructed document in ONE call with `max_tokens=8192` output —
  structurally incompatible with book-scale source text.** Not fixed this
  session (flagged, not remediated) — a real gap for any future book-heavy
  ingestion or backfill pass, needs a chunked/multi-call extraction
  redesign for `source_type='book'` specifically before those are retried.

**Corpus-wide state, live-queried:** of 857 total eligible documents
(licensed/unlicensed, not Precept Austin), **850 now have propositions, 7
do not** — exactly the 7 named above, nothing else. `propositions.
prompt_version` breakdown corpus-wide: `v3.1: 5592` (5,357 from this run +
235 from the prior sub-entry's proving batch — exact arithmetic match, no
double-counting), `v3: 222` (the first proving batch, untouched), `
legacy_unknown: 2409` (pre-session corpus, untouched, unaffected by any of
today's writes).

**Verified untouched, not merely assumed:** `store_propositions()`'s
clear-then-insert only ever fired against documents that had zero
propositions rows before this session touched them (by construction of the
selection query), so its `DELETE` was a no-op for every one of the 515 —
confirmed by the exact `v3: 222`/`legacy_unknown: 2409` counts holding
steady from before this run to after. Serving backend (`backend/app/`)
grepped directly for imports of `propositions.py`/`shared_ingest.py`: zero
matches — untouched, unreachable from any live request path.

**Operational note, not a data problem:** mid-run, the background wait-loop
I was using to monitor completion (a separate polling process, not the
backfill itself) was killed independently once, without explanation
available from this environment. The actual backfill process, launched
detached (`nohup`+disown) from that monitor, was completely unaffected and
continued correctly — confirmed by re-checking the live process and its
JSONL log, which was still actively appending. Re-established a second
monitor and the run completed cleanly. Documented here since it's a real
observed harness/environment behavior, not because it affected any output.

**Not done this session, explicitly left open:** the 7 still-failing
documents; a fix for the book-scale extraction gap; whether to retry the 5
known-bug documents again (their content is genuinely lost until either
retried again — non-deterministic for 4 of the 5 — or the JSON-parsing
robustness gap itself gets fixed). PLAN.md #17/#49 updated to reflect this
state.

---

## Named-teacher fix isolated and proven; "the author" defect closed for future generation (session state, 2026-07-30)

Mixed routing, both plain-script/DB-write path (no harness): the prompt/
code change itself was a small, carefully-scoped edit verified against the
existing test suite before any live call; the proving batch was a real
25-document DB-write run, same as the entry below it.

**Problem, measured at real scale for the first time in the prior sub-entry
below:** the live v3 extraction prompt's `"Attribute naturally (\"the
author teaches…\")"` line causes the model to write generic "the author"
instead of the real teacher's name — corrected count (word-boundary,
excludes "authority" false-matches): **90.1%** of 222 propositions in that
batch, not the initial rough 84% estimate.

**Fix, deliberately narrow — Alex's explicit instruction: isolate ONLY the
naming mechanism, not v4's bundled length/structure/voice retuning.**
New `EXTRACTION_PROMPT_V3_1` constant in `scripts/propositions.py`: v3's
exact wording, with a `{speaker}` placeholder replacing all 8 generic
"the author" references (verified by direct text diff, not assumed), plus
one added negative instruction ("never 'the author'") since the old
worked-example and attribution bullet both explicitly modeled the wrong
form — leaving those unchanged would have directly contradicted the new
rule. **Byte-identical to v3, verified programmatically:** the opening
framing sentence, the FOUR CORNERS rule, examples/claims bullets, "Neutral
voice," the entire "Count and distinctness" section, and — the
specifically-protected line — `"Length: ~80–150 words each."`, not v4's
expanded length section.

**Wired as opt-in, not a default swap — zero regression risk by
construction, not just by testing.** `process_document()`/
`extract_propositions()` gained new optional `speaker`/`prompt_version`
params, both `None` by default; `DEFAULT_PROMPT_VERSION` stays `"v3"`
untouched, so every pre-existing caller/test that doesn't pass these params
is byte-identical to before. Confirmed, not assumed: all 3 existing test
files that import `propositions.py`
(`test_propositions_closeness_gate.py`, `test_propositions_reference_
grounding.py`, `test_reference_grounding_unit_proof.py`) re-run clean, 0
regressions — including the one test that specifically asserts
`process_document()`'s stamped provenance matches `DEFAULT_PROMPT_VERSION`
exactly, which only stays true because that constant was deliberately left
unchanged. The real production call site (`shared_ingest.py`'s
`ingest_document()`) now explicitly opts in: `prompt_version="v3.1"` +
a resolved speaker name (prefers `author`, falls back to `source_name`,
falls back to a live `sources.name` lookup for the pre-resolved-`source_id`
caller path that can leave both empty) — so future fresh ingests get the
fix automatically, not just this session's backfill.

**Proof: a second, non-overlapping 25-document batch** (the first batch's
25 already have real stored propositions; re-running them would have
cleared and replaced that data via `store_propositions()`'s clear-then-
insert, which Alex's instruction explicitly ruled out — so a fresh,
same-methodology 25 was drawn instead and the substitution was disclosed,
not silent). Same teacher plan as the first batch (15 Prince/3 Savchuk/3
Kolenda/2 Ravenhill/1 Kreighbaum/1 Poonen) for an apples-to-apples
comparison.

- **"The author" rate: 0.0% (0/235)**, word-boundary-corrected (excludes
  "authority" false matches) — down from the corrected 90.1% v3 baseline
  (83.8% specifically at the start of a proposition). Not a partial
  improvement — the mechanism closed the gap completely in this sample.
- **Length: 38.8 words average, vs. 38.4 in the v3 baseline batch** — no
  meaningful shift, confirming the isolation held (this was Alex's
  explicit stop-and-report condition if it had drifted).
- 24/25 documents stored propositions (235 total, range 4–16/doc). 1
  error: Vlad Savchuk "God Decides When. Not You." — root-caused live, not
  just logged: a nested, unescaped quote around an Ecclesiastes 3:1
  quotation breaks `json.loads()`. **Confirmed deterministic** (identical
  malformed output across 4 separate live calls at `temperature=0.2`) **and
  confirmed pre-existing** — the same document, run through the unmodified
  v3 prompt with no speaker, produces the identical break. Not caused by
  this session's change; not fixed this session (out of scope, a JSON-
  parsing robustness gap, not a prompt-wording issue).
- 5 random samples pulled with full source passages, reviewed directly:
  names render naturally ("Derek Prince teaches...", "Vlad Savchuk
  teaches...", one no-attribution-frame form), content stays specific and
  well-anchored to source in 4/5 (the 5th merges two teaching points from
  different parts of a long document — a locator-script limitation in
  reviewing it, not necessarily a flaw in the proposition itself).

**Not yet established, flagged for whoever runs the next slice:** accuracy/
character of v3.1 output specifically at book-length scale — the very next
session (the full-backfill entry above this one) is what surfaced that gap,
so it's now closed-the-loop, not open. See that entry.

---

## First backfill proving batch — v3 baseline, "the author" defect measured at scale (session state, 2026-07-30)

Plain-script/DB-write path, per CLAUDE.md's Session Routing table's hard
rule. First scaled run of the generation path since generation stopped
2026-07-25 — a proving batch, not the full run, by explicit instruction.

**Correction to the session brief's own framing, caught before selecting
anything:** the backfill set is **564 documents live**, not the brief's
"~781", and **contains zero Bevere documents** — Bevere's 220 documents
were deleted 2026-07-25 (already recorded below); 781 was the stale
pre-deletion count. Derek Prince is 492 of the 564 (87%) — any future batch
skews Prince-heavy almost no matter how it's drawn.

**Selection: 25 documents, 6 teachers** (15 Derek Prince spanning 372–
11,368 words — deliberately including the long-form/book-adjacent range,
since PLAN.md #17 flagged extraction as unproven there; 3 Vlad Savchuk; 3
Daniel Kolenda; 2 Leonard Ravenhill; 1 Doug Kreighbaum; 1 Zac Poonen). Ran
on the live, unmodified v3 prompt (no code change this sub-session).

**Result, reconciled against the `propositions` table directly:** 222
propositions across 25 documents, range 4–15, mean 8.9. Every "stored:N"
matched the DB row count exactly. All 222 stamped `prompt_version='v3'`,
correct fingerprint, `model='llama-3.3-70b-versatile'`. Zero documents
produced a legitimate empty result. **Cost: ~$0.15–0.20**, well under the
$50 ceiling, disclosed before running.

**1 of 25 errored on the first pass** (Daniel Kolenda "Cessationism 8 (More
Calvinist Than Calvin)") — a Groq JSON-parse failure, confirmed transient
via isolated reproduction (`finish_reason: stop`, not a truncation;
succeeded cleanly on retry, unlike the deterministic case found in the next
sub-session). Retried once through the real path: stored 13. 25/25 have
propositions after the retry.

**The load-bearing finding: 84% of the 222 propositions open with "The
author" instead of the teacher's real name** — a known, already-documented
v3 defect (PLAN.md #46: "'the author' used instead of the teacher's real
name — v3's live prompt allows this; v4 already fixed it but is unwired"),
but this is the first time it was measured at real scale, and 84% is high
enough to directly undercut the product's "named teacher, not generic
authority" positioning. This measurement is what triggered the isolated-fix
session immediately above. Secondary finding: average proposition length
38 words — below even the previously-measured-deficient v3 average (~62–70
words, PLAN.md #46) and well under the 80–150 word design target, same
root cause (v3's length-guidance placement, PLAN.md #46's own diagnosis).

Reference-grounding: 18 scripture references flagged UNCERTAIN across the
batch, **all 18 overturned by Layer-3 arbitration and kept** (0 stripped as
fabricated) — good in that nothing looked fabricated, but this batch never
exercised the confirmed-absent strip path either way.

**5 random samples pulled with full source passages, reviewed directly.**
Three anchored solidly. One (Daniel Kolenda, a specific countable claim —
"over 20 references to tongues... only one connects them to human
languages") wasn't confirmed or refuted by the excerpt shown — a class of
claim the automated reference-grounding check doesn't cover (it verifies
chapter:verse citations, not prose claims about scripture content). One
(Leonard Ravenhill) — the locator script picked the wrong chunk in a
29-chunk document; a limitation of the quick word-overlap matcher used for
review, not evidence of a bad proposition.

---

## 23 pending commits safety-checked and pushed to origin/main (session state, 2026-07-29)

Git-push-only session per CLAUDE.md's Session Routing table — no code changes, no database writes. Working tree confirmed clean before and after; `origin/main` confirmed 23 commits behind `HEAD`, 0 ahead, before pushing.

**Pre-push safety check, read from the actual diffs rather than assumed:** (1) proposition/statement generation is still stopped — `propositions.py`'s closeness-gate branch is only reachable when a caller supplies `name_pattern`, no real caller (`shared_ingest.py`, `ingest_helloao.py`) does, and no cron/scheduled job anywhere in the repo triggers generation; (2) the closeness gate stays inert — this batch only moved its calibrated threshold (9→12 words, PLAN.md #46), which has no effect unless the gate is already active; (3) **one nuance, not silently assumed away:** the batch does touch four currently-serving files — `backend/app/routers/study.py` (mounted `/study/verse` endpoint), `backend/app/services/reference_verifier.py` (imported directly by `chat.py`, the live chat-answer citation verifier), `frontend/app/study/page.tsx`, and `frontend/lib/study-reference.ts` (the live chat-answer scripture underliner). The change is the BOOK_MAP ordinal-form widening already named in CLAUDE.md's Landmines (commit `ee267d4`) — purely additive (new alternate spellings like "1st Samuel"/"First Samuel"/"I Samuel" now recognized; nothing about forms that already matched changed). Flagged to Alex directly rather than pushed silently; Alex confirmed proceeding given the fix is deliberate, already-documented, and additive-only.

**Pushed:** `origin/main` advanced `703a8cb..212eb3e` (23 commits). No migration was applied as a side effect of the push — `073_positions.sql`/`074_proposition_chunks.sql` are plain SQL files; `backend/railway.toml`'s deploy `startCommand` is `uvicorn app.main:app ...` with no migration step, confirmed by reading the file directly. Railway's auto-deploy from `main` will pick up this push.

---

## Retroactive closeness-check triage: CLOSED without full completion, gate retired (session state, 2026-07-29)

Two sessions on this same track. **Session 1** built `scripts/closeness_triage.py`'s
complete local-only workflow — generation from the authoritative JSONL;
compact fast cards; one-file-per-item real-attention cards with the
calibrated near-verbatim run highlighted; chat-page commands; a persistent
`decisions.json` ledger; closed decision vocabularies; automatic UTC
timestamps; reviewer notes; progress reporting; no corpus mutation path, no
auto-fixing — but a live Supabase DNS-resolution failure in that managed
environment stopped card generation before any output existed. **Session 2**
(this one, harness route — executor/planner-reviewer, zero DB writes, every
Postgres touch a read-only/autocommit SELECT): Supabase was reachable this
time; `generate` ran, crashed partway through the real-attention loop at
item 15 of 74 on a real rendering bug (below), and after the fix, ran clean
to completion. Its exact split is **137 containment-only + 74 long-run + 2
too-little holds = 213**, unchanged from Session 1's analysis — the two
holds route to the binary fast queue, producing **139 fast items in seven
balanced batches (20, 20, 20, 20, 20, 20, 19)** and **74 real-attention
items**.

**Renderer bug, root cause and fix (commit `3bfa3f3`, local, not yet
pushed).** `closeness_check.py`'s `_mask_theology()` substitutes bare
`THEOLOGY_TERMS` words (e.g. "God", "Bible") via a plain `\b`-bounded regex —
`\b` matches between a word character and an apostrophe, so it also matches
"Bible" inside "Bible's", leaving a dangling `'s` that `tokenize()`'s word
regex then retokenizes as a standalone one-letter `"s"` token. `_real_card()`
was searching for this masked token sequence verbatim in the real, UNMASKED
source text — a sequence that never exists there (a real "Bible's" tokenizes
as one token). Two of 74 real-attention items hit this exactly: item 15
(`148864dd-0883-42c9-83a4-bb85dacc7c39`, Doug Kreighbaum, "Understanding the
Bible's story and theme... God's family") and item 29
(`b664f59e-89f8-48dc-826f-b156bb08dcee`, Leonard Ravenhill, "The Ark Of God" —
"God's power... God's judgment"). Fix: a new `compute_real_highlight_run()`
reuses the pre-existing, already-unmasked `raw_longest_run()` (the same
function `_fast_card` already used) to find the highlight span in raw text
instead of the masked run. The classifier-integrity check in `generate()`
(comparing a fresh masked-run reconstruction against the recorded JSONL's
`longest_run_words`) is untouched, unwrapped, still hard-raises on a
mismatch — only the rendering path changed, per PLAN.md's closeness-check
track staying classifier-frozen. Per-item highlight lookup is now wrapped in
try/except: a genuine failure writes an honest "could not locate" card (no
fabricated highlight, still carries the Proposition ID line so
`decide-real`/`show-real` keep working) and logs to a `highlight_failures`
list in the manifest, rather than crashing the whole batch. A regression
test reproducing the exact masked-possessive `"s"`-token artifact was added
to `test_closeness_triage.py` (6/6 green, up from 5/5).

**Generation completed clean, verified against actual file output — not
exit code.** `manifest.json` shows `containment_only=137`,
`real_attention.count=74`, `too_little_holds=2`, `flagged_total=213`,
`fast_pile.batch_sizes=[20,20,20,20,20,20,19]` (139 total), and
**`highlight_failures: []`** — zero rendering failures across all 74
real-attention items. 74 `item_001.md`..`item_074.md` files confirmed on
disk; item 15 and item 29 read directly and both show a real, coherent
`**...**`-highlighted near-verbatim run present in both the flagged-passage
and source-context sections. `decisions.json`'s shasum was identical before
and after regeneration (the ledger — currently 0 decisions recorded —
survived untouched, per its existing merge-on-regenerate design).

**Prior blocker cleared — was environment-specific to Session 1, not a
design flaw.** Live output exists locally at
`closeness_review/retroactive_triage/` (gitignored): 139 fast-pile items
across 7 batches, 74 real-attention cards, `decisions.json` ledger,
`manifest.json`.

**Session 3 (this one) — Alex triaged all 139 fast-pile items, then closed
the review before the 74-item real-attention queue was ever touched.**
Across seven batches, recorded via the tested `decide-fast` code path (never
hand-edited JSON): **115 cleared, 24 escalated** (word-count rule: near-verbatim
run ≥12 words → escalate, unless the run was itself a direct scripture
quotation or a quoted hymn/song line, in which case clear regardless of
length). The 24 escalated items are correctly recorded in `decisions.json`
(`decision: "send to real-attention pile"`) but were **never actually
folded into the real-attention queue or given full review-card content** —
a code change to do that (`generate()` producing `item_075.md` onward for
escalated items, plus extending `decide-real`/`show-real` to recognize them)
was designed but never implemented; this session pivoted to closing the
review instead. **The 74 originally-flagged real-attention items were never
reviewed at all — 0/74 decided, same as every prior session.**

**Closure decision, Alex's explicit call:** near-verbatim reuse of a
teacher's own exact wording is an accepted risk going forward, not
something to review or block. The remaining, un-triaged 74 real-attention
items and the 24 escalated-but-unexpanded items are **abandoned, not
paused** — this review will not be completed. All 213 recorded decisions
(115 clear / 24 escalate / 74 untouched) and the entire
`closeness_review/` directory are left exactly as they are: historical
record of what was actually reviewed, never touched or backfilled to look
complete.

**Gate retired, not deleted (`propositions.py`).** Added
`CLOSENESS_CHECK_RETIRED = True`, a module-level constant with no per-call
override, widening `process_document()`'s existing
`if name_pattern is None:` branch to `if name_pattern is None or
CLOSENESS_CHECK_RETIRED:` — this makes the `import closeness_check` /
`classify()` loop permanently unreachable regardless of what any caller
supplies, without deleting any of that code (reversible later by flipping
the one flag back to `False`). **Verified this was already fully inert
before this change** — read every real ingest call site
(`shared_ingest.py`'s `ingest_document()`, which doesn't even have
`name_pattern`/`verse_lookup`/`vocab_matcher` as parameters, plus
`ingest_helloao.py`'s direct call) and confirmed none of them ever supplied
these params, so production behavior is byte-identical before and after;
this change is pure belt-and-suspenders against a future regression, not a
fix for anything currently firing. Proven, not just asserted: updated
`test_propositions_closeness_gate.py` with a `closeness_check.classify()`
call-spy — even with a real `name_pattern` explicitly built and supplied,
`classify()` is called **zero times** and the result is `"stored:3"`
(all items, unfiltered), where the same call previously produced
`"stored:1:flagged:2"`. Full suite re-run clean end to end.
`closeness_check.py` itself is completely untouched — `classify()`,
`build_name_pattern()`, etc. remain fully functional for
`closeness_triage.py`/`validate_closeness_check.py`, independent of
`propositions.py`'s (now-retired) wiring into them.

**Position-layer gating, updated.** PLAN.md #47's own language — *"No
position may be built from any teacher's evidence until that teacher's
flagged items are resolved or explicitly risk-accepted"* — is satisfied by
this decision: it **is** the explicit risk-acceptance that clause names.
**Teacher-specific position building (#47/#48) is unblocked.** **Backfill
(#49) is only partially unblocked** — the closeness-review-tied precondition
is cleared, but #49 carries its own separate, still-open preconditions
untouched by this decision: the anti-fabrication re-wiring has only been
proven at n=1 document (not yet the ~429-document Derek Prince scale), and
the license-gate/Precept-Austin lockout gaps disclosed in CLAUDE.md
Invariant 11 remain open. Do not read this entry as "backfill ready to
run" — it is not.

**Not done this session, flagged as a follow-up, not silently left
inconsistent:** PLAN.md's own #47/#48/#49 gating language (e.g. "the gate
remains open," the teacher-risk-acceptance wording) still reads as it did
before this decision — this session deliberately scoped to `propositions.py`
+ its test + this file only, per explicit instruction. A separate pass
should reconcile PLAN.md's roadmap language with the closure recorded here.

---

## PLAN.md #47 calibrated closeness re-check reconciled; disposition still open (session state, 2026-07-29)

Plain/direct read-only diagnostic per CLAUDE.md's routing table. Every database connection was readonly/autocommit and every statement was a SELECT; statement generation remained stopped. The classifier path was verified before the run to contain no model client, HTTP request, or completion call: this was deterministic local code plus one-time readonly name/alias and WEB-verse lookups, so inference cost was $0.00. No database row changed.

**Ground truth and reconciliation.** Live count was re-queried at **2,409**, not trusted from the brief. All 2,409 rows were created no later than 2026-07-23, before the calibrated gate landed. The gate remains opt-in in code and no real-storage caller activated it; all live rows carry only the later-added `legacy_unknown` prompt-version marker, with null prompt fingerprints and null model fields. The calibrated thresholds read directly from `scripts/closeness_check.py` were: longest post-exemption run **12 words**, trigram containment floor **0.40**, and `HOLD_TOO_LITTLE` for **fewer than 8 residual tokens** (checked first and unconditionally). One bulk proposition+metadata query, one bulk chunks query, and one-time lookup queries fed the identical `classify()` function. Attempted arithmetic and the actual review file both reconcile: **2,409 = 2,196 PASS + 211 QUOTE_CANDIDATE + 2 HOLD_TOO_LITTLE + 0 errored**; the JSONL has 2,409 lines and 2,409 unique proposition IDs.

**Signal split.** Of 211 quote candidates, **74 (35.1%) trip the strong 12-word-run signal**: 12 run-only and 62 both run and containment. The remaining **137 (64.9%) trip containment alone**, the softer signal Alex was skeptical of during calibration. The **2 HOLD_TOO_LITTLE** rows are the same Vlad Savchuk propositions found in the 2026-07-26 scan, from the same document, with residual counts 7 and 5; the full run found no additional thin cases.

| Teacher | Total | PASS | QUOTE_CANDIDATE | HOLD | Flagged / total |
|---|---:|---:|---:|---:|---:|
| Carter Conlon | 43 | 38 | 5 | 0 | 11.6% |
| Charles Simpson | 24 | 13 | 11 | 0 | 45.8% |
| Daniel Kolenda | 17 | 12 | 5 | 0 | 29.4% |
| Derek Prince | 21 | 18 | 3 | 0 | 14.3% |
| Doug Kreighbaum | 31 | 19 | 12 | 0 | 38.7% |
| Ern Baxter | 15 | 7 | 8 | 0 | 53.3% |
| Jack Deere | 14 | 13 | 1 | 0 | 7.1% |
| Leonard Ravenhill | 766 | 724 | 42 | 0 | 5.5% |
| New Wine Magazine | 12 | 11 | 1 | 0 | 8.3% |
| Vlad Savchuk | 1,053 | 953 | 98 | 2 | 9.5% |
| Zac Poonen | 413 | 388 | 25 | 0 | 6.1% |

These rates describe how the mechanical wording signals interact with each teacher's phrasing style, not teaching quality. The highest rates belong to very small teacher samples, where a few items move the percentage sharply; Ravenhill's large corpus flags at 5.5% under the calibrated line, contrary to the earlier expectation that his aphoristic register would necessarily produce the highest corpus-wide rate.

Per-item findings are local-only at gitignored `closeness_review/calibrated_corpus_recheck_2026-07-29.jsonl`, one record per proposition with document, teacher, proposition ID/content, verdict, exact signal, measurements, and stored prompt-version/fingerprint/model provenance. **This session did not triage or decide any flagged item.** PLAN.md #47 is run and reconciled, not resolved. The 213-item flagged/held pile is bounded and human-reviewable, but large enough to require its own deliberate triage session before backfill/position-layer work can rely on it. **No position may be built from any teacher's evidence until that teacher's flagged items are resolved or explicitly risk-accepted; this gate remains open.**

---

## PLAN.md #46 human calibration closed out (session state, 2026-07-30)

Two sessions, both read-only/repo-only, zero DB writes throughout. Full detail: `PLAN.md` #46 (rewritten in place — the old "required, load-bearing, not yet run" framing is retired, not stacked on top). Build commit: `8f129c0`. Judging material: gitignored `calibration_review/` (blind file + hidden reference, not for permanent git history — copyrighted third-party transcript reconstructions).

**Session 1 — built the blind judging set.** 24 items, 8 each for Vlad Savchuk (chosen over Zac Poonen: 1,053 propositions/117 documents vs 413/44 — live-queried, not assumed), Leonard Ravenhill, Derek Prince. 20 real (pulled from real stored propositions, full source documents reconstructed fresh from `chunks`, never a cached excerpt — confirmed before finishing), 4 constructed (the too-little-to-measure shape has only 2 real corpus examples anywhere, both Savchuk, so Ravenhill and Prince needed 2 constructed apiece, clearly labeled in the hidden reference only). Alex judged blind, no automated score or category hint shown.

**Session 2 — Alex passed all 24 blind**, then ruled: shared vocabulary already doesn't count (existing exemption); short verbatim reuse is fine, only paragraph-scale copying is a violation; the line is a **longest verbatim run of 12 words, post-exemption** (was a provisional 9). The too-little-to-measure HOLD rule stays, Alex's explicit choice. Encoded same session: `LONGEST_RUN_WORD_THRESHOLD` 9→12. `CONTAINMENT_FLOOR` re-examined against both the calibration set and the real validation harness's R1 mechanical-ladder tier — found a genuine, quantified conflict (rescuing 3 calibration items needs floor >0.571; the real R1 tier flags 14/15 cases purely on containment in range [0.412, 0.563], which breaks if the floor moves that high) — held at 0.40 per the standing tie-break rule, with the 3 conflicting items (2 Ravenhill, 1 Prince) named as an accepted residual, not silently resolved. `RESIDUAL_TOO_LITTLE_CUTOFF` untouched, confirmed structurally independent (`classify()`'s residual gate fires first, unconditionally). A real regression was caught and fixed in the same pass: an existing unit test's hand-built verbatim-run string was exactly 11 words, one short of the new line — extended and re-verified. Mutation-tested both directions (reverting to 9 didn't fail the suite, since the fixed test case's run of 13 still clears 9; confirmed genuine dependency by mutating to 14 instead, which produced a real assertion failure) before landing on 12.

**Also surfaced, not yet actioned:** three generator-quality findings from reading real generated passages during the blind pass — "the author" used instead of the teacher's real name (v3's live prompt allows this; v4 already fixed it but is unwired), comma-chained run-on sentences (Alex's own complaint), and vague/insight-free output from thin sources even above the existing word-count floor. All three are required reading for whoever runs the extraction-prompt session that must precede any generation restart — see PLAN.md #46's own entry for full detail. Also stated plainly there: this is a single 24-item blind sitting, with the fatigue/anchoring limits that implies — treat the new threshold as Alex-calibrated, not permanently fixed, and revisit once real generated output exists at backfill scale.

---

## Generator rebuilt for bypass-proof grounded extraction (session state, 2026-07-29/30)

Mixed routing per CLAUDE.md's Session Routing table across five ordered phases — harness for repo-only build work (Phases 1, 2b, 3, 4), plain script path for the one additive schema migration (Phase 2a) and for the final live-proof pass (Phase 5, read-only diagnostic with live LLM calls, zero DB writes). Generation stayed STOPPED throughout every phase; zero propositions were stored anywhere in this session. Five build commits: `8d5b226`, `941c5cf`, `1bbeca7`, `8b9bbea`, `58f93f0`. Full detail: `PLAN.md` #45.8 (new); CLAUDE.md Invariants 10 and 11 rewritten to reflect the new structural state (both fully replaced, not stacked on top, per CLAUDE.md's own eviction rule); live-proof output: gitignored `generator_live_proof_review/phase5_live_proof_2026-07-30.jsonl`.

**What changed, plainly:**
- **Reference control, both directions (Phase 1).** Upstream: `extract_propositions()` now hands the model a closed, mechanically-derived list of references actually present in the source and tells it not to go beyond that list — unconditional, no opt-out, and proven not to change the tuned prompts' fingerprints. Downstream: an UNGROUNDED/UNCERTAIN reference is no longer stripped on sight — the live Layer 3 arbiter gets a real chance to overturn a false flag first (yesterday's evidence: 78.6% overturn rate). A real defect was caught at review and fixed: the arbiter's own parsing didn't handle dotted abbreviations ("1 Cor."), which could have false-stripped a genuine reference before the arbiter ever got to look at it properly.
- **Passage back-links (Phase 2).** New `proposition_chunks` table (migration 074, additive, zero rows) — every future stored proposition will record which chunk(s) of its document it actually came from, honestly (the whole document's chunk set, since extraction never operates on less than that).
- **Permission to produce nothing (Phase 3).** The extraction prompts now say plainly that zero output is correct for thin, non-substantive material — not a failure to paper over. A new mechanical floor (`MIN_SUBSTANTIVE_WORD_COUNT=50`, grounded in the real corpus's observed 61-word minimum) skips the model call entirely on genuinely degenerate input, at zero cost to anything that exists in the corpus today.
- **Provenance made structural, not conventional (Phase 4).** The exact mechanism the deleted `sample_v4_propositions_2026-07-23.py` script used to land NULL-provenance rows is now closed: `store_propositions()` requires a prompt version or refuses outright (`TypeError`, not a silent NULL write), and no longer trusts a caller to supply the fingerprint/model correctly — it derives both itself. Proven against the deleted script's exact call shape, not just asserted.
- **What's still open, named explicitly, not implied fixed:** the license gate and Precept-Austin lockout are still only inside `process_document()` — a caller that skips it, skips them too, same as before this session. Nothing can verify that stored content actually came from a real model call versus being hand-typed with an honest-looking label. The `propositions` table's provenance columns are still nullable at the schema level — enforcement is at the function boundary, not the database.
- **Live proof, storage disabled (Phase 5, ~$0.063 real cost).** Ran the real, unmodified generator against Leonard Ravenhill (aphorist), Derek Prince (expositor), and Vlad Savchuk (spoken transcript), plus a deliberately thin synthetic input, with only the final storage call intercepted by a no-op that recorded what would have been written. Zero errors, zero contract failures. Live arbitration overturned every UNCERTAIN reference it was asked about in this sample. The thin case correctly produced zero output at zero cost. Confirmed after the run: database row counts for all three documents are unchanged — nothing was written, including to the new chunk-link table (still zero rows anywhere in the live database).

**Not yet established:** any of this at the ~429-document long-form Derek Prince backfill scale (this session's one Prince document is representative in style, not in population size); #46's human calibration, which the backfill still needs regardless of how solid this generator rebuild is.

---

## Layer 3 citation verifier — first live run against a real model (session state, 2026-07-29)

Read-only diagnostic per CLAUDE.md's Session Routing table — zero DB writes anywhere in this session, every DB touch a SELECT. Full detail: `docs/audits/layer3_live_run_2026-07-29.md`; per-item verdicts: gitignored `layer3_llm_reading_pass_review/layer3_live_run_2026-07-29.jsonl` (43 lines). Records updated: `PLAN.md` #45.7 (new), corrections inline at #45.6 and #47. Spend: $5.00 session ceiling authorised, actual **~$0.44** (8.8% used).

**The 38-flagged-item figure from yesterday's cost estimate was an undercount — corrected to 42.** Yesterday's Scope A worked from a secondary markdown-table reconstruction that silently dropped 5 genuinely-flagged references (filed under the closeness check's quote-candidate bucket instead of "needs fixing") and included 9 already-fine context references that were never flagged at all. Re-running the current verifier directly against the real original baseline (`reference_fabrication_review/corpus_findings.jsonl`, 72 UNGROUNDED + 6 UNCERTAIN) gives the authoritative count: 30 of 78 now resolve automatically (Layer 1/2 fix), all 6 UNCERTAIN items are structurally blocked from ever reaching Layer 3 by the unrelated dotted-abbreviation parse gap, and **42 are the real Layer-3-reachable pool.**

**Layer 3 run live for the first time ever, all 42 items plus 1 illustrative UNCERTAIN item.** Zero call errors, zero parse failures, zero ambiguous responses. **33 of 42 (78.6%) confirmed genuine engagement** — the model judges the automated `ungrounded` flag was wrong, the teacher did engage the passage (non-WEB/KJV wording, paraphrase, or a form outside Layers 1/2's patterns). **9 of 42 (21.4%) denied** — real remaining candidates.

**Sharp, teacher-specific skew:** Leonard Ravenhill 7/8 denied (87.5% of his flagged items are genuine); Zac Poonen 0/19 denied (his flagged items are essentially all scanner false positives); Vlad Savchuk 2/12 denied.

**A measured reliability caveat, not a blocker:** 2 of 42 items (4.8%) flipped verdict between the shipped boolean-only prompt and a diagnostic variant of the identical call that also asked for a one-line reason — same model, same temperature (0.0), same input. Real prompt-sensitivity, not sampling noise.

**Not yet established:** accuracy on the long-form Derek Prince backfill register (#49) — this run's 42 items are all short-form material from the existing corpus. Full detail and the design implications: the audit doc above.

---

## Citation verifier build session: Layer 1 gap fixed, BOOK_MAP confirmed, Layer 3 cost-estimated (session state, 2026-07-28)

Repo-only multi-step build, harness route (`executor`/`planner-reviewer`)
per CLAUDE.md's Session Routing table — zero DB writes anywhere in the
build, SELECT-only reads used for real-corpus characterization and cost
sampling. Three ordered tasks, three separate commits: `ff74a42`, `4d9b193`,
`fd19bbe`. Full detail lives in the commits themselves and
`docs/audits/layer3_llm_cost_estimate_2026-07-28.md` — this is the
point-in-time pointer, not a duplicate.

**Task 1 — Layer 1's chapter-colon gap, fixed (`ff74a42`).** The documented
gap (PLAN.md #45.6: "Hebrews chapter 10:25" — a "chapter" keyword directly
followed by a colon-form verse, no literal "verse" word — matched none of
Layer 1's four existing patterns) was confirmed real and common against
real corpus text before fixing: 22 documents read directly, 101 documents
corpus-wide via SQL sweep, 38 with live propositions; reproduced live
against real Vlad Savchuk source text. Fixed via one new pattern
(`PATTERN_D`), reusing the existing book/number/gap fragments and the same
`word_or_digit_to_int()` + `_parse_verse_or_range()` re-validation
discipline as every pre-existing pattern — no bypass. Two related shapes
were investigated and deliberately left unfixed, locked in as regression
tests rather than left as assumptions: a "v."/"vs." verse-abbreviation
alias (real corpus-wide, but never found paired with an explicit "chapter"
keyword — every real instance is either a Roman-numeral chapter marker in
disguise or has no structural marker at all) and a bare colon-form
reference relying only on an earlier, non-adjacent chapter mention (no real
instance found that isn't already covered by the existing compact-form
scanner). Layer 2's bookless patterns carry the identical gap, left
unfixed as a flagged follow-up — out of this task's scope. This same
commit is also `scripts/citation_verifier_layers.py`'s first commit — it
and its test suite were built in a prior session, reviewed and approved
then, but never committed until now. Test suite: 75/75 assertions green.

**Task 2 — book-map source, confirmed already-correct, no fix needed
(`4d9b193`).** Checked whether the verifier reads a stale copy of the
book-name map post-`ee267d4` (per the five-map Landmine below) — it
doesn't. `citation_verifier_layers.py`'s `BOOK_MAP` is the same object as
`backend/app/constants.BOOK_MAP` (confirmed by object identity, not just an
import-line read), so it picked up `ee267d4`'s 34 new keys automatically.
Added a regression test proving four of the widened forms (First Samuel, I
Samuel, Second Corinthians, III John) resolve end-to-end through the real
verifier functions, not just `BOOK_MAP` dict membership.

**Task 3 — Layer 3 cost estimate produced, Layer 3 NOT run (`fd19bbe`,
`docs/audits/layer3_llm_cost_estimate_2026-07-28.md`).** Two findings that
correct stale figures rather than just producing a number: (1) re-checking
the 59+5 flagged propositions (79 individual references,
`docs/audits/statement_recheck_closeness_citation_2026-07-28.md`) against
today's fixed Layer 1/2 shows only **38** references genuinely still need
Layer 3, not the stale 64 — real cost **$0.20**. (2) The full-backfill
document count itself was stale: live-queried today at **564**, not 810
(2026-07-14, PLAN.md #17) or 781 (2026-07-24) — both predate the
220-document Bevere deletion (2026-07-25 below), and the 781→564 delta
reconciles almost exactly against that already-logged event. Projected via
three rates re-derived live against the full 2,409-proposition corpus
(propositions/document, reference-bearing rate, Layer 1/2 fail rate): ~364
projected Layer 3 calls, ~$1.95 central estimate (up to ~$5.30
stress-tested). Both scopes land far under the standing $50 ceiling
(CLAUDE.md). Pricing used ($0.59/M input, $0.79/M output,
`llama-3.3-70b-versatile`) confirmed directly from groq.com/pricing this
session, not assumed. Tokenization used `tiktoken` `cl100k_base` as a
disclosed Llama-tokenizer proxy, not exact.

**Not resolved by this session, flagged for Alex:** Layer 3's accuracy is
wiring-proven only — its test suite is 100% mocked, it has never been run
against real Groq output. Whether to run the 38 real Scope-A candidates as
a first, hand-checkable batch before any full-backfill-scale run is a
product/risk decision, not a cost decision — the cost estimate doesn't
resolve it either way.

**Concurrent-session note, not a conflict:** this session's three commits
(20:04–20:25) landed between the "Teacher-card investigation" records
entry below (`0e0a28a`, 20:35) and a separate later run of position-layer
calibration/threshold/backlog commits (`82aec74` through `4a5db2d`,
23:41–23:46) — a different Claude Code session working the same repo in
parallel. No file overlap: that session's work is position-layer
calibration and terminology; this session's is the citation verifier.
Terminology in this entry follows that session's "proposition" (not
"statement") convention, reconciled before committing.

---

## Teacher-card investigation + terminology/position-layer records pass (session state, 2026-07-28)

Read-only investigation, zero code touched, zero DB writes — routes under
CLAUDE.md's Session Routing table as read-only diagnostic (investigation)
plus docs/records-only (this write). Full settled-decision text lives in
PLAN.md (Position-synthesizing layer section, Open Decisions #14–16); not
repeated here beyond a pointer.

**Teacher-card investigation (SP4), confirmed by direct code read, nothing
changed:** the live "Position on this question" field is question-scoped
(the frontend sends the prior turn's raw question text alongside the
`source_id`), synthesized from raw `chunks.content` excerpts — not
`propositions` rows — embedded verbatim into a live Anthropic call in
`backend/app/routers/study.py::get_teacher_card()`, gated by the hardcoded
`TEACHER_POSITION_SIMILARITY_FLOOR = 0.3` (the 0.508-on-topic/0.152-off-topic
scores that justified this constant live only in this file and PLAN.md, not
in code), and regenerated from scratch on every single open — no cache table,
memoization, or SWR/React-Query layer anywhere in the path. This matches
PLAN.md #48's existing description of the leak surface; no correction to
prior records was needed.

**Terminology settled: "proposition" is canonical, "statement" retired as
drift.** The database (`propositions` table) is authoritative. Model-facing
prompt prose deliberately keeps "teaching passage" instead of "proposition"
(RAG-literature meaning fights the 80–150-word voiced target — see Pass 3,
2026-07-23 below) — that naming is correct and unchanged. Swept CLAUDE.md (2
instances) and PLAN.md (23 instances) for "statement" used as a synonym for
the DB concept and corrected to "proposition"; this file corrected the same
way (15 instances) — the 2026-07-28 citation-accuracy entry below no longer
contradicts the rest of this file's own "proposition" usage. Left untouched
throughout: real filenames (`docs/audits/statement_recheck_...`,
`scripts/eligible_statements.py`), "SQL/executable statement" in the code
sense, and passages describing what "proposition" means in the RAG
literature or the writing style permitted by the extraction prompt — none of
those are the drift this decision targets.

**Position lifecycle settled:** positions generate on demand at question
time, not ahead of time; every on-demand position persists once written,
never discarded after serving; an ahead-of-time pass comes later, informed
by real observed questions rather than a pre-invented topic list; permanent
locking is reachable only for a teacher whose corpus is complete. Revisit
trigger for the on-demand posture is unreviewed positions reaching real
users — not cost, not latency.

**Position empty-state design settled (four rules):** one empty message,
always the same shape, corpus thinness never exposed; wording is about the
library ("nothing found here on that topic"), never an assertion that the
teacher never taught it; refuse in the asked-for teacher's own voice, then
separately offer user-initiated crossover to who else addresses the topic —
never automatic; on a near-miss, refuse the question but name what the
teacher does address nearby, staying in his voice — never serve a
hedged/caveated position, since a hedge is still an assertion. Full text in
PLAN.md's Position-synthesizing layer section.

**Next Phase 4 slice identified:** the serving path — positions replacing
the live-synthesis answer flow, plus teacher-card migration off live
source-text synthesis (confirmed still exactly as-is by this session's
investigation above). Not more teachers — that stays mechanical, unscheduled
work.

**Left open, not settled this session** — PLAN.md Open Decisions #14–16:
refresh trigger for a persisted position as evidence grows (leaning
flag-on-growth-with-manual-approval, not decided); whether a rebuilt
position replaces or versions the prior one; the eventual ahead-of-time
topic list, deliberately not started.

---

## Citation-accuracy program consolidated; Phase 4 (position layer) started and decoupled from the backfill (records pass, 2026-07-28)

This entry replaces two prior session-state entries ("Retroactive re-check
run; citation-scanner blind spot found; BOOK_MAP defect fixed and shipped"
and "Scripture-citation fabrication — prevention fix + corpus-wide
detection") that together spanned six sub-sessions across 2026-07-28 and
ended mid-correction. Their substance is folded in here, corrected, not
stacked on top — see PLAN.md's own eviction rule. Full technical detail for
everything below lives in three audit reports, not repeated here:
`docs/audits/statement_recheck_closeness_citation_2026-07-28.md`,
`docs/audits/reference_grounding_dry_run_2026-07-28.md`, and
`docs/audits/position_layer_phase4_build_2026-07-28.md`.

**Where the citation-accuracy work landed, plainly:**
- The retroactive re-check (PLAN.md #47) ran once, 2026-07-28, across all
  2,409 live propositions: 2,067 passed both checks, 59 flagged for citation,
  0 for removal, 5 for manual review, 278 quote-candidates (parked, separate
  track). The closeness-check half is sound. The citation-check half is not
  — the scanner behind it only recognizes compact written citations and is
  blind to spoken forms and to the dominant expository pattern (book named
  once, verse-only citations after). Most of the 59, and most of the
  original 72-reference "known fabrication" baseline that number traces
  back to, are now believed to have been genuine references the scanner
  simply couldn't parse. **Do not cite the 72-item baseline as ground truth
  anywhere in the records — see CLAUDE.md's Landmines section.**
- Genuine citation fabrication now appears RARE. Two cases confirmed to
  date by direct full-source reading, from two independent detection
  efforts: Carter Conlon's Matthew 7:21-23 addition (2026-07-24, found via a
  since-rejected similarity-based misattribution check, see "Claim-to-source
  verification check" below) and Leonard Ravenhill's Philippians 4:8-9
  citation (2026-07-28, a real reference grafted onto the wrong point in the
  same sermon). A third, structurally distinct case — Savchuk's "Devil's
  Voice" invented scriptural-*authority* claim, no actual chapter:verse —
  remains confirmed but undetectable by any reference-grounding check by
  construction.
- **The anti-fabrication filter wired into `extract_propositions()` was
  found harmful before it ever ran against a live row, and its default is
  now reversed.** The original design stripped a scripture reference
  whenever it could NOT be confirmed grounded. A dry run against 20 real
  documents (before this design was ever used on a live row) found 85% of
  what it stripped (33/39) were genuine references wrongly removed, running
  25–67% loss per document on verse-by-verse expository material — Derek
  Prince's own style, the corpus's largest block. No live proposition was
  ever affected (generation stopped 2026-07-25, before this fix landed
  2026-07-28). **Standing decision: a reference may only be removed when the
  source is CONFIRMED NOT to contain it, never on mere failure to confirm.**
  Must not run against the backfill, or against resumed generation at all,
  until re-wired to use the three-layer verifier as its confirming step.
  Full detail: CLAUDE.md Invariant 11.
- **The three-layer citation verifier is repurposed, and (2026-07-28 build
  session) now committed with its chapter-colon gap fixed.** Layer 1
  patterns → Layer 2 document-wide book scope → Layer 3 LLM reading pass —
  `scripts/citation_verifier_layers.py`, committed `ff74a42`. Its primary
  job is no longer retroactive audit of old propositions — it's now the
  recognition/confirming engine the reversed anti-fabrication filter needs
  ahead of the backfill. Retroactive sweep of the existing corpus is
  demoted to a cheap, sampled, later pass. See the 2026-07-28 build-session
  entry above this one for the fix, the BOOK_MAP confirmation, and the
  Layer 3 cost estimate.
- **Book-name recognition fixed in the live product**, commit `ee267d4`
  (not pushed): ordinal ("1st Samuel"), spelled-word ("First Samuel"), and
  Roman-numeral ("I Samuel") forms now recognized at all four live-serving
  sites; a normalization bug that mangled ordinal forms before lookup also
  fixed. Two new open items came out of this fix, neither resolved this
  session — see "Open items carried forward" below.
- **Phase 4 (PLAN.md #48, position layer) is decoupled from the backfill
  and has STARTED**, Alex's explicit approval: teacher-specific positions
  built on the proven-clean proposition set don't depend on backfill volume,
  so #48 no longer waits for #47/#45.6 to fully close. Corpus-wide
  positions remain banned until the backfill (#49) completes — unchanged.
  Foundation shipped this same day, commit `5d6b428` — see the dedicated
  entry directly below.
- **Eligible-input set re-derived live, 2026-07-28: 2,069 pass-both
  propositions, not the report's 2,067.** The +2 is fully explained by the
  BOOK_MAP fix (above) resolving two previously-false citation failures —
  confirmed, not drift (the `uncertain` count is unchanged at 5, matching
  the original report exactly). Re-derivable any time via
  `scripts/eligible_statements.py`.

**Open items carried forward, none silently dropped:**
- **The 59 flagged and 5 manual-review propositions are superseded findings
  from a faulty instrument — formally UNRESOLVED, not live work.** They will
  be re-judged cheaply once the citation verifier lands. Do not mistake
  "the scanner that flagged these is now known unreliable" for "these are
  now known fine" — neither has been re-checked against the corrected
  scanner yet.
- **ASR-garbled book names in source text** (e.g. a Galatians-context
  document where a book name transcribed as "the plumbing") — a real
  corpus-quality problem, disclosed during the 2026-07-28 transcript-phrasing
  survey, out of scope for any check built so far. Own future session.
- **Single-translation ceiling on verse-wording matching** — `verses` stores
  only the WEB translation; a genuinely-quoted verse in KJV/NIV/other
  wording, with no citation string nearby, can misread as ungrounded on the
  wording arm. Recorded limitation, unsolved, affects both the closeness
  check's scripture exemption and the citation-grounding check.
- **Citation verifier remaining work — DONE, 2026-07-28 build session (see
  entry above this one), except the actual Layer 3 run.** Layer 1's
  chapter-colon gap is fixed and committed (`ff74a42`); the verifier was
  confirmed to already read the corrected book map, no fix needed
  (`4d9b193`); Layer 3's LLM reading pass is now cost-sized
  (`docs/audits/layer3_llm_cost_estimate_2026-07-28.md`, both scopes far
  under the $50 ceiling) but **still never run against real output** —
  that real run is Alex's call, not yet scheduled.
- **Prior parked items, still parked, carried forward:** the two
  HistoricalChristianFaith attribution mix-ups (`citation_mode` mismatch on
  307 documents; a C.S. Lewis document marked `public_domain` with a
  doubtful death-year basis — see Open blockers #15/#16 below); the
  Ravenhill listen-through backlog (weak-signal clip/full-sermon pairs and
  the near-Galatians "Cross" documents that need a human listen, not a
  content-match heuristic — see PLAN.md #44); and the harness write-path
  issue (`BASH_WRITE_INDICATORS` still deliberately over-flags benign Bash
  calls as writes — see Known Harness Bugs below).

**New standing rule, added to CLAUDE.md this session:** any LLM run with
meaningful per-item cost across the corpus requires a cost estimate
surfaced to Alex before running, should be designed to run once, and has a
$50 ceiling unless Alex explicitly approves exceeding it.

---

## Position layer foundation shipped — Phase 4 opening session (session state, 2026-07-28)

Build + live database write session (new tables and new rows only — no
existing row anywhere modified, verified by fresh query before and after:
`documents` 3,595→3,595, `propositions` 2,409→2,409, `sources` 73→73). Ran
on the plain/psycopg2 path per CLAUDE.md's Session Routing table, never the
harness. Commit `5d6b428`. Full report:
`docs/audits/position_layer_phase4_build_2026-07-28.md`.

**Shipped:** `positions` + `position_evidence` tables (migration 073,
verified on a fresh connection). `kind` is CHECK-locked to `'teacher'` —
corpus-wide is refused twice, once by application code (`write_position()`
raises before opening a transaction) and once by the DB constraint itself,
per the standing ban until the backfill completes. `prompt_version`/
`prompt_fingerprint`/`model` are `NOT NULL` from row one — an unstamped
position write is impossible at the schema level, unlike `propositions`'
nullable provenance columns. `scripts/positions.py::generate_position_text()`
— the only function that calls the LLM — takes teacher name, topic, and
evidence-proposition content only; no document/chunk access is possible by
its own signature, not by prompt instruction. An evidence-count floor of 5
(provisional, reasoned from real Savchuk data, not a #46-style calibration)
refuses to write a position below it — proven live, not just coded.

**Proven on Vlad Savchuk** — richest eligible coverage (898 propositions),
verified by live query rather than the "likely Ravenhill" (699) assumption
going in. 4 topics attempted: 3 written (deliverance/spiritual warfare,
effective prayer, fasting — full text in the report), 1 correctly refused
(infant baptism and the sacraments — 0 eligible evidence, no LLM call made).
Every evidence proposition ID fresh-verified as both in the eligible
2,069-set and belonging to the correct teacher, for all 45 evidence rows
across the 3 written positions. Actual cost: ~$0.05–0.08 (4 embeddings + 3
Claude Sonnet calls), reported to Alex before running, far under the $50
ceiling.

**Not done, explicitly next:** more teachers (mechanical, not a redesign);
floor calibration once more teachers' output exists to judge against; the
serving-path cutover itself (nothing users see has changed — the live
teacher-card synthesis in `study.py::get_teacher_card()` and the main chat
answer path are both untouched); a review/approval pass on the 3 specific
rows already written (all `status='draft'`, none read or approved by Alex
yet).

---

## Closeness-check track wrapped — routing gap, Phase 2 build, vocabulary exemption (session state, 2026-07-28)

Three back-to-back sessions, 2026-07-26 through 2026-07-28, all in one
continuous chat. Full substantive detail lives in each session's own entry
below, not duplicated here — this is the point-in-time pointer a fresh
session needs before touching any of this again.

**1. Harness routing gap closed (2026-07-26).** `CLAUDE.md` gained a
`## Session Routing` table — the reviewer's own instructions had pointed to
this table since the harness was built, and it never existed. Hard rule
written down: any session that writes to the database runs on the plain
script path, never the harness, no exceptions. See "Harness routing gap
closed" below.

**2. Closeness check (PLAN.md #45) built (2026-07-26).** The paraphrase
wording gate — trigram containment + longest-run secondary signal, scripture/
name/theology exemptions, a floor derived fresh from real corpus material
(`CONTAINMENT_FLOOR=0.40`, `LONGEST_RUN_WORD_THRESHOLD=9`,
`RESIDUAL_TOO_LITTLE_CUTOFF=8`), wired pre-write and inert. See "Closeness
check (PLAN.md #45)" below.

**3. Common-religious-vocabulary exemption added (2026-07-28).** Per Alex's
Phase 2b calibration ruling on a 27-pair sample. Corpus-derived 1,210-phrase
list, dominance-guarded, non-scripture-scoped, wired in safely. **Honest
result, the fact most worth carrying forward: the 27-pair calibration
sample showed zero of Alex's 5 named cases getting a genuine
vocab-exemption-credited pass** — every real outcome traced to something
else (already-passing propositions, genuine near-quote content the gate
correctly still catches, or a WEB-only scripture-translation gap surfacing
in two independent places). Shipped anyway, safe and provisional, per
Alex's explicit call — real validation is #46's job. See
"Common-religious-vocabulary exemption added" below.

**Standing state, all three sessions:**
- Proposition generation remains stopped throughout. Nothing in this whole
  track resumed it.
- The closeness-check gate (scripture + name + theology + vocab exemptions,
  trigram containment + longest-run signals) is fully built and wired, but
  **inert** — `process_document()`'s gating params are never supplied by any
  real caller yet. No live behavior changed anywhere in this track.
- Zero database writes across all three sessions. Every DB touch was
  SELECT-only.
- `TEACHER_POSITION_SIMILARITY_FLOOR` never touched.
- Six commits total, alternating build/records per Rule 7: `26105f4`
  (routing table + gap closure), `1b7168f`/`1a9a403` (closeness-check
  build/records), `33c6d60`/`a7a7bb4` (vocabulary-exemption build/records).
  All pushed to `origin/main`.
- **Real preconditions before the gate is ever turned on:** a transaction-
  ordering gap needing a `shared_ingest.py` fix (flagged, not fixed); #46's
  human calibration must run against full reconstructed documents, not
  windowed excerpts (this track found the excerpts can omit the content
  that actually drives a flag); the WEB-only scripture-translation gap
  (KJV/other-translation quotes can survive both the vocab-list filter and
  the runtime scripture exemption) is now concretely observed, not just
  theoretical.
- Working tree clean as of this entry (one unrelated, pre-existing
  untracked file in `docs/audits/` — a separate corpus-source audit, not
  part of this track).

---

## Common-religious-vocabulary exemption added to the closeness check (session state, 2026-07-28)

Follows directly from Alex's Phase 2b calibration ruling on the prior
session's 27-pair sample: shared Christian vocabulary is not any teacher's
property and must not count as borrowed wording. This session adds that
exemption. Ran on the harness (`executor`/`planner-reviewer`) per
`CLAUDE.md`'s Session Routing table — zero DB writes anywhere in the build.

**What shipped:** a corpus-derived list of 1,210 common religious/theological
phrases (`scripts/data/common_religious_vocab.json`), a new fuzzy-matched
`SENTINEL_VOCAB` exemption category in `scripts/closeness_check.py` (reuses
the existing scripture-quote matcher's anchor+gap-tolerant-extend+density-floor
discipline, factored into a shared `_anchor_extend_density_span` helper —
proven byte-identical to the prior single-purpose code via diffed test
output), wired through both `exempt_for_containment` and `exempt_for_run` in
masking order **scripture → vocab → names → theology** (vocab must run before
the word-level name/theology maskers, or they fragment a vocab phrase's own
anchor words first — proven on the Ravenhill "God the Father, God the Son"
stress case, with a reconstructed counter-example showing the rejected order
genuinely fails). Also wired inert into `scripts/propositions.py`'s
`process_document()` (optional, default-off, byte-identical when omitted —
same pattern as the existing scripture/name params).

**List derivation, in brief:** derived from real corpus source text
(`chunks.content`, 1,419 in-scope documents / 48 teachers, Precept Austin
excluded), not from general knowledge of Christian phrasing. A phrase
qualified only if it appeared in ≥8 documents AND ≥5 distinct teachers
(single-teacher dominance guard: any phrase where one teacher supplied >50%
of occurrences was rejected — confirmed working on real Derek Prince-only
phrases like "the truth of the matter is," 89% Prince, correctly excluded,
and on the one source that bundles 307 real historical authors under one
entity, "in the beginning was the word," 77% share, also correctly excluded).
Of an initial 6,528 frequency-qualifying candidates, two further passes cut
it to 1,210: a generic-English filter (removed non-theological common
collocations) and a scripture-verse exclusion (removed phrases that are
themselves literal Bible quotations, using the same live `verses`-table
lookup the runtime scripture exemption already uses) — both explicitly
Alex-directed, since the ask was specifically religious vocabulary, and
specifically non-scripture (scripture already has its own dedicated,
citation-anchored exemption; this list isn't meant to duplicate that job with
a cruder mechanism).

**Floor re-validated, holds unchanged.** Re-ran the same derivation
methodology from the prior session (50 Savchuk + 15 Ravenhill should-pass, a
mechanical R0/R1/R2 edit ladder + 5 adversarial splices as should-flag) with
the vocab exemption active. `CONTAINMENT_FLOOR=0.40`,
`LONGEST_RUN_WORD_THRESHOLD=9`, `RESIDUAL_TOO_LITTLE_CUTOFF=8` all still
cleanly separate the two sets — no should-flag point flipped to PASS
(no over-masking), no should-pass pair flipped to `HOLD_TOO_LITTLE` (the
residual-shrinkage risk flagged at the start of this build never
materialized). No constants changed.

**Calibration proof — honest result: no positive evidence found that the
exemption fixes what it was built to fix.** Ran all 27 pairs from the prior
session's calibration sample through `classify()` on their full reconstructed
source documents (not the sample markdown's ~440-word excerpts, which are too
narrow a window for this position-independent metric), with and without the
vocab exemption, to isolate its actual contribution. Of Alex's 5 named
cases, **zero show a genuine vocab-exemption-credited pass** — every
outcome traced to something else, verified directly rather than assumed:
- Ravenhill "Secret to Revival" passes, but already passed before this
  session's exemption existed — no credit due.
- Ravenhill "Cry for Revival" and Savchuk "Death with Dignity" correctly
  still flag (the required check that the exemption doesn't gut the gate).
- Kreighbaum "Ministry of God's Word" does **not** pass, genuinely — verified
  that even in the best possible case (every scripture-masking gap in that
  document perfectly fixed), the remaining overlap from Kreighbaum's own
  original commentary sentences alone still clears the flag threshold. This
  is the gate correctly catching real near-verbatim reproduction of his own
  writing, not a bug — but it means this calibration case doesn't demonstrate
  the vocabulary exemption working as intended.
- Prince "Deliverance And Demonology" (the probe/forceps case) flags — but
  not because of probe/forceps. A different, unrelated sentence in the same
  document (a 19-word near-verbatim reproduction of Prince's own commentary,
  sitting next to a 1 Cor 9:26 citation) independently trips the flag.
  Verified this isn't a scripture-exemption failure either — fixing that
  specific gap changes nothing, since the driving words are Prince's own,
  not scripture. The probe/forceps metaphor itself remains genuinely
  uncaught, consistent with the accepted-gap principle below — this specific
  pair just doesn't demonstrate it, because something else in the same
  document also happens to be a near-copy.
- The only 2 of 27 verdict changes anywhere in the whole sample (both
  Ravenhill, QUOTE_CANDIDATE→PASS) are the vocab list accidentally masking
  KJV-worded scripture — the exact out-of-scope behavior this exemption was
  told to avoid, not evidence of it doing its intended job. Real cause: the
  `verses` table stores only the WEB translation, so KJV phrasing (present
  in some real teacher material) survives the scripture-exclusion filter
  that built the vocab list and lands in it by mistake.

**A second, independent instance of the same WEB-only gap was found live in
the runtime scripture exemption itself** (not just the vocab list): Prince's
"as one that beats the air" (1 Cor 9:26, KJV-flavored) doesn't match WEB's
"not beating the air" closely enough to anchor-match — confirmed this
doesn't change any verdict in this sample, but it's the same root limitation
surfacing in two places now, not a new one. A real, separate, minor citation-
detection bug was also found and confirmed (a missing space, e.g.
"4:12For the word," breaks the citation scanner's word-boundary requirement)
— disclosed, not fixed, and confirmed not to change any outcome in this
sample either.

**Methodology finding for #46:** the 27-pair sample's ~440-word excerpts,
while adequate for the original build session's floor derivation, turned out
to be an unreliable stand-in for full-document ground truth on close
reading — `classify()` scores the entire reconstructed document, and this
session found real flag-driving content that sat outside some excerpts'
windows (though, importantly, verified NOT outside Alex's own excerpt for
the Prince case — that content was in what he read; the mismatch was in the
original session's assumption about *why* it flagged, not in what Alex saw).
**#46's human calibration pass should judge from full reconstructed
documents, not excerpts, to avoid this class of surprise.**

**Accepted gap, restated honestly:** the mechanism has no distinctiveness
signal (a corpus-wide rarity/distinctiveness signal was explicitly proposed
and declined by Alex this session) — so a short, distinctive construction a
teacher invented himself, appearing in isolation, produces neither high
containment nor a long run and passes uncaught. Derek Prince's "probe" and
"forceps" medical metaphor (`Deliverance And Demonology`) is the named
worked example of this *kind* of construction — but the specific calibration
pair does not itself demonstrate the gap, since that document also contains
an unrelated near-verbatim reproduction that flags it anyway. Alex accepted
this gap knowingly; it remains open and undesigned-around, by choice.

**Proposition generation remains stopped.** This session builds and measures
only — no generation resumed, no DB writes anywhere, gate stays inert
(nothing currently supplies the params that activate it).

**Standing facts a fresh session should know before doing anything else:**
- Two commits from this session: a build commit (`closeness_check.py`,
  `propositions.py`, `validate_closeness_check.py`,
  `test_closeness_check_unit_proof.py`, `scripts/data/common_religious_vocab.json`,
  `ARCHITECTURE.md`) and this records commit, kept separate per Rule 7.
- No DB writes anywhere in this session, harness or otherwise.
- `TEACHER_POSITION_SIMILARITY_FLOOR` untouched throughout.
- Alex's explicit decision on closing this session: ship the exemption
  inert as built (it's safe and correctly implemented), document the
  calibration gap honestly rather than hold the commit or re-derive a new
  sample — real validation is #46's job, done properly against full
  documents.

---

## Closeness check (PLAN.md #45) — wording gate built, floor derived, wired inert, generation still stopped (session state, 2026-07-26)

Full derivation detail, every distribution, every sub-group, lives in this
session's harness transcript and `scripts/closeness_check.py`'s own docstring
— this is the point-in-time pointer a fresh session needs, not a duplicate.
Ran on the harness (`executor`/`planner-reviewer`) per `CLAUDE.md`'s Session
Routing table's repo-only-multi-step-build row — zero DB writes anywhere in
the build.

**What shipped:** `scripts/closeness_check.py` (trigram-containment +
longest-run secondary signal + scripture/name/theology exemption),
`scripts/validate_closeness_check.py` (the validation harness, reusable),
wired pre-write into `scripts/propositions.py`'s `process_document()` as an
optional, default-OFF gate — PASS proceeds to the normal insert,
QUOTE_CANDIDATE/HOLD_TOO_LITTLE get withheld and written to gitignored
`closeness_review/flagged_propositions.jsonl` with full provenance. Also
new: `scripts/test_closeness_check_unit_proof.py`,
`scripts/test_propositions_closeness_gate.py` (DB-free mock, asserts both
the write path and the divert path), `scripts/demo_closeness_check_phase6.py`.

**Floor derived fresh (not inherited from the honest-empty floor — different
measurement, PLAN.md #48 already said it wouldn't transfer):**
`CONTAINMENT_FLOOR=0.40`, `LONGEST_RUN_WORD_THRESHOLD=9`,
`RESIDUAL_TOO_LITTLE_CUTOFF=8` — derived from ~65 real should-pass pairs (50
Savchuk + 15 Ravenhill, separately) and ~20 should-flag points (a real-source
mechanical edit ladder + 5 adversarial verbatim splices). All three
explicitly provisional, pre-#46 human calibration — not a production line.

**A real bug found and fixed mid-session, with two of its own design
self-corrections along the way:** the scripture exemption originally masked
only the citation ("Exodus 20:5"), not the quoted verse wording that follows
— a rule-compliant scripture quote (explicitly permitted verbatim by the
extraction prompt) was inflating containment as if it were copied teacher
wording. Fixed via a live `verses`-table lookup + fuzzy order-preserving
match with an explicit over-exemption guard (citation-anchored window,
≥4-word anchor, density floor) — caught missing partial-verse quotes once,
then caught over-absorbing stray coincidental words once, both fixed same
session before the floor was finalized. Three residual limitations remain,
disclosed in the module: translation mismatch (only WEB is stored in
`verses`), no-citation-anchor quotes, and untested wide-range citations.

**Two corrections to working assumptions made earlier this same session, not
just additions:**
1. **Real HOLD_TOO_LITTLE cases DO exist in the corpus** — a corpus-wide
   scan of all 2,409 live propositions found 2 (residual 5 and 7 tokens,
   both near-bare scripture citations), correcting the smaller 65-pair
   validation sample's apparent "no real case exists." The end-to-end demo
   therefore shows two real HOLD cases plus one Alex-authorized constructed
   proof case (explicitly labeled as such) — not zero real plus one
   constructed.
2. **`recovery/` is tracked in git, not gitignored** — corrects an
   assumption made mid-session (that it was already handled as local-only
   like the new `closeness_review/` path). `recovery/`'s Bevere-derived
   snapshot files are genuinely in git history today. Relevant to the still-
   open "should `recovery/` be gitignored" question logged earlier in this
   file — anyone reasoning from "recovery/ already handles this" is working
   from a false premise; `closeness_review/` set the opposite (gitignored)
   precedent for a reason (source-derived unlicensed proposition text is a
   worse fit for permanent git history than for the database it came from).

**Proposition generation remains stopped.** This session builds and proves
the gate only — it does not resume generation, and the gate is wired inert
(nothing currently supplies the params that activate it). Next required step
is Alex's own Phase 2b calibration pass (PLAN.md #46) across three writing
styles (aphorist/expositor/spoken-transcript) before any threshold here is
treated as a production line. A transaction-ordering gap (flagged in code,
not fixed) also needs a `shared_ingest.py` change before the gate is ever
activated live.

**Standing facts a fresh session should know before doing anything else:**
- Two commits from this session: a build commit (`closeness_check.py`,
  `validate_closeness_check.py`, `propositions.py` wiring, `.gitignore`, the
  three test/demo scripts, `ARCHITECTURE.md`'s Scripts-table update) and
  this records commit, kept separate per Rule 7.
- No DB writes anywhere in this session, harness or otherwise — every corpus
  read was SELECT-only.
- `TEACHER_POSITION_SIMILARITY_FLOOR` untouched throughout.

---

## Harness routing gap closed — Session Routing table added to CLAUDE.md (session state, 2026-07-26)

Closes the gap the 2026-07-25 linking session carried forward below ("Harness
routing-table gap — carried forward, not resolved"): `planner-reviewer.md`
has instructed the reviewer to read `CLAUDE.md`'s `## Session Routing` table
since the harness was built, and no such table existed. Docs-only session,
no code touched — routes itself under this file's own new **Docs/records-only
→ Plain** row.

**What was added:** `CLAUDE.md`, new `## Session Routing` section, placed
directly after the intro/design-filter paragraph and before `## Invariants`
— matching the reviewer's own stated load order ("Project Overview, Session
Routing, Tech Stack…"). Five session types, each with an objective trigger
condition (not judgment), an assigned path, and — for the one row that
actually uses the harness (repo-only multi-step build) — explicit "also
load"/"skip" guidance so the reviewer's load-order instruction has something
real to read. `planner-reviewer.md` needed no edit: its existing reference
to `## Session Routing` already matches the new section's exact heading.

**Hard rule, now written down for the first time: any session that writes to
the database runs on the plain script path, never the harness, no
exceptions.** Reason on record in the table itself — the harness's write
recorder is real ground truth for what it records, but
`BASH_WRITE_INDICATORS` still deliberately over-flags benign Bash calls as
writes (own future session, not scheduled), and a false-positive write flag
costs more on a genuine DB-write session than on a repo-only one. Revisit
trigger stated explicitly in the table: once that classifier is narrowed
*and* a second clean DB-write harness session is deliberately run and
reviewed — not before, not by default. The 2026-07-25 linking build
(migration 071) going cleanly through the harness does not change this rule;
the table says so directly, so a future session can't read that one success
as license to loosen it.

**Correction to a claim raised mid-session, verified before writing anything
here:** a chat-side draft asserted the 2026-07-18 12-turn write-detection
stall was still unresolved, citing a chat-side session-state document and
"project memory" as agreeing. Neither exists in this repo or in this
project's actual memory store — checked directly, zero hits. What the repo
itself already recorded, correctly, in this file's own "Known Harness Bugs"
section below: that stall was **fixed 2026-07-19, commit `d9ab1cc`**,
proven by `.claude/harness-selftest/test_write_accounting_loop_fix.py`
(loop convergence, a genuine undisclosed write still blocks, a genuine
disclosed write still passes). That entry did not need correcting — it was
already right. The chat-side document making the stale claim is being
corrected on the chat side, not here; this repo was the accurate record
throughout. The real, still-open residual item is narrower than "the stall":
`BASH_WRITE_INDICATORS`' benign-Bash-call over-flagging, which the same
Known Harness Bugs section already flags as its own future, unscheduled
session — that framing carries forward unchanged into the new table's hard
rule above.

**Standing facts a fresh session should know before doing anything else:**
- `CLAUDE.md`'s `## Session Routing` table is now the authoritative routing
  decision for any session type — read it before choosing harness vs. plain
  path, don't re-derive by judgment.
- DB-write prohibition on the harness path stands, unchanged, with the
  revisit trigger stated in the table itself.
- No code changed this session — `CLAUDE.md` + this entry are the only
  changes, committed together as one records-only commit.

---

## Document work-group linking — mechanism built, proven, and bulk-applied (session state, 2026-07-25)

Full substantive detail (every group, every reason, every held-back item, the
judgment call made) lives in `PLAN.md`'s #44 entry — this is the point-in-time
pointer a fresh session needs before touching this corpus again, not a
duplicate of the reasoning.

**Mechanism:** `migrations/071_document_work_groups.sql` — two new tables,
`document_work_groups` and `document_work_group_members`, additive only, no
`ALTER` on `documents`/`propositions`, reversible. Commit `659c7cf`.

**State as of tonight: 32 work-groups, 123 documents linked, zero deletes or
merges on any existing row.**
- Zac Poonen's "Sermon on the Mount" (11 documents — Part 10 was never
  ingested, a real corpus gap, not an error) is linked and was the at-scale
  proof: before, 11 independently-counted documents; after, one group, 102
  combined propositions reachable through it, every document and every
  proposition unchanged.
- One demo pair (Ravenhill "Something is Missing" clip + full sermon, 21
  combined propositions) from the prior session.
- 30 more groups from tonight's bulk apply: 17 standalone Derek Prince
  two-part/chapter series, "The Roman Pilgrimage" (20 parts), "Analysis of
  Hebrews" (21 chapter documents), Zac Poonen's "Sixteen Lessons I Have
  Learnt" (2), Derek Prince's Galatians "five deliverances" teaching as
  **two separate works** (Recording A, 6 documents; Recording B, 5
  documents — deliberately not merged into one), seven Leonard Ravenhill
  clusters (Cost of Discipleship, What Is Your Life, Paul's Passion And
  Preaching, Cry for Revival, A Man Of God, Pure Heart Pure Church,
  Laodicean Church/Sins of Laodicea), and the New Wine Magazine duplicate.

**Re-filing, separate from linking:** "Complete Salvation and How To Receive
It - Part 2" moved from Smith Wigglesworth to Derek Prince — Alex's explicit
ruling, confirmed by the document's own opening text and by Wigglesworth
having no other documents in the corpus. Migration `072`, commit `4d05e04`.
**The two "Complete Salvation" parts are deliberately NOT linked as one work**
— linking waits until the re-filing is settled, per Alex's instruction.

**Explicitly held back this session, none of it linked — still open:**
- All weak-signal Ravenhill pairs flagged for a human listen-through (shared
  illustrations/scripture across genuinely different sermons, not confirmed
  duplicates).
- The three "Cross" documents near the Galatians series (Cross in My Life
  Parts 1–2, The Cross Obscured) — moderate confidence only.
- "Paul's Passion And Preaching - Part 5" — shares the series title, content
  does not overlap the rest of the group.
- The "Pure Heart, Pure Church" weak third candidate ("(Sermon Quote) Is
  Christ Really In You?").
- Both "Complete Salvation" documents (re-filed, not linked).
- The 29 Ravenhill clip/#shorts-titled documents that matched no other
  document's content by this session's detection method — genuinely
  unresolved, not settled as "no parent."

**Two attribution questions surfaced, carried forward, not resolved:**
1. "Time for the True Church to Rise" is a three-speaker recording (Leonard
   Ravenhill, Alan Redpath, Paris Reidhead) attributed entirely to
   Ravenhill's source identity.
2. The Ravenhill clip "(clip) The Miracle of the New Birth" is correctly
   linked by content into the "What Is Your Life" group, but its own title
   is a phrase pulled from partway through that sermon's own text, not drawn
   from any sermon actually called that — worth knowing if clip titles are
   ever surfaced without their parent's context.

**Harness routing-table gap — carried forward, not resolved.**
`planner-reviewer.md` instructs the reviewer to read `CLAUDE.md`'s
`## Session Routing` table to determine session type before anything else —
no such table exists in `CLAUDE.md`. Surfaced twice this week (once by the
planner-reviewer agent itself during the migration-071 review, once when
Alex asked directly whether routing writes through the executor/
planner-reviewer harness was a deliberate call). There is currently no
written rule for when a session counts as a "harness session" — it's decided
by in-context judgment each time, not a documented trigger. Not fixed this
session (housekeeping-only, no code/doc-authoring scope). A future session
should either write that table or decide it isn't needed.

**Standing facts a fresh session should know before doing anything else:**
- Working tree clean as of this entry (one unrelated untracked file
  currently in `docs/audits/` — a separate corpus-source audit, not part of
  this track, reported to Alex directly rather than logged here).
- All linking/re-filing/records commits pushed to `origin/main`, confirmed
  by direct comparison, not assumed.
- No product code changed by any part of this track — only migrations 071/
  072 (schema + one re-filing UPDATE), data (work-group rows), and records
  (`PLAN.md`, this file).

---

## Corpus cleanup, PLAN.md #44 — three audits and two write sessions (session state, 2026-07-25)

Five back-to-back sessions against the propositions/position-layer cleanup (`PLAN.md` #44), all same day. Full substantive detail lives in `PLAN.md`'s #44 entry, not duplicated here — this is the point-in-time pointer plus the facts a fresh session needs before touching this corpus again.

**What's actually done, with commits:**
- Library re-filing: 13 documents attributed to "Christian Classics Ethereal Library" (a distributor, not a person) resolved and re-filed onto their 8 real named authors; one of the 13 (Horace Bushnell's "Christian Nurture") deleted by Alex's explicit doctrinal ruling. Commits `fc9b0b8`, `3f0a957`.
- Two CLF Church documents re-filed onto Doug Kreighbaum (named-teacher material they duplicate). Commit `fb233f7`.
- Records of both sessions above, plus the reversal below, written into `PLAN.md` #44. Commits `e169ba7` (position-layer, unrelated track), `2caa210`.

**What's found but NOT yet acted on:**
- 27 split-work groups (not 23 as previously believed) — candidates only, nothing linked.
- A Ravenhill clip/full-sermon duplication pattern across 66 documents / 44 pairs, live in the product (36 pairs carry propositions on both sides). **Original plan to delete the clip-side propositions was reversed the same day** after a direct measurement found ~70% of clip propositions capture a point their matching full sermon's own propositions never captured. Routed to the split-work linking session instead — nothing about these 66 documents has been touched.
- A New Wine Magazine duplicate (two titles, ~95% the same text) — blocked, not resolved: **no mechanism exists anywhere in this schema to link two documents as one work**, confirmed by a direct schema check. Both copies untouched.
- An Edwards "Religious Affections" / "Works, Volume One" anthology overlap — flagged only, not restructured.
- 4 documents (one Wesley, one Murray, one Brother Lawrence, one more Wesley) carry foreign text glued onto their own ending from a source website's recommendation footer — 3 of the 4 name a different real author than the document's own. Not trimmed.
- Derek Prince's true distinct-sermon count is 429, not his raw 492 — moves his projected post-backfill share from 77.6% to 75.1%. Does not change the concentration picture; that question is closed.

**Standing facts a fresh session should know before doing anything else:**
- **YouTube ingestion has stopped, Alex's decision.** Now also recorded in `CLAUDE.md`'s Landmines.
- **No linked-work mechanism exists yet** — also now in `CLAUDE.md`'s Landmines, since it affects more than just this cleanup.
- Total corpus document count: 3,595 (was 3,596 before today's one deletion).
- Working tree clean, all commits above pushed to `origin/main` as of this entry.

**Reconciliation.** No product code changed across any of today's sessions — only data (source re-filing, one deletion) plus records (`PLAN.md`, this file, `CLAUDE.md`). Full reasoning, all real numbers, and the coverage measurement behind the clip-deletion reversal are in `PLAN.md` #44 — read there before relying on a summary of a summary.

---

## Sidebar polish: New Chat CTA de-golded, footer nav centered (session state, 2026-07-25)

Two small, unrelated frontend-only fixes to `sidebar.tsx` and its footer, both requested directly by Alex, both scoped to exactly what he asked and nothing else.

**New Chat CTA (`sidebar.tsx:175-182`, commit `a5cba16`).** Was the `Button` default variant — solid `--primary` gold, the same accent color used for citations and active-nav states, competing with the chat input for attention. Alex chose (via an explicit A/B question) to keep a bordered "still reads as a button" treatment rather than going fully flat: now `variant="ghost"` + `border border-border text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground` — no fill at rest, hover treatment copied verbatim from the Chat/Discover/Study nav links directly below it so it doesn't introduce a new interaction pattern. `DESIGN.md`'s Extension Rules table updated in the same commit (was documenting the old gold treatment as deliberate — corrected, not stacked on top, per this file's own eviction rule). Verified live via Playwright against the running dev server (port 3000): computed `background-color` confirmed `rgba(0,0,0,0)` at rest → `rgb(15,15,14)` on hover, matching `--sidebar-accent`'s token value exactly; border confirmed `rgb(62,62,56)`, matching `--border`.

**Footer nav centered (`footer-nav.tsx`, commit `3487fa6`).** The "Home | Sources | Beliefs" row was left-aligned instead of centered under the sidebar. One class added — `justify-center` on the nav's flex container. Verified live via Playwright screenshot: row now centers, position (still bottom-anchored) and everything else unchanged.

**Reconciliation.** Two commits, both already pushed to `origin/main`: `a5cba16` (`DESIGN.md` + `sidebar.tsx`), `3487fa6` (`footer-nav.tsx`). No backend/DB/roadmap changes — this entry plus the already-updated `DESIGN.md` are the only records from this session; `PLAN.md` untouched, nothing here changes any open decision or roadmap item.

---

## Position-synthesizing layer architecture recorded — PLAN.md #44–49 (session state, 2026-07-25)

Records-only session, second of the day. No product code touched. Read-only pass confirmed PLAN.md as the durable home (rhemata-status.md is session-state only) and found no contradiction with anything previously recorded. Full content lives in PLAN.md's new "Position-synthesizing layer" track (#44–49), the new Open Decisions #13, Ordering Call G, and the Quote track addendum — not duplicated here. One commit, records only.

---

## Account panel redesign: profile merged into admin modal, deployed and live (session state, 2026-07-25)

Frontend/backend feature session, unrelated to the corpus-quality/deletion work logged below it — the sidebar's bare "Your profile" panel (display name + role text only) is now a full account surface, and it went through two shipped shapes in one session before landing.

**What shipped, in order:**
1. **`deletion_requests` migration + RLS** (migration `068`, commit `4508c79`) — mirrors `contributor_requests`' RLS pattern exactly (own-row read/insert, service-role full access, no anon policy). Verification script hit a real bug before landing: the authenticated-insert RLS check used a synthetic `uuid.uuid4()` for the test user, which fails on the table's real FK to `auth.users(id)` before RLS is ever evaluated — fixed by minting a real user via `admin.generate_link` (same technique `scripts/test_metering.py` already used), not by relaxing the check.
2. **`POST /account/delete-request`, `GET /account/delete-requests`, `POST /account/delete-requests/{id}/resolve`** (`backend/app/routers/account.py`, commit `fce2ee9`) — mirrors `pastors_notes.py`'s existing request/approve patterns. **This is a stub**: it logs a request row, nothing more. No cascading deletion exists. Recorded as a landmine in `CLAUDE.md` and in `ARCHITECTURE.md`'s Admin section so this doesn't get mistaken for real deletion later.
3. **First shape (commits `9ceeb27`, `6a492db`):** a standalone "Your account" `Dialog`, replacing the old settings `Sheet` and the dropdown menu on the sidebar footer button — Identity/Usage/Contributor-status/Account-actions sections, delete-account confirm flow. Deployed, and its `/account/*` dependency verified live end-to-end (`scripts/test_account_delete_request_e2e.py`, run against production after deploy: submit → duplicate-rejected-400 → admin-list → non-admin-403 → resolve → status confirmed, 6/6 checks passed).
4. **`Contributors` tab gained an "Account Deletion Requests" card** (`AdminModal.tsx`, commit `1717b57`) — lists pending requests, "Mark resolved" action. Same session.
5. **Superseded same day, on Alex's direct feedback that the standalone Dialog "looks like slop" and he preferred the admin panel's left-nav shell:** the account Dialog from step 3 was deleted entirely and merged into `AdminModal.tsx` as a new always-visible "Profile" nav item (commit `db6f4d0`). The modal's old admin-only gate (`roleChecked` closing it for non-admins) is gone — it now opens for any authenticated user; the four admin tabs (Corpus/Feedback/Contributors/Notes Queue) render in the same nav only when `role === 'admin'`. Full detail in `ARCHITECTURE.md`'s Admin section.
6. **Profile's content redesigned again** (commit `757ca89`) against a supplied mockup: identity header (avatar-initial circle, name, role badge, email, sign-out anchored right), then Display name / Email / Weekly usage / Delete-account as separate bordered cards. **Two copy claims in the mockup were checked against reality and corrected before shipping, not copied verbatim:** display-name is shown on published pastoral notes only, not "feedback" (checked `pastors_notes.py` — feedback rows carry no display_name anywhere); the mockup's "Verified" email badge was dropped outright — no email-verification concept exists anywhere in this codebase (grepped for `email_confirmed_at`, zero hits); delete-account copy changed from the mockup's "Permanently removes..." to "Sends a request to remove..." to match what the stub (item 2 above) actually does.

**A real bug was caught and fixed via the verification method itself, not by Alex.** A local Playwright screenshot harness (mint a real session for the project's established test account `creative@clf-church.com` via `admin.generate_link`, inject it into `localStorage` under Supabase's `sb-<project-ref>-auth-token` key, screenshot the rendered panel) surfaced `fmtResetDate()` rendering a UTC date-only string in the browser's local timezone — a Monday reset date displayed as Sunday. Fixed by pinning `timeZone: "UTC"` in the formatter; the value is a calendar day, not an instant to localize. Caught before push, not after.

**A pre-existing, unrelated gap surfaced by the same harness, not caused by this session's changes:** local `npm run dev` cannot reach the production API for authenticated calls — `/pastors-notes/me`, `/study/pins`, `/study/teachers`, `/usage` all fail CORS from `http://localhost:3000`. Railway's live `ALLOWED_ORIGINS` does not currently match what `backend/app/.env`'s local copy says (`http://localhost:3000`) — confirmed by reproducing the failure against multiple long-existing endpoints, not just the new ones. **Not fixed this session** — changing production CORS config wasn't in scope and wasn't asked for. Worth knowing before attempting local-against-prod browser verification again: expect to mock the relevant endpoints (as this session's screenshot script did) rather than assume local dev can hit real data.

**What's confirmed vs. not.** Confirmed live and working: the full `/account/*` backend flow (automated E2E, 6/6, against production). Confirmed via typecheck/lint/production-build/Impeccable-detector, all clean, at every commit in this session. **Not independently confirmed by Alex clicking through the live production UI himself** — verification for the final shape rests on this session's own automated checks plus a locally-mocked-data screenshot (real session, real layout, two API responses mocked due to the CORS gap above), which Alex reviewed and approved before the final push. One open judgment call, flagged to Alex but not yet explicitly resolved: where "Become a contributor" lives for `role === 'user'` accounts now that the old flat Contributor-status block is gone — currently a small card that only renders for that role, since the mockup (an admin's own account) didn't address it.

**Reconciliation.** All code commits pushed to `main`, live on Railway (backend) and Vercel (frontend, auto-deploys on push): `4508c79`, `fce2ee9`, `9ceeb27`, `6a492db`, `1717b57`, `fc68820`, `db6f4d0`, `757ca89`. This entry plus `CLAUDE.md` (new landmine bullet), `ARCHITECTURE.md` (Admin section rewrite, routers/tables lists), and `DESIGN.md` (role-badge token entry) committed together as one records-only commit, per this project's own standing convention of separating build commits from docs commits.

---

## Session close: CLAUDE.md Bevere landmine removed, CLF Zoom document deleted (session state, 2026-07-25)

Two small closes, both follow-on from the corpus quality measurement's open next-steps list (below) and this session's own Bevere deletion (directly below this entry).

**`CLAUDE.md`'s Landmines section corrected, not just annotated.** The "John Bevere's 219 documents are attributed by channel name only" bullet is now factually false — the entire Bevere corpus (220 documents, all under that one channel-attribution mechanism) was deleted earlier this same session. Per this file's own eviction rule ("if a decision is superseded, delete it — do not stack a correction on top"), the bullet was removed outright rather than amended to say "resolved."

**CLF Church's "Prophetic Equipping via Zoom" document deleted — the first live use of the single-document delete path** (`delete_document_cascade()`, distinct from the batch path `delete_documents_cascade()` used earlier this session for the 220 Bevere documents). Flagged in the 2026-07-24 corpus quality measurement as zero-teaching-content (102 words, 1 chunk, 0 propositions) — confirmed again this session by reading the live chunk content directly before deleting: the stored text is literally a meeting schedule, two Zoom URLs, and two passcodes, nothing else. Two other, unrelated CLF documents matched the same title search ("Prophetic Equipping with Pastor Paul Kidd & Tom Bedford," real teaching content, 10 chunks; "Prophet School: Prophetic Equipping Outline," a real table of contents, 1 chunk) — both explicitly confirmed NOT the target and confirmed still present after the delete. No recovery snapshot was taken for this one (unlike the Bevere batch): the deleted content had no teaching value to preserve. Verified by fresh re-query: target document and its chunk gone (0/0), both sibling documents still present (1/1 each), total corpus 3,597 → 3,596.

**Corrects two stale "not yet done" markers in the 2026-07-24 corpus quality entry below:** "Alex to read a sample of the best-scoring documents" — done, in a separate chat-side session the same day (15 best-scoring documents read in full). "Delete the CLF Church Zoom-link document" — done, this entry.

**Reconciliation.** No code changed. `CLAUDE.md` + this entry in `rhemata-status.md` + `PLAN.md` (small addendum to #15 noting real, non-drill use of both the single-document and batch delete paths) committed together as one records-only commit.

---

## John Bevere YouTube corpus deleted — 220 documents, first real (non-drill) cull using the proven export/delete tooling (session state, 2026-07-25)

This is the first live, non-drill use of `scripts/export_restore_document.py`, proven across the three prior 2026-07-24 sessions recorded below (single-document round trip, books/feedback SET-NULL collision fix, true multi-document batch). Target: all 220 documents with `author = 'John Bevere'`, all confirmed (this session and the prior 2026-07-24/07-25 attribution-review sessions) to sit under one canonical source_id (`755490fe-cf1d-4a54-bbb4-b67b72afb65f`) and nothing else — matched on author name + source_id, deliberately NOT on the free-text `source_name` column, which is NULL on 208 of 220 and would have silently caught only ~10.

**Why:** decision made outside this session (not re-litigated here) to stop carrying Bevere's YouTube-transcript material and re-source him from his blog instead. Reasons already on record from the 2026-07-24/07-25 diagnostics: a live, unresolved guest-speaker attribution risk (channel-only attribution, at least one confirmed still-live co-hosted document — "...w/ Rick Renner" — that a prior review pattern should have caught and didn't), plus 28 confirmed same-video duplicate-ingestion pairs (56 of the 220 documents) and a general chunk-boundary internal-duplication defect present in 78 of 220 documents (35%) — not concentrated in the duplicate pairs, a general pipeline issue. A structural raw/condensed shape-sort found zero condensed-rewrite documents in this set (0 markdown headings across 214 of 220, the other 6 being stray pipeline-artifact heading lines) — the redundancy in this set is duplicate ingestion, not raw-vs-condensed pairs.

**Staged execution, each phase re-verified live before proceeding, none trusted from the tool's own return value:**
- **Phase 1 (recovery export):** `recovery/bevere_deleted_backup.json` — 220 rows (video URL, title, author, canonical source name, chunk count, proposition count), re-verified against a fresh live count before writing. Total captured: 2,327 chunks, 4 propositions (correction to this file's earlier "zero propositions" note two sessions up — 4 pre-existing `legacy_unknown`-provenance propositions existed on one document, "Don't Be This Christian... — John Bevere"; harmless, now gone with the rest). Additionally, beyond what was asked: a full per-document DB-restorable snapshot (all 9 linked tables) was captured for all 220 via `export_restore_document.py`'s existing `export()`, written to `recovery/bevere_snapshots_2026-07-25/` — **not yet committed, see open question below.**
- **Phase 2 (dry run):** confirmed live — 220 target match, zero name mismatches in either direction, zero Precept Austin overlap, and the exact cascade behavior (`chunks`/`propositions`/`excerpts`/`book_quotes` CASCADE; `books`/`feedback` SET NULL, none present; `background_topics` NO ACTION and `removed_urls` no-FK, both zero for this batch and both handled explicitly by the tool regardless). Baseline captured for later diffing: 3,597 non-Bevere documents, 3,817 total, per-author counts for the 15 largest other sources.
- **Phase 3 (slice of 10):** deleted via `delete_documents_cascade()`, one transaction. Verified by independent fresh re-query, not the tool's own report: Bevere count 220→210, all 10 ids confirmed gone from `documents`, their chunks/propositions/excerpts confirmed at zero, every other author's count (Precept Austin 2,176, Derek Prince 495, and 13 more) matched the pre-delete baseline exactly, total corpus 3,817→3,807.
- **Phase 4 (remaining 210):** deleted via the same tool, one transaction. Verified by independent fresh re-query: Bevere author count now 0, zero documents remain under the canonical Bevere source_id, the source row itself confirmed still present (`755490fe-...`, name "John Bevere", visibility "shown", license_status "unlicensed" — deliberately NOT deleted, left dark for a future blog re-ingest under the same entity), all 220 original target ids confirmed gone, all their chunks/propositions/excerpts confirmed at zero, every other author's count re-matched the original baseline exactly, Precept Austin re-confirmed disjoint and untouched. Total corpus: 3,817 → 3,597 (exactly −220).

**Open question, not resolved this session — needs Alex's call:** the 220 full-content snapshot files written to `recovery/bevere_snapshots_2026-07-25/` contain the complete chunk text and embeddings of unlicensed material. This is the exact tension already logged as unresolved two sessions up ("should `recovery/` be gitignored going forward?") — full source text is a worse fit for permanent git history than for the database it came from, but these 220 files are also the only byte-for-byte restore path that exists now that the live rows are gone (the manifest only has video URLs, sufficient for re-ingest-from-blog but not for an exact restore). Left on local disk, untracked, pending Alex's decision on whether to keep them temporarily, commit them anyway, or delete them now that the re-ingest-from-blog plan is the actual intended path forward.

**Reconciliation.** No code changed this session — only pre-existing, already-proven tooling (`scripts/export_restore_document.py`) was used for every write, via `psycopg2`/`SUPABASE_DB_URL` directly, never the MCP write tools. This entry plus `recovery/bevere_deleted_backup.json` committed together as one records-only commit, separate from any code, per standing instruction.

---

## Corpus quality measurement: two extraction-pipeline bugs found, worst-list is repair not cull (session state, 2026-07-24)

Read-only, countable-signal measurement (no LLM calls) of all 1,641 in-scope documents (every document except Precept Austin, which stays excluded by standing source-level policy) on three independent dimensions — attribution risk, signal density, text integrity — via new tooling: `scripts/score_corpus_quality.py` + `scripts/build_corpus_quality_report.py`, committed as code `fb3fe22`. Nothing was deleted, no visibility changed, no writes to any table. Full report: `docs/audits/corpus_quality_report_2026-07-24.md` / `docs/audits/corpus_quality_scores_2026-07-24.json`, committed as records in this same session once findings were reviewed (held back from the initial commit per this session's own instruction to review before recording).

**Headline finding: the worst-scoring list is dominated by two extraction-pipeline bugs, not weak teaching content — this is a repair job, not a cull.** Of the 40 worst-scoring documents, only 5 are unexplained by a known caveat below; the rest trace to the two bugs plus one recorded methodology limitation.

**Bug 1 — New Wine Magazine extraction leak.** 29 of 33 `magazine_article` documents (the entire ingested New Wine Magazine population) end their stored text with a leaked JSON/markdown code-fence artifact — literally `"\n}\n\`\`\`` or `"\n}` — from the Gemini/Groq extraction pipeline (`scripts/extract_magazine.py`). The artifact sits inside the LAST retrievable chunk of each document, the exact segment most likely to surface in a real answer attributed to a real teacher — a live product defect, not a cosmetic one. **167 raw PDFs sit untouched in `sources/magazine/01_to_extract/`, plus 5 already extracted and 9 already approved but not yet ingested (confirmed live this session, all three folder counts) — all downstream of or including the buggy extraction step.** Fix the pipeline before extracting or ingesting any of them, or they inherit the same defect.

**Bug 2 — CCEL scrape leak.** At least 19 public-domain books end their stored text with a leaked CCEL website artifact — an ebook-store promo footer, or a bare "Index of Scripture References" page-number dump — from `scripts/scrape_ccel.py`/`download_ccel.py`. Not limited to the 13 documents resolving to the literal "Christian Classics Ethereal Library" source: also hits books correctly attributed to their real author — Andrew Murray (×4), E.M. Bounds (×4), Charles G. Finney (×2), John Wesley, Brother Lawrence, R.A. Torrey, An Unknown Christian — all scraped through the same pipeline regardless of which `source_id` they resolved to. Same defect location (last retrievable chunk) and same live-product implication as Bug 1. One more title (E.M. Bounds' *Power Through Prayer*) shows the same bare-trailing-page-number pattern; not separately confirmed as the same root cause.

**One document has zero teaching content.** CLF Church's "Prophetic Equipping via Zoom" (102 words, 1 chunk) is a Zoom meeting link and passcode, nothing else. Flagged for deletion — will be the first live (non-drill) use of the export/restore/delete tooling proven in the two prior 2026-07-24 sessions (`scripts/export_restore_document.py`), not another drill.

**Methodology limit found and recorded, not smoothed over.** The attribution-risk signal's "multi-voice channel" component (source has ≥3 distinct authors and <50% author/source-name match) cannot distinguish a correctly-credited anthology (CCEL, HistoricalChristianFaith, unresolved New Wine articles) from a channel with real uncredited co-speakers. 18 of the 40 worst-scoring documents are flagged only via this signal. **This does NOT resolve the open John Bevere 219-document guest-speaker question logged in the "Claim-to-source verification" entry below — that still needs a per-document read.** This tooling cannot substitute for that.

**A scoring bug was found and fixed in-session, before any result was finalized.** The text-integrity signal's repeated-character-run check initially matched digit runs, firing on HistoricalChristianFaith's internal verse-reference codes (e.g. `revelation 5000001`) as if they were scan garbage, and used a raw count instead of a length-normalized rate, letting multi-million-word documents dominate purely by length. Both fixed (digits excluded from the pattern; rate-per-10k-chars with a length floor) before scoring ran for the numbers actually reported.

**Open next steps:**
- Alex to read a sample of the best-scoring documents to confirm the ranking is trustworthy before acting on it further — **DONE, 2026-07-25** (15 best-scoring documents read in full, separate chat-side session).
- Fix both extraction pipelines (`extract_magazine.py`, `scrape_ccel.py`) before re-running affected documents or ingesting any of the 167+5+9 queued New Wine issues. — still open.
- Delete the CLF Church Zoom-link document — **DONE, 2026-07-25**, see the "Session close" entry above. Turned out not to be the first live (non-drill) use of the restore tooling as this line originally predicted — the 220-document Bevere deletion, same session, beat it to that distinction; this was the first use of the *single-document* delete path specifically.
- Restore tool: batch delete/restore combined with an attachment-bearing document (a document with real `books`/`feedback`/`excerpts` rows) remains unproven together — see the 2026-07-24 restore-tool-hardening entry below and PLAN.md #15. Run a first-ten-out-and-back drill before any real cull day, including the CLF Zoom-document deletion above.
- One real user feedback row exists: `thumbs_down`, question "What is the baptism of the Holy Spirit?", `created_at` 2026-05-23 17:08 UTC, `source_document_id` NULL, no comment (confirmed live this session, full row re-queried). The `feedback` table has no review/resolution column at all — Roadmap #16 (feedback→flag-proposition path) is still unbuilt, so nothing in the schema or code has ever programmatically consumed this row. Whether Alex has read it personally is unknown; not claimed either way here.

**Reconciliation.** Code commit `fb3fe22`: `scripts/score_corpus_quality.py`, `scripts/build_corpus_quality_report.py`. This entry plus `docs/audits/corpus_quality_report_2026-07-24.md` and `docs/audits/corpus_quality_scores_2026-07-24.json` committed as records only, in a separate commit, once findings were reviewed — per this session's own standing instruction to hold records back until then.

---

## Restore-tool hardening: books/feedback collision path and multi-document batch both proven, independently re-verified (session state, 2026-07-24)

Follow-on to the same day's record-level restore drill (below), closing the two gaps that session explicitly left open: the tool had only ever been exercised on a document with rows in 3 of 9 in-scope tables, so the `ON DELETE SET NULL` collision fix (books/feedback rows surviving a delete with a nulled FK) had never actually run live, and no multi-document batch had been tried. No cull work happened — this was hardening the mechanism, same as the prior session.

**Table occupancy, queried live:** of the 9 in-scope tables, `books` (50 rows, 10 with a real `document_id` — all Andrew Murray titles) and `feedback` (1 row, genuinely a real authenticated user's real thumbs-down on "What is the baptism of the Holy Spirit?", `source_document_id` NULL) were the only two worth scrutinizing. **The one real feedback row is genuine user content and was confirmed, by code (the only write path is the real `POST /feedback` endpoint, no seed/test script touches this table), to require protection — and since its FK is permanently NULL, it was also mechanically unreachable by the drill either way.** No real document exists with a populated `feedback` FK, so closing this gap required one new, clearly-marked synthetic row, added with Alex's explicit approval and cleaned up at the end of the session — never a synthetic document or source, to keep the sources table uncontaminated, per Alex's explicit instruction.

**Drill 1 — single document, exercising the SET NULL collision path.** Target: Andrew Murray's "The True Vine" (public_domain/shown, lowest-footprint of the 10 real books-linked documents: 70 chunks, one real `books` row) plus one synthetic `feedback` row inserted for this drill (marker text `'[SYNTHETIC TEST ROW — export/restore drill 2026-07-24 — safe to delete]'`, `anon_id='drill-test-2026-07-24'`). Fingerprint → export → hard gate (snapshot counts matched fresh live counts exactly) → delete → **mandatory mid-drill assertion, keyed by exact primary key, never a table-wide count** (the real feedback row shares the same permanently-NULL-FK state as the synthetic one and must never be mistaken for drill evidence): confirmed both the `books` row and the synthetic `feedback` row survived the delete with their FK genuinely NULL, and separately confirmed the real feedback row was completely untouched → restore → fingerprint → compare: `identical: true`, zero differences. A clean fingerprint alone was again treated as insufficient (same lesson as the prior session): closed by querying the same two rows' `xmin` post-restore — both now carry the exact restore-transaction id, proving the `INSERT ... ON CONFLICT DO UPDATE` branch genuinely fired on the surviving rows rather than being a silent no-op.

**Drill 2 — true multi-document batch, one transaction each way.** Five E.M. Bounds documents (public_domain/shown, chunks-only footprint, unused in any prior drill), deleted together via a new `delete_documents_cascade()` and restored together via a new `restore_many()` — both added to `scripts/export_restore_document.py` this session, reusing all existing per-table logic rather than forking a second copy. Hard gate passed on all 45 cells (5 docs × 9 tables) before deletion; mid-drill assertion confirmed all 45 cells at exactly zero after `delete-batch`; all 5 documents' fingerprints matched exactly after `restore-batch`. Forensic proof the batch genuinely ran as one transaction: every one of the 5 documents' restored `documents` and `chunks` rows — 5 documents' worth, independently — shares one single identical `xmin`, something 5 separate restores could not produce.

**Independence check, not skipped.** Because both drills were run directly by the orchestrating session (via Bash, not through the executor) after repeated report-corruption from a hook this session, a review correctly declined to treat the orchestrator's own report as sufficient proof on its own — the driver that ran the assertions was itself unreviewed. Closed by a second, independent, hook-recorded pass through the executor, re-querying the same persisted `xmin` values and primary-key states fresh: identical numbers confirmed both drills, with no smoothing over any discrepancy (none was found).

**Precision, not overclaim, on one point.** The batch delete's single-transaction atomicity is code-proven (verified in the actual executable statements, not trusted from a docstring) and consistent with everything observed, but was not proven by runtime fault injection — no test forced document 3 of 5 to fail and confirmed documents 1–2 rolled back too. Recorded as a real, narrow, still-open gap rather than folded into "proven."

**A genuinely remaining gap, stated plainly per Alex's instruction: batch + attachment-bearing documents together has never been tested.** Drill 2's batch used chunks-only documents; Drill 1's attachment-bearing document was tested alone. No single run has exercised a multi-document batch where at least one document also carries `books`/`feedback`/`excerpts` rows — the two conditions are proven separately, never combined.

**Cleanup, confirmed not just assumed.** The synthetic `feedback` row was deleted by its exact primary key only (never by matching the marker text or any broader condition, precisely because the real row shares its NULL-FK shape) — confirmed gone by a fresh `COUNT`, real row confirmed unchanged, total `feedback` count back to exactly 1. The Andrew Murray book card's link (`books.document_id`) confirmed correctly re-linked to the restored document, not left null or pointed anywhere else. All drill snapshot files deleted from the working tree, not committed — same reasoning as the prior session (copyrighted source text and embeddings are a worse fit for permanent git history than for the database), leaving only the two pre-existing, unrelated files that were already in `recovery/` before this session.

**Roadmap #15 stays partially satisfied, not done** — this closes the two conditions the prior session's caveat named, but Supabase's own backup/PITR coverage is still undeterminable from this environment, no staging project exists, and whole-project disaster restore remains completely unperformed. See #15 in PLAN.md for the full, current state.

---

## Record-level export/delete/restore proven; Supabase's own backup coverage still unknown; a real schema-drift and a real restore bug both found and fixed in-session (session state, 2026-07-24)

Precondition check for a future corpus cull: can one document and everything attached to it be removed from the live database and restored byte-identical? Read-only audit first, confirmed by Alex, before any build; build reviewed before the live test; the live test itself is the first real deletion this project has ever performed against production as a deliberate, instrumented drill. No cull work happened this session — this was proving the mechanism, not using it.

**Backup coverage: genuinely undeterminable from this environment, not assumed fine.** Daily-backup status, retention window, PITR on/off, and last-backup timestamp all require Supabase's account-level Management API, which needs a personal-access-token-class credential. None exists anywhere checked: `backend/app/.env`, `frontend/.env.local`, shell environment, `~/.supabase/`, `~/.config/supabase/`, macOS keychain — all empty; the Supabase CLI isn't installed. This is the same "no staging project, no backup/PITR automation in-repo" gap this file's Open Decision/Ground Truth section has named since the July diagnostic — now confirmed directly rather than inferred. Getting a real answer needs either the Supabase dashboard checked by hand or a management-API token supplied out-of-band.

**Every table keyed to a document, found by direct schema inspection, not memory:** `chunks.document_id`, `excerpts.document_id`, `propositions.document_id`, `book_quotes.document_id` (all `ON DELETE CASCADE`); `books.document_id` and `feedback.source_document_id` (`ON DELETE SET NULL`); `background_topics.document_id` (`NOT NULL`, `ON DELETE NO ACTION` — deleting a document while a background_topics row still references it raises a foreign-key violation rather than cascading or nulling). **A real gap found:** `removed_urls.document_id` has no FK constraint at all — an ordinary, unenforced UUID column. Its 2 live rows already point at document ids that no longer exist anywhere in `documents`. Nothing in the schema will cascade, null, or warn on this table; any delete/restore/cull logic has to handle it by application logic, not by trusting the database.

**A real, previously-undocumented schema drift found:** `chunks.fts` is defined in `migrations/006_chunks_fts_index.sql` as a true `GENERATED ALWAYS` column, but the live column is actually a plain tsvector, recomputed by a `BEFORE INSERT OR UPDATE` trigger (`trg_chunks_fts` → `chunks_fts_trigger()`) whose own committed migration file (`008_fts_trigger.sql`) even says so in its header comment — yet neither file's trigger/function names match what's actually running live (`chunks_fts_update()`/`chunks_fts_trigger` in the file vs. `chunks_fts_trigger()`/`trg_chunks_fts` live). Most likely explanation: manual hand-patching directly in the Supabase SQL Editor (this project's documented practice for running migrations) that was never back-ported into the committed `.sql` files. Nobody was actively looking for this — it surfaced only because building a restore script forces you to know, precisely, whether an INSERT naming a column will error or silently get overwritten. `propositions.fts` is the opposite case — genuinely `GENERATED ALWAYS`, matching its migration exactly; naming it in an INSERT errors outright. This distinction is now documented in the new scripts' code, not just here.

**A real restore bug found and fixed before the live test ran, not after:** the first version of the restore script did a plain `INSERT` for every table, including `books` and `feedback` — but those two are `ON DELETE SET NULL`, so a delete leaves their rows alive with a nulled foreign key rather than removing them. A plain re-insert of the same original row would have collided with that survivor's primary key and failed the whole restore, for any document that actually has books/feedback rows (the chosen test document has zero of either, so this wouldn't have shown up in the drill at all — it would have looked like a clean pass while being broken for the general case). Fixed by upserting those two tables specifically (`INSERT ... ON CONFLICT (id) DO UPDATE`) so a surviving nulled-FK row gets every column, including the link, reset back to the snapshot's values. Caught and fixed during code review, before any live data was touched.

**The one-document live test: proven, not just claimed.** Test document: Ern Baxter's "Christ's Eternal Lordship" (id `0e84a6ce-d4f2-4796-85ea-fba35059fe9d`) — a low-blast-radius choice (2 documents total under its source), deliberately not Derek Prince/John Bevere/Vlad Savchuk (all under live attribution scrutiny elsewhere in this file). Fingerprinted, exported (12 chunks, 15 propositions, all other 6 tables empty — snapshot counts matched a fresh independent live count before anything was touched), deleted in one transaction, confirmed empty, restored, fingerprinted again: `identical: true`, zero differences, matching per-table down to every embedding vector and the exact NULL-vs-`'legacy_unknown'` distinction in the legacy propositions' provenance columns (only `prompt_version` carries a sentinel string; `prompt_fingerprint`/`model` are true nulls, and stay true nulls after restore, not normalized). **That fingerprint match alone was treated as insufficient proof, on review** — an identical before/after fingerprint is also exactly what "the delete silently never fired" would produce, since a restored row is byte-identical to an untouched one by construction. Closed by a separate, independent check: every one of the 28 restored rows (1 document + 12 chunks + 15 propositions) shares the exact same Postgres transaction id, and that id is newer than the most recent real write anywhere in the corpus in the last 11 days — impossible for a row whose `created_at` claims April/June, unless it had genuinely been deleted and freshly reinserted in one transaction. The restore scripts never use `ON CONFLICT` for documents/chunks/propositions, so a stale surviving row would have hard-failed the insert rather than silently passing.

**Five-document scale check (export only, no deletion):** five Leonard Ravenhill documents (a different, unscrutinized source), picked deterministically by document id. All 45 cells (5 documents × 9 tables) matched a fresh independent live count exactly. Scope is honestly narrower than it might sound: all 5 documents had zero rows in 6 of the 9 tables (excerpts, book_quotes, books, background_topics, feedback, removed_urls), so this proves export fidelity for documents/chunks/propositions at 5×, not that every table's capture path has been exercised with real rows at any scale. The delete-and-restore round trip itself remains proven only at the single-document scale.

**What this does and doesn't close.** Closes: one document's full footprint can be exported, deleted, and restored byte-identical, independent of whatever Supabase's own backup mechanism does or doesn't do. Does NOT close: whether Supabase's automated project-level backup/PITR actually works (still genuinely unknown — no credential to check it from this environment); full-project disaster recovery (no staging project exists to even attempt this against); a corpus-wide bulk driver (five sequential single-document CLI invocations is not the same code path as a real batch tool, and would need its own reconciliation discipline if built).

**Scripts added:** `scripts/export_restore_document.py` (export/restore/delete, one document at a time, transaction-safe, fails closed on any error — no partial completion path) and `scripts/fingerprint_document.py` (deterministic per-table/per-row/per-field content signature, including embeddings, excluding only the three trigger/generated tsvector columns from the load-bearing hash since those are derived from other columns the hash already covers). Both reviewed and their design decisions checked against the live schema before being trusted with real data — including the schema-drift and restore-bug findings above, both caught before touching production.

**Demonstrated, not proven — plainly worded, per Alex's instruction.** The live round trip only exercised a document with zero rows in `books`, `feedback`, `excerpts`, `book_quotes`, and `background_topics`. That means the `ON DELETE SET NULL` collision fix (books/feedback rows surviving a delete with a nulled FK, colliding with a plain restore INSERT) has never actually run live — it's fixed in code review, not proven in practice. Before this tool is used ahead of any bulk removal: run the full round trip on (a) a document that has at least one books/feedback row, and (b) a small multi-document batch with delete+restore together, not just export. Until then this is demonstrated capability, not a proven one. See the matching open item logged in PLAN.md's #15.

**Drill snapshots deleted, not committed, per Alex's instruction (2026-07-24).** The nine files this session wrote under `recovery/` (the one-document fingerprint/snapshot/compare set plus the five Ravenhill export-only snapshots) were deleted from the working tree rather than committed. Reasoning, Alex's own: throwaway test artifacts with no future value, large, and — the load-bearing reason — they contain the full text of copyrighted teaching material (embeddings and chunk content included), and a git repository's history is effectively permanent and travels with every clone, making it a worse home for that content than the database it came from. The two pre-existing, unrelated files already in `recovery/` (`deleted_urls_backup_2026-07-16.json`, `ingest_queue.xlsx.PRE_0a_DELETE_2026-07-16.bak`) were left untouched.

**Open design question, logged not resolved: should `recovery/` be gitignored going forward?** Its current non-ignored status is deliberate — ARCHITECTURE.md states it exists specifically "NOT under `sources/`, since `sources/` is gitignored and would drop [deletion exports]," i.e. the folder's whole point was to survive via git where `sources/` doesn't. That convention predates this session's discovery that a real snapshot from this same tooling can contain full copyrighted source text and embeddings, which is exactly the kind of content this project is otherwise careful never to commit. The tension: gitignoring `recovery/` protects against ever committing that content by accident, but also removes the git-backed durability the folder was originally designed to provide for legitimate deletion-export records. Not resolved this session — flagged for a future decision, not decided here.

---

## Vlad Savchuk guest-speaker review — exact record checked, no separate incident found (session state, 2026-07-24)

Read-only follow-up prompted by a recollection that Savchuk's channel had been checked and came back "less bad than feared." Went through git history, the saved deletion record, and the live ingest tracker specifically to confirm or refute that against what's actually written down, rather than trust the recollection.

**The only check on record is the 2026-07-16 six-channel review** (the same one covering Bevere, recorded above) — no separate Savchuk-specific audit exists before or after it. That review ran against Savchuk's full original set of **143 documents**, not a pre-flagged subset, and removed **17**: **12 confirmed as an actual different person speaking** (several named directly in the saved record — e.g. a "John Ramirez," a "Heather Shod," a "Sarah" — credited in place of Savchuk), plus **5 marked unresolvable** and removed on that basis rather than kept.

**No record of a larger "initial suspicion" that got revised down.** Searched specifically for that narrative — nothing in git history, no wording anywhere near Savchuk's name suggesting a bigger feared number that the actual check corrected. The saved conclusion is a flat, one-pass tally (quoted in full in the earlier session-state entry above), not a two-stage "suspected X, confirmed only Y" story. If the "less bad than feared" impression is accurate, it isn't written down anywhere in this project's history — most likely explanation, unconfirmed: in the same review, Sam Storms lost all 5 of its documents and "Bible Study Podcast" was removed entirely (source and all, no reliable single-host attribution at all) — Savchuk's 17-of-143 (~12%) reads as mild only by comparison to those two, not because anyone recorded expecting worse from him specifically.

**Where it stands now: 126 Savchuk documents remain** (143 originals minus the 17 removed), **117 of them with propositions written, 1,053 propositions total.** That's the post-review survivor set, not unexamined leftovers — confirmed by direct comparison, zero of the 126 match any of the 17 removed URLs.

---

## Claim-to-source verification check: similarity method rejected after corpus-wide test; Bevere attribution risk found (session state, 2026-07-24)

Follow-on from the provenance-stamping work: with no mechanical check ever having verified a stored proposition against its actual source, this session built and tested one. Read-only throughout — nothing in the corpus was written, deleted, or flagged in the database.

**The similarity-based check is REJECTED as a flagging mechanism, not shelved as unfinished — a real result, not a lack of time.** Built two things: comparing a proposition's meaning against the single best-matching passage in its own document, and the same thing compared to its own document's *other* propositions (to correct for different teachers' speaking styles naturally scoring differently in absolute terms). The relative version looked genuinely promising on its first test — the one known real fabrication (Leonard Ravenhill's actual teaching, wrongly attached to a Derek Prince document about demons) scored dramatically lower than every real proposition on that same document. But run across the whole corpus and checked against real reading, not just re-tested on the one case it was built to catch: **at a cutoff loose enough to flag that real fabrication, two separately-confirmed-accurate propositions scored even more extreme than the fabrication did.** No line separates them — a stricter cutoff excludes the good ones only by also excluding the fabrication. Confirmed with real numbers, not a guess: 32 propositions across Derek Prince, Leonard Ravenhill, Zac Poonen, Vlad Savchuk, and Carter Conlon were read in full against their actual source text. 31 were genuinely accurate, faithful paraphrases that simply scored low on this method for reasons unrelated to accuracy (register mismatch, multi-passage synthesis, natural variation). Exactly one was a real, confirmed problem — Carter Conlon's proposition adding a specific chapter-and-verse citation (Matthew 7:21-23) that the speaker alluded to but never stated aloud, a real violation of the extraction prompt's own rule against supplying an unstated reference. **A coarse, whole-document version of this same signal (is this document's overall proposition set unusually disconnected from its own source, as a crude backstop against a whole document being systematically wrong) remains available at effectively zero additional cost, since the underlying numbers are already computed — but it is unbuilt and unvalidated, since no known whole-document failure case currently exists to test it against. Shelved, not built, pending Alex's call on whether it's worth the (small) engineering time for an unproven backstop.**

**What's still worth building: the check that verifies every name, number, and scripture reference in a proposition actually appears in its source.** It's the one thing that caught the real problem in the 32 read above. **But it is blind to the actual demonstrated failure this whole effort exists to catch** — the Ravenhill-into-Prince fabrication contains no checkable names, numbers, or citations at all, just a plausible-sounding claim with nothing to verify against. **No cheap check currently covers that failure class — a real, accurate claim from one named teacher, attached to a different named teacher's document.** This is the open gap. Nothing built this session closes it.

**Separately: a live, currently-uncaught guest-speaker attribution risk found in John Bevere's material, ahead of any backfill decision.** Bevere's 219 sermon documents were attributed to him purely by which YouTube channel published them ("John Bevere TV"), with no per-video speaker verification — recorded in the ingest queue itself as `channel_name → resolved_source`, automatic, no check. This is the exact mechanism that has already caused real, corrected problems elsewhere in this project. The July 16 "0a" review did cover Bevere's material — all 221 documents that existed at the time — but only by reading each document's first two chunks, and removed 2 for a confirmed co-hosted video naming Rick Renner as a joint speaker. **A title and content scan this session found a second, still-live document — "The Antichrist, Nephilim & the State of the Church w/ Rick Renner," 17 chunks, zero propositions yet — that the same review pattern should have caught and didn't.** A close sibling of the video that WAS removed (same guest, same apocalyptic-teaching format, same channel), still sitting in the corpus attributed solely to Bevere. One more candidate ("The Man Who Will Fool The Entire World Is Alive Today") shows dialogue-format language ("that's what I was going to ask you") alongside a Rick Renner citation — genuinely ambiguous from a partial read, not confirmed either way, flagged for a closer look rather than asserted as a problem. Everything else the scan surfaced (assorted "with," "interview," "joining me" hits) was checked and came back benign — Bevere referencing another teacher's work or addressing his live audience, not a co-speaker. **Net finding: the risk is real and at least one live instance of it currently exists in the corpus, unresolved, in the single largest block (219 of 781) of what's still awaiting the eventual propositions backfill.** Neither found document has been touched — no deletions, no changes, per instruction.

**Cost of a more thorough Bevere check, if wanted:** reading each full document (not just its first two chunks) and asking explicitly whether it shows signs of a second speaker, rather than the lighter check the July review used. Same rough shape and cost as the extraction step itself, just for classification instead of writing propositions — cheap in absolute terms (low single-digit dollars, well under an hour) relative to the fact that this is the largest remaining block of backfill material.

---

## Propositions provenance stamping shipped (session state, 2026-07-23)

Follows directly from the same day's backfill-scope diagnostic and fabrication sweep (recorded further below): that sweep found zero contamination in the live corpus, but only by manually searching text and reconstructing prompt history from git, because nothing recorded which prompt version or model produced any given row. This closes that gap going forward.

**What's recorded now.** Every proposition written from this point on carries three new pieces of information: a human-chosen label for which named revision of the extraction instructions was used; a fingerprint — a short digital signature computed automatically from the exact, literal wording of those instructions at the moment of the call, never hand-typed; and which AI model answered the call. **The fingerprint is authoritative whenever it and the label disagree** — deliberately, because the label already proved unreliable within this same session: today's two tuning passes both kept calling themselves "v4" while the actual instruction wording changed twice. A future investigation should trust the fingerprint, not the label, when the two don't match.

**Existing rows.** All 2,413 propositions written before this change now carry an explicit, clearly-named "unknown" marker — deliberately NOT a guess at which version actually produced them, even though today's earlier diagnostic built a reasonably strong circumstantial case for that (git history plus a corpus-wide text search). A guessed value would be worse than an honest blank, because the entire reason this field exists is to be trusted during a future investigation — and a field that sometimes contains a guess can't be trusted blindly. If a real answer is ever needed for a specific pre-existing row, the git-history/text-search method from today's diagnostic is still the way to get it — it's just not stored as a database fact.

**Where this is wired.** Every real way a proposition gets written funnels through exactly one place in the code, so stamping that one place covers the entire live pipeline — the standalone document importer, the magazine importer, the Precept Austin importer, the lexicon importer, the YouTube pipeline, and the HelloAO commentary script (currently a no-op since its sources are public domain, but fully wired and will start writing real, stamped rows automatically the moment that changes). Confirmed by a full-codebase search before building anything — no admin button, API route, or database-level automation was ever found to generate a proposition outside this one path.

**Standing expectation going forward:** any new way of writing propositions — a new ingest script, the eventual full backfill, or any code that calls the underlying storage function directly rather than through the shared entry point — must pass real values for all three fields. A write that skips this silently reopens the exact gap this closed. (This is now also recorded as a standing invariant in `CLAUDE.md`.)

**Today's throwaway 5-teacher sample-test script (used for the three tuning-pass comparisons recorded below) was deleted rather than stamped**, per Alex's instruction — its purpose was already served, and there was no reason to carry it forward as a fifth thing to maintain.

**Honesty note on how this was verified.** Rather than writing any real new proposition content to prove the mechanism works, verification used a synthetic insert-then-immediately-delete cycle through the real storage function, confirmed net-zero row change before and after. One thing worth flagging plainly: the document used for that throwaway test happened to be a Precept Austin document, picked automatically by a query that filtered for "no propositions yet" but didn't think to also exclude Precept Austin by name. Precept Austin is permanently locked out of real propositions by design — bypassing that lock wasn't the point of the test and the real lock (which lives one level up, in the normal write path, not in the raw storage function) was never touched or weakened, and the test row was fully deleted and confirmed gone. But a more careful first pick would have avoided a Precept Austin document entirely, and that's noted here rather than smoothed over.

**Migration:** applied manually by Alex in the Supabase SQL Editor, per this project's standing practice — three new fields added to the table that stores propositions, all optional, so nothing existing was put at risk.

**Open item, NOT addressed by this work — logged so it isn't mistaken for closed:** nothing in this system mechanically verifies that a stored proposition actually matches what its source document says. Today's sweep confirmed one specific, already-known bug (a leaked worked example) did not spread beyond the small test batch where it was first found — it did NOT establish that the corpus is free of other, unrelated fabrication. Worth being precise about why this matters here specifically: the one confirmed failure was real Leonard Ravenhill teaching, wrongly attributed by name to Derek Prince. A future safeguard that only checks "is this teacher's name one who was actually retrieved" would NOT have caught that — the name attached was a real, retrieved teacher's name, just the wrong one. Whatever mechanism eventually gets built to guard against this needs to check that a claim traces back to its OWN attributed teacher's material, not merely that the name belongs to someone in the batch.

---

## v4 propositions prompt — passes 2 & 3 (sentence structure, terminology rename), still NOT a backfill decision (session state, 2026-07-23)

Two more tuning passes on top of the pass-1 checkpoint recorded below, run against the identical 15-document/5-teacher sample (clear-then-write per document each time, so each pass's numbers are a clean apples-to-apples overwrite of the same set — nothing outside it touched, Ravenhill untouched).

**Pass 2 (commit `8f65f1c`) — sentence structure.** Manual review of pass 1's raw output found the likely cause of the short/inconsistent length: propositions were written as one run-on sentence chaining claims with repeated "and that... and that...". Added an explicit 2-4-sentence requirement plus a thin/run-on/well-formed contrast example. Result: grand mean word count barely moved (65.1 words vs pass 1's 62.2), but sentence structure genuinely improved for most documents (avg 2-3 sentences, matching the target). **Found a serious unplanned bug while reviewing pass 2's output: in 4 of the 15 documents (Prince, Deere ×2, Kreighbaum), the model's first proposition was a near-verbatim copy of the prompt's own concrete worked example** ("{Teacher} teaches that prayer matters more than preaching...") with only the speaker's name swapped in — fabricated content wrongly attributed to a real teacher, a direct four-corners violation.

**Pass 3 (commit `5bc4916`) — terminology rename + leakage fix.** Alex's hypothesis: the word "proposition" carries a strong competing RAG-literature meaning (atomic/minimal/indivisible single-fact statement — Chen et al. 2023) that fights the 80-150-word, multi-sentence, voiced target. Renamed all model-facing prose to "teaching passage"/"passage" (the JSON output key `proposition_index` deliberately left untouched — structural, not prose, per instruction). Also fixed pass 2's leakage bug by replacing the concrete worked example with a bracketed structural template that has no real sentence left to copy.

Result, reconciled directly against the DB (one document needed a manual retry — see below): **15 documents, 107 propositions, grand mean 70.7 words** — the best of the three passes, though still under the 80-150 floor. Per-teacher averages: Jack Deere 83.4 (now the strongest teacher, was weakest in pass 1), Doug Kreighbaum 75.9, Charles Simpson 66.9, Derek Prince 66.4, Daniel Kolenda 61.7. **Leakage bug: zero instances across all 15 documents** — confirmed fixed.

**Operational finding, not prompt-quality: one genuine transient failure.** Derek Prince's "Deliverance And Demonology" hit a JSON parse error on the first pass-3 attempt (`Expecting ',' delimiter`) — a Groq generation glitch, not a systematic issue. Because `store_propositions()` only runs on a successful extraction, the failure silently left pass 2's *stale, leak-contaminated* propositions live in the table for that one document, masquerading as current data until caught by re-querying and cross-checking timestamps. A manual retry (same script, same doc) succeeded on the first attempt and produced clean pass-3 output. **This is worth carrying into the eventual full backfill (#17): a failed extraction currently leaves old data in place rather than either blocking or clearing it — fine for a hand-verified sample where the discrepancy gets caught, but worth deciding on purpose for an unattended batch run.**

**New finding pass 3 surfaced: the run-on ban is not universally obeyed.** Two of the 15 documents reverted to full run-on structure despite the explicit ban — Daniel Kolenda's "Cessationism 5" is still built from literal "and that... and that..." chains (the exact banned pattern), and Doug Kreighbaum's "Leadership in the House of God" produces one 100-120-word sentence per passage using different connective tissue ("as seen in... where... and as described in...") to route around the letter of the rule while keeping its run-on spirit. The other 13 of 15 documents show genuine 2-4-sentence structure. **Net read: real improvement, not a full fix — the underlying tendency to chain rather than segment is suppressed most of the time, not eliminated.**

**Voice and specifics — held up across all three passes, no regression from the rename.** Named-speaker attribution stays 100% (zero "the author" across all runs). Concrete names/numbers/citations (David Hume, Benjamin Warfield, Jack Deere's son, Charles Simpson's "seven practical steps") continue to survive paraphrase. Per-teacher voice stays distinct.

**Not decided by this session:** whether v4 proceeds to full backfill (#17), gets a fourth tuning pass, or is discarded. Alex has not yet reviewed raw sample output himself.

---

## v4 propositions prompt — pass 1, 5-teacher sample checkpoint (session state, 2026-07-23)

Ran `scripts/sample_v4_propositions_2026-07-23.py` (commit `07d53ee`) — a throwaway, standalone script, not a change to `propositions.py`/`shared_ingest.py`/`ingest.py` — against 15 documents across 5 teachers currently at zero propositions: **Derek Prince** (3 docs), **Daniel Kolenda** (3), **Jack Deere** (3), **Doug Kreighbaum** (3), **Charles Simpson** (3). Selected specifically for stylistic contrast from each other and from Ravenhill (already validated separately, 766 propositions live). Wrote real rows through the same `extract_propositions()`/`store_propositions()` every ingest script uses — reconciled directly against the DB post-run: 15/15 documents stored, 0 errors, 114 propositions, all 5 sources confirmed to have had zero propositions before this run.

**Named-speaker attribution and specifics-preservation — both hold up.** Zero instances of "the author" across all 114 propositions (grep-confirmed). Concrete names/numbers/scripture citations survive per teacher (e.g. Kolenda naming David Hume and Benjamin Warfield by name and characterizing their actual arguments; Deere's account of his son's death; Simpson's "seven practical steps"). Voice reads as genuinely distinct teacher-to-teacher — Kolenda combative/polemical, Deere testimonial, Kreighbaum textbook-structured, Simpson pastoral/relational, Prince systematic-doctrinal.

**Length target (80-150 words) is NOT reliably met.** Grand mean across all 114 propositions: **~62 words** — below the low end of the stated target. Per-teacher averages: Prince 76, Simpson 65, Kolenda 57, Deere 58, Kreighbaum 55. One single document — Kreighbaum's "Ministry of God's Word: Speaking, Preaching and Teaching" — averaged **40.3 words**, matching the exact pre-retune defect the v4 prompt was built to fix.

**New, narrower framing pattern, not caught by the original bug report.** All 114 propositions use an explicit attributive opener — "{Teacher} teaches/argues/explains/emphasizes/shares/warns/criticizes that..." or "According to {Teacher}..." (grep-confirmed, 0 exceptions). The v4 prompt explicitly permits dropping the attributive frame entirely for direct-voice statements (its own worked example: "Prayer matters more than preaching, because...") — that option was never exercised in this sample. Reads as a smaller, more varied version of the original "the author teaches that" problem, not a full fix of the underlying pattern.

**Not decided by this session:** whether v4 proceeds to full backfill (#17), gets iterated again, or is discarded. Alex has not yet reviewed the raw sample output himself.

---

## Chat input: shine-border/holy-glow removed (session state, 2026-07-23)

Alex asked for the glowing gold border effect on the chat input removed, keeping the normal border. The effect was actually two stacked pieces (`frontend/app/globals.css`): an animated warm-gradient shimmer ring (`.shine-border::before`, ramping in on hover/focus-within) and a separate pulsing box-shadow halo (`holy-glow` keyframes, only while `streaming`). DESIGN.md documented both together as the product's one deliberate "Signature Flourish," so scope was confirmed with Alex before touching anything — **both removed entirely**, not just the streaming pulse, per his choice.

**Changed:** `chat-input.tsx` — dropped the `shine-border`/`streaming` classes from the input container (now plain `rounded-2xl border border-border bg-card`), removed the now-unused `streaming` prop from `ChatInputProps` and the `cn` import. `page.tsx` — dropped `streaming={chatLoading}` at both call sites (empty-state and active-conversation input), since that was its only consumer. `globals.css` — deleted the `.shine-border`/`holy-glow`/`shimmer` rules and keyframes outright (grepped repo-wide first — confirmed zero other usages outside `.next` build cache). `DESIGN.md` — removed the now-inaccurate "Signature Flourish — Shine Border" section describing a feature that no longer exists, rather than leaving stale doc alongside the removal.

**Verified live (Playwright, against the already-running local dev server on port 3000, not restarted):** at the real chat input (`/`, guest empty-state), computed `box-shadow` is `none` and there's no `::before` overlay at rest, on hover, and while focused (typing) — all three states identical: plain `1px solid` `border-border`-colored outline, no shimmer, no pulse. Screenshots at rest and focused confirm visually flat borders. `tsc --noEmit` clean. Pre-existing, unrelated lint findings in `page.tsx` (an unused `UsageRing` import, two `set-state-in-effect` warnings at lines 130/356) and a CORS console error against the production `/study/teachers` endpoint were confirmed via diff to be outside this change's two touched lines — not introduced here.

**Reconciliation.** Four files touched: `frontend/components/rhemata/chat-input.tsx`, `frontend/app/page.tsx`, `frontend/app/globals.css`, `DESIGN.md`. One commit, per instruction.

---

## Landing page footer: Product list now reflects available-now vs coming-soon, standalone Study retired from footer (session state, 2026-07-23)

Resolves open question #3 logged in the "Chat-only beta" session entry further down this file ("The landing page footer's 'Product' link list still lists 'Study'/'Discover' as labels... copy decision, out of scope, per instruction") — that footer copy decision is now made.

**Change, frontend-only, `frontend/app/home/page.tsx` (footer's "Product" `<ul>` only):** "Study" removed as a standalone footer item — permanently, not deferred; the in-chat Study Panel (verse cards, word study, teacher cards, Pastors' Notes) supersedes standalone Study, and no footer link points to a standalone Study route. "Chat" stays available-now, now carries a sub-line ("Study tools built into every conversation") communicating that Bible study tooling lives inside the chat experience, not a separate destination. "Pastors' Notes" stays available-now, grouped directly under Chat, now carries a sub-line ("A small, growing collection") — accurate about the current small note count without overselling or apologizing. "Discover" moved to a visually distinct coming-soon treatment: a non-link `<span>` (no href, not focusable, no hover state), muted color, with a small rounded-full "Coming soon" tag — reuses the same treatment already shipped at `weekly-limit-card.tsx`'s billing-disabled state rather than inventing a new pattern, and matches DESIGN.md's "pills/badges: rounded-md or rounded-full for tags only" rule.

**Explicitly untouched, per instruction:** `NEXT_PUBLIC_FULL_NAV_ENABLED` and all navigation-gating/routing logic; the landing page's `MockSidebar` illustration (still shows Study/Discover, still stale — a separately logged, later design pass, not this one). Chat and Pastors' Notes both still link to `/` — the same pre-existing placeholder href noted (not fixed) in the Chat-only-beta entry further down; out of scope for this copy/markup-only change.

**Verified live, real browser (Playwright, against the local dev server already running on port 3000 — not restarted):** at both 1440×900 and 390×844, the Product list renders exactly three items — Chat (+ sub-line), Pastors' Notes (+ sub-line), Discover (+ "Coming soon" tag) — no "Study" item, confirmed by reading the live DOM, not just the diff. Chat and Pastors' Notes confirmed as real `<a href="/">` elements with a working hover color transition (computed `color` genuinely changed on hover, not just a class name check). Discover confirmed as a `<span>` — zero `<a>` elements inside its `<li>`, not keyboard-focusable (`tabIndex` not ≥0) — so it cannot be clicked or tabbed to. Screenshots taken at both widths confirm no overflow or awkward wrapping.

**Reconciliation.** One file touched: `frontend/app/home/page.tsx` (footer Product list only, confirmed by diff — no other line changed). One commit, bundling this status update with the code change per this session's own instruction — a deliberate exception to the usual separate build/records-commit pattern used elsewhere in this file.

---

## Mobile study panel: swipe-to-close + bottom safe-area, Phases 0-3 (session state, 2026-07-23)

A read-only audit of this surface ran immediately before this session and is not re-litigated here (its findings were treated as current, verified only where a phase called for it). Two independent, narrowly-scoped fixes to the mobile sheet, one commit each.

**Phase 0 confirmed all three pre-build facts directly from the code** (not from the audit's memory of it): the grab handle at `study-panel.tsx` renders only under `{isMobile && (...)}`, structurally unreachable on desktop; the single shared close path (`Root`'s `onOpenChange` → `onClose` prop) was intact; the handle's existing tap-to-close (`PanelPrimitive.Close asChild`) worked as described. No stop triggered.

**Phase 1 (`ee351bb`) — swipe-to-close, deliberately reduced from roadmap #43.** #43's written spec describes drag-to-follow (the sheet tracks the finger) with chat peeking mid-drag underneath. **This is NOT what shipped, and #43 is NOT met as originally written.** What shipped: pointer-event tracking on the grab handle only (not `Content`, not `PanelBody`, not either scrollable region) — a downward release past a 44px threshold (matching this codebase's existing min-touch-target convention, not a new number) calls the exact same `onClose` every other close path already uses. Below threshold, or upward: true no-op — no animation, no snap-back, the sheet never moves. **Reason for the reduction, stated plainly:** the fuller drag-to-follow spec cannot be honestly verified without a physical touchscreen (a still-image drag position can be faked by nudging DOM style in a script; a discrete "did it close or not" outcome from a real dispatched touch sequence cannot), and per the pre-session audit would very likely require either a new gesture-tracking dependency or re-platforming this sheet onto a different drawer library (e.g. `vaul`) to get physics-correct follow behavior — both explicitly out of this session's "no new dependencies" rule. **Whether the remainder of #43 (drag-to-follow, chat-peek) stays open as future work, or the reduced scope shipped here is considered the closing word on #43, is Alex's decision — NOT YET MADE as of this record.** The grab handle itself was not new: it already existed with tap-to-close and a code comment explicitly marking drag as a deferred follow-up (`"drag-to-dismiss is a follow-up (no drag dependency in this project yet)"`) — this session completed that exact follow-up, at the reduced scope above, not a new feature invented from nothing.

**Phase 1's hard constraint held:** `handlePointerDownOutside`, `handleFocusOutside`, and `onCloseAutoFocus` on the shared `Content` element — the mechanisms behind Escape, outside-click, and swap-in-place, all three desktop-reachable — were not touched, confirmed by diff. The gesture handlers live entirely on the mobile-only handle button.

**Phase 1's REAL STOP — desktop regression check — passed with real evidence, not inference.** Re-ran the same real-browser test suite from the prior (geometry v3) session: Escape closes (0 open dialogs after); outside-click closes (0 open dialogs after); swap-in-place shows the same DOM node before/after a second-reference click, zero `data-state` transitions through `"closed"` via a live `MutationObserver` (no close-then-reopen flicker). All three PASS, matching the prior session's own results exactly — no drift.

**Phase 1 mobile self-verify used genuine touch emulation, not mouse events standing in for touch** — Chromium's CDP `Input.dispatchTouchEvent` for real multi-phase touch sequences, `hasTouch: true` browser context. All six checks (a–f) passed: swipe down past threshold closes; a swipe clearly-a-drag but below threshold is a true no-op (dialog bounding box byte-identical before/after, not just "still open"); swipe up does nothing; a tap still closes; dragging to scroll inside BOTH the main row view and the word-study sub-view does not close the sheet (the critical scroll-vs-swipe check, the one this whole gesture design exists to get right); the X button still closes.

**Phase 2 (`eb0ad36`) — bottom safe-area clearance, a deliberate bounded exception to the no-bundling rule, not drift.** Pre-existing, independent of the swipe work: `Content`'s `pt-[env(safe-area-inset-top)]` had no bottom equivalent, and `Content` is `inset-0` (extends to the true viewport bottom), so scrolled-to-end content could sit in the home-indicator strip. Fixed by composing `env(safe-area-inset-bottom)` directly into the padding of both scrollable regions (main row view + word-study sub-view) — not an outer static wrapper, since clearance has to live IN the scrolled region for reaching max-scroll to actually clear the indicator. Both divs are shared, unbranched, with desktop — confirmed by diff that only the className changed — where `env()` naturally resolves to `0` and the computed value degrades to exactly today's `16px`, unchanged.

**Phase 2 verified with genuine notch emulation, not a guessed inset number** — Chromium CDP `Emulation.setSafeAreaInsetsOverride` (`top: 59px, bottom: 34px`, an actual iPhone-shaped inset). Computed `padding-bottom` = `50px` (16px + 34px), confirmed. Scrolled to true max-scroll in the realistic **as-shipped default-open state** (Interlinear open, matching what a fresh panel open actually renders): last content element's bottom edge sits at 707px, well clear of the 810px indicator-zone start. Word-study sub-view behaves identically. Desktop re-confirmed unchanged at exactly 16px. A screenshot confirms real, visible margin below the last accordion before the screen edge.

**NEW FINDING, discovered during Phase 2 verification, NOT fixed this session — pre-existing, unrelated to either Phase 1 or Phase 2's own changes, reported per this project's standing honesty practice rather than smoothed over.** The mobile sheet's scrollable container can grow past the true viewport's fixed bottom edge when enough accordion content is expanded simultaneously — confirmed directly: with only the default Interlinear section open, the container correctly stays within the 844px viewport (`bottom: 844`, exactly at the edge, no overflow). With Commentaries and Pastors' Notes ALSO expanded (even with near-empty mock content), the same container's own `getBoundingClientRect().bottom` grows to `872px` — **28px past the true screen edge**, into space that does not exist on a real device. This is the classic Tailwind flex-overflow trap: a `flex-1 overflow-y-auto` child without `min-h-0` on itself or an ancestor defaults to `min-height: auto`, which can grow to the intrinsic content height and break out of its flex parent's allocated space instead of clipping and internally scrolling. `Content` itself has no `overflow-hidden` to catch this, so when it triggers, content genuinely renders below the visible screen — unreachable, not just improperly padded. **Because this session's padding fix (Phase 2) lives on the same growing container, it does NOT protect against this case** — no amount of internal padding helps once the container itself has broken out of the viewport's true bounds. Confirmed via direct DOM measurement (`getBoundingClientRect()`, CDP-verified notch emulation), not assumed. Out of scope for this session's explicit no-bundling rule (Phase 2 was safe-area padding only, not flex containment) — flagged here as a new, real, unfixed defect for a future session, not silently absorbed into Phase 2's "done" claim.

**HONESTY BAR, unsoftened.** Browser device mode with CDP-dispatched touch events genuinely exercises real touch semantics — multi-phase `touchstart`/`touchmove`/`touchend` sequences, real gesture recognition by the browser engine, not synthetic mouse-event substitutes. **The swipe gesture itself IS meaningfully verified** by this method — this is a materially different and stronger claim than "I read the code and it looks right." Equally plainly: **no physical device was used anywhere in this session.** Bottom safe-area clearance is verified against Chromium's CDP-level safe-area-inset override, which produces a real, correct `env()` value for the CSS engine to resolve against — but it is still emulation, not hardware, and remains unproven on a real notched iPhone, exactly as it was for the two prior mobile-adjacent sessions (chat-only-beta gating, Study Panel geometry v3) that logged the same caveat. Nothing in this session closes that hardware gap; it only adds one more layer of increasingly faithful emulation on top of it.

**Reconciliation.** Files touched, confirmed by `git diff --stat` across both build commits: `frontend/components/rhemata/study-panel.tsx` only. Commits, each confirmed landed by `git show --stat` immediately after committing: `ee351bb` (Phase 1, swipe-to-close), `eb0ad36` (Phase 2, bottom safe-area). This records entry is its own separate commit, after both build commits. **Push state, reported not acted on:** `main` is already 7 commits ahead of `origin/main` before this records commit (`ee351bb`, `eb0ad36`, plus the 5 already-ahead commits from the two prior sessions today — the textarea-focus fix and its own records commit, plus the Study Panel geometry v3 session's three commits) — will be 8 once this commit lands. None of today's work has been pushed yet.

---

## Study Panel geometry v3: nested-in-card, capped reading column (session state, 2026-07-23)

**This is the THIRD geometry for this surface, and it REPLACES the previous one — it is not a refinement of it.** History: floating overlay (`bb5cdc0`, zero layout shift, panel covers the chat) → side-by-side chat-narrowing (`d2c31e1`, panel reflows the chat card via `main`'s padding-right) → **now: nested-inside-card with a capped reading column.** Why the replacement, stated plainly: both earlier versions made the reader pay a cost every time the panel opened — the floating overlay covered content outright, and the chat-narrowing version compressed the reading text to a variable, panel-dependent width. This version spends *reserved margin* instead: the reading column is capped at a fixed width whether or not the panel exists, and the panel takes the slack that was already being left empty. Validated in a static mockup at real laptop width before this session; the exact numbers below came from that mockup and were implemented verbatim, not re-derived.

**Exact geometry shipped:**
- Chat reading column: `max-w-2xl` (672px), centered, `px-4 md:px-12` (~48px desktop gutter) — DESIGN.md's existing reader-content pattern, applied to chat. Desktop only; mobile (`px-4`) unaffected.
- Panel: rendered as a real DOM child inside the chat card (not a portal-to-`document.body` overlay), separated by a single `border-left: 1px solid`. No outer gap, no second rounded corner, no separate shadow — the card's own `rounded-xl`/`border`/`overflow-hidden` clips and unifies both.
- Panel width: `clamp(340px, calc(100% - 720px), 440px)`, `100%` = the card's own inner width.
- Panel background: flat, matches the card (`bg-background`, unchanged token). Section cards inside (Interlinear/Commentaries/Pastors' Notes) keep their existing `bg-popover` treatment — untouched, confirmed by not touching `PanelBody` at all.
- Transition: 300ms, same duration as before, now driving the slot's `width` (0 ↔ the clamp formula) instead of `main`'s `padding-right`.

**The permanent, deliberate tradeoff:** with the panel closed, the chat column no longer fills the available card width — there's now visible empty margin on a wide viewport, which is exactly the space the panel occupies when open. Accepted on purpose; this is what makes the open/closed transition genuinely zero-reflow for the reading column, the whole point of this rebuild.

**How it was built (`f120fff`, `b18fca9` — both local, not yet pushed, see reconciliation at the end):** Phase 1 applied the reading cap to `app/page.tsx`'s message list, empty-state composer wrapper, and `chat-input.tsx`'s own form — all three already shared one measure, kept that way. Phase 2 restructured the chat card into a flex row (chat region | panel slot) and redirected `study-panel.tsx`'s Radix `Portal` to mount into that slot via its `container` prop, instead of the Radix default (`document.body`). This was the key design decision: desktop keeps using **real Radix `Dialog.Content`** — only where its Portal mounts and how `Content` is styled changed — so every primitive-provided behavior (Escape, outside-click dismiss, the swap-in-place suppression, the `Title`/`Description` aria wiring) stayed intact automatically, with zero reimplementation. Mobile's branch (`Root`/default-`Portal`/`Overlay`/`Content`) was not touched at all.

**Phase 0 behaviour list** (carried forward for Phase 3 to verify against): (a) Escape closes the panel — primitive-provided, no override in this file. (b) Outside-click closes it — primitive base (`DismissableLayer`) + a hand-written exception for `data-study-trigger` elements. (c) Second-reference swap-in-place — hybrid: the swap itself is plain app state, but only works because the primitive's default dismiss is suppressed for trigger elements. (d) Focus/keyboard/aria — mostly primitive (`Title`/`Description` auto-wire `aria-labelledby`/`describedby`; `role="dialog"` is automatic), with one hand-written override (`onCloseAutoFocus`, since this panel has no `Trigger` for Radix to restore focus to by default).

**Phase 3 result, per behaviour, with evidence (real headless-browser interaction against the local dev server, `/chat` intercepted with a shape-accurate SSE test double — same established pattern as Phase 2's own verification):**
- **(a) Escape — PASS.** Opened via a real click, pressed Escape, confirmed zero `[role="dialog"][data-state="open"]` elements remained.
- **(b) Outside-click — PASS.** Opened, clicked empty chat-card background (not a trigger), confirmed zero open dialogs afterward.
- **(c) Swap-in-place — PASS, strongest evidence of the three.** Mocked an answer with two distinct verse references. Tagged the actual `Content` DOM node before clicking the second reference, confirmed it was the *exact same node* afterward (no unmount/remount). A live `MutationObserver` on the node's `data-state` attribute recorded **zero transitions** during the swap — it never touched `"closed"`, let alone flickered. Title text correctly moved from one reference to the other in place. This is the exact mechanism that broke twice in production before this session (see the pin-dropdown-closes-panel entry below) — confirmed intact after the restructuring.
- **(d) Aria wiring — PASS.** `role="dialog"` present; `aria-modal` correctly absent (non-modal); `aria-labelledby`/`aria-describedby` both resolve to real, correct live text.
- **(d) Focus restoration — FAIL.** See Open Blocker below.

**Phase 0 self-correction, logged as a correction, not a restatement:** Phase 0 reported that the non-modal desktop panel (`modal={false}`) has "no automatic focus trap." That claim was inferred from reading the prop, not from testing it, and it was **wrong**. Direct testing — 25 real Tab presses — showed focus looping indefinitely within the dialog (Close → Interlinear → Commentaries → Pastors' Notes → Pin → Close → ...), never once escaping. Radix evidently loops Tab navigation within `Content` regardless of `modal`. This is reasoned, not re-verified against the pre-session baseline, to be pre-existing rather than something this session's Portal-container change caused — React effect/focus-scope behavior is a function of the component tree, not where its DOM output is portaled — but that reasoning has not been empirically confirmed the way the textarea-blur bug below was.

**Open Blockers — both real, both confirmed pre-existing, neither caused by this session. Evidence levels differ; not flattened into one claim:**

- **BLOCKER — panel fails to open when the chat textarea has focus. BETA-BLOCKING. FIXED same day, commit `0e2f32c`.** Clicking a verse/teacher reference while the chat textarea is focused silently does nothing — no panel opens, no error. Traced with full event instrumentation: `pointerdown` → `mousedown` → `focusout` (textarea) fire, then **nothing** — no `mouseup`, no `click`, no `focusin` on the reference button. **Real root cause, found by tracing DOM node identity across the click, not by guessing again:** `react-markdown`'s default `<Markdown>` component recreates its whole processor and output from scratch on every render, unconditionally (confirmed directly from its own source via Context7 — `createProcessor()` runs fresh every call, no internal memoization for the sync export). `ChatMessage` was never memoized, so any unrelated ancestor re-render — including `ChatFocusContext`'s `inputFocused` toggling on the textarea's blur — remounted every rendered message's DOM, including the verse/teacher reference `<button>`s nested inside paragraphs. A direct DOM-node-marker check proved this: the button element was **destroyed and replaced** between mousedown and mouseup, so the browser had no valid click gesture left to complete — not a timing race (confirmed by testing 0-200ms artificial delays between mousedown/mouseup, all failed identically). Original hypothesis (blur handler racing the click) was directionally right but incomplete; the actual mechanism is this remount. **Fix:** wrapped `ChatMessage` in `React.memo`, plus `useCallback` on `handleCitationClick` (`page.tsx`) so it stays reference-stable — required for the memo's shallow prop comparison to actually hold. Verified: the delay-matrix repro now succeeds at every delay; the button survives the blur-triggered re-render (direct marker check); the full Phase 3 behavior suite (Escape, outside-click, swap-in-place with `MutationObserver` evidence, aria wiring) re-run clean; the panel geometry regression suite re-run clean, no side effects; citation-click path independently re-verified against the real `Citation` shape. **Confirmed pre-existing via an isolated git worktree** at `a60cc22` before the fix was written — identical repro, identical failure signature, on code neither the beta-nav nor the geometry session touched.
- **BLOCKER — focus restoration on panel close lands on `<body>`, not the trigger. CLOSED as a side effect of the fix above, same commit `0e2f32c` — confirmed, not assumed.** Original hypothesis (`previouslyFocusedRef` capturing the wrong element due to effect-ordering) was reasoned, not proven, per this entry's own original text. Re-ran the exact same focus-restoration test after the `React.memo` fix above: **it now passes** — closing the panel correctly returns focus to the original trigger button. Since the button element is no longer destroyed/recreated mid-interaction, `previouslyFocusedRef` now captures and restores the correct, stable node. The original effect-ordering hypothesis for this specific blocker was not independently re-confirmed as the mechanism — it's reported as fixed on the strength of the before/after test result, not a proven causal chain distinct from the node-replacement fix above.

**HONESTY BAR.** Phase 3 used real browser interaction and live DOM inspection — a materially stronger verification standard than the previous session's (chat-only-beta gating), which relied on `curl` against SSR HTML plus diff review with no real browser at all. Say what was still *not* done, equally plainly: no physical device was used at any point; no screen reader (VoiceOver/NVDA) was run; and the two keyboard findings above (Tab-loop, focus-restoration) were reasoned to be pre-existing but **not** independently re-verified against the pre-session baseline the way the textarea-blur bug was — that specific distinction matters and should not be flattened into "everything here was confirmed against baseline."

**Reconciliation.** Files touched, confirmed by `git diff --stat` across both build commits: `frontend/app/page.tsx`, `frontend/components/rhemata/chat-input.tsx`, `frontend/components/rhemata/study-panel.tsx`. Commits, each confirmed landed by `git show --stat` immediately after committing: `f120fff` (Phase 1, reading-width cap), `b18fca9` (Phase 2, nest panel inside card). No Phase 3 commit — verification only, no code changed. This records update is commit-separate from both build commits, per the session's own rule. **Push state, reported not acted on:** `main` is 2 commits ahead of `origin/main` (`f120fff`, `b18fca9`, plus this records commit once made) — none of this session's work has been pushed. The prior session's chat-only-beta commits (`b531215` through `893bf0b`) **were** pushed before this session began — this work was built on top of pushed, not unverified-and-unpushed, prior work.

---

## Chat-only beta: gate Study/Discover navigation, Phases 0-5 (session state, 2026-07-23)

Ships a chat-only beta: Study and Discover become unreachable from the UI on every platform, behind one reversible flag. Routes/pages/components/data untouched — only the ways in were removed. Two prior read-only audits (mobile drawer clipping bug, then entry-point mapping) ran earlier this session and are not re-litigated here; this is the build.

**The switch — `NEXT_PUBLIC_FULL_NAV_ENABLED`, `frontend/lib/chat-only-beta-flag.ts`.** `isFullNavEnabled()` returns `process.env.NEXT_PUBLIC_FULL_NAV_ENABLED === "true"` — **defaults to the beta (hidden) state when unset**, inverse of `study-panel-flag.ts`'s convention, so production ships correctly with zero env change. Set the var to `"true"` to restore full navigation exactly as it was.

**Phase 0 (read-only) found real risk and stopped the session, as designed.** Grepped the whole frontend for `env(safe-area-inset-top)`/`.pt-safe`: zero matches anywhere — nothing in this codebase had ever compensated for a top inset. Four elements sit flush at the true device top with no such compensation: the landing page's `fixed top-0` nav (`app/home/page.tsx`), the chat page's floating circular drawer-open button (`app/page.tsx`, the *only* way to open the drawer once the tab bar is gone), the study panel's mobile close control (`study-panel.tsx`), and the mobile drawer's wordmark/close row (`sidebar.tsx`, already a non-safe-area-aware fixed 24px). Session halted per its own contract — one designated stop — rather than shipping `viewport-fit=cover` with this unreviewed. Alex reviewed and chose to fold the fix into Phase 4 rather than defer the switch: deferring would have meant Phases 2-3's new bottom clearance silently resolves to zero on physical devices (no `viewport-fit=cover` → `env()` always falls back to `0px`), leaving the original drawer-clipping bug from the first audit **still unfixed** in production. Folding it in was the only path that actually closes that bug this session.

**Phase 1 (`b531215`) — the flag + all six entry points, one commit.** Gated: `mobile-tab-bar.tsx`'s Study and Discover tabs (Chat tab stays, via a `requiresFullNav` filter); the *entire* desktop sidebar nav block in `sidebar.tsx` (`hidden md:block`, all three links including Chat — with Study/Discover gone there's nowhere else to navigate to, so a single always-active Chat link is dead weight; flag-on restores all three unchanged); the landing page's "Study" nav-bar link and "Explore Study →" CTA (`app/home/page.tsx`). `isDiscover` checked and left alone — still referenced inside the (flag-on-preserved) Discover link, never became genuinely unused. Verified: default state confirmed live via `curl` against the already-running dev server on port 3000 (all six doors absent from rendered HTML); flag-on state confirmed by diffing every preserved branch against pre-edit `git show` — byte-identical, wrapped not altered.

**Phase 2 (`3194966`) — gate the whole tab bar, fix its dead spacing.** `MobileTabBar` now returns `null` outright in beta state (Phase 1 alone would have left a Chat-only single-tab bar). Chat page's bottom padding (`app/page.tsx`) no longer reserves 56px for a bar that isn't there — beta state uses `pb-safe`; flag-on is byte-identical to today's `inputFocused ? pb-0 : pb-14` toggle. `useChatFocus` itself untouched, per instruction — the chat page still reads `inputFocused`, just only in the flag-on branch now. Verified live via curl: default state's chat `<main>` carries `pb-safe`, not `pb-14`/`pb-0`.

**Phase 3 (`d1a0be2`) — drawer footer clearance, unconditional.** This is the fix for the bug the first audit found: the account row / sign-in button had zero bottom offset in *either* flag state. New mobile-scoped CSS (`.pb-drawer-footer-safe`, `.pb-drawer-footer-safe-tabbar`, both inside `@media (max-width: 767px)` — matching `use-mobile.ts`'s own breakpoint) composes the tab bar's existing 56px with `env(safe-area-inset-bottom)` rather than guessing a new number. Had to be media-query-scoped, not just unlayered like the existing `.pb-safe`: this footer div is shared markup between the desktop aside and the mobile drawer, and per this codebase's own documented CSS fact (see the iOS-input-zoom-fix comment already in `globals.css`) unlayered rules beat Tailwind utilities *unconditionally*, regardless of media query — without the 767px wrapper this would have shrunk the **desktop** sidebar's `pb-4` too, an unreviewed visual change nobody asked for. Verified live: default state's footer div carries `pb-drawer-footer-safe` (confirmed via curl, both the desktop-aside and mobile-aside render paths). Signed-in vs. signed-out not independently live-tested — same div/class applies to both by construction (`isLoggedIn` only swaps the children, never the wrapper's className), and this session had no backend to authenticate against.

**Phase 4 (`eebbf32`) — `viewport-fit: "cover"` + all four Phase 0 fixes, one commit.** Landing nav: `h-14` became the *content* box via `pt-[env(safe-area-inset-top)]` plus a matching height increase, so the logo/links/CTA sit at today's exact visual position — only the translucent background now extends up under the notch. Floating menu button: `top-3` → `top-[calc(0.75rem+env(safe-area-inset-top))]`, same reasoning. Study panel close control: `pt-[env(safe-area-inset-top)]` added to the mobile-only branch of its className (desktop's floating card, which never touches the top edge, is untouched). Drawer top block: `pt-6` → `pt-[max(1.5rem,env(safe-area-inset-top))]` — **not additive**, per instruction — so it's pixel-identical to today wherever the real inset is ≤24px, and only grows on devices where 24px genuinely wasn't enough. All four degrade to their exact current value when the inset resolves to `0` (desktop, non-notched phones) **by construction of the CSS**, not by assumption. Verified live via curl: the viewport meta tag now reads `viewport-fit=cover`; all four elements' new classes/styles render exactly as written; Phases 2-3's classes re-confirmed still present and unbroken now that insets are live.

**Standalone Study vs. Discover — different lifespans, one shared switch, logged as ARRIVED not decided.** This session's framing (Study hidden because the in-chat panel now supersedes it; Discover hidden because it's simply unfinished) is the first real arrival of the long-flagged "does standalone Study survive" founder checkpoint referenced in this file's Study Panel history. Nothing was decided about Study's page ever being deleted — it stays live, fully functional, reachable by direct URL/bookmark, its `isStudy`-gated Saved Words sidebar content untouched — this session only removed the navigational doors, per the explicit "hidden not deleted" brief. Whether standalone Study is ever formally retired is a separate, future decision.

**Open, logged, deliberately NOT done this session (per explicit scope lock):**
- Dead static `pb-24` bottom-padding reservations on `app/study/page.tsx`, `app/library/page.tsx` (×2), `app/library/authors/page.tsx` — these pages are nav-unreachable in beta, so a stale bar-height gap on them was accepted rather than fixed.
- `useChatFocus`'s `inputFocused` value is now read by only one real consumer (the chat page's flag-on padding branch) instead of two — the tab bar's own use of it disappeared with the bar. Provider, hook, and `chat-input.tsx`'s focus/blur handlers all untouched, exactly as instructed.
- The landing page's `MockSidebar` illustration (`app/home/page.tsx`) still visually shows Discover/Study as mock nav items — cosmetic only, contradicts the real product now, logged as a future design pass.
- The landing page footer's "Product" link list still lists "Study"/"Discover" as labels (though both already pointed at `/` pre-session, a separate pre-existing issue) — copy decision, out of scope, per instruction.

**HONESTY BAR — stated plainly, not softened.** No physical device was used this session, and no real browser (mobile or desktop emulation, DevTools, Playwright) was launched either — a second `next dev` instance for this project directory is blocked by Next's own single-instance-per-directory dev lock, and the alternative (restarting Alex's own already-running dev server with a different env var) risked disrupting a session he might have had open, so it wasn't done. Every "live" verification this session claims is `curl` against the SSR HTML of that already-running dev server (default/beta flag state only) plus `git diff` review confirming flag-on branches are byte-identical to pre-edit code. `env(safe-area-inset-*)` cannot be exercised this way at all — it is a real-device/real-Safari runtime value that curl, SSR, and even Chrome DevTools' device-toolbar emulation cannot produce; only genuine iOS Safari hardware can. **Concretely unproven and owed:** whether the drawer footer actually clears the home indicator on a real iPhone (Phase 3's actual fix target); whether all four Phase 4 elements actually render at pixel parity with today on a real notched/Dynamic-Island device; whether the mobile tab bar's absence in beta state looks correct in a real mobile viewport (untestable by curl regardless of my changes, since `useIsMobile()` was already client-hydration-gated before this session and is unmodified). This is the same class of gap this file's own prior sessions have hit before (see the pin-dropdown bug above, where local-dev/isolated verification passed while the real bug persisted) — flagging it here rather than letting a curl-clean result read as more proof than it is.

**Reconciliation.** All 8 touched files, confirmed by `git diff --stat` across all 4 build commits: `frontend/lib/chat-only-beta-flag.ts` (new), `frontend/components/rhemata/sidebar.tsx`, `frontend/components/rhemata/mobile-tab-bar.tsx`, `frontend/components/rhemata/study-panel.tsx`, `frontend/app/home/page.tsx`, `frontend/app/page.tsx`, `frontend/app/layout.tsx`, `frontend/app/globals.css`. All six Phase-1-listed entry points confirmed closed (see Phase 1 above). Explicit DO-NOT-TOUCH list from the brief — library breadcrumbs, the admin edit redirect, the landing footer Product list, `MockSidebar`, the study/library `pb-24` reservations, `useChatFocus`'s own chain — confirmed untouched, none appear in the 8-file diff. Working tree clean after each commit (`git status --short`, empty every time). Commits, in order, each confirmed landed by `git show --stat` immediately after committing: `b531215` (Phase 1), `3194966` (Phase 2), `d1a0be2` (Phase 3), `eebbf32` (Phase 4). This records update is its own separate commit, after all four build commits, per the session's own rule.

---

## Study Panel refinement v2 — Phases 0-5 (session state, 2026-07-22)

Five fully-specified UX refinements, executed as six numbered phases (0 = read-only audit, 1-5 = build, each its own commit with a live-check stop). **All commits through the records commit (`fbd6c56`) are on `origin/main`** — Phases 4-5 (`23a845d`, `f1ee036`) went up in the same push as the records commit itself.

**Phase 0 audit — the fe310e2 discrepancy, resolved by explanation, not a bug fix.** Alex's live screen showed a split-view reflow (sidebar disappearing, chat narrowing) despite records saying "floating overlay" shipped 2026-07-21 (`fe310e2`). Direct code read found both things were true at once: `fe310e2` genuinely gave the panel `Content` element floating-card CSS (`inset-y-2 right-2 rounded-xl`, no scrim) — but `app/page.tsx` still actively collapsed the sidebar (`collapsed={studyPanelOpen}`) and reserved chat padding-right sized to the panel's width, **by design** — the commit's own message states it grew that reservation "so the chat card actually resizes to 'about two-thirds' per spec." Not half-landed, not a regression: `fe310e2` fully shipped what it intended (a floating-*styled* card that still reflows layout), satisfying an older "chat keeps two-thirds" spec goal that this session's Phase 1 set out to supersede.

**Also re-checked and found already-correct, no bug:** the swap-in-place mechanism (shell never unmounts/re-slides on a target change, only content resets) was flagged going into this session as a possible "recorded shell re-slide" regression to fix. Direct code read of `fe310e2` and this file's own prior entry (below) found neither ever described shell re-sliding — `fe310e2`'s `handlePointerDownOutside` suppression of Radix's dismiss-on-outside-click for `data-study-trigger` elements was *always* genuine swap-in-place from the moment it shipped, and this file's existing "Reset-on-swap" note (below) already correctly described content-only reset (`key`-forced remount of the inner content div), not shell remounting. **Correction to the record is: there was nothing to correct here** — stated plainly rather than inventing a fix for a premise that didn't hold up.

**Phase 1 → live design reversal (both pushed, both real commits, not a false start):**
- Built as specified: a true floating overlay, zero layout shift ever (`bb5cdc0`) — sidebar's `collapsed` prop removed entirely, `main` permanently `md:ml-64`, panel background switched to `bg-sidebar`, desktop slide 300ms→200ms.
- Alex reviewed live on `rhemata.app` and disliked it. New direction, decided live: sidebar still never collapses, but the chat card narrows via `padding-right` (not a true overlay) so the two read as side-by-side — reverses Phase 1's own "zero layout shift" acceptance criterion, by design (`d2c31e1`). Panel background reverted to `bg-background` (matches the chat card it now sits beside, not the sidebar); slide duration reverted to 300ms (matches `main`'s transition timing so both motions read as one).
- **Net effect for anyone reading Phase 1's original spec text later: its "true overlay" geometry decision is superseded by `d2c31e1`. Its "sidebar never collapses" piece stands.**

**Phase 2 (`c3659cd`, pushed) — Interlinear-open default state.** Dismiss-anywhere, sidebar-click-closes-and-navigates-in-one-click, and Escape-to-close all turned out to already be correct (Radix non-modal defaults, unoverridden) — zero code changed for those. The one real gap: `fe310e2`'s swap-reset effect closed Interlinear on every fresh open and swap; flipped to open by default (Commentaries/Pastors' Notes still default closed, via the existing `key`-remount). Also fixed both `interlinearOpen`'s and its `page.tsx` mirror's initial `useState` default to `true`, closing a first-open flash window.

**Phase 3 (`a60cc22`, pushed) — fixed width, Interlinear wraps.** Panel width is now permanently `w-[33vw] min-w-[380px] max-w-[480px]` — the old 50vw Interlinear-open expansion is gone, along with all the plumbing (`interlinearWide`, the external `onInterlinearOpenChange` callback chain) that existed only to mirror it into `page.tsx`'s reservation. `InterlinearBlocks` switched from `overflow-x-auto` to `flex-wrap` (both the loading skeleton and the real token row) — applied universally, not desktop-gated, since it's shared with the standalone `/study` page and is a strict improvement on any width. STEPBible CC BY attribution line untouched.

**Phase 4 (`23a845d`) — section cards.** Interlinear/Commentaries/Pastors' Notes are now distinct `bg-popover` cards (`rounded-lg`, bordered, `space-y-3` gaps) instead of a flat `border-b` divider stack. `bg-popover` was chosen over `bg-card` specifically because DESIGN.md documents `--card` as deliberately flat/identical to `--background` ("no color elevation") — it would have produced zero visible separation; `--popover` is DESIGN.md's one token that's a genuinely lighter "lifted surface," already paired with `text-popover-foreground` by `DropdownMenuContent` elsewhere in this codebase. Visual restyle only — confirmed `CommentaryAccordionRow` (nested per-excerpt expand inside Commentaries results) is a separate implementation that doesn't import this component.

**Phase 5 (`f1ee036`) — pin icon family.** The pinned-verses collection trigger (top-bar dropdown) changed from a `Bookmark` glyph to the same outline `Pin` icon as the panel's own header pin-this action, plus a live count badge hidden at 0. Went straight to the badge option (no fallback needed) since Phase 0 confirmed `pins.length` was already read at the trigger's render site for its tooltip — zero new data plumbing. Badge styling (`bg-primary` pill, `h-4 min-w-4`, `text-[10px]`) matches `AdminModal.tsx`'s existing pending-count badge exactly, rather than inventing new values. The standalone `/study` page's own, unrelated `Bookmark` usage (a "save word study" feature) was confirmed out of scope and left untouched.

**Mobile: untouched and deliberately out of scope this entire track**, per every phase's own instruction — tracked separately as PLAN.md #43 (SP5). Nothing here should be read as mobile progress.

**Verification method and its real limits, stated plainly:** every phase was `tsc --noEmit`-clean and diff-reviewed before commit. Beyond that, this session's own verification was a local-dev Playwright smoke test confirming only the closed-panel baseline (sidebar at its fixed `x:0`/256px position, `main`'s margin/padding math, zero new console errors) — **opening the panel itself was never independently driven end-to-end by this session**, since local dev cannot reach the production backend for real chat/verse data (CORS-blocked, the same pre-existing gap noted in every prior SP2 session below). Alex closed that gap directly: reviewed Phases 1 (both the original overlay build and the live reversal) through 5 live on `rhemata.app`, confirming each as it shipped, plus an explicit post-push pass on Phases 4 and 5 confirming the section cards read as clearly separated when two are open and the pin badge shows and updates the correct live count. **Every phase now has a real live confirmation, not just a local-dev proxy.**

---

## Pin-dropdown-closes-panel bug — found post-ship, fixed in two rounds (session state, 2026-07-22)

Alex found this live right after the Phase 0-5 work above shipped: selecting a pinned verse from the top-bar `PinDropdown` opened the Study Panel, then it closed itself again within about half a second. Not covered by any of the five phases' own acceptance checks (none of them exercised the pin-dropdown-to-panel path specifically) — a real gap this session's own "every phase now has a real live confirmation" claim above didn't anticipate, since the *phases'* content was confirmed but this specific cross-feature interaction wasn't.

**Root cause:** Radix's `DismissableLayer` (underlying `Dialog.Content`) fires `onFocusOutside` — and dismisses on it, same as `onPointerDownOutside` — for *any* `focusin` event whose target isn't already inside the layer's own subtree, not just the interaction that opened it. Selecting a `DropdownMenuItem` closes that Radix `DropdownMenu`, and Radix's own default close behavior restores focus afterward — landing on elements outside the Study Panel's `Content`, which its (until now unhandled) default `onFocusOutside` read as a dismiss signal.

**Round 1 (`722f4ee`):** added an `onFocusOutside` handler mirroring the existing `onPointerDownOutside` swap-in-place suppression, and marked the `PinDropdown` trigger button `data-study-trigger`. Verified working via a real isolated reproduction (temporary local route mounting the actual `PinDropdown`/`StudyPanel` with fixture data, Playwright-driven, before/after via `git stash`) — genuinely fixed the mechanism as understood at that point. **Did not fix the live bug** — Alex reported it was still broken after this deployed.

**Round 2 (`e9c736b`) — found by tracing real DOM events live, not by guessing again.** Created a disposable admin-created test account via the Supabase Admin API (service-role key, `email_confirm: true`, no real email needed) and seeded one real `study_pins` row (`ROM.8.28`) directly via SQL. Signed in through the real `LoginModal` on `rhemata.app` with Playwright, instrumented `focusin`/`focusout`/`pointerdown`/`click` at the document level via `page.addInitScript` (armed before any app code runs), then drove the actual interaction. The real event sequence on selecting a pinned verse: **item → `DropdownMenuContent`'s own portal container → trigger button** — an intermediate focus stop on the dropdown's own content div, a separate Radix portal that is not a DOM ancestor of the trigger button, so round 1's marker never covered it. That intermediate `focusin` dismissed the panel before focus ever reached the trigger. Fix: `DropdownMenuContent` now also carries `data-study-trigger`.

**Verified with the same live method, confirmed working:** re-ran the identical Playwright trace against production after deploy — confirmed `[role="menu"][data-study-trigger]` present (new code actually deployed, not stale cache) and the panel's `data-state` stayed `"open"` across a full 3-second window (screenshot: verse text, Interlinear open with real Greek tokens, Commentaries/Pastors' Notes closed — all Phase 0-5 work rendering correctly together). **This is the strongest verification in this session** — real signed-in production session, real seeded data, real DOM event trace, not local-dev fixtures or code-reading inference.

**Test account cleanup, confirmed:** the disposable account and its pin were deleted after verification via the same Admin API + direct SQL — `SELECT count(*)` on both `study_pins` and `auth.users` for that `user_id` returned 0 before this record was written. No residual test data.

**Lesson for future sessions on this panel, stated plainly:** local-dev fixture testing (as used in round 1, and throughout Phases 0-5 above) can miss real bugs that only manifest from the actual deployed app's specific DOM/portal structure — round 1's isolated reproduction *passed* even though the live bug wasn't actually fixed yet. When a fix is verified only in an isolated harness, say so, and treat a subsequent "still doesn't work" report as new information, not user error — the live DOM trace in round 2 found the real cause in one pass where more guessing would not have.

---

## Records reconciliation — push ladder + SP4 sign-off closure (session state, 2026-07-21)

**Push ladder, verified against git, not assumed:** `git rev-parse main` and `git rev-parse origin/main` are identical (`5f2c125`) after an explicit `git fetch`; `git branch -vv` confirms `main` tracks `origin/main` with nothing ahead or behind. Every commit from this cycle — `3f68ddc` (teachers-on-verse removal), `ae7e583`, `65b36e2` (chrome cleanup), `916c883`, `fe310e2` (Phase 2 floating overlay), `5f2c125` — is already on `origin/main`. **This corrects an assumption otherwise carried into this reconciliation that the Phase 2 build might be unpushed/hard-stopped locally — it was not; nothing from this cycle is sitting local-only.**

**SP4 sign-off, confirmed complete:** Alex signed in on `rhemata.app` and ran the full authenticated verification pass. All four checks passed: real card content for a signed-in user, the honest-empty state, nested back-return, and keyboard-only navigation. This closes SP4 teacher-card verification — the "NOT verified this session — needs Alex's own pass" framing in the 2026-07-18 SP4 entry below is superseded by this pass (closing note added there), not deleted.

**This same pass also confirmed, live in production, the two same-day removals below:**
- "Your teachers on this verse" is genuinely gone on `rhemata.app` — closes that section's own "full authenticated production re-verification... has not been done" caveat (closing note added there).
- The dev-trigger button + shortcut and the "Open in Study" link are genuinely gone on `rhemata.app`, and STEPBible/Tyndale attribution still renders correctly — closes that section's equivalent gap (closing note added there).

**Not closed by this pass — stays open:** the Phase 2 floating-overlay build (`fe310e2`) **shipped after** this sign-off pass and has only been verified against local-dev route-interception doubles (see that section's own caveat below, left as-is — still accurate). Its "shipped, build commit `fe310e2`" status is a different claim from "signed off" — don't conflate them. A hands-on authenticated `rhemata.app` pass on the overlay itself is still owed.

**Forward:** SP5 (mobile bottom-sheet, roadmap #43) is next and reuses the overlay's shared open/swap/close model (`page.tsx` state + `PanelBody`'s swap-reset), built presentation-agnostic for exactly this reuse. Two long-standing items remain open, untouched by this session: no real screen-reader pass has ever been run (Open blockers #13), and the Hebrew lexicon permission gate from Online Bible has not been obtained (Open blockers #14).

---

## SP panel refinement — Phase 2: floating overlay (session state, 2026-07-21)

**Superseded 2026-07-22 — read the new entry at the top of this file first.** "Desktop presentation" below is no longer current: `page.tsx` never stopped reflowing the sidebar/chat around this "floating" card (confirmed by direct code read, not a regression — this commit's own reservation-growing change was intentional), and the geometry itself was replaced twice more since (a true zero-reflow overlay, then a live reversal to side-by-side chat-narrowing). "Non-modal + swap-in-place" and "Reset-on-swap" below both held up under re-audit and are still accurate as descriptions of what shipped, except "Reset-on-swap" collapsing Interlinear on swap — Phase 2 of the 2026-07-22 session flipped that default to open. Kept below verbatim for provenance.

Shipped, build commit `fe310e2` — `frontend/app/page.tsx`, `frontend/components/rhemata/chat-message.tsx`, `frontend/components/rhemata/study-panel.tsx` only. Alex's SP4 sign-off (the gate this phase was waiting on) cleared before this session started. **Goes further than the original Phase 2 scope** (`docs/superpowers/plans/2026-07-19-study-panel-refinement.md`, Tasks 6-9), which was margin/rounding only — this session's explicit spec added non-modal desktop interaction and swap-in-place, superseding that plan's narrower Task 9 assumption (default Radix modal dismiss unmodified).

**Desktop presentation:** the panel is a floating card — `inset-y-2 right-2 rounded-xl border border-border`, reusing the existing `shadow-lg` (all values already in use elsewhere in this codebase, per DESIGN.md's "no new shadows/radii/colors" rule and its own "popovers/sheets are the only lifted surfaces" carve-out) — instead of a docked column flush against the screen edge. `page.tsx`'s reserved-width clamps grew by `+1rem` per bound (`clamp(496px,calc(50vw+1rem),736px)` / `clamp(396px,calc(33vw+1rem),496px)`) so a real gap shows between the chat card and the panel, not an overlap.

**Non-modal + swap-in-place:** `PanelPrimitive.Root` now takes `modal={isMobile}` — desktop is non-modal (Radix's documented `DialogContentNonModal` path, confirmed via `/radix-ui/primitives` docs and the installed `@radix-ui/react-dialog@1.1.16` type declarations before writing any code), and desktop renders no `Overlay` at all. Chat stays fully visible and interactive behind it. `VerseReferenceSpan`/`TeacherReferenceSpan` (`chat-message.tsx`) get a `data-study-trigger` marker; `Content`'s `onPointerDownOutside` checks for it via `event.detail.originalEvent.target.closest(...)` and calls `event.preventDefault()` only for those, letting a second underline click swap `reference` in place (page.tsx's `handleVerseClick` already did this unconditionally — no page.tsx change was needed there) instead of racing Radix's default dismiss into a close-then-reopen. Everything else outside the panel still closes it normally — no blocking layer anywhere (confirmed by grep and by reading the full diff).

**Reset-on-swap:** `PanelBody` now collapses Interlinear and resets scroll to top on every genuine target-identity change (`referenceKey(reference)`, a content-identity string — re-clicking the same target is correctly a no-op), and fades the content subtree in via a `key`-forced remount. This supersedes the old "leave Interlinear open across a verse switch" decision from SP2 Phase 8.

**Shared-model note for SP5:** the target/open/close state (`page.tsx`) and the swap-reset behavior (`PanelBody`) are presentation-agnostic and were already shared between mobile/desktop (single `<StudyPanel>`, branching only on `useIsMobile()`); only the modal/overlay/positioning pieces differ now. A future mobile bottom-sheet build can reuse both without touching this logic — the desktop side-slide and a future mobile bottom-rise are presentation layers over the same shared behavior.

**Live-verified, real evidence (Playwright, local dev, route-interception test doubles for `/chat` and `/study/interlinear` only — same CORS-driven method as the two sessions above):** chat textarea stayed typeable while the panel was open; clicking a second, different verse underline while open swapped content to it in place (screenshot: same panel shell, new verse text, Interlinear auto-collapsed, no flicker/stack); scroll position confirmed reset to 0 after a swap; the X button closed the panel; clicking plain chat text (not a trigger) closed the panel; mobile (iPhone 13 emulation) confirmed **completely unaffected** — full-screen sheet, dark scrim, no rounded corners, no gap, chat hidden underneath, byte-for-byte the same presentation as before.

**Caveat, stated plainly:** as with the two sessions above, this is local-dev verification against route-interception doubles, not a full authenticated pass against `rhemata.app`. That full production re-verification (still owed from the "your teachers on this verse" removal earlier this session too) has not been run yet.

---

## SP2 — Panel chrome cleanup (session state, 2026-07-21)

Three approved UI-only changes, build commit `65b36e2`, `frontend/app/page.tsx` + `frontend/components/rhemata/study-panel.tsx` only:

1. **Removed the floating "Study preview" dev-trigger button and its Cmd/Ctrl+Shift+S shortcut** (`app/page.tsx`) — collided with the chat button and duplicated the panel's one real open path. The panel now opens **only** via a verse/teacher underline click. `NEXT_PUBLIC_STUDY_PANEL_ENABLED` and the underline click-path (`onVerseClick`/`onSelectPin` wiring into `handleVerseClick`) are untouched — confirmed by diff, not by inference.
2. **Removed the "Open in Study" link** from the bottom of the panel (`study-panel.tsx`). The standalone `/study` page remains live and reachable by direct URL as the fallback — confirmed by direct navigation, untouched by this diff.
3. **STEPBible/Tyndale House attribution (CC BY 4.0 license condition) retained, no restyling needed.** All four rendering surfaces — `InterlinearBlocks` (shared by the panel's Interlinear row and the standalone page), the panel's own `WordStudyView`, and the standalone page's `WordStudyPanel`/`InlineWordPanel` — already use `text-xs text-muted-foreground`, DESIGN.md's own documented low-prominence pattern (line 120, same class used for verse-number superscripts). No code changed on this point.

**Live verification method, since local dev is CORS-blocked from the production backend for `/chat`, `/study/interlinear`, and `/study/lexicon` (the same pre-existing constraint noted in the "your teachers on this verse" removal above and in Phase 7/8/9's history):** used Playwright route interception as network-level test doubles for those three endpoints only (synthetic but shape-accurate SSE/JSON responses) — every other request (Commentaries, Pastors' Notes, pins) hit the real backend unmodified. This produced a **genuine click on a real verse-underline** (not the removed dev button) that opened the panel, expanded Interlinear with real-shaped tokens, and opened the word-study view — confirming the attribution renders correctly in both panel surfaces by direct observation, not class-name inspection. Pin click showed the expected guest Beta Access gate, no crash. Standalone `/study` loaded directly with no crash.

**Not touched:** SP4's curated `TeacherCard` path, Commentaries, Pastors' Notes, pins, and all interlinear/lexicon *data* fetching — chrome only, per scope lock.

**Production confirmation, 2026-07-21:** Alex's SP4 authenticated sign-off pass confirmed all three changes live on `rhemata.app` — dev-trigger button and shortcut gone, "Open in Study" link gone, STEPBible/Tyndale attribution still renders correctly. Full detail in the reconciliation entry at the top of this file.

---

## SP2 — "Your teachers on this verse" removed (session state, 2026-07-21)

**Removed, build commit `3f68ddc`, frontend-only diff (99 deletions, `frontend/components/rhemata/study-panel.tsx` only):** `useTeachersOnVerse`, `TeacherOnVerseResult`, `isVerseRef`, and the "Your teachers on this verse" render block. **Reason:** verse-anchored nearest-chunk matching (`source_kind_filter=sermon_transcript`) surfaced irrelevant excerpts under teacher names. Retired pending a possible theme-based approach via the SP4 teacher-card path instead, not replaced same-session.

Preceded by a read-only removal-footprint audit (previous session) that traced the feature to commits `af5be46` (Task 9, backend filter param) and `8698e4a` (Task 11, the panel wiring), then classified every symbol it introduced as UNIQUE (safe to remove) or NOW-SHARED (must stay). That classification held with zero surprises during execution.

**Intentionally preserved as shared infrastructure — zero backend changes this session:**
- `/study/commentary` endpoint, `source_kind_filter` param, and both its conditional branches (`commentary` / `sermon_transcript`) — the sermon-results code path predates this feature entirely (`git log -S match_sermon_chunks_by_ref` traces it to `1375b3f`, well before `af5be46`); the standalone Study page's default (unfiltered) query depends on both branches running together, and `CommentaryAccordionRow` depends on the explicit `commentary` filter.
- The `accessToken` prop chain (`app/page.tsx` → `StudyPanel` → `PanelBody`) — now feeds `TeacherCard`, `CommentaryAccordionRow`, `PastorsNotesSection`, and `useLexiconDefinition`.
- `verseIdStr` — feeds `useInterlinear` and the `selectedStrongs`-reset effect; only the `useTeachersOnVerse` reference to it was removed.

**Proof performed before commit:**
- Zero-hit greps repo-wide for `useTeachersOnVerse`, `TeacherOnVerseResult`, `isVerseRef`, `teacherResults`, `teachersLoading` — confirmed clean.
- `tsc --noEmit` clean; `next build` production build clean.
- Live against local dev (`localhost:3000`, Playwright, guest session): verse card, Interlinear, Commentaries, Pastors' Notes, and pin-click (guest → Beta Access gate, not a crash) all render correctly; "Your teachers on this verse" text confirmed absent; a real Commentaries-row fetch was observed carrying `source_kind_filter=commentary` with **no accompanying `sermon_transcript` request** — direct proof the removed hook no longer fires, not just a code-reading inference. Standalone `/study` page loaded without error, same fail-quiet "No commentary found"/"Couldn't load notes" states as the panel (consistent with this environment's known local-dev-to-production CORS block, not a regression).
- **Caveat, stated plainly:** local dev cannot reach the production backend for authenticated calls (CORS-blocked, a pre-existing constraint this project has hit before — see Phase 7/8/9 entries below, which all needed a real `rhemata.app` session to verify auth-gated behavior). This session's live checks are real but guest/local-only; a full authenticated production re-verification (real commentary/sermon results, Pastors' Notes content) has **not** been done post-removal and would need a push + a real signed-in session on `rhemata.app`, the same as prior SP2/SP4 sessions did.
  - **Closed 2026-07-21** — Alex's SP4 authenticated sign-off pass confirmed this removal live in production (the text is genuinely gone). Full detail in the reconciliation entry at the top of this file.

**Not touched:** SP4's curated `TeacherCard` path (`reference.type === "teacher"`) — a different feature, confirmed unrelated during the audit (disjoint code path, coincidentally similar name).

---

## SP panel refinement — Phase 1: reference-persistence fix (session state, 2026-07-19)

Shipped per `docs/superpowers/plans/2026-07-19-study-panel-refinement.md` (PLAN.md #42.5), following a grill-me interview session that resolved the "clicking does nothing" premise in code before any build work started.

**Root cause, confirmed by direct code trace, not assumed:** `verified_references` (SP1's fail-quiet reference data) and `citations` were computed fresh every chat turn and attached only to that turn's SSE `meta` event (`chat.py:1026-1031`) — never written to the database. `_save_conversation` (`chat.py:445-479`) inserted only `id`, `conversation_id`, `role`, `content` per message; there is no backend `/conversations` endpoint at all — the frontend reads conversation history straight from Supabase (`useConversations.ts`), requesting only `role, content`. Consequence: every reopened conversation lost 100% of its verse/teacher underline clickability and citation pills, regardless of signed-in/guest state or reference type — not the signed-in/guest or verse/teacher distinction the inherited notes assumed. `message_id` turned out to already survive (it's the message row's own `id`); it just wasn't being selected on reload.

**Shipped, commits in order:** plan doc + PLAN.md `#42.5` entry (`0285920`, `166c238`); `.gitignore` entry for `.worktrees/` (`cd9ccd6`); migration `066_messages_reference_data.sql` (`98bb59e` — nullable `messages.citations`, `messages.verified_references` jsonb columns, applied and verified on a fresh connection before commit); `chat.py`'s `_save_conversation` persisting both on the assistant row only (`08b2a7d` — bundled per Alex's explicit call, citations had the identical bug for the identical reason); `useConversations.ts`'s `loadMessages` selecting `id, role, content, citations, verified_references` and mapping them into `Message`'s existing optional fields (`b19f6d0`); this record itself (`a775f86`). Underline's own visual treatment deliberately unchanged (Alex's explicit call — the "not looking tappable" complaint was very likely this same persistence bug, not a separate design issue).

**Live-verified, real evidence (Playwright against `rhemata.app` production, disposable admin-created test account, deleted after — zero residual rows confirmed):**
- Fresh answer to "What does Derek Prince teach about deliverance, based on Romans 8:28?": 4 real underlined spans rendered post-stream (Derek Prince, Romans 8:28 ×2, Joel 2:32); clicking one opened the panel correctly.
- **The actual bug, proven fixed:** clicked "New Chat," then reselected the same conversation from the sidebar — the identical 4 underlines were still present and still genuinely opened the panel on click. This is the literal scenario that was broken before this fix.
- Direct DB query on the same row: `citations` had 8 entries, `verified_references` had 3 (matching the 4 rendered spans — "Romans 8:28" occurs twice in text but resolves to one verified identity, reconciling exactly).
- Guest (unauthenticated) chat streaming confirmed unaffected on production — guests never call `_save_conversation` (`chat.py`'s `if user_id:` branch), so this fix has zero guest-facing surface, confirmed live not just by code-reading.
- Simulated a pre-migration row (nulled `citations`/`verified_references` directly in the DB on a real assistant message) and reloaded it live: zero underlines, plain answer text rendered normally, zero console/page errors. Confirms graceful degradation — this is NOT the same as the spec's "retrofitting old conversations" exclusion (which stays correctly out of scope), it's proof the new code path fails safe on old data shapes.

**Process note:** executed in an isolated git worktree (`.worktrees/sp-panel-refinement-phase1`, branch `sp-panel-refinement-phase1`) per Alex's explicit choice this session (departure from this repo's usual direct-to-main convention), fast-forward-merged into `main` and pushed only after Alex confirmed that was the right way to reach a real deploy for live verification. Worktree removed after merge; branch fully merged, safe to delete.

**Left open, for whoever (or whichever panel) picks this up next:** Phase 2 (floating overlay, desktop only) is scoped and ready in the plan doc but explicitly gated on Alex's own SP4 sign-off (see below) — do not start it before that sign-off is confirmed. Isolated worktree (`sp-panel-refinement-phase1`) and its branch were removed after the fast-forward merge to `main`; nothing dangling. This session did not touch `HARNESS.md` or `ARCHITECTURE.md` — the concurrent records-cleanup session's note below already flags `ARCHITECTURE.md`'s missing `messages.citations`/`verified_references` columns; still true after this session.

---

## Records cleanup + harness write-detection loop fix (session state, 2026-07-19)

Ran chronologically before the SP panel refinement session above (commits
land 15:03–16:02 vs. that session's 17:57–18:44) — inserted here, not at the
top, to keep this file's ordering true to when the work actually happened,
not when it was logged.

**Records-only cleanup — commit `b510b31`.** Reconciled three places PLAN.md
contradicted itself or reality: `sources/` backup marked DONE 2026-07-19
(Google Drive; restore explicitly flagged unverified — not tested), SP2 status
in `docs/inline-study-panel-spec.md` corrected from "NOT yet scheduled or
built" to reflect its actual shipped state, and harness `#5.5` exit condition
(a) corrected from PLAN.md's stale "OPEN" to the CLOSED state confirmed by
direct code read + `git log` (commit `96bc3ff`). No logic/DB changes.

**Read-only PLAN.md-vs-live-DB audit — no file changes, findings unaddressed.**
Compared every DB-checkable claim in PLAN.md against direct live queries.
Most drift is honestly dated-and-labeled (chunk/doc/proposition totals aging
since the 2026-07-14 refresh). Two live findings Alex hasn't acted on yet:
(1) New Wine's "33 articles/9 issues" claim is now 15 docs/8 issues — matches
the SP4 pre-build fix's own 33→15 number below, just never folded back into
PLAN.md `#26`. (2) SermonIndex's "#34 still open" framing is *more* wrong
than PLAN.md itself knows — Carter Conlon (`visibility='shown'`, unlicensed)
now has 6 real ingested documents, contradicting the "only ingested speaker
is hidden, structurally blocked" note under SP2 Phase 7. Propositions count
also dropped 2,488→2,306 since the 07-14 refresh with no documented cause —
worth a look. Full comparison table not persisted anywhere; re-run the audit
if this matters before relying on any PLAN.md count.

**Executor write-detection infinite loop — diagnosed then fixed, commits
`d9ab1cc` (build) + `f1e5184` (records).** Root-caused the 2026-07-18 bug
below by reading the real surviving `/tmp/rhemata-harness-writes` log from
that incident: a benign grep for a bare SQL-verb-shaped pattern
(`"ALTER TABLE..."`) against a directory-only target got recorded as a write
with zero extractable referents, so it could never be "accounted for" by any
report, ever; retries piled up undeduplicated copies of the same
unsatisfiable record forever. Fixed in `deterministic_gate.py` only
(`guard_pretooluse.py` and `check_reconciliation()`'s fallback both
untouched, per explicit scope lock): referent extraction now always yields
something meaningful, and accounting checks the cumulative, deduped text of
everything the finishing agent has said all session, not just its latest
message. Proven via a new `.claude/harness-selftest/test_write_accounting_loop_fix.py`
against the real recorded incident command — loop converges and stays
converged; a genuine undisclosed write still blocks; a genuine disclosed
write still passes. `BASH_WRITE_INDICATORS` deliberately left over-flagging
benign searches (the safe default) — narrowing it is flagged below as its
own future session, not done here.

**Left open, not done this session — flagged for whoever picks this up
next:** `HARNESS.md`'s "Closed" section still doesn't list the loop fix
above (`d9ab1cc`) — that's the durable home for it per HARNESS.md's own
eviction rule; right now the only record is in this file, which gets
reshuffled every session (see this section's own insertion above).
`ARCHITECTURE.md`'s `## Database` table list is also stale — missing
`jewish_perspectives` (still live, 2 rows, confirmed by the audit above),
`study_pins` (SP2 Phase 5), `teacher_profiles` (SP4), and the new
`messages.citations`/`messages.verified_references` columns from the panel
refinement session above. Neither touched this session — Alex hadn't
confirmed he wanted them done yet when this session closed.

---

## SP4 — Teacher Cards (session state, 2026-07-18)

Built per `docs/superpowers/plans/2026-07-18-sp4-teacher-cards.md` (11 tasks),
following the pre-build data fix recorded below. Shipped: migrations `064`
(`teacher_profiles` table + 9-row seed) and `065` (`match_teacher_chunks`
RPC, license-gated); `app/services/llm_client.py` (extracted shared
Anthropic client + guardrails-text loader, also now used by `chat.py`);
`GET /study/teachers` + `GET /study/teacher/{source_id}` (combined
bio/works/live-position-synthesis endpoint, own similarity floor since the
RPC supplies none); frontend curated-teacher detection/verification
(`study-reference.ts`), underline rendering (`chat-message.tsx`), the
`TeacherCard` component, and full wiring through `study-panel.tsx` /
`page.tsx`. All 10 build commits pushed; `origin/main` confirmed at each
step.

**Live-verified, real evidence:**
- Backend: `curl https://rhemata-production.up.railway.app/study/teachers`
  returns all 9 curated teachers with correct `source_id`s, live in
  production — confirmed directly, not assumed from a successful deploy.
- The `TEACHER_POSITION_SIMILARITY_FLOOR = 0.3` value is empirically
  validated against this corpus's real score distribution, not a guess:
  `scripts/test_teacher_card.py` shows an on-topic query's best similarity
  at 0.508 (clears the floor) and an off-topic query's best score at 0.152
  (stays well below it) — this directly closes the gap the 2026-07-18
  pre-build diagnostic flagged (no threshold exists in `match_chunks`/
  `match_teacher_chunks` themselves).
- Frontend, live on `rhemata.app` (real Playwright session, guest/no
  auth): asked "What does Derek Prince teach about deliverance?", waited
  for the real streamed answer to fully stabilize (not a fixed timeout —
  polled until page text stopped changing), confirmed **2 real underlined
  "Derek Prince" buttons** in the rendered answer, exact class match to
  `TeacherReferenceSpan`'s styling. Clicked one: the panel opened with
  header "TEACHER" / "Derek Prince" (confirms correct mode-switch, not the
  verse card, no nesting/back-stack residue). As a guest (no access token),
  the card body read "This teacher's card isn't available right now" —
  honest and non-crashing, not a silently-swallowed fake-empty state (the
  exact bug class Phase 7 found in `pastors_notes.py`), though it doesn't
  specifically prompt sign-in the way some other gated surfaces do — see
  Open Flags below.

**NOT verified this session — needs Alex's own pass, blocked by the Beta
Access gate:** signing up a real disposable test account to check requires
a beta access code this session doesn't have (`Become a test user` → a
`BetaGate` code-entry screen, dead end without the code). Specifically
unverified: (1) real card content for a signed-in user — actual bio text,
a real works-in-corpus list, a real synthesized position; (2) the
Interlinear-width-collapse fix (Task 9) — switching from a verse card with
Interlinear open to a teacher card should snap the panel back to 33vw, not
stay at 50vw; (3) the fail-quiet floor behavior live, end-to-end, on an
authenticated off-topic question (Task 5's script validates the floor
value itself against real scores, but not the full authenticated request
path). None of these are new risks invented for this note — they're the
literal gaps left by not being able to sign in.

**Closed 2026-07-21** — Alex signed in and ran the full authenticated pass:
real card content, the Interlinear-width-collapse behavior, the fail-quiet
floor end-to-end, back-navigation, and keyboard-only nav all confirmed.
Full detail in the reconciliation entry at the top of this file.

---

## SP2 — Inline Study Panel (session state, 2026-07-17)

Phase 7 (Commentaries + Pastors' Notes accordion rows) shipped and live-verified
on `rhemata.app`. Commits `69df175`, `063fcab`, `5c82975`, `0c8b75f`. Separately:
`32f5b25` fixed a Phase 5 defect (pin-cap tooltip still checked `>= 4` after the
real cap moved to 8).

**Found during Phase 7, then fixed same session:** `backend/app/routers/pastors_notes.py`
never imported `get_user_role`, called at 3 sites (`list_cards`, `create_card`,
`update_card`). NameError → 500 on every authenticated `/pastors-notes/cards`
call, 100% reproducible; guests unaffected (they skip that branch). The
frontend's `.catch(() => setCards([]))` silently repainted every crash as an
honest-looking empty state — broken for every signed-in user on the standalone
Study page too, not just the new panel row, for as long as the import gap
existed. Fixed in `5d430b7` (one-line import, plus closes the read-path
silent-swallow with a distinct error state; add/edit/delete already surfaced
real errors correctly and were untouched). Proven live, not just a 200 —
full round trip on `rhemata.app` with a disposable test account (created,
elevated to admin, deleted after): note added, visible after a fresh reload
(real server persistence, not local state), edited, edit visible after a
fresh reload, deleted. Zero residual test data confirmed.

**Attribution correction:** an earlier note this session described leaving
this bug unfixed as "Alex's explicit call." That was wrong — the actual answer
was to a narrower question about touching the backend in that specific moment,
not a decision to leave the bug open. Corrected here; the bug is now fixed.

**Phase 8 (Interlinear + lexicon word study, moved in from the dissolved SP3)
shipped and live-verified on `rhemata.app`, same session.** Commit `9415f11`
— Tasks 28–30 combined into one commit rather than three: the `AccordionRow`
controlled-mode extension and lifting `interlinearOpen` up through
`StudyPanel` to `page.tsx` serve both the row's mount and the width-borrowing
together, and weren't cleanly separable after the fact without redoing
already-correct, already-typechecked work.

- **Interlinear row (Task 28):** `useInterlinear` + `InterlinearBlocks`
  (both Phase 6 extractions), mounted first, before Commentaries. Live on
  Romans 8:28: 18 real Greek tokens rendered, STEPBible/Tyndale House
  attribution visible.
- **Word-study view (Task 29):** tapping a token opens the panel's one
  back-button surface — `WordDefinitionCard` + `useLexiconDefinition`,
  object construction copied exactly from `study/page.tsx`'s own
  interlinear-tap call site (`selectedToken ? {...} : selectedStrongs &&
  lexiconEntry ? {...} : null`). Live: tapped a real token (Strong's
  `G6063`), word-study view opened, Back button returned to the normal row
  view with Interlinear still expanded. STEPBible attribution added to this
  view directly (Phase 2's Task 4 had deferred the panel's copy here) —
  deliberately not baked into `WordDefinitionCard` itself, keeping Phase 6's
  file as Phase 6 left it.
- **Width-borrowing (Task 30):** confirmed live both directions — 422px
  (33vw clamp) collapsed, 640px (50vw clamp) while Interlinear is open,
  automatic, no user toggle.
- **Task 31 (grep):** zero `Translations`/`Cross-references` references
  anywhere in the frontend.
- **Task 32, live, not just structural:** a real, SP1-verified "Genesis
  1:1" underline (from a real streamed chat answer, not the hardcoded dev
  demo reference) opened the panel and showed the honest "No interlinear
  data available for this verse" message — zero fake "coming soon" copy,
  zero Greek tokens for an OT verse. Precept Austin / "From the Library"
  confirmed absent both structurally (`WordDefinitionCard` has no such code
  path — verified by reading its source, not inferred) and live (zero
  matches after tapping a real Greek word).
- **One judgment call made without a plan citation, flagged here rather than
  silently decided:** the word-study view's header has only a Close button,
  no Pin — pins are verse-scoped and still one tap away via Back, so nothing
  is actually lost, just an extra tap. The plan's Task 29 doesn't specify
  either way.

**Phase 9 (keyboard + screen-reader verification) shipped and live-verified on
`rhemata.app`, same session.** Commit `bb8aa43`. Diagnostic-first: audited
read-only, reported 5 confirmed gaps plus 4 confirmed-clean surfaces, stopped
for Alex's go-ahead before touching anything — all 5 confirmed gaps approved
for a fix, all additive, none of the 4 clean surfaces touched.

- **Gap 1 — accordion rows didn't announce open/closed state.** `aria-expanded`
  added to all three `AccordionRow` triggers (Interlinear/Commentaries/
  Pastors' Notes) and to Commentaries' nested per-excerpt toggle. Live,
  before/after a real keyboard toggle: all four went `false → true` correctly.
- **Gap 2 — closing the panel dropped focus to `<body>`.** This panel has no
  `Dialog.Trigger` (opened from verse-underline clicks, the dev button, or a
  keyboard shortcut), so Radix had nothing to restore focus to. Now captures
  `document.activeElement` on open and restores it via `onCloseAutoFocus`
  (Radix's own override point — doesn't touch the focus-trap mechanism, a
  separate concern), falling back to the chat textarea if the original
  element is gone. Live, both close paths tested: clicking the panel's own
  Close button and pressing Escape each correctly returned focus to the
  actual triggering element (the dev button, in both tests).
- **Gap 3 — word-study view lost focus to a generic container, both
  directions.** Entering now focuses the Back button (the one actionable
  element at the top of this back-stack surface); leaving via Back now
  refocuses the *specific* token that was tapped, not just "the row" —
  `data-strongs-token` added to the shared `InterlinearBlocks` (inert
  markup, zero behavior change for the standalone page's existing use),
  read by a `PanelBody` effect that fires once after Back clears the word
  view. Live: tapped a real token (Strong's `G6063`), confirmed focus
  landed on "← Back" on entry, confirmed focus returned to the *exact same*
  `G6063` token button on exit (`data-strongs-token` matched exactly, not
  just "some token"). Falls back to the row view's own container
  (`tabIndex={-1}`) if the exact token isn't found — not separately
  exercised live (no known way to force that path without breaking the
  fetch deliberately), but the fallback ref is real and typechecked.
- **Gap 4 — pin button had no real accessible name, only a `title`
  fallback.** Added `aria-label` mirroring the existing title text. Live:
  confirmed `aria-label="Pin limit reached (8)"` on the live DOM in the
  cap-reached state.
- **Gap 5 — pin-cap message wasn't announced.** Added `role="alert"` (implies
  assertive live-region semantics, fires on insertion — correct for a
  message that auto-dismisses in ~2.5s and can't rely on the user already
  being focused on it). Live: confirmed `role="alert"` on the live DOM
  element, using a real 9th-pin-attempt trigger (8 real seeded pins, a real
  refusal).
- **All 4 previously-clean surfaces re-confirmed unaffected, live:** focus
  trap (25 tabs, no leak), `aria-labelledby`/`aria-describedby` panel
  labeling both present, pin dropdown (real `role="menu"`, opens/closes via
  keyboard), verse underlines (real, keyboard-activatable buttons in a
  fresh answer).
- **Honesty bar, explicit:** every claim above is either real keyboard
  interaction (Tab/Enter/Escape driving the actual page) or live
  accessibility-tree/DOM attribute inspection (`aria-expanded`, `aria-label`,
  `role`, `data-*`) on the deployed site — not source-code inference and not
  a screen-reader run. **No actual screen reader (VoiceOver/NVDA) has been
  run against this panel.** That remains a genuinely open, unproven check —
  logged as a new open flag below, not closed by this session.

**Phase 10 (records correction) DONE, same session — commit `a7417eb`.**
Task 35 (PLAN.md): appended the Phase 7/8/9 completion record to #40 (Steps
1–5 of the task were already recorded by earlier sessions, verified against
PLAN.md's live content rather than assumed — #41's supersession, the
teacher-tap decision, the pin-system redesign, the Precept Austin deferral,
and the Hebrew permission gate were all already present); added the two
still-missing pieces — Step 6 (#33's STEPBible half marked closed, the
openbible.info half stays open) and Step 7 (the SP track intro's "old
/study page untouched" wording marked superseded by Phase 4 + Phase 6,
with the same "behaviorally, not literally" distinction those two phases
already proved live). Task 36 (this file): Open Flags 16/17 were already
closed by the sessions that shipped Phase 1/3 — PLAN.md's own #40 entry
already carries "closes Open Flag 17" inline, nothing further to do there;
added Blocker #14 for the Hebrew permission gate, cross-referencing PLAN.md
Open Decisions #11 per the task's explicit instruction.

**SP2 is now fully done, all 10 phases.** The only two things this build
leaves genuinely open are Blocker #13 (no real screen-reader pass) and
Blocker #14 (Hebrew lexicon permission) — both real, both already logged,
neither invented for this closing note.

---

## SP4 pre-build data fix (session state, 2026-07-18)

5 teachers (Bob Mumford, Ern Baxter, Charles Simpson, Don Basham, Oswald J.
Smith) had no `sources` row and no `source_aliases` entry — all their
documents carried the shared New Wine Magazine `source_id`
(`72b2f583-d7f9-4361-be1c-6d5aebe59fac`). Derek Prince additionally had 5
articles mis-attributed to the same magazine bucket despite having his own
resolved source. Fixed via direct `psycopg2` transactions (one per teacher),
each verified live: licensing columns (`license_status`, `visibility`,
`permission_granted_at`, `permission_contact`, `permission_terms`) copied
verbatim from the magazine row, alias resolution replicated
`reference_verifier.py`'s exact path, identity counts matched, spot-checked
chunks/embeddings unchanged. Independently re-verified against a fresh DB
connection before this record was written, not just taken from the
executor's own report.

- Bob Mumford → new source `e2a4babd-c49f-46b2-940e-9771b95e695f`, 4 docs moved
- Ern Baxter → new source `63bdb33a-f672-415e-a209-0dd12fdf29de`, 2 docs moved
- Charles Simpson → new source `c39c4e62-59f3-4a51-9f86-6d1fbcdc6758`, 4 docs moved
- Don Basham → new source `1870bc05-2583-4f88-a6c3-0f5bd31212b9`, 2 docs moved
- Oswald J. Smith → new source `9baaf49f-f9cd-463c-af8b-88ed5b976eb5`, 1 doc moved
- Derek Prince → 5 stray docs re-pointed to his existing source
  `17be391b-d025-4178-8543-3e84da675c5d`, no new source/alias

New Wine Magazine bucket: 33 → 15 documents. Total `documents` row count
unchanged at 3,817 (no rows created or deleted — every write was a
single-column `source_id` UPDATE). Full 9-teacher audit (identity count vs.
name count) re-run after the fix: every alias resolves, every delta is 0.
SP4 build (#42, teacher card content) is now unblocked on this front — no
remaining hardcoded-bio teacher shares another entity's source_id.

## Known Harness Bugs

- **Executor loop, 2026-07-18 diagnostic — FIXED 2026-07-19, commit
  `d9ab1cc`.** Write-detection gate flagged an already-fully-disclosed
  benign action (failed grep + scratchpad cleanup) for 12 consecutive
  turns, alternating "1 of 9"/"2 of 9" flagged-item counts with no change
  in actions between turns. Root cause, confirmed against the real
  surviving 2026-07-18 write-state log: a benign grep for a bare
  SQL-verb-shaped pattern against a directory-only target got recorded as
  a write with zero extractable referents, so it could never be
  "accounted for" by any report text, and retries piled up undeduplicated
  copies of the same unsatisfiable record forever. Fixed by making
  referent extraction always yield something meaningful (never empty) and
  by checking disclosure cumulatively against everything the finishing
  agent has said all session, deduped, instead of only the latest
  message per turn. Proven via `.claude/harness-selftest/test_write_accounting_loop_fix.py`
  (loop converges and stays converged; a genuine undisclosed write still
  blocks; a genuine disclosed write still passes) — only this is claimed
  fixed, nothing broader. **Does not alter #5.5** — exit condition (a)
  stays closed exactly as PLAN.md records it; this session touched
  neither of its two named bridges. **Does not touch**
  `check_reconciliation()`'s fail-closed fallback (missing session_id /
  unreadable state file) — left exactly as-is, the safe-direction default
  for a different, narrower case.

- **`BASH_WRITE_INDICATORS`' SQL-verb over-flagging — NARROWED 2026-07-31,
  commit `569d412`.** A grep for a bare SQL-verb-shaped word (e.g. "ALTER
  TABLE") used to get recorded as a write regardless of context — the
  2026-07-19 fix above only made that already-flagged record satisfiable
  and non-looping, it did not reduce what got flagged. This session split
  `BASH_WRITE_INDICATORS` (`.claude/hooks/guard_pretooluse.py`) into an
  untouched `BASH_WRITE_INDICATORS_ALWAYS` set (shell redirection,
  file-mutating commands, sed -i — still deliberately over-inclusive,
  principle 5 unchanged there) and a `BASH_WRITE_INDICATORS_SQL_VERBS` set
  now suppressed only when the entire command is a shell-quote-aware-parsed
  chain of pure text-search/display commands (grep/egrep/fgrep/rg/cat/head/
  tail/less/more/wc/sort/uniq/echo) with no command substitution, process
  substitution, or backgrounding anywhere in it — any of those fails
  closed and the command stays flagged, same as before. No DB-write-capable
  command (psql, python3, tee, xargs, sed, etc) is in the allowlist, so
  this cannot mask a genuine write. Proven by
  `.claude/harness-selftest/test_sql_verb_narrowing.py`: the real
  2026-07-18 incident's grep command no longer gets recorded as a write;
  five true-positive cases (a real psql `ALTER TABLE` execution, a known
  write-script invocation, a redirection+SQL-verb mixed case, a
  command-substitution edge case, an `rm`-chained case) still flag exactly
  as before; two additional benign cases (a `cat | grep` file-content
  pipeline, a `;`-chained pure-grep pair) also narrow correctly.
  `test_write_accounting_loop_fix.py`'s check A5 was corrected in the same
  commit — its dedup-count expectation (2) had baked the pre-narrowing
  bug's phantom write record into what it treated as correct behavior; now
  1, with A1-A4 (the actual loop-convergence/cumulative-disclosure proof)
  unchanged. This closes the "future session, not bundled here" flag this
  entry used to name — CLAUDE.md's Session Routing hard rule and its
  DB-write-prohibition revisit trigger are untouched by this session on
  purpose; narrowing this classifier was only one of that rule's two named
  revisit conditions, and the other (a second clean DB-write harness
  session, deliberately run and reviewed) remains separately open.

---

## Open blockers

**1. Dead `~/Desktop/rhemata` path — 8 scripts — DONE 2026-07-22.**
3 scripts (`scrape_youtube.py`, `clean_transcripts.py`, `ingest.py`'s
`DOCS_FOLDER`) had it hardcoded as an actual runtime constant — now derived
from the script's own file location at runtime (`Path(__file__).resolve()`
or the equivalent `os.path` form), so a future repo move can't reintroduce
this. The other 5 (`ingest_tahot.py`, `generate_excerpts.py`,
`extract_book_quotes.py`, `ingest_interlinear.py`,
`test_excerpt_generation.py`) already derived the real path correctly at
runtime — the dead path only appeared in a docstring usage example, replaced
with a relative "run from repo root" instruction. Verified live: each script
runs clean (`--help` or module-level import) from repo root post-fix.
Commit `5bdf720`.

**2. `CommandBlock.tsx` hardcodes `/Users/alexwhitley` — DONE 2026-07-22.**
The file itself no longer exists — it was refactored at some point into
`frontend/components/admin/corpus-data.ts` (data) + `card-modal.tsx`
(rendering), and this blocker's filename had gone stale along with the path
it named. Fixed at the actual current location: 75 command strings in
`corpus-data.ts` had the dead path baked in; centralized into one exported
`REPO_ROOT` constant so a future move is a one-line change instead of a
75-line find/replace. Commit `5bdf720`.

**3. `sources/` backup — DONE 2026-07-19.** Corpus + `ingest_queue.xlsx`
backed up to Google Drive (PLAN.md #1). Restore not yet verified — do not
assume a restore would work until tested. `recovery/` remains a separate,
narrower backup of specific deleted rows only, not the corpus — the two are
not the same thing.

**4. `ingest_helloao.py` unconverted.** Own Supabase REST `.insert()` path, not
routed through `shared_ingest`. Live API, resume-safe, genuinely blocks the 8
further HelloAO commentaries in PLAN.md #27. This is the real chokepoint gap.

**5. `ingest_commentaries.py` — RESOLVED 2026-07-22, retired.** Read a
hardcoded `/tmp` SQLite dump that no longer exists; hard-shaped to one
collection's schema, no scraping or generic-format capability. Script
deleted, all dead references removed (commit `d4826dc`). **Framing:**
HistoricalChristianFaith commentary GROWTH is DEFERRED, not cut — rebuildable
from scratch later against a real source if Alex wants more from this
collection. The 307 documents already ingested (Augustine, Chrysostom,
Desert Fathers, Wesley, C.S. Lewis, etc. — under the `HistoricalChristianFaith
Commentaries Database` source) are untouched, remain live in the corpus, and
have no overlap with the HelloAO public-domain commentary set. See #15/#16
below for two findings about those 307 documents that surfaced during the
retirement audit and still need review.

**6. Guest→account conversion unlinked.** Email-confirmation session handoff
likely broken (cookie-vs-localStorage mismatch). Trace in `docs/audits/GUEST_AUTH_AUDIT.md`.

**7. Auth CTA inconsistencies.** `/library/authors` bypasses BetaGate and opens
the wrong modal mode; `/home` shows signup CTAs to logged-in users; dead
`AuthButton.tsx`. Trace in `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.

**8. Proposition backfill gap.** Unlicensed docs ingested before the wiring have
no propositions. Alias gaps remain for several entities — re-ingesting their
content sentinels silently. Counts unverified; query live.

**9. v4 propositions prompt — decision pending.**
`propositions.py::EXTRACTION_PROMPT_V4` exists (line 76), committed `ff0652c`,
but unwired. v3 remains the default (line 139). Calling v4 requires
`prompt_version="v4"` explicitly. Tested on 18 documents
(`docs/audits/proposition-v3-v4-comparison-2026-07-16.md`): median word count 40 → 60,
still short of the 80–150 target. Adopt, iterate, or discard — and if adopt,
decide on backfill.

**10. Precept Austin raw-source gap.** Fewer raw scrape files remain in
`sources/precept_austin/raw/` than there are ingested documents — some documents
have no local raw backing if re-verification is ever needed. Not cross-checked
against the excerpt-less figure in #8.

**11. `verify_chunk_alignment.py` docstring is stale.** Describes
`shared_ingest.py` insert modes (`psycopg2_batch` / `rest_per_chunk`) that no
longer exist — `insert_mode` was introduced in `fb575ae` (2026-07-13) and
collapsed away in the all-or-nothing rewrite.

**12. `jewish_perspectives` table is orphaned.** 2 rows, zero code references
outside migrations and docs.

**13. SP2 Study Panel — no real screen-reader pass has ever been run.**
Phase 9 (2026-07-17) fixed 5 real keyboard/ARIA gaps and verified them via
real keyboard interaction plus live accessibility-tree/DOM inspection
(`aria-expanded`, `aria-label`, `role`, `data-*` attributes) — that is a
genuine, live-proven check of what a screen reader *would* consume, but it
is not the same as actually running one. No VoiceOver, NVDA, or other
screen reader has been used against this panel. Don't treat Phase 9 as
having closed this — it closed the 5 gaps the structural/keyboard audit
could find and prove; a real screen-reader listen could still surface
things that audit can't (announcement phrasing, reading order, timing).

**14. Hebrew lexicon permission gate — SP2 Study Panel excludes Hebrew
entirely because of this, do not assume it's cleared.** The Hebrew brief
lexicon (TBESH) is NOT covered by the same CC BY 4.0 grant that clears
Greek (TBESG, TFLSJ) — its definitions are third-party (Abridged BDB,
Online Bible) and need Online Bible's own permission before use in any
project. Greek is unaffected; SP2's Interlinear/word-study rows already
only ever render Greek, structurally (confirmed live, Phase 8). Full
reasoning: PLAN.md Open Decisions #11. Gates any future Hebrew
interlinear/word-study work specifically — do not build against TBESH
until that permission is obtained.

**15. Attribution-mode mismatch on the 307 HistoricalChristianFaith
documents (found 2026-07-22, during `ingest_commentaries.py` retirement
audit) — RE-CHECKED 2026-07-31, still open, decision needed.** The
importer's insert set `citation_mode='citable'` on every row (confirmed via
the deleted script's full git history), but all 307 live rows are, and
remain today, `silent_context` — named historical authors (Augustine,
Chrysostom, Wesley, C.S. Lewis, etc.) served as unattributed background
rather than cited by name in the main chat path. Still unclear whether the
correction to `silent_context` was intentional (matching the design intent
for `source_kind='commentary'`, stated directly in `study.py`'s own code
comment) or accidental — no migration, commit, or script anywhere records
who made the change or when. Full re-investigation, plus two new findings
(license_status is source-level only and covers three not-safely-PD
authors; Study Mode always shows author names regardless of citation_mode):
`docs/audits/historical_commentary_attribution_and_copyright_audit_2026-07-31.md`.
Given attribution is core to Rhemata's positioning (CLAUDE.md invariant 7),
this still needs a real decision from Alex, not an assumption either way —
see that audit's five open questions.

**16. Copyright flag on the HistoricalChristianFaith source — EXPANDED
2026-07-31, still open.** Originally flagged 2026-07-22 for one document
(C.S. Lewis, d. 1963) sitting under a source marked
`license_status='public_domain'`, `visibility='shown'`. **Re-checked
2026-07-31 against the full 307-author roster: two more authors have the
same problem** — J.R.R. Tolkien (d. 1973) and Douglas Wilson (a living
author) — all three under the identical blanket `public_domain`/`shown`
source record as every ancient/medieval author in the set, because
license_status lives on the `sources` table only, with no per-document or
per-author override anywhere in the schema. G.K. Chesterton and J.B.
Lightfoot were also checked and already safely clear life-plus-70. Full
detail, sources cited:
`docs/audits/historical_commentary_attribution_and_copyright_audit_2026-07-31.md`.
Still wants the same fail-closed review named in the original finding —
verify actual copyright status or gate these three specifically — before
treating them as safely servable at face value. An existing admin-side
lever already exists if Alex wants an immediate interim mitigation: the
`source_toggles` row for `source_kind='commentary'` ("Historical
Commentaries") can pull the whole source from retrieval with one click;
confirmed currently `enabled=True` (not pulled).

---

## Resolved — removed from the blocker list 2026-07-17

- **Quote verifier "blocker" — premise dissolved.** Commit `0af69a6`
  (2026-07-10) retired the verified-verbatim-quote claim from the product
  entirely. `system_prompt.txt`, `POSITIONING.md`, and
  `docs/how-rhemata-handles-sources.md` now state paraphrase-and-cite as the
  live posture and verbatim quoting as future/planned. Nothing is waiting on a
  verifier. The old CLAUDE.md decision entry permitting "verbatim retrieval
  quotes up to 50 words" is stale and was removed.
- **Migration 058 "uncommitted"** — false. Committed `72476b7` (2026-07-09),
  working tree clean.
- **"Only ingest.py converted"** — false. `ingest.py`, `ingest_magazine.py`,
  `ingest_preceptaustin.py`, `ingest_lexicon.py` all route through
  `shared_ingest`. See blockers #4 and #5 for what actually remains.
- **v4 prompt "uncommitted"** — false. Committed `ff0652c`. Unwired is still
  true; see #9.

---

## Undocumented, now known

- `scripts/ingest_lexicon_runner.py` (2026-07-14) — batching/pacing driver over
  `ingest_lexicon`, drives `shared_ingest.ingest_document()` in checkpointed
  slices. Committed, was absent from the scripts table.
- `scripts/verify_chunk_alignment.py` — standalone embedding/content alignment
  spot-checker. Committed, was absent from the scripts table. See #11.

---

## Mobile UI

- **Pass A shipped:** floating-panel chat layout, full-bleed mobile shell,
  bottom tab bar (Study · Chat · Discover) hiding on keyboard focus via
  `ChatFocusContext`, circular floating menu button. **Correction
  2026-07-23:** the tab bar itself is now gated off by default behind
  `NEXT_PUBLIC_FULL_NAV_ENABLED` (chat-only beta, see the session entry at
  the top of this file) — this line describes what Pass A originally
  built, not what currently renders by default. `NEXT_PUBLIC_FULL_NAV_ENABLED=true`
  restores it exactly as described here.
- **Pass B pending:** `UsageRing` was pulled from the mobile top bar and has not
  been remounted in the sidebar drawer.

---

## Next

1. **#13 — route `ingest_helloao.py` through `shared_ingest`.** Sole remaining
   chokepoint conversion. Unblocks HelloAO commentary growth (#27) only, not
   corpus growth generally.
2. **#14 remainder — folder renames** (`lexicon/`→`stepbible/`,
   `documents/`→`inbox/`) + drop `jewish_perspectives` table.
3. **#15 — staging Supabase + backup/restore test.** Gates the core-serving
   band (#16–20).

(#1 — `sources/` backup — DONE 2026-07-19, restore not yet verified; see Open
blockers #3. Oldest item on the plan, no longer next.)

SP track: SP2 done (Phases 1–9), SP3 dissolved 2026-07-15 (absorbed into SP2
Phase 8, shipped `9415f11`). SP4 (teacher card content) shipped 2026-07-18 and
is now fully signed off (Alex's authenticated production pass, 2026-07-21 — all
four checks passed; see the reconciliation entry at the top of this file). SP
panel refinement (#42.5) is also done: Phase 1 (reference-persistence fix)
shipped 2026-07-19; Phase 2 (floating overlay) shipped 2026-07-21 (`fe310e2`),
built but not yet production-verified itself (see above). **Next SP item is #43
(SP5, mobile bottom-sheet)**, which reuses the overlay's shared open/swap/close
model. #38 (SP0 mobile mockup) completion status unverified — confirm before assuming.

#11/#12 are DONE (reuse path resolved 2026-07-13). The old "#11 → #12 → SP3"
chain no longer holds — all three links resolved.
