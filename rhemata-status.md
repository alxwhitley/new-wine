# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-04 (async worker service deployed + verified end-to-end).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Trimmed 2026-08-01
(from ~2,700 lines) and twice more 2026-08-04 (from ~840, then this pass from
~480). Cut material is never the only copy — it survives in git history and in
the per-topic durable homes: PLAN.md (roadmap/decisions), CLAUDE.md
(invariants/landmines), `docs/audits/`, and the commits named below.

---

## Current state

**Deployment.** `origin/main` = local `main` at `2ba9f12` (pushed 2026-08-04).
Async path stays DARK: `chat.py`/`main.py` byte-identical to pre-async Stage 2,
routes unmounted (`ASYNC_ANSWER_ENABLED` unset), DB switch
`async_answer_config.serving_enabled=false`. Live serving path is unchanged.
Deploy history: commits `2ba9f12`, `6dca017`, `196f1f2`, `dd71b87`; full
narrative in PLAN.md's version history.

**Project 1 (scalable async answers) — worker built, deployed, verified;
switches still OFF.** Worker service exists on Railway (repo-root
`nixpacks.toml`), completed one real end-to-end generation ($0.076, cleaned up
after). Transaction-pooler connection (port 6543) confirmed reachable; 20/20
simultaneous generations measured; five 20-slot replicas reach the 100-slot
dial without an architecture change. **Residual, unconfirmed:** whether the
worker's live `SUPABASE_DB_URL` is actually the transaction pooler (6543) vs
session pooler (5432, ~12/worker cap) — Supavisor masks this from the DB side;
needs `railway variables` on the worker service or Alex pasting the URL. Full
detail: PLAN.md CURRENT BUILD SEQUENCE + CLAUDE.md's async landmine.

**Answer path — current behavior (live `/chat`, unchanged).** Buffers fully,
runs the Phase-2 retrieval-grounding guard + prose-attribution scan +
`verify_references`, resolves ungrounded credit
(regenerate-once-then-refuse), reveals as paced playback. A teacher earns a
verified link only if retrieved for the question. The position-paper
(house-voice) path serves the baptism + tongues pillars via `chat.py`
interception and still streams live.

**Corpus/data.** Propositions backfill COMPLETE (0 genuine documents
remaining). Chapter-scoped book extraction covers 8/53 books; the
numeral-heading detector is built but uncommitted (zero callers). Position
serving path is built + proven standalone, NOT wired into live chat. All
counts: query live.

**Attribution audit (2026-08-04, read-only, zero writes).**
`docs/audits/historical_commentary_attribution_reverification_2026-08-04.md`.
307 HistoricalChristianFaith docs: author names intact, nothing stripped
(Open blocker #15 premise resolved). The C.S. Lewis doc under this source is
correctly attributed but wrongly tagged `public_domain` (protected to
~2033); Tolkien / Douglas Wilson are the same class — Open blocker #16, still
open.

---

## Open blockers

**Launch blockers (Project 1's remit, neither blocks further build work):**
~68s to a fully-revealed answer (dominated by hidden model reasoning, ~59% of
wall-clock, untrimmable without an accuracy oracle — Open Decision #20); ~40
simultaneous-chat ceiling (anyio threadpool exhaustion) — replacement built
(Project 1 Stage 1) but not cut over yet.

- **#4** `ingest_helloao.py` unconverted — blocks 8 further HelloAO commentaries only, not corpus growth generally.
- **#6** Guest→account conversion likely broken (cookie/localStorage mismatch). `docs/audits/GUEST_AUTH_AUDIT.md`.
- **#7** Auth CTA inconsistencies (`/library/authors`, `/home`, dead `AuthButton.tsx`). `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.
- **#9** v4 propositions prompt (`EXTRACTION_PROMPT_V4`) built, unwired — adopt/iterate/discard undecided.
- **#10** Precept Austin raw-source gap — fewer raw scrape files than ingested docs.
- **#11** `verify_chunk_alignment.py` docstring stale (describes removed insert modes).
- **#12** `jewish_perspectives` table orphaned (2 rows, no code references).
- **#13** SP2 Study Panel — no real screen-reader (VoiceOver/NVDA) pass ever run.
- **#14** Hebrew lexicon (TBESH) not covered by the Greek CC BY 4.0 grant — don't build against it until cleared.
- **#16** C.S. Lewis / Tolkien / Douglas Wilson mistagged `public_domain` under HistoricalChristianFaith — live exposure; durable fix needs a per-author license override (Alex's schema decision).
- **#18** Home-page marketing line names Bevere (empty source, 0 props) and Koulianos (not in corpus) as "trusted teachers" — living-minister misrepresentation, still open.
- **#19** External pipeline diagram (non-repo, not found locally) stale in 4 ways — fix if/when it resurfaces.

Resolved (git history): #1, #2, #3, #5, #15, #17.

## Known harness bugs

Both resolved: the 2026-07-18 executor write-accounting loop (`d9ab1cc`) and
`BASH_WRITE_INDICATORS` SQL-verb over-flagging (`569d412`). CLAUDE.md's
Session Routing DB-write hard rule and its revisit trigger are unchanged.

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar —
  gated behind `NEXT_PUBLIC_FULL_NAV_ENABLED`).
- Pass B pending: `UsageRing` not yet remounted in the sidebar drawer.

---

## Next

1. **Confirm the worker's DB route is the transaction pooler (6543), not the
   session pooler (5432)** — the one residual blocking cutover (`railway
   variables` on the worker, or Alex pasting `SUPABASE_DB_URL`). Then set
   `ASYNC_ANSWER_ENABLED=true` on the backend (dark health check with
   `serving_enabled` still false), run the controlled public traffic window,
   and flip `serving_enabled` back off immediately after. Project 2 starts
   only once that cutover is stable.
2. **Position layer — UN-DEFERRED 2026-08-04 (CLAUDE.md item 18); steps 2-3
   BUILT + verified, step 4 not started.** Step 2: materialized eligibility
   (migration 080, 8,284/11,139 eligible — real cost 2h04m, corrects the
   stale "~15+ min" estimate 8x), `cache_control`, streaming siblings. Step 3:
   `gather_evidence()`/`gather_evidence_corpus()` now gated on
   license/visibility (`LICENSE_GATE_SQL`, reusing Invariant 2's predicate
   verbatim, no migration needed) — confirmed real effect, not a no-op
   (Savchuk/Poonen, both unlicensed+hidden, now correctly excluded). Both
   steps verified: `test_serve_position.py` clean; `prove_serving_path.py`
   32/36, the 4 gaps a pre-existing unrelated test-fixture staleness issue,
   not a regression — see audit doc. Commits `6fc39bc`/`82e5d2e`. Next: step
   4's topic-matching (Open Decision #16, now a hard prerequisite) and
   chat.py wiring behind a two-level off-switch. `get_teacher_card()`'s
   live-synthesis leak stays
   Project 2 scope, untouched by this. Full plan:
   `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.
3. Route `ingest_helloao.py` through `shared_ingest` (blocker #4).
4. Folder renames (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop the
   orphaned `jewish_perspectives` table.
5. Staging Supabase + a verified backup/restore test (backup exists, restore
   never tested at project level).

SP track: SP2 done (Phases 1–9); SP4 teacher cards shipped and signed off; SP
panel refinement done. Next SP item is #43 (SP5, mobile bottom-sheet). #38
(SP0 mobile mockup) completion unverified — confirm before assuming.
