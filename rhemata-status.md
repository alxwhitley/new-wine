# rhemata-status.md

**As of:** 2026-07-13 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** the Sermonindex partial-write remediation thread (not yet a numbered PLAN.md item — an incident-response track running alongside the linear roadmap below). The two documents this incident left broken are now cleaned up (see this session, below) — **nothing broken remains live in production from this incident.** What's still open is the underlying cause: the document writer itself can still leave a future document half-written the same way if interrupted mid-run.
- **Next action:** wire `shared_ingest.py`'s `ingest_document()` to act on the paraphrase step's now-honest failure signal (built two sessions ago — see "Sermonindex remediation thread" below), then build the actual all-or-nothing writer (record + all chunks + propositions committed as one atomic unit, or nothing). That's the fix that prevents this class of incident from recurring; today's session only cleaned up after the last occurrence.
- **Separately, still true, unchanged by this session:** the `ingest_preceptaustin.py` PA batch-loop track (#9/#10/#11 below) is untouched. #10 (`ingest_commentaries.py` conversion) is still the next step on that track whenever Alex picks it back up; the #11 resequencing conversation with Alex is still open.

---

## This session (2026-07-13) — cleanup: two broken documents removed and re-queued

**No git commits this session.** Both writes this session were to the live database and to the (gitignored) ingest workbook — `git status` confirms zero tracked-file changes, so there is nothing to commit. This is expected, not an oversight: `sources/youtube/ingest_queue.xlsx` is excluded via `.gitignore` (`/sources/`), and the database isn't in git at all.

**What this closes:** the two documents left broken by the Sermonindex incident (identified two sessions ago, root-caused in the diagnostic session after that) are no longer live or servable — they've been fully removed and their source rows reset so a future queue run will re-ingest them cleanly from scratch.

**Confirmed before deleting anything, fresh against the live database (not reused from memory):**
- *"Waiting For The Moving Of The Water" by Carter Conlon* — 5 of an expected ~22 chunks, 0 propositions. Sheet status was `failed`.
- *"The Ultimate Heist" by Carter Conlon* — 5 of an expected ~19 chunks, 0 propositions. Sheet status was `triaged` (had never been updated — the process died before it could be). One correction to earlier notes: this document has 5 chunks today, not 3 as an earlier summary said — doesn't change the conclusion, still clearly partial.
- Checked scope: Carter Conlon has 8 documents total; the other 6 all have healthy, complete chunk counts (11–18). Only these two showed the broken signature. Confirmed by explicit user "yes" before any deletion.

**What was deleted:** both `documents` rows and all 10 associated `chunks` rows (5 + 5). Zero `propositions` rows existed for either, so zero were deleted there. Verified independently afterward, not just trusted from the delete script's own report: zero rows remain in `documents` or `chunks` for either document ID, and a separate check by URL (not just by ID) also came back zero — no stray duplicate left behind either.

**What was reset in the workbook (Sermonindex tab):**
- Row 5 ("Waiting For The Moving Of The Water"): `status` changed `failed` → `triaged`; `resolved_source` cleared from `Carter Conlon` to blank. (Caught and fixed a real bug in my own first attempt here: openpyxl's `cell(..., value=None)` is a silent no-op, not a clear — had to set `.value = None` directly on the cell object instead. Verified the fix actually took before saving.)
- Row 60 ("The Ultimate Heist"): already sitting at `status = triaged`, `resolved_source = blank` — it had never been touched since the process died mid-row, so it was already in the correct "never processed" state. No change needed; confirmed rather than assumed.
- Both rows now match the exact `status`/`resolved_source` shape of the 552 other genuinely-untouched `triaged` rows in this tab — confirmed by direct comparison before writing, not assumed.

**Deliberately not done this session:** no re-ingest was triggered — both sermons will only come back the next time someone runs the queue ingest orchestrator against the Sermonindex tab, same as any other pending row. The writer itself (the actual bug that let this happen) is still unbuilt — see next action above. No other document or row was touched.

---

## Sermonindex remediation thread — full sequence so far

This incident-response thread isn't a numbered PLAN.md item; tracking it here across sessions since it isn't a single self-contained piece of work.

1. **Incident:** a real, time-capped Sermonindex ingest was killed by something external (not the intended time cap) partway through, leaving two documents half-written but live.
2. **Diagnostic session (read-only):** traced the full write sequence, confirmed the writer commits the document record, then each chunk, then propositions, as three separate steps with no rollback across them — and separately found the paraphrase step couldn't tell "failed" from "genuinely empty," which would block building a clean fix. Recommended options; built nothing.
3. **Propositions-honesty session:** fixed the paraphrase-step ambiguity found above. Commit `42022a8`. Three outcomes (found content / genuinely empty / call failed) are now cleanly distinguishable where there used to be two. `shared_ingest.py` doesn't act on this yet — deliberately deferred.
4. **This session:** removed the two broken documents and reset their source rows to pending. No code changes.
5. **Still ahead:** wire `shared_ingest.py` to the honest signal from step 3, then build the actual all-or-nothing writer so a future interruption can't repeat step 1.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list — unrelated to, and untouched by, the Sermonindex thread above)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — `0935697`.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`): DONE.** Loader: `ffc8c81` + `fb575ae`. Conversion: `c678514`. Interim survivability guard (downstream of #9): `82ce9e4`. No production PA re-ingest has run.
- **#10–#13, #15–#37:** untouched. #10 next, whenever this track is picked back up.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain open, untouched.

---

## Open Flags

**Sermonindex remediation thread:**
8. **`shared_ingest.py` doesn't yet act on the paraphrase-step's honest failure signal.** `ingest_document()` still treats `"error"`, `"no_propositions"`, and `"stored:N"` identically — no branching yet. Next piece.
9. **The all-or-nothing writer itself is still unbuilt.** Document record / chunks / propositions still commit in three separate steps, so a future kill or crash mid-run can still leave a document half-written — the same way today's two (now cleaned up) documents broke.
10. ~~Two known-broken documents remain live in production, unrepaired~~ — **RESOLVED this session.** Both deleted, both source rows reset to pending.

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

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — this session touched only the live database and the gitignored workbook, neither of which shows up in `git status`, plus this doc.

---

## Next Session Should

Wire `shared_ingest.py`'s `ingest_document()` to actually branch on the paraphrase step's result — decide and implement what happens when it comes back `"error"` versus `"no_propositions"` versus `"stored:N"`, under the "finished" definition already agreed: record + all chunks + paraphrase-step-having-run-to-completion, where a genuine empty counts as finished and a failed call does not. That's the direct prerequisite for the all-or-nothing writer restructuring, which remains the larger goal after that — it's the actual fix that prevents another Sermonindex-style incident. The PA/#10 track (`ingest_commentaries.py` conversion) and the #11 resequencing conversation remain open on their own separate track — Alex's call on which gets picked up first.
