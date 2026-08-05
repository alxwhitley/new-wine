# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06 (Sonnet 5 model swap + a live model-switch config
lever both built and live-tested with real generations — see below; both
uncommitted).

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

**Attribution audit (2026-08-04).** `docs/audits/
historical_commentary_attribution_reverification_2026-08-04.md` — 307
HistoricalChristianFaith docs intact, nothing stripped (#15 resolved). C.S.
Lewis/Tolkien/Douglas Wilson mistagged `public_domain` — #16, still open.

**Model swap (Sonnet 5) — built, live-tested, NOT committed.**
`claude-sonnet-4-5` → `claude-sonnet-5` at all generation call sites;
`thinking={"type":"disabled"}` added explicitly everywhere (Sonnet 5
defaults adaptive thinking ON when omitted — would've silently eaten the
`max_tokens=3000` budget). Harness-built + independently re-verified.
**Live-tested 2026-08-06** — 7 real generations via `producer.produce()`
(offline, SELECT-only, ~$0.26 total): teacher-allowlist +
`verify_references` guards held every time, zero misattribution. **Real
median cost $0.0504 at the intro rate ($2/$10/MTok, expires 2026-08-31),
$0.0755 at list ($3/$15)** — vs the $0.039 baseline
(`docs/audits/per_answer_cost_measurement_2026-08-03.md`): +29%/+94%,
driven by the new tokenizer, not a broken swap. **Real risk found:** one
long-form question hit `max_tokens=3000`, cut off cleanly (§7a fired, no
leak) — but lost ALL citation verification (0 refs vs 5-6 real citations
visibly present), since the model never reached `<reference_mentions>`.
**Reproduced, not new:** `match_position_paper`'s scripture-question
over-match (already flagged, 2026-08-03 audit) fired on 2/7 questions.

**Same day: live model-switch lever added, ALSO uncommitted.** New table
`generation_model_config` (migration 081, a real DB write — correctly
plain-script per Session Routing's hard rule, not harness) holds the live
model ID; `llm_client.get_generation_model()` reads it with a 60s
in-process cache (matches `source_filter.get_disabled_filters()`), falling
back to the hardcoded `GENERATION_MODEL` constant — logged — on any
missing/empty/unreachable value; no allow-list. Every generation call site
now reads through this accessor instead of a frozen constant (producer.py's
old `GEN_MODEL` and positions.py's `MODEL` module-level snapshots are both
gone — either would defeat a live switch). **Proven live:** switched to
`claude-haiku-4-5`, confirmed via real `chat._stream_answer()` +
`producer._generate_and_capture()` calls that the actual Anthropic
`response.model` reflects it; switched back to `claude-sonnet-5`, confirmed
again; simulated an empty config value, confirmed the fallback fires
(logged) and generation still succeeds. No env var/flag/serving-switch
touched. Both this and the model swap are uncommitted, same diff.

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

1. **Confirm the worker's DB route is the transaction pooler (6543), not the
   session pooler (5432)** — the one residual blocking cutover (`railway
   variables` on the worker, or Alex pasting `SUPABASE_DB_URL`). Then set
   `ASYNC_ANSWER_ENABLED=true` on the backend (dark health check with
   `serving_enabled` still false), run the controlled public traffic window,
   and flip `serving_enabled` back off immediately after. Project 2 starts
   only once that cutover is stable.
2. **Position layer — one-hop build sequence** (Current state above; detail
   in the audit doc): topic list + `match_stored_position()` (#16) →
   review workflow → chunk-shape adapter → concurrency fix → `chat.py`
   injection → freshness sweep → rollout. Undecided: rewrite the 2
   remediated propositions? pull Savchuk? retract superseded versions?
3. Route `ingest_helloao.py` through `shared_ingest` (blocker #4).
4. Folder renames (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop the
   orphaned `jewish_perspectives` table.
5. Staging Supabase + a verified backup/restore test (backup exists, restore
   never tested).
6. **Flip `async_answers/config.py`'s cost constants back to list price on or
   after 2026-08-31.** `USD_PER_MTOK_INPUT`/`USD_PER_MTOK_OUTPUT` currently
   hold Sonnet 5's introductory rate ($2/$10 per MTok, Alex's call
   2026-08-05), not list price ($3/$15) — the constants themselves carry an
   `*** EXPIRES 2026-08-31 ***` comment, but nothing enforces the flip
   automatically. Miss this and every cost estimate silently under-reports by
   ~33% after the intro window closes.

SP track: SP2/SP4/panel-refinement done. Next: #43 (SP5, mobile bottom-sheet).
#38 (SP0 mobile mockup) completion unverified — confirm before assuming.
