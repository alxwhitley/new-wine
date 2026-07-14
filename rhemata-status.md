# rhemata-status.md

**As of:** 2026-07-14 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority: PLAN #12 is DONE — `ingest_lexicon.py` converted cleanly, no gate stop.** The highest-risk chokepoint conversion is complete: resolve/insert/chunk/embed/propositions now all route through `shared_ingest.ingest_document()`. All five Phase 1 checks confirmed clean before building (see this session below); Phase 2 built in full; Phase 3 proved on real lexicon data via throwaway titles, never touching the four real production STEPBible documents.
- **The chunk_fn override and the reuse/append mechanism both saw their first production use this session** — previously built generically (`chunk_fn` hook existed since the writer's original design; the append mechanism was built and proven synthetically last session) but never exercised by a real, converted caller until now. Both worked exactly as designed against real lexicon data.
- **The lexicon path is now ready for a full batch run** — not run this session (explicitly out of scope: proof entries only, single-entry + tiny two-entry append). A full run of all four lexicon files (STEPBible currently holds ~32,000 chunks total across them from the pre-conversion script) is a separate, later session's call. One design note surfaced and resolved with Alex before building: the old script's insert pacing/retry (2s sleeps, 5x retry, meaningful at thousands-of-entries scale) has no equivalent in the new one-shot atomic writer — resolved as the future full-batch runner's job (call the writer once per bounded slice of entries, using the append mechanism itself as the natural checkpoint) rather than something `shared_ingest.py` itself needs. No writer changes were made for this; it's a note for whoever builds that runner.
- **The Inline Study Panel's SP3 (interlinear/word-study tool rows) is unblocked at the ingest layer.** SP3's hard gate was "lexicon conversion (#12) done + word-level-tagged licensed text source confirmed" (PLAN.md) — the first half is now true. The second half (a word-level-tagged licensed text source) is a separate, unrelated confirmation SP3 still needs before it can actually start.

---

## This session (2026-07-14) — #12: convert `ingest_lexicon.py`

**One commit: `33e92b4`.** File touched: `scripts/ingest_lexicon.py` only — no migration needed this time (last session's `documents.ingest_completed_at` already covers this).

**Phase 1 (hard read-only gate — all five checks confirmed clean, no STOP triggered):**
- (a) Confirmed the current write path precisely: title-keyed find-or-create, one-chunk-per-entry formatting with truncation for unusually long entries, count-based resume, batched-and-paced insert with retry, propositions run directly (bypassing `shared_ingest.py` entirely) on the full joined text.
- (b) Confirmed `chunk_fn` cleanly expresses one-entry-one-chunk: a closure that ignores the writer's default token-chunker and the `body_text` argument entirely, returning the pre-formatted per-entry list captured at call time. No structural mismatch, no writer change needed.
- (c) Confirmed the gated-off path is correct for lexicon specifically: STEPBible's live `license_status` is `public_domain` (checked directly, not assumed), which the propositions gate already routes to `skipped_licensed` — and last session's writer treats that as a finished, stampable outcome, not an incomplete one. Verified in Phase 3, not just reasoned.
- (d) Confirmed the reuse/append mechanism (built and proven synthetically last session) needs zero modification to fit lexicon's real pattern — it was generalized FROM this exact script's shape in the first place.
- (e) Confirmed attribution resolves cleanly: a real `stepbible` alias already exists and points at the correct source, so the writer's resolve step hits no `ALIAS_MISS`.
- **One thing found beyond the three known edge behaviors, surfaced to Alex before building (not silently decided):** the pacing/retry logic described above. Alex's answer: the future full-batch runner's job, not the writer's — recorded above, no writer change made.

**Phase 2 (build):** Converted `ingest_file()` to route through `shared_ingest.ingest_document()`, using the `chunk_fn` override for one-entry-one-chunk and `on_existing="reuse"` for resume/append (or `"delete_and_reingest"` when `--delete` is passed — now a true atomic swap instead of a separate non-atomic pre-delete). Removed the now-duplicated local write logic entirely: `find_or_create_document()`, `insert_chunk_batch()`, `delete_document()`, the direct `propositions.process_document()` call, and the manual `embed_batch()`/`embed_one()` wrappers. Parsing, TSV-header detection, HTML stripping, and entry formatting are all unchanged — only the writing moved.

**Phase 3 (proof, real lexicon file data via throwaway document titles — never touching the four real production STEPBible documents, confirmed untouched before and after by chunk count):**
- **Single-entry test:** the real first TBESG entry, ingested through the real converted `ingest_file()`, lands as record + exactly one chunk, stamped, zero propositions, correct `source_id`. **Passed.**
- **Kill test:** a pre-commit kill on one real entry leaves zero trace. **Passed.**
- **Append test:** a second pass adding one real additional entry appends with continued numbering — verified by direct DB recomputation: the chunk sequence is exactly `[0, 1]`, the first pass's chunk row ID is byte-identical after the second pass (proof it was never re-touched), and the new chunk's stored content matches the real second dictionary entry exactly. **Passed.**
- **Re-run-no-op test:** a third pass with nothing new correctly no-ops (`already_complete`), touching the database not at all. **Passed.**
- **Gated-off confirmation:** propositions returned `skipped_licensed` on every pass; no lexicon document was ever treated as incomplete for lacking a paraphrase layer.
- Final sweep confirmed zero test-artifact rows anywhere; the four real STEPBible documents show identical chunk counts (5324 / 11034 / 10258 / 5709) and remain unstamped, exactly as before this session.

**Deliberately not done this session:** no full lexicon batch ran (proof entries only, per scope). The 2 genuinely-broken Precept Austin documents (own session). The remaining unconverted scripts (`ingest_helloao.py`, `ingest_commentaries.py`). The 551 untouched Sermonindex rows. `--time-limit`. CLAUDE.md's stale notes.

---

## Sermonindex / ingest-integrity thread — closed (history, compressed)

1. **Incident:** a real, time-capped Sermonindex ingest was killed mid-run, leaving two documents half-written but live.
2. **Diagnostic session:** traced the write sequence; found the paraphrase step couldn't distinguish "failed" from "genuinely empty."
3. **Propositions-honesty session:** fixed that ambiguity. Commit `42022a8`.
4. **Cleanup session:** removed the two broken documents, reset their source rows to pending.
5. **All-or-nothing writer session:** record + chunks + propositions now commit as one atomic transaction. Commit `6708060`.
6. **Redo/reuse dispatcher session:** completeness stamp + skip/redo/reuse-append, resolving PLAN #11 and Decision 9 together. Commit `1ec5226`.
7. **This session:** first real conversion to exercise the append mechanism and the chunk_fn override — PLAN #12. Commit `33e92b4`.

The original incident's thread is fully closed. #12 is downstream of it (it needed the append mechanism the incident's remediation produced) but is really PLAN's chokepoint-conversion track, not the incident thread itself — tracked here once more since this is where the mechanism's history lives.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — `0935697`.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`): DONE.** No production PA re-ingest has run.
- **#10 (convert `ingest_commentaries.py`): still next on this track**, whenever Alex picks it back up — untouched, independent of #11/#12.
- **#11 (build `on_existing="reuse"` chunk-dedup): DONE** — `1ec5226`.
- **#12 (convert `ingest_lexicon.py`): DONE this session** — `33e92b4`. No STOP triggered; one design question surfaced and resolved with Alex before building (see above). Full batch not run — separate session.
- **#13, #15–#37:** untouched.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain open, untouched.

---

## Open Flags

**New:**
14. **A full lexicon batch run is ready but not scheduled.** All four files (TBESG, TBESH, TFLSJ×2) can now be re-run for real through the converted script — but per the design note above, whoever runs it should think about slicing the work into bounded per-call chunks (a few hundred entries per `ingest_document()` call) rather than one call per file, so a mid-run failure only loses the current slice, not the whole file's remaining backlog.
15. **SP3's ingest-layer gate is cleared; its data-source gate is not.** PLAN.md's SP3 hard-gate had two parts — "#12 done" (now true) and "word-level-tagged licensed text source confirmed" (still open, unrelated to this session's work).

**Carried forward, unchanged:**
1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12). Now recurs for only two remaining unconverted scripts: `ingest_helloao.py`, `ingest_commentaries.py` (`ingest_lexicon.py` is converted as of this session).
2. **Magazine queue hard pre-ingest gate — 27 of 27 pending articles contaminated** (found at #8). Unresolved, untouched.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). Not exercised this session.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`. Untouched this session.
6. **PLAN.md #5.5 closing line is stale.** Needs Alex's explicit go-ahead on replacement wording.
7. **PLAN.md #14 drift.** Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.
10. **CLAUDE.md's "unconverted scripts" count is stale and now needs a second correction.** It still says "four" (`ingest_magazine.py`, `ingest_preceptaustin.py`, `ingest_lexicon.py`, `ingest_commentaries.py`) when the real count is now two (`ingest_helloao.py`, `ingest_commentaries.py`). Corrects in its own future docs pass, same as the "batch path deferred" note — not bundled here.
12. **PA's ~398 "excerpt-less" documents — 396 need `generate_excerpts.py`, not the writer, and 2 need a REDO healing run.** Neither run yet. Unrelated to this session.
13. **The "PA's survivability guard will now rarely fire" claim (from the #11 session) is still unconfirmed against real data.**

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — this session's real change (`scripts/ingest_lexicon.py`) was committed, plus this doc.

---

## Next Session Should

Alex's call between: (a) schedule the full lexicon batch run (mechanism proven, ready — see the slicing note above), (b) the short PA follow-up (run `generate_excerpts.py` against the 396 complete-but-unexcerpted docs; REDO the 2 genuinely-broken ones), or (c) #10 — convert `ingest_commentaries.py` (unrelated track). All three are independent and unblocked.
