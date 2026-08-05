# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-04 (position-layer fabrication remediation executed +
verified live; store-then-synthesize design rejected, one-hop revision
written — see below).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Trimmed
2026-08-01 (from ~2,700 lines) and repeatedly since. Cut material is never
the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

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
after); 20/20 simultaneous generations measured. **Residual, unconfirmed:**
whether the worker's live `SUPABASE_DB_URL` is the transaction pooler (6543)
vs session pooler (5432, ~12/worker cap) — needs `railway variables` on the
worker or Alex pasting the URL. Detail: PLAN.md CURRENT BUILD SEQUENCE +
CLAUDE.md's async landmine.

**Answer path — current behavior (live `/chat`, unchanged).** Buffers fully,
runs the Phase-2 retrieval-grounding guard + prose-attribution scan +
`verify_references`, resolves ungrounded credit
(regenerate-once-then-refuse), reveals as paced playback. A teacher earns a
verified link only if retrieved for the question. The position-paper
(house-voice) path serves the baptism + tongues pillars via `chat.py`
interception and still streams live.

**Position layer — design revised 2026-08-04, nothing built.** The
stored-position-then-rewrite (two-hop) design was pressure-tested and found
fatally flawed: a check on the generated answer can't see drift already baked
into the stored position (proven live — a documented fabrication, Ravenhill/
Philippians 4:8-9, was found still `eligible=true` and already feeding a
real stored position's evidence); reactive invalidation can't detect corpus
material being ADDED, the dominant real case (517 new eligible propositions
landed 2026-08-03, after both live corpus positions were built); no
concurrency guard or failure memory existed either. **Accepted direction is
now one hop:** a matched position's underlying propositions — never its
rendered text — feed `chat.py`'s existing, already-hardened pipeline
directly, supplementing normal retrieval; the position's own text becomes a
build-time human-review artifact only, never served. Same-day remediation
cleared 2 of 3 documented fabrication cases (Ravenhill, Conlon — now
`eligible=false`, content not rewritten, undecided) and demonstrated the
volatility live: removing one bad proposition flipped `holiness and personal
purity` from a 4-teacher corpus position to a Prince-only teacher position
(commits `ab18222`/`b8034eb`). Third case (Savchuk) unconfirmed, untouched.
Topic-matching (`match_stored_position()`, #16) remains the real, unbuilt
prerequisite. Full diagnostic/pressure test/remediation/revised design/ranked
weaknesses: `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

**Corpus/data.** Propositions backfill COMPLETE (0 genuine documents
remaining). Chapter-scoped book extraction covers 8/53 books; the
numeral-heading detector is built but uncommitted. All counts: query live.

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

Resolved: #1, #2, #3, #5, #15, #17.

## Known harness bugs

Both resolved: the 2026-07-18 executor write-accounting loop (`d9ab1cc`) and
`BASH_WRITE_INDICATORS` over-flagging (`569d412`). Session Routing's
DB-write hard rule and revisit trigger are unchanged.

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar,
  gated behind `NEXT_PUBLIC_FULL_NAV_ENABLED`). Pass B pending: `UsageRing`
  not yet remounted in the sidebar drawer.

---

## Next

1. **Confirm the worker's DB route is the transaction pooler (6543), not the
   session pooler (5432)** — the one residual blocking cutover (`railway
   variables` on the worker, or Alex pasting `SUPABASE_DB_URL`). Then set
   `ASYNC_ANSWER_ENABLED=true` on the backend (dark health check with
   `serving_enabled` still false), run the controlled public traffic window,
   and flip `serving_enabled` back off immediately after. Project 2 starts
   only once that cutover is stable.
2. **Position layer — revised build sequence (see Current state above; full
   detail in the audit doc), one hop not two.** In order: topic list +
   `match_stored_position()` (Open Decision #16, still the hard
   prerequisite) → build-time review workflow → the chunk-shape adapter
   (position evidence → `chat.py`'s existing chunk shape) → the
   `_insert_position_version()` concurrency fix (unguarded unique-index
   violation, found live in the pressure test) → the `chat.py` injection
   point (parallel to existing background-topic injection) → the freshness
   re-gather-and-diff sweep → rollout (shadow mode, then the async path's
   proven two-level off-switch). Also still open, not decided: whether the
   two remediated propositions get rewritten, whether the unconfirmed
   Savchuk case gets pulled, whether superseded position versions get
   retracted vs. left as-is.
3. Route `ingest_helloao.py` through `shared_ingest` (blocker #4).
4. Folder renames (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop the
   orphaned `jewish_perspectives` table.
5. Staging Supabase + a verified backup/restore test (backup exists, restore
   never tested).

SP track: SP2 done (Phases 1–9); SP4 teacher cards shipped and signed off; SP
panel refinement done. Next SP item is #43 (SP5, mobile bottom-sheet). #38
(SP0 mobile mockup) completion unverified — confirm before assuming.
