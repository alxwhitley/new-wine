# rhemata-status.md

**As of:** 2026-07-13 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** the Sermonindex partial-write remediation thread (not yet a numbered PLAN.md item — an incident-response track running alongside the linear roadmap below). Today's real ingest run of the Sermonindex tab was killed mid-run and left two documents in the live database as broken partials — "Waiting For The Moving Of The Water" and "The Ultimate Heist," both by Carter Conlon, both currently servable in production. Those two documents are still broken; this session did not touch them (out of scope, by design).
- **Next action:** wire `shared_ingest.py` to act on the honesty signal this session just built (see below) — i.e., have `ingest_document()` check whether the paraphrase step returned `"error"` and, if so, either not count the document as finished or hold the whole write back, per whatever the all-or-nothing writer design decides. After that, the actual all-or-nothing writer restructuring (record + all chunks + propositions committed as one atomic unit, or nothing) can proceed — it was blocked on exactly the ambiguity this session closed.
- **Separately, still true, unchanged by this session:** the `ingest_preceptaustin.py` PA batch-loop track (#9/#10/#11 below) is untouched. #10 (`ingest_commentaries.py` conversion) is still the next step on that track whenever Alex picks it back up; the #11 resequencing conversation with Alex is still open.

---

## This session (2026-07-13) — propositions.py: make model-call failure honest

**One commit: `42022a8`.** File touched: `scripts/propositions.py` only, as scoped.

**The problem this closes:** two sessions ago, a read-only diagnostic (prompted by the Carter Conlon partial-write incident) traced the full document-writer sequence and found a second, separate problem sitting underneath the "chunks can die half-written" bug: the paraphrase-extraction step's own model call caught *every* failure — network error, rate limit, timeout, a response that doesn't parse — and silently returned an empty result, indistinguishable from the AI genuinely finding nothing to extract in a document. A later session that tried to start building an all-or-nothing writer hit this directly and **stopped rather than build on top of it**, since "if paraphrase failed, write nothing" is impossible to implement honestly when failure and empty look identical.

**What changed:** `extract_propositions()` now raises a new, distinct exception (`PropositionExtractionFailed`) when the model call itself fails, instead of swallowing the failure into `[]`. A genuine empty result (the call succeeds, the model legitimately finds nothing) still returns `[]` exactly as before — untouched. One layer up, `process_document()` already had a catch-all exception handler (originally there for storage-side failures only); that same handler now also catches this new exception and reports `"error"` — so no new code was needed there, only a docstring update clarifying what `"error"` and `"no_propositions"` now precisely mean. `process_document()`'s "never raises" contract is unchanged — a call failure is still non-fatal to the overall ingest run, just no longer silently indistinguishable from success.

**Result: three cleanly separate, caller-visible outcomes now exist** where there used to be an ambiguous two:
1. Model ran, found teaching points → the points (unchanged).
2. Model ran, genuinely found nothing → `"no_propositions"` — a real completed result, not a failure.
3. The call itself failed → `"error"` — distinct, detectable, and non-fatal.

**Proof, all synthetic, no production data touched:**
- **Test 1 (forced call failure):** mocked the model call to raise. Confirmed `extract_propositions()` raises `PropositionExtractionFailed`, and confirmed `process_document()` catches it and returns `"error"` — no crash. **Passed.**
- **Test 2 (genuine empty):** mocked the model call to succeed and return an empty list. Confirmed `extract_propositions()` still returns `[]` with no exception, and `process_document()` returns `"no_propositions"` — cleanly separate from Test 1's `"error"`. **Passed.**
- **Test 3 (normal case, full round-trip):** mocked the model call to return two real proposition-shaped entries. Created one throwaway `documents` row (required — `propositions.document_id` has a foreign-key constraint, so a real row was needed to test the actual storage path), ran `process_document()` end-to-end, confirmed it returned `"stored:2"` and that the two rows landed in the `propositions` table with the right content. **Passed.** All test artifacts (the throwaway document + its two proposition rows) were deleted immediately after, and a final sweep confirmed zero rows remain anywhere.

**Deliberately not done this session (explicitly out of scope, staged for next):** `shared_ingest.py` was read (to see how it consumes the paraphrase-step result) but not edited — it still just passes `"error"`/`"no_propositions"`/`"stored:N"` straight through without branching on any of them. The all-or-nothing writer restructuring itself is untouched. The skip-check ("already ingested?") logic is untouched. The two broken Carter Conlon documents are untouched. No real/production ingest ran. The stale CLAUDE.md note (which still says the batch-insert path is "deliberately deferred" when it's actually fully built) was left alone, as instructed — that's a separate docs-only pass.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list — unrelated to, and untouched by, this session's Sermonindex work above)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — `0935697`.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`): DONE.** Loader: `ffc8c81` + `fb575ae`. Conversion: `c678514`. Interim survivability guard (prior session, downstream of #9): `82ce9e4`. No production PA re-ingest has run.
- **#10–#13, #15–#37:** untouched. #10 next, whenever this track is picked back up.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain open, untouched.

---

## Open Flags

**New this session:**
8. **`shared_ingest.py` doesn't yet act on the paraphrase-step's honest failure signal.** `ingest_document()` still treats `"error"`, `"no_propositions"`, and `"stored:N"` identically — prints and returns whatever string it gets, no branching. The signal is now trustworthy; nothing reads it differently yet. This is the very next piece.
9. **The all-or-nothing writer itself is still unbuilt.** Today's document record / chunks / propositions still commit in three separate steps, in that order, so a kill or crash mid-run can still leave a document half-written (this is precisely how the two Carter Conlon documents broke). This session only removed one blocker to building it safely.
10. **Two known-broken documents remain live in production, unrepaired:** "Waiting For The Moving Of The Water" and "The Ultimate Heist," both Carter Conlon, both currently servable (Carter Conlon's source is `unlicensed`/`shown`). Cleanup is explicitly its own separate session.

**Carried forward, unchanged (PA/#9-#11 track):**
1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12). Still recurs at #10–13 for the remaining unconverted/stale-listed scripts.
2. **Magazine queue hard pre-ingest gate — 27 of 27 pending articles contaminated** (found at #8). Unresolved, untouched.
3. **`on_existing="reuse"` PATTERN — two known holes, survivable but still open** (unconditional re-chunk/re-insert; document-row/`full_text` skipped on reuse). Still #11's job.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). Not exercised this session.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`. Untouched this session.
6. **PLAN.md #5.5 closing line is stale.** Needs Alex's explicit go-ahead on replacement wording.
7. **PLAN.md #14 drift.** Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — the one file this session actually edited (`scripts/propositions.py`) plus this doc were both committed/updated, nothing else touched.

---

## Next Session Should

Wire `shared_ingest.py`'s `ingest_document()` to actually branch on the paraphrase step's result — specifically, decide and implement what happens when it comes back `"error"` (per this session's new, honest signal) versus `"no_propositions"` versus `"stored:N"`, under the "finished" definition already agreed: record + all chunks + paraphrase-step-having-run-to-completion, where a genuine empty counts as finished and a failed call does not. That's the direct prerequisite for the all-or-nothing writer restructuring itself, which remains the larger goal after that. The PA/#10 track (`ingest_commentaries.py` conversion) and the #11 resequencing conversation remain open on their own separate track — Alex's call on which gets picked up first.
