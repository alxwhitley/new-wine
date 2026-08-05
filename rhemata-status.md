# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06 (max_tokens truncation measured, fixed, and
verified live — see below; committed `d186c22`).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Trimmed
2026-08-01 (from ~2,700 lines) and repeatedly since. Cut material is never
the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

---

## Current state

**Deployment.** `origin/main` = local `main` at `2ba9f12` (pushed 2026-08-04).
Async path stays DARK (`ASYNC_ANSWER_ENABLED` unset, DB switch
`serving_enabled=false`); live serving path unchanged. Deploy history:
`2ba9f12`, `6dca017`, `196f1f2`, `dd71b87`; full narrative in PLAN.md.

**Project 1 (scalable async answers) — worker built, deployed, verified;
switches still OFF.** Worker on Railway; one real end-to-end generation
proven ($0.076); 20/20 simultaneous generations measured. **Residual:**
worker's `SUPABASE_DB_URL` — transaction pooler (6543) or session pooler
(5432, ~12/worker cap)? Needs `railway variables` or Alex pasting the URL.
Detail: PLAN.md + CLAUDE.md's async landmine.

**Answer path — current behavior (live `/chat`, unchanged).** Buffers fully,
runs the Phase-2 retrieval-grounding guard + prose-attribution scan +
`verify_references`, resolves ungrounded credit (regenerate-once-then-
refuse), reveals as paced playback. Position-paper (house-voice) path
serves baptism + tongues via `chat.py` interception, still streams live.

**Position layer — design revised 2026-08-04, nothing built.** Two-hop
stored-position-then-rewrite rejected (can't see drift baked into a stored
position; can't detect corpus material being ADDED). **Accepted: one hop**
— a matched position's underlying propositions, never its rendered text,
feed `chat.py`'s hardened pipeline directly; the position's own text is a
build-time review artifact only. Cleared 2/3 fabrication cases (Ravenhill,
Conlon — `eligible=false`), Savchuk unconfirmed. Topic-matching
(`match_stored_position()`, #16) remains the unbuilt prerequisite. Detail:
`docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

**Corpus/data.** Propositions backfill COMPLETE. Chapter-scoped book
extraction covers 8/53 books; numeral-heading detector built, uncommitted.
Counts: query live.

**Attribution audit (2026-08-04).** 307 HistoricalChristianFaith docs intact
(#15 resolved). C.S. Lewis/Tolkien/Wilson mistagged `public_domain` — #16,
open. Detail: `docs/audits/historical_commentary_attribution_reverification_2026-08-04.md`.

**Model swap (Sonnet 5) + live model-switch lever — built, live-tested,
committed (`fe56086`).** `claude-sonnet-4-5` → `claude-sonnet-5` at all
generation call sites, `thinking={"type":"disabled"}` added explicitly
everywhere (Sonnet 5 defaults adaptive thinking ON when omitted). Real median
cost $0.0504 at intro rate / $0.0755 at list — vs $0.039 baseline
(`docs/audits/per_answer_cost_measurement_2026-08-03.md`): +29%/+94%, new
tokenizer, not a broken swap. `generation_model_config` table (migration 081)
holds the live model ID; `llm_client.get_generation_model()` reads it with a
60s cache, falls back to a hardcoded constant (logged) if missing/unreachable
— proven live both ways. **Reproduced, not new:** `match_position_paper`'s
scripture-question over-match fired on 2/7 test questions.

**max_tokens truncation — MEASURED and FIXED, 2026-08-06 (`d186c22`).**
Measured across 20 real moderate-to-long questions (offline
`producer.produce()`, $1.75): **27% of single-call answers (4/15) hit the old
3000-token ceiling**, split ~evenly between (a) visible — §7a's "cut off"
notice fires — and (b) **silent, not previously known** — `<answer>` closes
cleanly (reads complete, no disclosure) but `<reference_mentions>`, which
comes AFTER `</answer>` in the same budget, never starts/finishes, so
`verified_references` comes back empty with zero signal. Confirmed via
`stop_reason` instrumentation, not inferred. **Fix:** `GEN_MAX_TOKENS`
(`producer.py:51`) and `chat.py:568` (documented mirror pair) both
3000→8000. Post-edit verification on the actual edited files, both call
sites, 4 known-failing questions: 8/8 pass, `stop_reason=end_turn`
throughout, real usage topped out at 5612/8000 — no runaway generation. Cost
impact ~zero for typical answers; mixed-sign for the previously-truncating
minority (some used FEWER tokens post-fix — one clean pass replaces what was
two truncated regenerate-once attempts). **Still open, not fixed this
session:** `verified_references=[]` can occur on a cleanly-completed answer
with room to spare (seen at 2865/3000 pre-fix, 6085/8000 and 3073/8000
post-fix, all `end_turn`) — not a token-budget artifact, cause unconfirmed.

---

## Open blockers

**Launch blockers (Project 1's remit, neither blocks further build work):**
~68s to a fully-revealed answer (~59% is hidden model reasoning, untrimmable
without an accuracy oracle — Open Decision #20); ~40 simultaneous-chat
ceiling (anyio threadpool exhaustion) — replacement built, not cut over yet.

- **#4** `ingest_helloao.py` unconverted — blocks 8 further HelloAO commentaries only, not corpus growth generally.
- **#6** Guest→account conversion likely broken (cookie/localStorage mismatch). `docs/audits/GUEST_AUTH_AUDIT.md`.
- **#7** Auth CTA inconsistencies (`/library/authors`, `/home`, dead `AuthButton.tsx`). `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.
- **#9** v4 propositions prompt (`EXTRACTION_PROMPT_V4`) built, unwired — adopt/iterate/discard undecided.
- **#10** Precept Austin raw-source gap — fewer raw scrape files than ingested docs.
- **#11** `verify_chunk_alignment.py` docstring stale (describes removed insert modes).
- **#12** `jewish_perspectives` table orphaned (2 rows, no code references).
- **#13** SP2 Study Panel — no real screen-reader (VoiceOver/NVDA) pass ever run.
- **#14** Hebrew lexicon (TBESH) not covered by the Greek CC BY 4.0 grant — don't build against it until cleared.
- **#16** Lewis/Tolkien/Wilson mistagged `public_domain` under HistoricalChristianFaith — durable fix needs a per-author license override (Alex's schema decision).
- **#18** Home-page names Bevere (empty, 0 props) and Koulianos (not in corpus) as "trusted teachers" — living-minister misrepresentation, still open.
- **#19** External pipeline diagram (non-repo, not found) stale in 4 ways — fix if it resurfaces.

Resolved: #1, #2, #3, #5, #15, #17.

## Known harness bugs

Both resolved (`d9ab1cc`, `569d412`). Session Routing's DB-write hard rule
and revisit trigger unchanged.

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar,
  gated behind `NEXT_PUBLIC_FULL_NAV_ENABLED`). Pass B pending: `UsageRing`
  not yet remounted in the sidebar drawer.

---

## Next

1. **Confirm the worker's DB route is the transaction pooler (6543), not
   session pooler (5432)** — one residual blocking cutover (`railway
   variables` on the worker, or Alex pasting `SUPABASE_DB_URL`). Then set
   `ASYNC_ANSWER_ENABLED=true` (dark health check, `serving_enabled` still
   false), run the controlled traffic window, flip back off. Project 2
   starts only once that cutover is stable.
2. **Position layer — one-hop build sequence** (detail in the audit doc):
   topic list + `match_stored_position()` (#16) → review workflow →
   chunk-shape adapter → concurrency fix → `chat.py` injection → freshness
   sweep → rollout. Undecided: rewrite the 2 remediated propositions? pull
   Savchuk? retract superseded versions?
3. Route `ingest_helloao.py` through `shared_ingest` (blocker #4).
4. Folder renames (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop the
   orphaned `jewish_perspectives` table.
5. Staging Supabase + a verified backup/restore test (backup exists, restore
   never tested).
6. **Flip `async_answers/config.py`'s cost constants to list price ($3/$15)
   on/after 2026-08-31** — currently Sonnet 5's intro rate ($2/$10); the
   `*** EXPIRES 2026-08-31 ***` comment doesn't enforce itself. Miss this and
   cost estimates silently under-report ~33%.

SP track: SP2/SP4/panel-refinement done. Next: #43 (SP5, mobile bottom-sheet).
#38 (SP0 mobile mockup) completion unverified — confirm before assuming.
