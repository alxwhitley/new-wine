# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-13 (Grok authorized-write session).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**This session executed two already-reviewed production writes** — an
explicit, one-time exception to "harness never executes production DB
writes." Claude wrote/reviewed the scripts; Grok ran each once, verbatim,
no retries, no extra SQL. Independently re-read against the live DB at
close (same `SUPABASE_DB_URL`).

1. **Retired `background_topics.topic_key='gift_of_prophecy'`.** One row
   deleted and confirmed gone. Table now holds only `baptism_holy_spirit`
   and `speaking_in_tongues`. Underlying document
   `52a4f7fd-252d-4b99-94a0-1e2a1055fcaa` still present; 18 chunks
   untouched. Do not re-run the retire script.
2. **Ingested two house position papers** via
   `shared_ingest.ingest_document()` (no `--dry-run`):
   - Deliverance and Spiritual Warfare —
     `fe8c8381-6438-4ad8-9eaa-5ce581f6071b`, 8 chunks
   - Prosperity and Faith Teaching —
     `4545e31f-e728-43e8-8030-b030337d92fa`, 4 chunks
   Both `status="processed"`, `propositions: skipped_licensed` (owned
   house source — expected). Re-read: exactly one document per title/path,
   no duplicates. IDs match `PILLARS` in `position_papers.py` (registered
   later the same day in `5ccc73c`).

**Already true before this wrap, unchanged here:** all 8 charismatic
pillars are registered/live; remaining four closed in `a81bb67`/`10374e0`.
One answer path (async, `serving_enabled` TRUE). Quote rail live. Position
one-hop live on origin.

**Auto Mode landmine (still current):** Claude Code Auto Mode blocks
direct production DB writes; no settings self-grant. The Grok-routing
pattern used for these two writes is recorded in CLAUDE.md Landmines —
working pattern, not a settled practice.

**O5 harness:** built, review-ACCEPT, **not merged**
(`codex/o5-budgets-hard-stops`). Merge + records closeout wait on Alex.
O6 not started. O3/O4 still local-only on `main` (`b580915`/`7ab9f15`).

**Worktree note:** uncommitted edits exist in `CLAUDE.md`, `PLAN.md`,
`quote_subchunk_exclusion.py`, and
`extract_quote_candidates_derek_prince.py` from a different session. Not
this session's; left untouched.

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
