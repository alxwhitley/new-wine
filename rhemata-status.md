# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06 (Project 1 async cutover PROVEN end-to-end and now
LIVE — `serving_enabled=true`; Project 2 phase 1's debate-vs-settled
classifier now BUILT and `get_teacher_card()` fixed to use it — see below).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Trimmed
2026-08-01 (from ~2,700 lines) and repeatedly since. Cut material is never
the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

---

## Current state

**Deployment.** Railway (`rhemata` + `answer-worker`) both confirmed
DEPLOYED at `127eacc`/`d186c22` — pushed, max_tokens fix live on both
mirror sites, `SUPABASE_DB_URL` (`:6543`) confirmed identical on both. Live
`/chat` unchanged, remains the automatic fallback on any `503
async_serving_disabled`. **Local `main` is now 1 commit ahead of
`origin/main`** (`d99798a`, this session's classifier build) — NOT pushed,
NOT deployed; a backend-only change (`debate_topics.py` + `study.py`), no
migration, no env var.

**Project 1 (scalable async answers) — PROVEN end-to-end 2026-08-06;
`serving_enabled` is now TRUE, async routes SERVING real traffic.** Real
question through the deployed HTTP route (`POST /async-chat/submit` →
`GET /async-chat/result/{job_id}` SSE, `frontend/lib/api.ts`'s exact shape)
confirmed against the `answer_jobs` row: `status=done`, `outcome=answered`,
`output_tokens=7247` (no truncation), 11 citations, 6 non-empty
`verified_references` — the failure mode under test did not occur. Cost
$0.173, ~106s. **Not proven:** real concurrency at the 100-dial target —
one serial request only; watch the worker under real multi-user traffic
before treating the ~40-concurrent ceiling as lifted in practice.

**Project 2 (one named voice per answer) — phase 1's classifier now BUILT
and `get_teacher_card()` fixed to use it (commit `d99798a`); retrieval lock
(step 2) NOT started, classifier not yet consumed outside `study.py`.**
Full detail: PLAN.md v5.24, CLAUDE.md #11/#15 (roadmap entries not updated
this session — records commit scoped to this file). `backend/app/services/
debate_topics.py::classify_topic(question) -> "debate"|"settled"` —
deterministic phrase-list matching mirroring `is_calvinism_predestination_
topic()`'s shape (Open Decision #20 already ruled out LLM/embedding
judgment for this). Defaults to `"debate"` on no match, never `"settled"`;
unmatched questions log at INFO for future list-widening, same open gap as
the Calvinism matcher. Also exports `matched_debate_topic(question) ->
Optional[str]` since `classify_topic()`'s binary output can't distinguish
"matched a debate topic" from "matched nothing, defaulted" — step 2 will
need that distinction (`matched_debate_topic() is not None`, not
`classify_topic() == "debate"`) same as the `get_teacher_card()` fix did:
added `TEACHER_POSITION_DEBATE_PROMPT` (closes the same force-resolved-
tension gap `positions.py`'s Calvinism prompt closes, generalized to all 4
topics), gated on `matched_debate_topic()` non-None — gating on
`classify_topic()=="debate"` instead was caught live by this build's own
test putting false "teachers disagree" framing on ordinary questions like
tithing. `scripts/test_debate_topics.py` (Tier A + live Tier B vs. Derek
Prince) passing; independent planner-reviewer pass found no invariant
violation, no DB write, no scope creep before commit.

**Answer path — current behavior.** Buffers fully, runs the Phase-2
retrieval-grounding guard + prose-attribution scan + `verify_references`,
resolves ungrounded credit (regenerate-once-then-refuse); server-paced
playback on `/chat`, client-paced on the now-live async path. Position-paper
path serves baptism + tongues via interception on both `chat.py` and its
async mirror. **Position layer** — design revised 2026-08-04, nothing
built; one-hop accepted (a matched position's PROPOSITIONS, never its
rendered text, feed `chat.py`'s hardened pipeline). 2/3 fabrication cases
cleared (`eligible=false`), Savchuk unconfirmed. Topic-matching (#16) is
the unbuilt prerequisite — see Project 2's classifier adjacency above.
Detail: `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

**Corpus/data.** Propositions backfill COMPLETE. Chapter-scoped book
extraction covers 8/53 books; roman-numeral/bare-"Chapter N" detector
COMMITTED (`8d6b7bc`) but zero production callers pending per-book
verification (see CLAUDE.md Landmines). Attribution audit (2026-08-04): 307
HistoricalChristianFaith docs intact (#15 resolved); Lewis/Tolkien/Wilson
mistagged `public_domain` (#16, open). Counts: query live. **Model swap**
(Sonnet 5) + live model-switch lever built, live-tested, committed
(`fe56086`) — all generation call sites on `claude-sonnet-5`, `thinking`
disabled; `generation_model_config` (migration 081) holds the live model
ID, 60s-cached.

---

## Open blockers

**Launch blockers (Project 1's remit, neither blocks further build work):**
~68s to a fully-revealed answer (~59% hidden reasoning, untrimmable without
an accuracy oracle — #20); ~40-concurrent ceiling replacement LIVE
(2026-08-06) but unproven at real concurrency, one serial test only.

- **#4** `ingest_helloao.py` unconverted — blocks 8 further HelloAO commentaries only.
- **#6** Guest→account conversion likely broken (cookie/localStorage mismatch). `docs/audits/GUEST_AUTH_AUDIT.md`.
- **#7** Auth CTA inconsistencies (`/library/authors`, `/home`, dead `AuthButton.tsx`). `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.
- **#9** v4 propositions prompt (`EXTRACTION_PROMPT_V4`) built, unwired — adopt/iterate/discard undecided.
- **#10** Precept Austin raw-source gap — fewer raw scrape files than ingested docs.
- **#11** `verify_chunk_alignment.py` docstring stale; **#12** `jewish_perspectives` table orphaned (2 rows, no code references).
- **#13** SP2 Study Panel — no real screen-reader (VoiceOver/NVDA) pass ever run.
- **#14** Hebrew lexicon (TBESH) not covered by the Greek CC BY 4.0 grant — don't build against it until cleared.
- **#16** Lewis/Tolkien/Wilson mistagged `public_domain` under HistoricalChristianFaith — durable fix needs a per-author license override (Alex's schema decision).
- **#18** Home-page names Bevere (empty, 0 props) and Koulianos (not in corpus) as "trusted teachers" — living-minister misrepresentation, still open.
- **#19** External pipeline diagram (non-repo, not found) stale in 4 ways — fix if it resurfaces.

Resolved: #1, #2, #3, #5, #15, #17. Known harness bugs: both resolved
(`d9ab1cc`, `569d412`) — Session Routing's hard rule/revisit trigger unchanged.

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar,
  gated behind `NEXT_PUBLIC_FULL_NAV_ENABLED`). Pass B pending:
  `UsageRing` not yet remounted in the sidebar drawer.

---

## Next

1. **Watch the live flip.** `serving_enabled=true` (2026-08-06) is proven
   by one serial test job only, not a soak under real concurrency — watch
   worker logs / `answer_jobs` outcomes as real users hit it. Revert with
   one UPDATE (`serving_enabled=false`) if anything looks wrong. Project 2
   build starts once this is confirmed stable under real usage.
2. **Project 2 phase 1**: classifier + `get_teacher_card()` fix DONE (see
   Project 2 section above — supersedes this item's prior "embedding-
   similarity gate" framing). Remaining: the retrieval lock itself in
   `chat.py`+`producer.py` (step 2, not started).
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

SP track: SP2/SP4/panel-refinement done. Next: #43 (SP5, mobile
bottom-sheet). #38 (SP0 mobile mockup) completion unverified.
