# rhemata-status.md

**As of:** 2026-07-13 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** none open. `ingest_preceptaustin.py`'s batch loop is now survivable — a single excerpt-less doc colliding on `chunks(document_id, chunk_index)` no longer kills the whole run. This is an **interim guard, not #11**: skipped docs are still not updated, the excerpt-vs-chunks mismatch underneath is unchanged.
- **Next action:** #10 — convert `ingest_commentaries.py` (reuses `psycopg2_batch` + the existing `propositions_conn` hook, straight convert per Decision 8). **Resequencing note carried from last session, still unresolved:** #11 (the real reuse-path fix) is now higher priority than its position in the linear list suggests, since #9's conversion made its exposure live. This session's guard buys time — a real PA batch is survivable now — but does not remove the reason to move #11 earlier. Worth a scoping conversation with Alex, not a unilateral reorder.
- **Still true, unchanged by this session:** no production PA re-ingest has run. PA's ~1,778 already-ingested (excerpt-having) docs would still be skipped correctly by the pre-existing excerpt guard; the ~398 excerpt-less docs would now be skipped too (via the new interim guard) rather than crash the batch — but "skipped" is not "corrected." A real batch run today would produce a clean-looking summary reporting ~398 skips, which is expected and correct to report, but does not mean those 398 docs got updated in any way.

---

## This session (2026-07-13, interim guard) — PA batch loop survivability

One commit: **`82ce9e4`**.

**What changed, narrowly:** `ingest_preceptaustin.py`'s `main()` loop now wraps each file's `ingest_file()` call in a `try/except psycopg2.errors.UniqueViolation`. A new helper, `_is_chunk_index_collision(exc)`, checks `exc.diag.constraint_name == "chunks_document_id_chunk_index_key"` — the loop catches ONLY that exact, expected, benign case (this document's chunks are already present) and re-raises everything else, including a `UniqueViolation` on any *other* constraint. Tally split into three buckets (`processed` / `skipped_duplicate` / `skipped_other`, the last covering the guard's own pre-existing bad-filename/empty-file/excerpt-exists skips) and an end-of-run summary prints total files seen, all three counts, and the skipped-duplicate filenames (first 20 + a remainder count if more). Exits 0 on a clean run with skips — skipping already-present docs is expected behavior for PA, not a failure signal.

**Connection-state check, done not assumed (per this session's explicit ask):** verified by reading `shared_ingest.py` (unmodified this session) that both `_insert_chunks_psycopg2_batch` and `_run_propositions` open their own `psycopg2` connection per call and close it in a `finally` block regardless of outcome — no connection or transaction is shared across loop iterations, so a caught rejection cannot leave a poisoned session behind for the next document. Confirmed empirically too (see proof below): fresh documents processed immediately after a caught collision wrote correctly.

**Proof, synthetic only, no production data touched:**
- Pre-inserted one document ("collidealpha", 3 chunks, deliberately no excerpt row) via a direct `shared_ingest.ingest_document()` call, replicating the exact already-ingested-but-excerpt-less state the real #11 hole describes.
- Built a 3-file test batch (the pre-existing collider + two fresh word studies) and ran the real, converted script (`python3 scripts/ingest_preceptaustin.py --source-dir ...`) from this main session — not a subagent, so Rule 10 was never in play regardless.
- Result matched exactly: the colliding file was skipped with a clear log line naming the constraint, the loop continued, both fresh files processed normally. End-of-run summary: 3 seen, 2 processed, 1 skipped-duplicate (named), 0 skipped-other. **Exit code 0.**
- Verified off the live DB: the collided document still had exactly 3 chunks (no duplication, no partial write — the per-document transaction rolled back cleanly); both fresh documents existed with correct chunk counts and `full_text` populated.
- Narrowness proven directly, not just asserted: fed the real `_is_chunk_index_collision()` function (via a verbatim copy of the loop's own try/except structure) three rigged cases — a `UniqueViolation` on a fabricated *different* constraint name (correctly NOT caught, propagated), a completely unrelated exception type simulating "the loader itself is broken" (correctly NOT caught, propagated), and the real expected case with the correct constraint name (correctly caught). All three matched the intended behavior.
- Cleaned up all three synthetic documents (chunks + document rows + propositions, though PA's structural lockout means propositions were never at risk) and confirmed zero remaining across all three tables for all three doc_ids.

**Deliberately not done:** no fix to the excerpt-keyed reuse guard itself, no retry/update-on-conflict logic, no real PA batch run against the actual corpus. All of that stays #11's job.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — `0935697`.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`): DONE.** Loader: `ffc8c81` + `fb575ae`. Conversion: `c678514`. Interim survivability guard (this session, not part of #9's original scope but directly downstream of it): `82ce9e4`. No production PA re-ingest has run.
- **#10–#13, #15–#37:** untouched. #10 next.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain open, untouched.

---

## Open Flags — carried forward, one narrowed further this session

1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12; `ingest_preceptaustin.py` removed from the list last session). Unchanged this session — the guard built here is unrelated to Rule 10 (it fires inside the script's own loop, not at the PreToolUse layer). Still recurs at #10–13 for the remaining unconverted/stale-listed scripts.
2. **Magazine queue hard pre-ingest gate — 27 of 27 pending articles contaminated** (found at #8). Unresolved, untouched.
3. **`on_existing="reuse"` PATTERN — two known holes, now SURVIVABLE but still open.** Holes (1) unconditional re-chunk/re-insert and (2) document-row/`full_text` skipped on reuse remain unchanged — still #11's job. **This session's addition:** a real re-run hitting hole (1) no longer crashes the batch (this session's guard), but still does not correct anything — a colliding doc is silently-to-the-batch-but-visibly-in-the-log skipped, staying stale in the DB. Do not read "survivable" as "fixed." #11 resequencing is still an open conversation with Alex, not resolved by this guard.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). Not exercised this session.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`. Untouched this session (this session edited `ingest_preceptaustin.py`, not the harness gate files).
6. **PLAN.md #5.5 closing line is stale.** Needs Alex's explicit go-ahead on replacement wording.
7. **PLAN.md #14 drift.** Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift, last touched 2026-07-10/11 — not this session's work) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — the one file this session actually edited (`ingest_preceptaustin.py`) plus this doc were both committed, nothing left as carve-out drift.

---

## Next Session Should

Either (a) convert `ingest_commentaries.py` (#10, straight convert, reuses `psycopg2_batch` + `propositions_conn`), or (b) raise the #11 resequencing question with Alex explicitly before doing anything else — this session's guard means there's no longer time pressure forcing #11 forward (a real PA batch won't crash), but the underlying correctness gap (excerpt-less docs never get corrected on reuse) is unchanged and now two sessions old. Either is a reasonable next step; which one is Alex's call, not a default.
