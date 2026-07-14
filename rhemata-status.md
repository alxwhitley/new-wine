# rhemata-status.md

**As of:** 2026-07-14 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority: the lexicon slice-runner is built and proven — commit `dd609fb`.** `scripts/ingest_lexicon_runner.py` drives the already-converted `ingest_lexicon.py` through `shared_ingest.ingest_document()` in bounded, checkpointed slices (~50–100 entries), with retry-then-bisect-then-skip-and-log so one bad entry can never halt a run. Proven on a bounded real slice, including a genuine resumability check and a genuine forced-failure check (both verified by direct DB recomputation, not self-report — details below). **The full lexicon batch was NOT run this session.**
- **Important correction to the prior session's own claim:** `rhemata-status.md` (and this session's own build brief) both assumed a real, un-appended lexicon backlog existed for the runner to make lasting progress on tonight ("the front of the batch you'll finish tonight"). A direct live-DB query at the start of this session disproved that: **all four real STEPBible lexicon documents are already 100% loaded** (chunk counts match today's fresh file-parse counts exactly — TBESG 11,034 / TBESH 10,258 / TFLSJ 0-5624 5,709 / TFLSJ extra 5,324), just via the OLD pre-conversion script, unstamped. There is no real backlog left under these four titles. **"Ready to launch tonight" is the wrong frame — there is nothing left to launch for these four files** unless Alex wants a deliberate REDO through the new converted+stamped path for consistency (a separate decision, not made here).
- **Given that, the proof run targeted a throwaway test title** (real TBESG entries, fake document title, fully deleted at session close) rather than one of the four real titles — the only way to prove real appending/resumability/failure-handling without either touching already-complete production docs or fabricating fake entry content. See "This session" below for exactly what was proven and cleaned up.
- **A real bug was found and fixed during self-testing, not glossed over:** the runner's end-of-run summary initially undercounted skipped entries (a recursion/bisection edge case where an early branch's skip was overwritten by a later branch's return value). Caught by the forced-failure test itself, fixed, and re-verified clean. See below.
- **Carried forward, unrelated:** the Study Panel shell/motion session (commit `161c4de`/`fc2f273`, pushed to `origin/main` as `fc2f273`) is untouched this session — no frontend work happened here.

---

## This session (2026-07-14) — lexicon slice-runner: build + prove

**One commit: `dd609fb`.** File: `scripts/ingest_lexicon_runner.py` (new). `ingest_lexicon.py` and `shared_ingest.py` are **untouched** — all new complexity (slicing, retry/backoff, bisection, the persistent skip list) lives in the runner alone, per the pacing decision surfaced during #12's own scoping.

**Phase 1 findings (read-only, before building):**
- `ingest_lexicon.py`'s `ingest_file(filename, title, max_entries=N)` already gives cumulative-prefix slicing through the writer's `on_existing="reuse"` append mechanism — genuinely resumable, zero writer change needed for the "grow" direction.
- It has no hook to exclude one specific bad entry from the middle of a file (`max_entries` only grows/shrinks a prefix boundary) — needed for the failure policy's "skip just the one bad entry" requirement. Rather than add a parameter to the already-converted, already-tested `ingest_file()`, the runner imports its pure helpers (`parse_file`, `format_chunk_content`, `truncate_for_embedding`) and calls `shared_ingest.ingest_document()` directly, with its own skip-aware entry list. Zero modification to either existing file.
- Resumability ("what's already stored") is fully inherited from the writer's `_get_chunk_count()` — no runner-side bookkeeping needed there. The **one** thing the runner tracks itself is the permanent skip list (which entries to never retry) — a policy decision outside the writer's scope, not a gap in it.
- Real file sizes confirmed by fresh parse (not assumed): TBESG 11,034 / TBESH 10,258 / TFLSJ(0-5624) 5,709 / TFLSJ(extra) 5,324 entries. **A direct live-DB query then found all four already fully loaded** — see Current Priority above. This reshaped the proof-run design (throwaway test title instead of a real one).
- Matched `run_queue_ingest.py`'s existing orchestrator shape: per-unit fault tolerance, aggregated stats, a final tally table — minus `--time-limit` (out of scope this session).

**Design, Alex-confirmed:**
- Slices of ~50–100 entries (default 75), each slice = one checkpoint = one call through the writer (also = at most one OpenAI embedding batch call, `EMBED_BATCH_SIZE=100`).
- On failure: retry the same target 3× with a brief backoff (2s/5s/10s) — handles the realistic failure mode (a transient network/rate-limit blip, which fails an entire in-flight batch regardless of content, not a specific entry). If still failing, bisect the remaining span and recurse, down to a single entry if necessary. A single entry that still fails is the genuine culprit: logged (Strong's code + reason) to a persistent JSON skip list (`logs/lexicon_slice_runner_skips.json`, gitignored), permanently excluded from every future attempt (this run and any resumed run), and the run continues past it.
- `--simulate-failure-at N` is a real, built-in test hook (not an ad hoc monkeypatch) for proving the failure path deterministically.

**Proof run (bounded, real content, throwaway title — cleaned up after):**
1. **Initial load:** 250 real TBESG entries (genuine parsed file content — Strong's G0001 "Alpha" through G0238) under the title `STEPBible Greek Lexicon (TBESG) — RUNNER PROOF (test, delete before session close)`, in 4 slices (75/75/75/25). Verified via direct DB recomputation: 250 contiguous `chunk_index` values (0–249), zero dupes, correctly stamped (`ingest_completed_at` set).
2. **Resumability:** identical command re-run produced a clean no-op (`stored=250 of target_total=250`, zero new writes). Verified via direct DB recomputation: chunk count still exactly 250, still contiguous — no duplicates, no partials.
3. **Failure policy:** `--limit 300 --simulate-failure-at 260` forced entry `G0249` to fail every attempt. Observed: 3 retries with backoff at the full span, then progressively smaller bisected spans, correctly isolating `G0249` alone; it was logged and permanently skipped; **the run continued and completed all 300 target entries** (299 real + `G0249` excluded). Verified via direct DB recomputation: 300 contiguous chunks, `G0249`'s content confirmed absent. A re-run with the same flag afterward correctly no-op'd (current already at target) and correctly re-targeted the *next* entry at that position, proving the skip is durable across runs.
4. **A real bug found by test 3, fixed, re-verified:** the first version's end-of-run summary reported `skipped=0` even though the skip genuinely happened (visible in the log, correctly persisted to the JSON skip file) — a bisection recursion bug where only the last recursive branch's return value reached the caller, silently dropping an earlier branch's skip from the summary. Fixed by threading a shared `collected_skips` list through the whole recursion tree instead of relying on return values. Re-ran all three tests clean afterward; the summary now correctly reports `skipped=1` with the entry and reason listed.

**Cleanup:** the throwaway test document (all 300 chunks) and its skip-log JSON entry were deleted at session close — confirmed via direct query that this was disposable test data, not real corpus content (it duplicated real TBESG text under a fake title). The four real production lexicon documents were re-queried immediately after and confirmed **exactly unchanged** (11,034/10,258/5,709/5,324 chunks, still unstamped) — this session touched zero real corpus rows.

**How many real lexicon entries are now in the DB from this session's proof run: zero, by design.** Everything written during proof/resumability/failure-policy testing was deleted as a throwaway artifact at session close (see above) — none of it was "the front of a batch to finish tonight," because there was no real backlog to be the front of.

**Deliberately not done this session (per the brief):** the full lexicon batch (all four files, from wherever they'd need to start — in practice: nothing, since they're already loaded; a REDO would be the only reason to run it, and that's Alex's call, not made here); the 551 Sermonindex rows; the 2 broken PA docs; `--time-limit`; CLAUDE.md's stale notes; any frontend/Study Panel work.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list, plus the SP track added 2026-07-13)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end.
- **#6 (aliases + sentinel cleanup + strict mode):** DONE.
- **#7 (`documents.full_text` chokepoint):** DONE.
- **#8 (convert `ingest_magazine.py`):** DONE.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`):** DONE. No production PA re-ingest has run.
- **#10 (convert `ingest_commentaries.py`):** still next on this track whenever Alex picks it back up — untouched.
- **#11 (build `on_existing="reuse"` chunk-dedup):** DONE.
- **#12 (convert `ingest_lexicon.py`):** DONE (commit `33e92b4`). **Its batch-scale companion (the slice-runner) is now also built and proven this session (`dd609fb`) — but the real lexicon is already fully loaded (see Current Priority), so there is no pending "full run" left to schedule for these four files specifically.**
- **#13, #15–#37:** untouched.
- **#14 (T-tail housekeeping):** docs-truth clause DONE. Folder renames and the `jewish_perspectives` drop remain open.
- **SP track (#38–43):** untouched this session — see the prior session's Study Panel work (commit `161c4de`/`fc2f273`, already pushed) for its own status; not restated here.

---

## Open Flags

**New:**
20. **The "full lexicon batch ready to launch" framing from the last two sessions was wrong and is now corrected.** All four real STEPBible documents are already 100% loaded (unstamped, via the pre-conversion script). If Alex wants them re-loaded through the new converted+stamped path for consistency, that requires a deliberate REDO (`on_existing="delete_and_reingest"`) decision — a real, brief-outage-shaped operation on live production docs, not a resume-from-partial. Not something to do casually; flagging it as a real option, not a default next step.
21. **The slice-runner is proven only on a throwaway test title, never against a real title.** Nothing in this session exercised the runner against real production lexicon documents (there was nothing to append). If a REDO (above) is ever run, that would be the runner's first real-title exercise — worth attention the first time, not assumed identical to the test-title proof.
22. **The runner's summary-tracking bug (fixed this session) is a reminder that bisection-recursion code is easy to get subtly wrong.** Fixed and re-verified, but if the failure policy is ever extended (e.g., different retry counts per depth, parallelism), re-run the same three-part proof (initial/resumability/failure) before trusting it.

**Carried forward, unchanged:**
1. Rule 10 freeze is a bare-substring match, not an invocation check — recurs for `ingest_helloao.py`, `ingest_commentaries.py` only.
2. Magazine queue hard pre-ingest gate — 27 of 27 pending articles contaminated. Unresolved, untouched. **NEEDS ALEX REVIEW (2026-07-14 records-vs-database reconciliation):** the original "27 contaminated" signal can't be located against current state. Closest current signal: 32 articles across 5 issues sit in `sources/magazine/02_extracted/` awaiting approval; the extraction tracker shows 53 issues with failed (mostly transient network) extraction runs and 48 with QA flags — none of these cleanly confirms or refutes the original "27" figure. Flagging, not correcting, until Alex says what this originally referred to.
4. Database-number verification gap. Not exercised this session.
5. `GOVERNED_FILES` gap (`guard_pretooluse.py`/`settings.json`). Untouched this session.
6. PLAN.md #5.5 closing line is stale. Needs Alex's explicit go-ahead on replacement wording.
7. PLAN.md #14 drift — folder renames and the `jewish_perspectives` drop still open.
10. CLAUDE.md's "unconverted scripts" count is stale (says four, real count is two: `ingest_helloao.py`, `ingest_commentaries.py`). Untouched this session.
12. PA's ~398 "excerpt-less" documents — unrelated to this session.
13. The "PA's survivability guard will now rarely fire" claim is still unconfirmed against real data. **NEEDS ALEX REVIEW (2026-07-14 records-vs-database reconciliation):** this is a claim about future behavior under real failure conditions, not a present DB state — it can't be confirmed or refuted by a database query either way. Left flagged as genuinely open, not stale.
16. No kill switch / beta flag exists for the Study Panel (carried from the prior session, untouched here).
17. The Study Panel's verse-reference detector is a narrow client-side stand-in, not the real SP1 backend (carried from the prior session, untouched here).

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else beyond a session's real change: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — deliberately left out of this session's commit (`dd609fb`), which contains only the one new runner file.

---

## Next Session Should

Alex's call between several independent, unblocked options: (a) decide whether the four real lexicon documents are worth a deliberate REDO through the new converted+stamped path (not urgent — they already serve correctly; this is a consistency/hygiene question, not a data-completeness one), (b) the short PA follow-up (`generate_excerpts.py` against 396 complete-but-unexcerpted docs; REDO the 2 broken ones), (c) #10 — convert `ingest_commentaries.py`, or (d) the Study Panel's open flags (kill switch / SP1 backend) if that direction is confirmed. All are independent.
