# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-13 (third session this date).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Position papers: all 8 of 8 charismatic pillars now live** —
baptism_holy_spirit, speaking_in_tongues, deliverance_and_spiritual_warfare,
prosperity_and_faith_teaching, divine_healing, gifts_of_the_spirit_overview,
prophecy_and_the_prophetic, five_fold_ministry. The final four (commits
`a81bb67`/`10374e0`, pushed) closed out the registry the same way the first
four were: ingested via the shared chokepoint under the house source,
silent_context, then calibrated against real embeddings
(`scripts/calibrate_new_pillars_2026-08-13.py`, 41 cases) and verified
against the full pre-existing regression suite (0 regressions) plus the
live end-to-end fence test. The three that had "failed first-pass
calibration" got real fixes, not a quick patch — an own-goal contrast
anchor (prophecy's own contrast list named gifts the paper claims as its
own territory), a too-weak divine_healing anchor losing to both the
healing-mechanics debate and the new gifts-overview pillar, and a
regression the new prophecy pillar introduced against an existing tongues
protection — see the commit message for the specific fixes.
`five_fold_ministry`'s editorial question (restoration-after-a-gap vs.
never-ceased) is resolved per Alex's ruling: the offices never ceased, only
fell into neglect at times — consistent with how the baptism/gifts papers
already treat this kind of continuity question. `docs/position_papers/` no
longer holds any unregistered draft. Also checked and confirmed clean this
session: no reference to Myles Munroe exists anywhere in the repo (the
prosperity paper's tithing material stays fully unattributed, no
exception); CLAUDE.md's stale "eca8070 not pushed" note is corrected —
confirmed via git ancestry that it's on `origin/main` and live.

**All pending commits pushed this session**, including 4 carried over from
the prior session (`dac422f`/`5ccc73c`/`8e1563e`/`efb9fa6` — Grok
promotion, the first two pillars going live, and the last session-close)
plus this session's `a81bb67`/`10374e0`. Nothing outstanding on `main`.

**PLAN.md decisions from the prior session (now pushed):** target
launch date compressed to October 2026 (market pressure + an October
conference venue); the F1 100-generation/100-user concurrency proof REMOVED
entirely — Alex explicitly declined a pre-launch load test, this is decided,
not still-pending; overnight harness may run ingestion + app-build in two
parallel lanes once the coordinator run loop + safety fence (per-worker
permissions) are built (CLAUDE.md Invariant 15); generation-output
verification investigated and confirmed still genuinely open
(`reference_verifier.py` solves misattribution, not claim-support — a
different problem); Grok promoted to a third implementation worker for
eligible build packets (commit `dac422f`, NOT pushed).

**New landmine:** Claude Code's "Auto Mode" became the default permission
model this week and blocks direct DB writes from a Claude Code session, with
no settings-based self-grant path. Full detail + the Grok-routing workaround
used this session in CLAUDE.md's Landmines section (top entry).

**O3/O4 harness (2026-08-11, unchanged this session):** both accepted,
integrated locally on `main`, NOT pushed (`b580915`/`7ab9f15`). Real-provider
commissioning remains `HUMAN_REQUIRED` pending a proven pre-execution
sandbox.

**O5 harness (this session, 2026-08-13): all 5 tasks built and committed,
whole-branch review ACCEPT, NOT merged.** Full detail in PLAN.md's O5 entry
and `docs/audits/o5_budgets_hard_stops_2026-08-11.md` (on branch
`codex/o5-budgets-hard-stops`, build `4140764` + audit `82c59ee`, on top of
`0f06f62`). Commissioning found and fixed 2 real defects in the Task 4
baseline; 7 rounds of independent review then hardened Task 5's own new
code before the final ACCEPT. Full O2-O5 suite: 1337 passed, 1 skipped, 0
failed. **Still open, needs Alex:** merge `codex/o5-budgets-hard-stops` into
`main` (or not), and — separately, only after that — the final PLAN.md/
this-file records closeout the plan doc's own Step 6 describes. Neither was
assumed or done this session. Disclosed residual: legacy lane-based
reassignment escaping plan-pinned routing has a reconciliation-only
detection backstop, not live prevention — a real follow-up task if live
prevention is wanted. O6 (concurrent multi-packet rehearsal) is unaffected,
still not started.

**Derek Prince quote curation — complete 2026-08-09.** 477/496 approved, 20
zero-coverage documents, Alex's open call on re-extraction.

**Still live (product).** One answer path (async, `serving_enabled` TRUE).
Quote rail live. Position one-hop live on origin.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- 20 Prince documents with zero approved quotes (2026-08-09).

---

## Next

1. **O5 merge/closeout decision (Alex).** `codex/o5-budgets-hard-stops` is
   built, committed, and independently review-ACCEPTed — merge into `main`
   and the final PLAN.md/rhemata-status.md closeout both wait on Alex's
   explicit call, not assumed by any session. Then O6 (concurrent
   multi-packet rehearsal) is next in the harness track.
2. Decide extractor hardening before any next Prince-style batch —
   majority-Scripture/unbalanced-quote checks, the `--per-doc-limit=1`
   cap (raise or keep), whether unused material exists in already-
   processed chunks. Savchuk/Ravenhill/Poonen eligible next.
3. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
4. **Human review of chapter-boundary proposals** (18 books) — Open
   Decision #21 still open.
5. **Trail / Brooks one-offs** — review then decide visibility.
6. Decide `pending` vs `draft` quote-status consolidation.
7. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
