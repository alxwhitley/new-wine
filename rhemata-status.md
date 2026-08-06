# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06 (Project 1 async cutover PROVEN end-to-end and now
LIVE — `serving_enabled=true`; Project 2 phase 1 steps 1+2 DONE; position
papers rebuilt as fence + guarded retrieval, closing the 2026-08-01
CLAUDE.md decision #8 conflict — see below).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Cut material is
never the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

---

## Current state

**Deployment.** Railway (`rhemata` + `answer-worker`) both confirmed
DEPLOYED at `127eacc`/`d186c22` — pushed, max_tokens fix live on both
mirror sites, `SUPABASE_DB_URL` (`:6543`) confirmed identical on both. Live
`/chat` unchanged, remains the automatic fallback on any `503
async_serving_disabled`. **Local `main` is now 6 commits ahead of
`origin/main`** (Project 2 phase 1 steps 1+2 + the position-papers rebuild,
`d99798a`/`0f6e372`/`ff7a389`/`97c007c`/`b9af800` + this session's records) —
NOT pushed, NOT deployed; backend-only changes, no migration, no env var.

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

**Project 2 (one named voice per answer) — phase 1 steps 1+2 DONE**
(`d99798a`/`0f6e372` step 1, `ff7a389`/`97c007c` step 2); **step 3 (quote
rail) still blocked.** PLAN.md v5.26, CLAUDE.md #11/#15. Step 1:
`debate_topics.py`'s deterministic phrase-list `classify_topic()`/
`matched_debate_topic()`/`matched_settled_topic()`, defaults to `"debate"`,
never `"settled"`. Step 2: `single_teacher_lock.py::
apply_single_teacher_lock()` restricts retrieval to one teacher when a
`matched_settled_topic()`-confirmed question's chunks concentrate >=60% in
them (`app.services.dominance.determine_scope()`, shared with
`scripts/positions.py`). Still doesn't fire on real tongues questions (no
teacher clears 60% dominance) — but now for a live, not structural, reason
(see below; the original "never even reaches retrieval" premise is gone).

**Position papers — rebuilt 2026-08-06 as fence + guarded retrieval
(`b9af800`), closing CLAUDE.md decision #8's flagged 2026-08-01 conflict**
(Invariant 12(b)/ARCHITECTURE.md blessed the exact direct-serve mechanism
decision #8 said should never exist — now resolved in #8's favor). A match
(2 live pillars — `baptism_holy_spirit`, `speaking_in_tongues`; 6 more
unregistered drafts) no longer bypasses retrieval: the paper's body is
injected as bounding `[House Position]` silent context around a normal,
cited answer. New `position_paper_exclusion.py` — one call/question —
excludes any retrieved teacher whose material genuinely contradicts the
house position, never silently reframed into agreement (decision #9's
flagged risk, also fixed at `system_prompt.txt`'s self-check). If
exclusion empties an otherwise-real retrieval, `render_paper_voice_with_
disclaimer()` serves the paper's voice WITH the standard disclaimer — the
ONLY sanctioned reason for that fallback. Live-tested on both papers: real
exclusions fired on genuine corpus contradictions; a constructed everyone-
excluded case proved the fallback fires, uncited, disclaimer present.
CLAUDE.md #8/#9 RESOLVED + 2 new decisions (#16/#17); Invariant 12(b)/
ARCHITECTURE.md/PLAN.md corrected to match. `single_teacher_lock.py` and
the classifier untouched.

**Answer path — current behavior.** Buffers fully, runs the Phase-2
retrieval-grounding guard + prose-attribution scan + `verify_references`,
resolves ungrounded credit (regenerate-once-then-refuse); server-paced
playback on `/chat`, client-paced on the now-live async path.
**Position layer** (the OTHER "position" — teacher/corpus `positions`
table, unrelated to position PAPERS above) — design revised 2026-08-04,
nothing built; one-hop accepted (a matched position's PROPOSITIONS, never
its rendered text, feed `chat.py`'s pipeline). 2/3 fabrication cases
cleared (`eligible=false`), Savchuk unconfirmed. Topic-matching (#16) is
the unbuilt prerequisite. Detail: `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

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

- **#4** `ingest_helloao.py` unconverted — blocks 8 further HelloAO commentaries only. **#6** Guest→account conversion likely broken (cookie/localStorage mismatch). `docs/audits/GUEST_AUTH_AUDIT.md`.
- **#7** Auth CTA inconsistencies (`/library/authors`, `/home`, dead `AuthButton.tsx`). `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.
- **#9** v4 propositions prompt (`EXTRACTION_PROMPT_V4`) built, unwired — adopt/iterate/discard undecided.
- **#10** Precept Austin raw-source gap — fewer raw scrape files than ingested docs.
- **#11** `verify_chunk_alignment.py` docstring stale; **#12** `jewish_perspectives` orphaned (2 rows); **#13** SP2 Study Panel — no real screen-reader pass ever run.
- **#14** Hebrew lexicon (TBESH) not covered by the Greek CC BY 4.0 grant. **#16** Lewis/Tolkien/Wilson mistagged `public_domain` under HistoricalChristianFaith — needs a per-author license override.
- **#18** Home-page names Bevere (empty, 0 props) and Koulianos (not in corpus) as "trusted teachers" — living-minister misrepresentation, still open. **#19** External pipeline diagram stale in 4 ways — fix if it resurfaces.

Resolved: #1-3, #5, #15, #17. Harness bugs: both resolved (`d9ab1cc`, `569d412`).

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
   one UPDATE (`serving_enabled=false`) if anything looks wrong.
2. **Project 2 phase 1: steps 1+2 DONE, position papers rebuilt** (see
   sections above). Remaining: step 3, the quote rail — still blocked,
   unaffected.
3. **Position layer — one-hop build sequence** (detail in the audit doc):
   topic list (#16, may double up with item 2's classifier — check before
   building either twice) → `match_stored_position()` → review workflow →
   chunk-shape adapter → concurrency fix → `chat.py` injection → rollout.
4. Route `ingest_helloao.py` through `shared_ingest` (blocker #4). Folder
   renames (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop the
   orphaned `jewish_perspectives` table.
5. Staging Supabase + a verified backup/restore test (backup exists,
   restore never tested).
6. **Flip `async_answers/config.py`'s cost constants to list price ($3/$15)
   on/after 2026-08-31** — currently Sonnet 5's intro rate ($2/$10).
7. **Decide the roman-numeral book-chapter detector's fate** — committed
   (`8d6b7bc`) but deliberately not wired in; needs per-book verification
   before it gets a production caller, or an explicit decision to shelve it.

SP track: SP2/SP4/panel-refinement done. Next: #43 (SP5, mobile bottom-sheet). #38 (SP0 mobile mockup) completion unverified.
