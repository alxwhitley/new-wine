# rhemata-status.md

**As of:** 2026-07-13 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** none open. **#9 is DONE** — `psycopg2_batch` built and proven (prior session), `ingest_preceptaustin.py` converted and proven (this session). Read the caveats below before treating "done" as "nothing left here": no production re-ingest of the real PA corpus has run, and two adjacent things stay explicitly open.
- **Next action:** #10 — convert `ingest_commentaries.py`, which reuses the same `psycopg2_batch` mode plus the existing `propositions_conn` connection-reuse hook. Per PLAN.md: "straight convert, no atomicity rework" (Decision 8 already dropped commentaries' atomic doc+chunks transaction).
- **Not this session, still owed:**
  - **No real PA batch has been run.** PA's ~1,778 already-ingested files were never touched. A future real re-run of `ingest_preceptaustin.py` (no `--source-dir`) will: skip the 1,778 docs that already have a `word_study_article` excerpt (unchanged guard, correct); for the ~398 that don't, it will **reuse the doc_id and attempt to re-insert chunks at the same `chunk_index` values already in the DB — migration 061's `UNIQUE(document_id, chunk_index)` constraint will now reject that loudly (a raised `psycopg2.IntegrityError`), crashing that file's ingest and, since `main()`'s loop has no per-file exception handling, likely the whole batch run.** This is the reuse path, and it's `#11`'s job to fix (chunk-count lookup + positional-skip + continued numbering), not patched here.
  - **Rule 10's substring-match weakness (Open Flag #1) is unchanged as a mechanism** — `ingest_preceptaustin.py` was removed from `UNCONVERTED_INGEST_SCRIPTS` this session (so the freeze no longer fires on it specifically), but the underlying bare-substring-match approach in `check_rule_10_freeze()` is untouched and still affects `ingest_magazine.py` (already converted, still listed — deliberately not fixed here either, per Flag #1's own "not fixed piecemeal" note), `ingest_lexicon.py`, `ingest_commentaries.py`, `ingest_helloao.py`.

---

## This session (2026-07-13, PA conversion) — #9 closed out

Three parts, real code change + two proof runs, one commit for the code:

**Part 1 — conversion, commit `c678514`.** `ingest_preceptaustin.py`'s insert path now hands off to `shared_ingest.ingest_document(insert_mode="psycopg2_batch")`. Everything PA-specific stayed caller-side, unchanged: hardcoded `is_copyrighted=True`/`citation_mode='silent_context'`, filename parsing (`G1459_egkataleipo` → strongs/transliteration) + `index.json` gloss lookup, and — most load-bearing to leave untouched — the excerpt-keyed reuse/skip guard (`excerpts.excerpt_type='word_study_article'`), wired into the shared writer via its existing `find_existing_fn`/`on_existing="reuse"` hooks rather than reimplemented. The local `embed_batch()`/`insert_chunks_psycopg2()` functions were removed (subsumed by the shared writer — this is what "convert" means, not scope creep). Added `--dry-run`/`--source-dir` safe-test flags matching #8's established pattern; the pre-existing manual `--language` `sys.argv` parsing was left completely untouched (new argparse uses `parse_known_args()` specifically so it doesn't collide with it). `guard_pretooluse.py`'s `UNCONVERTED_INGEST_SCRIPTS` updated to drop `ingest_preceptaustin.py` — verified via regex unit check, not assumed.

**Part 2 — dry-run proof on a real file, no writes.** Copied one real PA source file (`G0005_abba.txt`) into an isolated scratch directory and ran `--dry-run --source-dir`. Confirmed: filename parsed to `strongs=G0005, transliteration=abba`; `index.json` resolved `english_word=Abba` (out of 1,859 real entries); title built correctly; metadata printed correctly (`is_copyrighted=True`, `citation_mode=silent_context`, source correct); 50 real chunks built from the real file content. Zero DB reads or writes — dry-run returns before the existing-document lookup even runs.

**Part 3 — single real-write proof, fabricated item, from this main session.** Built a synthetic PA-shaped file (`G9999_synthetictestproof.txt` — `G9999` confirmed absent from the real 1,859-entry index, so it cannot collide with any real word study) in an isolated directory, ran the converted script for real (no `--dry-run`) from this orchestrating session — not a subagent, so Rule 10's freeze had no occasion to apply regardless of the list update. Result: resolved to the real Precept Austin source (`698e0596-…`, via `source_name`), new document inserted, 12 chunks batch-inserted, `propositions: skipped_precept_austin` (lockout held). Verified off the live DB, not stdout:
1. **Reconciliation:** attempted 12, `SELECT count(*)` = 12. Match.
2. **Alignment spot-check** (`verify_chunk_alignment.py`, all 12 chunks): cosine similarity 0.999999–1.0.
3. **Index integrity:** zero duplicate `chunk_index` rows.
4. **Metadata + conversion tripwire:** `is_copyrighted=true`, `citation_mode='silent_context'`, `source_id` matched the real Precept Austin source exactly, **`full_text` populated (18,541 chars, matching the synthetic body exactly)** — proves the run went through `ingest_document()`, not a bypass. (Previous baseline: 0/2,176 real PA docs have `full_text` populated, since none have been touched by the chokepoint yet.)
5. **Propositions:** 0 rows — PA lockout held under the real conversion path, not just in isolation.

Cleaned up immediately after: explicit `propositions` delete (belt-and-braces, PA lockout already made this a no-op) + `shared_ingest._delete_document()`, then a fresh `SELECT count(*)` across all three tables confirmed zero remaining. No trace of the test item survives in the DB.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`. Full design history in CLAUDE.md.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — `0935697`.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`): DONE.** Loader: `ffc8c81` (precondition) + `fb575ae` (build), proven on synthetic data. Conversion: `c678514`, proven on a real-file dry-run + a fabricated real-write, both this session. **No production PA re-ingest has run** — see "Current Priority" caveats above; the reuse path for the 398 excerpt-less real docs stays open at #11.
- **#10–#13, #15–#37:** untouched. #10 (`ingest_commentaries.py`) is next — reuses `psycopg2_batch` + the existing `propositions_conn` hook.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain genuinely open, untouched.

---

## Open Flags — carried forward, one narrowed this session

1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12). **Narrowed this session:** `ingest_preceptaustin.py` removed from `UNCONVERTED_INGEST_SCRIPTS`, so the freeze no longer fires on it at all (verified via direct regex check, not assumed) — this specific instance is closed, not by fixing the mechanism, but by the script no longer needing to be on the list. The mechanism itself is unchanged and will recur identically at #10–13 (`ingest_magazine.py` — already converted, deliberately still listed, not touched again this session; `ingest_lexicon.py`, `ingest_commentaries.py`, `ingest_helloao.py` — still exposed). Needs its own harness session.
2. **Magazine queue hard pre-ingest gate — 27 of 27 (100%) pending articles contaminated** (found at #8, 2026-07-12). Unresolved, untouched this session.
3. **`on_existing="reuse"` PATTERN — two known holes, exercised for real by a converted script for the first time this session.** Holes (1) unconditional re-chunk/re-insert and (2) document-row/`full_text` skipped on reuse remain unchanged and unfixed — still #11's job. **New this session:** `ingest_preceptaustin.py` is now the first *converted* script to actually invoke `on_existing="reuse"` (via its excerpt-keyed `find_existing_fn`), so this is no longer a theoretical future exposure for the chokepoint's own hook — it's live, gated only by the fact that no production PA batch has been run yet. The migration `061` constraint means the first real re-run to hit an excerpt-less PA doc will raise loudly rather than duplicate silently — better than before, but still an uncaught crash of the whole batch (`main()`'s loop has no per-file exception handling for this). Do not run a real PA batch before #11 lands, or budget for that crash explicitly.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). Not exercised this session — done directly by the orchestrating session with explicit DB verification, not the executor/planner-reviewer loop.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`. Its own separate session. (This session edited `guard_pretooluse.py` directly from the main session, which has always been permitted — this flag is about *subagents* editing it unchecked, unaffected either way.)
6. **PLAN.md #5.5 closing line is stale.** Needs Alex's explicit go-ahead on replacement wording.
7. **PLAN.md #14 drift.** Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift, last touched 2026-07-10/11 — not this session's work) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — every file this session actually created or edited (`ingest_preceptaustin.py`, `guard_pretooluse.py`, this doc) was committed, none left as carve-out drift.

---

## Next Session Should

Convert `ingest_commentaries.py` (#10) — reuses `psycopg2_batch` and the existing `propositions_conn` connection-reuse hook; per PLAN.md, a straight convert with no atomicity rework (Decision 8 already accepted losing the atomic doc+chunks transaction). Separately, and not bundled into #10: #11 (the `on_existing="reuse"` chunk-dedup fix) is now higher-priority than its position in the linear list might suggest, since #9's conversion makes its exposure live rather than theoretical — worth a scoping conversation with Alex about resequencing, not a unilateral reorder here.
