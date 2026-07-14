# rhemata-status.md

**As of:** 2026-07-13 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority: the Sermonindex remediation thread is DONE.** The writer that produced the incident is fixed — `shared_ingest.ingest_document()` now writes a document record + all its chunks + propositions as one atomic transaction, proven by a kill test, a paraphrase-failure test, a gated-off test, and a full round-trip test (all passed, all throwaway artifacts deleted and independently verified gone). The two documents the original incident broke were already cleaned up and re-queued last session, untouched this session (confirmed still pending, still absent from the DB).
- **Next action / next conversation:** the "already-ingested"/skip-check logic (`already_ingested()` — pure existence check, not completeness) was deliberately left untouched again this session, same as the propositions-honesty session. Whether/how its design merges with PLAN #11's `on_existing="reuse"` fix is an open decision for Alex, not resolved by this session. That's the next conversation, not a next build.
- **Separately, still true, unchanged by this session:** the PA/#9-#11 batch-loop track below is otherwise untouched (aside from two small mechanical fixes this session made *to* `ingest_preceptaustin.py` as a necessary consequence of changing the writer it calls — see below, not a #10/#11 advance). #10 (`ingest_commentaries.py` conversion) is still the next step on that track whenever Alex picks it back up; the #11 resequencing conversation with Alex is still open.
- **A stale-fact correction surfaced this session, worth knowing for future scoping:** CLAUDE.md's shared_ingest decision entry (and this file's own prior wording) said four scripts were unconverted: `ingest_magazine.py`, `ingest_preceptaustin.py`, `ingest_lexicon.py`, `ingest_commentaries.py`. That's stale — checked directly against the code this session: `ingest_magazine.py` and `ingest_preceptaustin.py` **are** converted (they call `shared_ingest.ingest_document()` directly; `ingest_magazine.py`'s conversion is #8, already marked DONE below — this file just hadn't updated the "four unconverted" framing to match). The real unconverted set today is three: `ingest_lexicon.py`, `ingest_helloao.py` (not in the original "four" at all — added since), and `ingest_commentaries.py`, all of which call `propositions.process_document()` directly and bypass `shared_ingest.py` entirely. Not corrected in CLAUDE.md this session (that's its own docs-only pass, same as the "batch path deferred" note) — flagging here so the next session doesn't scope work off the stale count.

---

## This session (2026-07-13) — the all-or-nothing writer

**One commit: `6708060`.** Files touched: `scripts/shared_ingest.py` (the writer itself), plus two small, necessary companion fixes to its real callers — `scripts/ingest.py` and `scripts/ingest_preceptaustin.py` (see below for why those were in scope).

**Phase 1 (read-only, could have stopped the session — it didn't):**
- Confirmed the existing atomic batch-chunk-insert path is real and genuinely all-or-nothing (single transaction, explicit rollback + re-raise on error) — CLAUDE.md's "deliberately deferred" note is confirmed stale, left uncorrected as instructed (separate docs pass). But it only ever covered chunks, not the document record — the record was still written first, separately, via the REST client.
- The crux question — can record + chunks + propositions share one transaction — resolved cleanly: the document record's REST-based insert was the only piece not already using psycopg2; chunks (batch mode) and propositions already did. Converting the record insert to psycopg2 and sharing one connection across all three was a contained, single-session change, not a bigger refactor.
- Traced every real caller of `ingest_document()` to check blast radius (this is where the stale "four unconverted scripts" fact, above, was caught) — confirmed exactly three: `ingest.py`, `ingest_magazine.py`, `ingest_preceptaustin.py`. The other three scripts don't call this function at all, so restructuring it can't affect them.
- Confirmed `propositions.process_document()`'s three-way outcome (`stored:N` / `no_propositions` / `error`, from last session's `42022a8`) is cleanly string-matchable.

**Phase 2 (build):**
- `ingest_document()` now computes chunks, embeddings, and (implicitly, via the unmodified `propositions.process_document()`) the paraphrase result before anything is durably written, then opens ONE psycopg2 connection for the document record + all chunks + propositions together.
- The key design insight: `propositions.process_document()` already commits internally on success and rolls back internally on failure (that's exactly what last session's fix produced) — by handing it the SAME connection the record and chunks were staged on, its own existing commit/rollback becomes the single all-or-nothing boundary for the *entire* document, with no changes needed to `propositions.py` at all (left fully untouched, as scoped).
- `insert_mode` (the old `"rest_per_chunk"` vs `"psycopg2_batch"` choice) is gone — the shared-connection atomic path is now the only path, since keeping a non-atomic alternative around would have defeated the point. This required two small, mechanical companion fixes to stay correct: `ingest_preceptaustin.py` passed `insert_mode="psycopg2_batch"` explicitly (removed — one line, no behavior change since that's now the only mode) and `ingest.py`'s `ingest_file()` had no explicit handling for the new `"failed"` status (previously anything non-"skipped" was silently treated as success — fixed to return `("failed", reason)` instead, since otherwise the youtube pipeline call site that this whole effort exists to protect would have kept silently reporting paraphrase failures as done). `ingest_magazine.py` and `ingest_preceptaustin.py`'s own status-handling were already safe as written — checked, not assumed.
- Gated-off sources (public_domain, owned, Precept Austin) are unaffected in the way that matters: `process_document()`'s existing gate still decides whether paraphrase runs at all, and the writer commits record + chunks regardless of that outcome, never blocking a document for lacking a propositions layer it was never supposed to have.

**Phase 3 (proof, all on throwaway documents, all deleted and independently reconfirmed gone afterward):**
- **Kill test:** staged a document record + one chunk on an open transaction using the writer's own internal functions, then closed the connection without committing (the same thing Postgres does on an actual process kill). Zero trace afterward — no record, no chunk, no proposition. **Passed.**
- **Paraphrase-failure test:** forced the model call to fail on a real gated-on (unlicensed) source. `ingest_document()` returned `status="failed"` without the overall call crashing, and nothing was written for that document. **Passed.**
- **Gated-off test:** a real public_domain source landed whole — record + all expected chunks — with propositions correctly and deliberately skipped (`skipped_licensed`), reported as `status="processed"`, not a failure. **Passed.**
- **Full round-trip test:** a real gated-on source, unmocked, landed whole end-to-end — record, chunk, and a genuinely stored proposition, all inside the one transaction. **Passed.**
- Final sweep confirmed zero rows anywhere matching any of the test titles.

**Deliberately not done this session:** the skip-check (`already_ingested()`) is untouched — still a pure existence check, still the thing that would let a future incomplete document (if one somehow existed) block a clean retry forever. That's explicitly the next conversation, not resolved here. The two re-queued Carter Conlon rows were confirmed untouched (still `triaged`, still absent from the database) — not re-ingested this session. No real/production ingest ran. `--time-limit` untouched. The stale CLAUDE.md note stays stale until its own docs pass.

---

## Sermonindex remediation thread — full sequence (now closed)

1. **Incident:** a real, time-capped Sermonindex ingest was killed by something external partway through, leaving two documents half-written but live.
2. **Diagnostic session (read-only):** traced the write sequence, found three separate commit steps with no rollback across them, and found the paraphrase step couldn't distinguish "failed" from "genuinely empty." Recommended options; built nothing.
3. **Propositions-honesty session:** fixed the paraphrase-step ambiguity. Commit `42022a8`.
4. **Cleanup session:** removed the two broken documents, reset their source rows to pending. No code changes.
5. **This session:** built the all-or-nothing writer itself. Commit `6708060`.
6. **Still open, separately:** whether the skip-check's design should change (and how that interacts with PLAN #11) — an explicit next conversation with Alex, not a build.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list — unrelated to, and untouched by, the Sermonindex thread above, aside from the two small companion fixes noted this session)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — `0935697`.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`): DONE.** Loader: `ffc8c81` + `fb575ae`. Conversion: `c678514`. Interim survivability guard: `82ce9e4`. This session's writer rework touched `ingest_preceptaustin.py` only mechanically (removed its now-obsolete `insert_mode` kwarg, updated two comments describing the old two-connection architecture) — no change to its own PA-specific logic or its known reuse-path holes. No production PA re-ingest has run.
- **#10–#13, #15–#37:** untouched. #10 next, whenever this track is picked back up.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain open, untouched.

---

## Open Flags

**Sermonindex remediation thread — both resolved this session:**
8. ~~`shared_ingest.py` doesn't yet act on the paraphrase-step's honest failure signal~~ — **RESOLVED.** It now does, as the writer's own commit/rollback boundary.
9. ~~The all-or-nothing writer itself is still unbuilt~~ — **RESOLVED.** Built and proven this session, commit `6708060`.

**New, replacing them:**
11. **The skip-check's design is an open decision, not yet scheduled.** `already_ingested()` still only checks existence, not completeness. With the writer now genuinely atomic, a future incomplete document should be structurally impossible from *this* writer — but the skip-check itself hasn't changed, and its relationship to PLAN #11's reuse-path fix is still an open conversation with Alex.

**Carried forward, unchanged (PA/#9-#11 track):**
1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12). Still recurs at #10–13 for the remaining unconverted/stale-listed scripts.
2. **Magazine queue hard pre-ingest gate — 27 of 27 pending articles contaminated** (found at #8). Unresolved, untouched.
3. **`on_existing="reuse"` PATTERN — two known holes, survivable but still open** (unconditional re-chunk/re-insert; document-row/`full_text` skipped on reuse). Still #11's job — the writer rework preserved this path's existing behavior exactly, did not fix it.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). Not exercised this session.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`. Untouched this session.
6. **PLAN.md #5.5 closing line is stale.** Needs Alex's explicit go-ahead on replacement wording.
7. **PLAN.md #14 drift.** Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.
10. **CLAUDE.md's "four unconverted scripts" count is stale** (see Current Priority above) — corrects in the same future docs pass as the "batch path deferred" note, not bundled here.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — this session's real changes (`shared_ingest.py`, `ingest.py`, `ingest_preceptaustin.py`) were committed, plus this doc.

---

## Next Session Should

Have the skip-check/PLAN-#11 sequencing conversation with Alex — decide whether `already_ingested()` needs a completeness check now that the writer is atomic (structurally, a document written by the new path can no longer be incomplete, but the check itself hasn't changed to reflect or rely on that), and how that decision interacts with PLAN #11's separate `on_existing="reuse"` fix. Once that's settled, either that becomes the next build, or the PA/#10 track (`ingest_commentaries.py` conversion) picks back up on its own separate schedule — Alex's call.
