# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06 (async cutover in progress — `ASYNC_ANSWER_ENABLED`
live; Project 2 phase 1's debate-topic anchors now complete, sanctification
models removed as a debate topic — see below).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Trimmed
2026-08-01 (from ~2,700 lines) and repeatedly since. Cut material is never
the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

---

## Current state

**Deployment.** Local `main` and `origin/main` both at `127eacc` — pushed,
fully in sync, nothing pending. This session: `bec0f54`..`127eacc` (7
commits — apostolic-authority wording fix, commentary styling, 5 draft
position papers, numeral-heading book-chapter detector, eschatological-
timing anchor, decision #11 correction, `system_prompt.txt` match-up; see
Project 2 below for the debate-topic detail). Backend + frontend both
redeployed off this push — confirm both landed Ready/Online before relying
on any of it live. Async routes are LIVE-MOUNTED on the `rhemata` Railway
service (`ASYNC_ANSWER_ENABLED=true`, set 2026-08-06); DB switch
`serving_enabled=false` — no real traffic yet. Live `/chat` unchanged.

**Project 1 (scalable async answers) — cutover in progress, one real step
closer.** Worker pooler RESOLVED: transaction pooler (6543), Alex-confirmed.
`ASYNC_ANSWER_ENABLED=true` set and verified live (`/async-chat/mode`: 404 →
200). `rhemata`'s missing `SUPABASE_DB_URL` (PostgREST-only; async routes
need direct Postgres) was found and fixed by copying the worker's confirmed
transaction-pooler URL onto it. `POST /async-chat/submit` correctly refuses
503 while `serving_enabled=false`. **Not yet re-proven against this exact
deployed code:** full claim→produce→complete via the real HTTP route — only
proven previously via direct-enqueue bypass and local `producer.produce()`
calls. **Before a traffic window:** one real end-to-end submission against
the CURRENT code — Alex's call on method.

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

**Answer path — current behavior (live `/chat`, unchanged).** Buffers fully,
runs the Phase-2 retrieval-grounding guard + prose-attribution scan +
`verify_references`, resolves ungrounded credit (regenerate-once-then-
refuse), reveals as paced playback. Position-paper path serves baptism +
tongues via `chat.py` interception.

**Position layer — design revised 2026-08-04, nothing built.** One-hop
accepted (a matched position's PROPOSITIONS, never its rendered text, feed
`chat.py`'s hardened pipeline; the position's own text is a build-time
review artifact only). 2/3 fabrication cases cleared (`eligible=false`),
Savchuk unconfirmed. Topic-matching (#16) remains the unbuilt prerequisite —
see Project 2's classifier adjacency above. Detail: `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

**Corpus/data.** Propositions backfill COMPLETE. Chapter-scoped book
extraction covers 8/53 books; roman-numeral/bare-"Chapter N" numeral-heading
detector now COMMITTED (`8d6b7bc`) — still zero production callers, not
wired into real ingestion pending per-book verification (a confident-wrong-
answer failure mode was found twice building it, only one fixed — see
CLAUDE.md Landmines). Counts: query live.

**Attribution audit (2026-08-04).** 307 HistoricalChristianFaith docs
intact (#15 resolved). Lewis/Tolkien/Wilson mistagged `public_domain` —
#16, open.

**Model swap (Sonnet 5) + live model-switch lever — built, live-tested,
committed (`fe56086`).** All generation call sites on `claude-sonnet-5`,
`thinking` disabled. Real median cost $0.0504 intro / $0.0755 list.
`generation_model_config` (migration 081) holds the live model ID,
60s-cached — proven live both ways.

**max_tokens truncation — MEASURED and FIXED, 2026-08-06 (`d186c22`).**
27% of single-call answers hit the old 3000-token ceiling, half silently
(`verified_references` came back empty with zero signal). `GEN_MAX_TOKENS`
(`producer.py`/`chat.py` mirror pair) 3000→8000, verified 8/8, real usage
topped out at 5612/8000. **Still open:** `verified_references=[]` can occur
on a cleanly-completed answer with room to spare — cause unconfirmed.

---

## Open blockers

**Launch blockers (Project 1's remit, neither blocks further build work):**
~68s to a fully-revealed answer (~59% hidden reasoning, untrimmable without
an accuracy oracle — #20); ~40 simultaneous-chat ceiling — replacement
built, not cut over yet.

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

1. **One real end-to-end submission against the current deployed code**
   (brief `serving_enabled` flip, or the enqueue bypass — Alex's call), to
   prove claim→produce→complete before opening a controlled traffic window.
   Then run the window, flip `serving_enabled` back off. Project 2 build
   starts only once that cutover is stable.
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
