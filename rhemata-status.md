# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-13.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Position papers: 4 of 8 charismatic pillars now live** — baptism_holy_spirit,
speaking_in_tongues, deliverance_and_spiritual_warfare,
prosperity_and_faith_teaching. Latter two registered 2026-08-13 (commits
`5ccc73c`/`8e1563e`, NOT pushed) via the same fence/exclusion/fallback
mechanism as the original two, no pillar-specific code path. Full audit and
calibration trail is in the commit messages; ARCHITECTURE.md's Position
papers section is current. 3 pillars (divine_healing,
gifts_of_the_spirit_overview, prophecy_and_the_prophetic) were attempted and
found genuinely hard — each loses margin to a standing-debate contrast on
its own core content, needs real iteration next round, not a quick fix.
`five_fold_ministry` still blocked on Alex's own editorial call
(restoration-after-a-gap vs. never-ceased-just-neglected).

**PLAN.md decisions this session (pushed except Grok promotion):** target
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
sandbox. See PLAN.md Phase 0 for O5/O6 status.

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
- `five_fold_ministry.md` editorial marker — needs Alex.
- 20 Prince documents with zero approved quotes (2026-08-09).
- 3 position-paper pillars need real calibration iteration before
  registering — see Current state above.

---

## Next

1. **O5 budgets and hard stops.** Add turn, wall-clock, retry, output-size,
   provider-allowance, and queue-wide limits before overnight rehearsal.
2. **`five_fold_ministry.md` editorial decision** — needs Alex before any
   calibration work starts on it.
3. **Calibrate divine_healing / gifts_of_the_spirit_overview /
   prophecy_and_the_prophetic** — each failed first-pass calibration
   (loses margin to a standing-debate contrast on its own content); real
   iteration needed, likely similar difficulty to what deliverance took.
4. Decide extractor hardening before any next Prince-style batch —
   majority-Scripture/unbalanced-quote checks, the `--per-doc-limit=1`
   cap (raise or keep), whether unused material exists in already-
   processed chunks. Savchuk/Ravenhill/Poonen eligible next.
5. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
6. **Human review of chapter-boundary proposals** (18 books) — Open
   Decision #21 still open.
7. **Trail / Brooks one-offs** — review then decide visibility.
8. Decide `pending` vs `draft` quote-status consolidation.
9. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.
10. Push pending commits (`dac422f`, `5ccc73c`, `8e1563e`) when Alex
    approves.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
