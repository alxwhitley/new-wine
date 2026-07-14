# rhemata-status.md

**As of:** 2026-07-13 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority: PLAN #11 is DONE, in full — not a mid-point stop.** The shared writer's "found an existing document" dispatcher is built: skip / redo (atomic swap) / reuse-append (continued numbering, the re-chunk-from-0 bug fixed), plus a completeness stamp (migration 062, `documents.ingest_completed_at`) written inside the writer's own atomic transaction. All four Phase 2 steps landed in one session; none deferred.
- **Next action: #12 (`ingest_lexicon.py` conversion) is unblocked** — the mechanism it needs (continued-numbering append) now exists and is proven, including a two-pass incremental-build test verified by direct database recomputation, not self-report. Converting the script itself is still its own separate session, not done here.
- **A real, evidence-based finding worth carrying forward:** of Precept Austin's 398 "excerpt-less" documents (previously an open question under PLAN #11), **396 are actually complete** — checked directly by re-chunking each one's real raw source file and comparing to its actual stored chunk count. PA's own skip-check tests for an unrelated downstream artifact (`generate_excerpts.py`'s output), not ingestion completeness, so it was flagging complete documents as suspect. Only **2 of the 398 are genuinely broken** (zero chunks — the same two "Word Study: Fortunes" / "Word Study: Innocent" docs flagged in an earlier diagnostic). REDO is the correct healing mechanism for those 2 specifically. **Not healed this session** — the healing run is explicitly its own session, and no real Precept Austin document was touched. Worth noting: as a side effect of this session's general fix, if `ingest_preceptaustin.py` is ever run for real again, the 396 complete "excerpt-less" docs should now gracefully no-op (`already_complete`) instead of raising the `UniqueViolation` its interim survivability guard currently catches — this was reasoned through, not run against real PA data this session, so treat it as a strong expectation to confirm, not a proven fact.
- **Decision 9 (skip-check ∕ #11 overlap) is resolved.** Alex's call: stamp-based completeness, merged with #11 as one build (matching Decision 9's "current lean: merge"). The skip-check itself (`already_ingested()`, the URL/filename existence check) is still untouched by design — completeness is now knowable via the stamp for any FUTURE code that wants to check it, but nothing this session wires the plain "skip" path to read it. Skip stays a pure existence check, exactly as Alex specified: "skip stays default and applies to stamped AND unstamped docs."

---

## This session (2026-07-13) — the redo/reuse dispatcher + completeness stamp

**One commit: `1ec5226`.** Files touched: `migrations/062_documents_ingest_completed_at.sql` (new) and `scripts/shared_ingest.py`. Repo precedent (`55e46f1`, the `full_text` migration + its shared_ingest.py wiring) bundles a migration with the code that uses it in one commit — followed that convention here.

**Phase 1 (read-only, could have stopped the session — it didn't):**
- Confirmed all three `on_existing` hooks (skip/reuse/delete_and_reingest) exist; `skip` works and is unused by any real caller today; `reuse` (used by `ingest_preceptaustin.py`) has the confirmed re-chunk-from-0 bug; `delete_and_reingest` is defined but unused, and its delete goes through the REST client as a separate, already-committed step — not atomic with the fresh write that follows.
- Read `ingest_lexicon.py` in full: it doesn't go through `shared_ingest.py` at all today (bespoke resume logic: re-chunks the whole file every run, skips whatever's already stored by count, appends the rest). That's the exact shape #11's general mechanism needed to generalize for #12's future conversion.
- **The Precept Austin finding above** — checked by direct recomputation against real raw files, not assumed.
- Confirmed the stamp needs a `documents` migration; drafted and applied `062` (nullable `ingest_completed_at`, forward-only, no backfill — matching the `060_documents_full_text.sql` precedent), verified on a fresh connection before touching any code.
- No STOP condition triggered: the atomic swap fits in one transaction (delete + fresh insert, same connection); continued numbering is safe against the uniqueness constraint by always resuming from `MAX(chunk_index)+1`; the hook architecture didn't need a bigger refactor.

**Phase 2 (build, all four steps landed — no mid-point stop needed):**
1. Migration 062 applied and verified.
2. The writer now writes `ingest_completed_at = now()` inside its existing atomic transaction, if and only if the document lands whole under the same gated "finished" definition from last session (paraphrase ran to completion, or correctly doesn't apply).
3. `skip` unchanged — applies identically to stamped and unstamped documents, never consults the stamp. `delete_and_reingest` is now a true atomic swap: the old document's delete (cascading via foreign keys to its chunks/propositions/excerpts) and the new document's full write happen in the same transaction as everything else — confirmed the cascade behavior directly against the database rather than assuming it (`chunks`, `propositions`, and `excerpts` all `ON DELETE CASCADE` from `documents`).
4. `reuse` now re-chunks the current full body text, finds the next free chunk_index by direct query, and appends only the new tail with continued numbering — chunk_index values already present are never re-touched. If a fresh re-chunk finds nothing new past what's already stored, it's a clean no-op (`status=skipped, reason=already_complete`) that touches the database not at all.

**Phase 3 (proof, all on throwaway documents, all deleted and independently reconfirmed gone afterward; one real legacy document read from but never written to):**
- **Stamp test:** a fresh document lands stamped on success. A simulated kill before the final write (staged, connection closed without committing — the same thing Postgres does on a real kill) leaves zero trace and no stamp. **Passed.**
- **Skip test:** re-running against a stamped throwaway returns it untouched. A real, genuinely unstamped legacy document (`ingest_completed_at IS NULL`) is also skipped by the same default path — checked directly against a real document, confirmed unchanged before and after (skip touches nothing, by construction, so this was safe to test against real data). **Passed.**
- **Redo test:** a simulated kill mid-swap (delete + fresh insert staged, connection closed without committing) leaves the OLD document exactly as it was — same id, same chunks. A real redo swaps cleanly to a new id with the new content, fully stamped. **Passed.**
- **Reuse test:** a two-pass incremental build (a small custom chunker for a cheap, precise test) appended correctly — verified by direct database recomputation, not self-report: the final chunk_index sequence is exactly `0..5` with no gaps or duplicates, AND the first pass's three chunk row IDs are byte-identical before and after the second pass (proof they were never re-touched, not just that the count matches). A third pass with nothing new to add came back as a clean no-op. **Passed.**
- Final sweep confirmed zero test-artifact rows anywhere.

**Deliberately not done this session:** healing the 2 genuinely-broken PA documents (explicitly its own session). Converting `ingest_lexicon.py` itself (PLAN #12, a separate session — this session only built the mechanism it needs). The skip-check (`already_ingested()`) itself is untouched. The two re-queued Carter Conlon rows were not touched and do not re-ingest until a normal future queue run. No real/production ingest ran. `--time-limit` untouched. CLAUDE.md's stale notes (batch path "deferred," the "four unconverted scripts" count) are still stale — their own docs pass, not bundled here.

---

## Sermonindex remediation thread — closed (history, compressed)

1. **Incident:** a real, time-capped Sermonindex ingest was killed by something external partway through, leaving two documents half-written but live.
2. **Diagnostic session (read-only):** traced the write sequence; found the paraphrase step couldn't distinguish "failed" from "genuinely empty."
3. **Propositions-honesty session:** fixed that ambiguity. Commit `42022a8`.
4. **Cleanup session:** removed the two broken documents, reset their source rows to pending.
5. **All-or-nothing writer session:** record + chunks + propositions now commit as one atomic transaction. Commit `6708060`.
6. **This session:** the redo/reuse dispatcher + completeness stamp, resolving PLAN #11 and Decision 9 together. Commit `1ec5226`.

This thread is now fully closed — no further open items from the original incident remain unaddressed at the writer level. The two genuinely-broken PA documents found along the way are a separate, adjacent cleanup item (see Current Priority above), not part of the original Sermonindex thread.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — `0935697`.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`): DONE.** Loader: `ffc8c81` + `fb575ae`. Conversion: `c678514`. Interim survivability guard: `82ce9e4`. No production PA re-ingest has run; the excerpt-less finding above suggests this guard may now rarely-to-never fire again once the fixed reuse path is exercised for real, but that's untested against real data.
- **#10 (convert `ingest_commentaries.py`): still next on this track**, whenever Alex picks it back up — untouched by the #11 work above (that track and the Sermonindex/#11 thread are separate).
- **#11 (build `on_existing="reuse"` chunk-dedup): DONE this session.** Commit `1ec5226`. Merged with the completeness-stamp decision per Decision 9.
- **#12 (convert `ingest_lexicon.py`): unblocked, not started.** The mechanism it needs now exists and is proven; the conversion itself is its own session.
- **#13, #15–#37:** untouched.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain open, untouched.

---

## Open Flags

**Resolved this session:**
9. ~~The skip-check's design is an open decision, not yet scheduled~~ — **RESOLVED as Decision 9**, merged with #11, built this session.
3. ~~`on_existing="reuse"` PATTERN — two known holes~~ — **RESOLVED.** Continued numbering fixed; document-row/`full_text` is still never re-inserted on reuse, but that's by design now (reuse only ever appends chunks), not an open hole.

**New:**
12. **PA's ~398 "excerpt-less" documents — 396 need `generate_excerpts.py`, not the writer, and 2 need a REDO healing run.** Neither run this session. Worth a short follow-up session: (a) run `generate_excerpts.py` against the 396 complete-but-unexcerpted docs (a completely different pipeline than anything touched this session), (b) REDO the 2 genuinely-broken ones through the now-fixed dispatcher.
13. **The "reasoned-through-but-unverified" claim above** (that PA's survivability guard will now rarely fire) should be confirmed, not assumed, whenever PA is next run for real.

**Carried forward, unchanged:**
1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12). Still recurs for the remaining unconverted scripts (`ingest_lexicon.py`, `ingest_helloao.py`, `ingest_commentaries.py` — corrected count, see below).
2. **Magazine queue hard pre-ingest gate — 27 of 27 pending articles contaminated** (found at #8). Unresolved, untouched.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). Not exercised this session.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`. Untouched this session.
6. **PLAN.md #5.5 closing line is stale.** Needs Alex's explicit go-ahead on replacement wording.
7. **PLAN.md #14 drift.** Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.
10. **CLAUDE.md's "four unconverted scripts" count is stale.** The real unconverted set is three: `ingest_lexicon.py`, `ingest_helloao.py`, `ingest_commentaries.py` (all three call `propositions.process_document()` directly, bypassing `shared_ingest.py`). Corrects in its own future docs pass, same as the "batch path deferred" note — not bundled here.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — this session's real changes (`migrations/062_documents_ingest_completed_at.sql`, `scripts/shared_ingest.py`) were committed, plus this doc.

---

## Next Session Should

Alex's call between: (a) the short PA follow-up (run `generate_excerpts.py` against the 396 complete-but-unexcerpted docs; REDO the 2 genuinely-broken ones through the fixed dispatcher), (b) #12 — convert `ingest_lexicon.py` to actually use the append mechanism this session built, or (c) #10 — convert `ingest_commentaries.py` (unrelated track, still waiting). All three are now unblocked and independent of each other.
