# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06 (Project 1 async cutover PROVEN end-to-end and now
LIVE — `serving_enabled=true`; Project 2 phase 1's debate-topic anchors
complete, sanctification models removed as a debate topic — see below).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Trimmed
2026-08-01 (from ~2,700 lines) and repeatedly since. Cut material is never
the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

---

## Current state

**Deployment.** Local `main` and `origin/main` both at `127eacc` — pushed,
fully in sync, nothing pending. Backend (`rhemata`) and worker
(`answer-worker`) Railway services both confirmed DEPLOYED at `127eacc`
(`railway status --json`: both `SUCCESS`/`RUNNING`), after `d186c22` — so
the max_tokens fix is live, not just committed, on both mirror sites.
`SUPABASE_DB_URL` (transaction pooler, `:6543`) confirmed present and
identical on both services via `railway variables`. Live `/chat` unchanged,
remains the automatic fallback on any `503 async_serving_disabled`.

**Project 1 (scalable async answers) — PROVEN end-to-end 2026-08-06;
`serving_enabled` is now TRUE, async routes SERVING real traffic.** Both
pre-flip fixes confirmed DEPLOYED (not just committed) first — see
Deployment above. Then one real question through the actual deployed HTTP
route — `POST /async-chat/submit` → `GET /async-chat/result/{job_id}` SSE,
the exact shape `frontend/lib/api.ts` uses, not a DB bypass, not a unit
test (job `b4323fe5-9f70-40c1-8447-325bd49ecbe5`, 12:48–12:49 UTC).
Result, confirmed against the `answer_jobs` row: `status=done`,
`outcome=answered`, `last_error=None`, `output_tokens=7247` (under the 8000
ceiling, clean ending — no truncation), 11 citations, 6 non-empty
`verified_references` — the exact failure mode under test (old bug
silently emptied this field on truncation) did not occur. Cost $0.173,
~106s claim-to-done. `serving_enabled` flipped true immediately after.
**Not proven by this pass:** real concurrency at the 100-dial target — one
serial request only; watch the worker under real multi-user traffic before
treating the ~40-concurrent ceiling as lifted in practice.

**Project 2 (one named voice per answer) — phase 1 DESIGNED; debate-topic
anchors now COMPLETE; classifier itself still unbuilt.** Full detail:
PLAN.md v5.24, CLAUDE.md #11/#15. "Renderer attaches names" is RETIRED as a
build target, not deferred — `reference_verifier.py`'s existing guard
already achieves the real safety goal with a size-1 permitted-name set.
**Decision #11 corrected (Alex's ruling):** sanctification models REMOVED as
a debate topic entirely, not deferred — not a genuine live debate, reverts
to an ordinary single-teacher topic. `STANDING_DEBATE_CONTRASTS`
(`position_papers.py:207-234`) now covers all 4 confirmed topics — healing
mechanics, prophetic accountability, apostolic authority (wording corrected
`bec0f54`), eschatological timing (added `57ddb67`) — each anchor's live
cache regeneration verified (fresh-embed cosine 1.000 against the current
constant). `system_prompt.txt`'s in-house-debate list corrected to match
(`127eacc`). **Still open:** the classifier itself — no code today
classifies a question against these 4 anchors; they're currently consumed
only defensively (position-paper false-match guard).

**Answer path — current behavior.** Buffers fully, runs the Phase-2
retrieval-grounding guard + prose-attribution scan + `verify_references`,
resolves ungrounded credit (regenerate-once-then-refuse); server-paced
playback on `/chat`, client-paced on the now-live async path. Position-paper
path serves baptism + tongues via interception on both `chat.py` and its
async mirror.

**Position layer — design revised 2026-08-04, nothing built.** One-hop
accepted (a matched position's PROPOSITIONS, never its rendered text, feed
`chat.py`'s hardened pipeline; the position's own text is a build-time
review artifact only). 2/3 fabrication cases cleared (`eligible=false`),
Savchuk unconfirmed. Topic-matching (#16) is the unbuilt prerequisite — see
Project 2's classifier adjacency above. Detail: `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

**Corpus/data.** Propositions backfill COMPLETE. Chapter-scoped book
extraction covers 8/53 books; roman-numeral/bare-"Chapter N" detector
COMMITTED (`8d6b7bc`) but zero production callers pending per-book
verification (see CLAUDE.md Landmines). Attribution audit (2026-08-04): 307
HistoricalChristianFaith docs intact (#15 resolved); Lewis/Tolkien/Wilson
mistagged `public_domain` (#16, open). Counts: query live.

**Model swap (Sonnet 5) + live model-switch lever — built, live-tested,
committed (`fe56086`).** All generation call sites on `claude-sonnet-5`,
`thinking` disabled. `generation_model_config` (migration 081) holds the
live model ID, 60s-cached.

---

## Open blockers

**Launch blockers (Project 1's remit, neither blocks further build work):**
~68s to a fully-revealed answer (~59% hidden reasoning, untrimmable without
an accuracy oracle — #20); ~40 simultaneous-chat ceiling — replacement now
LIVE (2026-08-06) but unproven at real concurrency, one serial test only.

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

Resolved: #1, #2, #3, #5, #15, #17. Known harness bugs: both resolved
(`d9ab1cc`, `569d412`) — Session Routing's DB-write hard rule and revisit
trigger unchanged.

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar,
  gated behind `NEXT_PUBLIC_FULL_NAV_ENABLED`). Pass B pending: `UsageRing`
  not yet remounted in the sidebar drawer.

---

## Next

1. **Watch the live flip.** `serving_enabled=true` (2026-08-06) is proven
   by one serial test job only, not a soak under real concurrency — watch
   worker logs / `answer_jobs` outcomes as real users hit it. Revert with
   one UPDATE (`serving_enabled=false`) if anything looks wrong. Project 2
   build starts once this is confirmed stable under real usage.
2. **Project 2 phase 1 build**: debate-topic classifier (anchor text now
   complete for all 4 topics — build the embedding-similarity gate,
   fail-toward-debate on uncertainty) → retrieval lock in
   `chat.py`+`producer.py` → `get_teacher_card()` precompute (depends on the
   classifier, not independent). Full detail: PLAN.md v5.24.
3. **Position layer — one-hop build sequence** (detail in the audit doc):
   topic list (#16, may double up with item 2's classifier — check before
   building either twice) → `match_stored_position()` → review workflow →
   chunk-shape adapter → concurrency fix → `chat.py` injection → rollout.
4. Route `ingest_helloao.py` through `shared_ingest` (blocker #4).
5. Folder renames (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop the
   orphaned `jewish_perspectives` table.
6. Staging Supabase + a verified backup/restore test (backup exists, restore
   never tested).
7. **Flip `async_answers/config.py`'s cost constants to list price ($3/$15)
   on/after 2026-08-31** — currently Sonnet 5's intro rate ($2/$10).
8. **Decide the roman-numeral book-chapter detector's fate** — committed
   (`8d6b7bc`) but deliberately not wired in; needs per-book verification
   before it gets a production caller, or an explicit decision to shelve it.

SP track: SP2/SP4/panel-refinement done. Next: #43 (SP5, mobile bottom-sheet).
#38 (SP0 mobile mockup) completion unverified — confirm before assuming.
