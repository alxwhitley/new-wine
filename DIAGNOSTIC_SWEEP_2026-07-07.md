# Diagnostic Sweep — 2026-07-07

**Method:** read-only. Code traced by grep/inspection; DB facts pulled live via psycopg2 (parsed `SUPABASE_DB_URL`, explicit keyword args); table existence via `to_regclass()` on a fresh connection. Zero writes, zero commits.

**Environment note:** the sweep instructions named `/Users/alexwhitley/Desktop/rhemata` as repo root. That path is a leftover stub from the 2026-07-06 folder move (contains only two orphaned copies of the marketing markdown files and a `.impeccable` hook cache). The actual repo is **`/Users/alexwhitley/rhemata`** (verified: `.git` present, HEAD = `c47bbd3`). All checks ran against the real repo.

---

## Findings table

| Check | Expected | Actual | Status | Notes |
|---|---|---|---|---|
| **A. Canonical text at quote-verification time** | Verifier exists; question is what it checks against | **No verifier exists anywhere in the codebase.** No full-document text field either; only chunks (heuristic, lossy reconstruction) | **drift** (severe) | See prose section below |
| **B. Sentinel hard-guard (admin UI)** | Guard built? | **Partially.** Sentinel *row mutation* is hard-guarded: `backend/app/routers/admin.py:428` and `:450` reject visibility/license-status changes with 403 (`_SENTINEL_SOURCE_ID` at `:20`); frontend locks the row (`AdminModal.tsx:1034-1071`, Lock icon, controls hidden). No delete-source endpoint exists at all (only `DELETE /admin/document/{id}`, `admin.py:232`) — sentinel deletion impossible by absence. **But** a guard that "blocks a save when document→source resolution falls to the sentinel" was never built — there is **no admin UI for assigning a source to a document at all** (doc edit endpoint accepts only title/author/content). Closest existing behavior: `youtube_ingest.py` refuses to ingest videos whose speaker resolves to sentinel (`needs_source` status) | **drift** (partial) | Guard exists for protecting the sentinel row itself; the assignment-time guard has no surface to live on yet |
| **C. `jewish_perspectives` table** | exists, 2 rows | Exists (`to_regclass` confirms), **2 rows**. Code references: **zero** — no reads or writes anywhere in `backend/`, `frontend/`, or `scripts/` | **match** | Fully orphaned table; CLAUDE.md's claim of "residual refs in frontend/app/library/* and backend/app/constants.py" is itself stale — those are gone too |
| **D. ingested/ disk-vs-DB** | ~5 files on disk absent from DB | 80 files on disk, **5 absent from DB**: `8.21.24 Prophetic Teaching - Prophetic Ministry.docx`, `murray_deeper_christian_life.pdf`, `murray_surrender.pdf`, `murray_waiting_on_god.pdf`, `murray_with_christ_in_school_of_prayer.pdf` | **match** | Per 2026-07-05 investigation: 3 of the Murray files are duplicate filenames of books already in the DB under other names (`murray_deeper.pdf`, `murray_waiting.pdf`, `murray_prayer.pdf`); `murray_surrender.pdf` ambiguous vs `murray_absolute_surrender.pdf`; the `.docx` is genuinely uningested |
| **E. Licensed sources** | 0 | **0** | **match** | The `'licensed'` gate branch remains unexercised by production data |
| **F. Backfill gap** | ~2,980 zero-prop unlicensed; 251 with props | **2,980** unlicensed docs with zero propositions; **251** docs with ≥1 proposition | **match** | Unchanged since 2026-07-05 sweep — no backfill has run |
| **G. Missing aliases** | Deere, Brown, Bedford, CLC missing | All four **still missing** — `source_aliases` has zero rows matching deere / michael brown / bedford / church life | **match** (drift unresolved) | New ingests of these names would still fall to sentinel |
| **H. Chokepoint state** | stub intact; latest migration; converted list | `psycopg2_batch` still unimplemented: absent from `_INSERT_MODES` (`shared_ingest.py:157-163`), `NotImplementedError` raised at `:235`. Latest migration on disk: **058_clf_aliases.sql** (note: untracked in git — never committed). Imports `shared_ingest`: **`ingest.py` only** (1 of 5). Unconverted: `ingest_magazine.py`, `ingest_preceptaustin.py`, `ingest_lexicon.py`, `ingest_commentaries.py` | **match** | |
| **I. Sentinel doc count** | 3 | **3** | **match** | |
| **J. Extraction model config** | Groq Llama 3.3 | `model="llama-3.3-70b-versatile"` **hardcoded** at `scripts/propositions.py:75` (inside `extract_propositions`; `temperature=0.2`, `max_tokens=8192`). Not env-configurable — changing models requires a code edit | **match** | Single call site; no other extraction-model config exists |
| **K. sources/ backup visibility** | — | Remote: single — `origin https://github.com/alxwhitley/rhemata.git` (fetch+push). `sources/` **is** gitignored (`.gitignore:10`, anchored to `/sources/` on 2026-07-06). Backup scripts/config: **none found** — no rsync/rclone/S3/tarball/Time Machine reference anywhere in `scripts/`, repo root, or `docs/` | **n/a (fact)** | Net: the `sources/` content (raw PDFs, transcripts, ingest workbook) exists only on this one Mac unless an out-of-repo backup exists that the repo can't see |

---

## Check A — Canonical text availability (prose)

**The verifier does not exist.** The question was "what source string does the verifier check quotes against" — the answer is that there is nothing to trace. An exhaustive search of `backend/app`, `frontend/`, and `scripts/` for verification logic (verbatim/exact-match/character/difflib/fuzz/substring-containment patterns) finds no code that checks generated quotes against source text — not at generation time, not as post-processing on the answer stream, not at render time.

**What exists instead is an instruction, not a mechanism.** The only "verbatim" enforcement in the serving path is a system-prompt rule to the LLM (`backend/app/system_prompt.txt:112`: retrieval mode may quote ≤50 words from citable sources; `:129`: never lift phrasing verbatim in other modes). The streaming code in `chat.py` extracts `<answer>` tags and forwards tokens as-is (`chat.py:918-939`) — no quote inspection of any kind. Similarly, `scripts/extract_book_quotes.py` populates the `book_quotes` table by *asking* Claude Haiku for exact passages, with no verification that the returned strings actually appear in the source.

**This directly contradicts shipped and internal positioning.** `POSITIONING.md:76` ("Brief quotes are machine-checked character-for-character against the source before they can be served... Rhemata structurally cannot [hallucinate quotes]"), `POSITIONING.md:145` ("served only when code-verified as exact source text"), and the live `/sources` marketing page (`frontend/app/sources/page.tsx`, "Every quote is verified — by code, not trust... enforced mechanically, not editorially") all describe a mechanism that has not been built. As of this sweep, the claim is aspirational.

**If the verifier were built today, what canonical text could it check against?**

1. **No full-document text field exists.** The `documents` table's only body-adjacent column is `content_summary` — live data shows it is a genuine summary, not full text: 619 of 3,796 docs populated, average ~597 chars, max 877 chars, versus e.g. 50,493 chars of chunk content for the same document (sampled 3 docs: summary is ~1–3% of chunk-text length). There is no separate full-text table.

2. **The only full-text path is reconstruction from chunks, and it is heuristic, not lossless.** The reader endpoint (`backend/app/routers/document.py:45-115`) rebuilds articles by concatenating chunks ordered by `chunk_index`, trimming a fixed `CHUNK_OVERLAP = 200` **characters** from every chunk after the first (`document.py:12, :92`). But the chunker (`backend/app/services/chunker.py:21-66`) overlaps by ~80 **tokens**, with the actual overlap varying per chunk because of boundary-adjustment logic (heading/paragraph/sentence break-points shrink chunks) and a trailing `.strip()` on each chunk. A fixed 200-char trim against a variable token-level overlap guarantees duplicated or dropped characters at most seams. Magazine chunks additionally carry `[Source | Ref]` metadata headers stripped by a bracket heuristic (`document.py:85-89`). Historical inconsistency compounds this: pre-refactor standalone ingest used 1000-char/200-char-overlap character splitting (per CLAUDE.md), so overlap semantics differ by ingest era and pipeline.

3. **Chunk ordering itself is not clean corpus-wide: 186 documents have non-contiguous or duplicate `chunk_index` sequences** (live query: `max(chunk_index) != count-1` or duplicate indexes). For those documents, even a smarter overlap-aware rebuild has gaps or collisions to resolve.

**Bottom line for the beta-tier / verifier design decision:** a character-for-character verifier cannot currently be implemented as specified, because no canonical text exists to verify against. Chunk `content` is the closest thing to ground truth (it is verbatim source text — the safest near-term check would be "quote must be a substring of at least one retrieved chunk," which sidesteps reconstruction entirely and tolerates the overlap). Verifying against *full documents* would require either a new full-text column populated at ingest (the chokepoint in `shared_ingest.py` has the full `body_text` in scope at exactly the right moment) or a repair of the 186 broken chunk sequences plus an overlap-aware reassembler.

**Open question (recorded, not acted on):** whether the `/sources` page's "verified by code" copy should be softened until the mechanism exists, or the mechanism built to match the copy — decision deferred to the follow-up design session.

---

*Report generated 2026-07-07. No changes made; nothing committed. All expected-vs-actual values verified live, not inherited from prior session notes.*
