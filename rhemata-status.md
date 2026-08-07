# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-07 (session close: mirror-unification complete,
chat.py deleted — local commits only, NOT yet pushed to origin).

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-07) — Mirror-unification job: chat.py deleted,
async is the only answer path.** Ran through the repo's harness
(executor/planner-reviewer); two independent review passes REJECTED work
before approving it (a fabricated code-comment claim about git history;
stale post-deletion prose in producer.py/metering.py/api.ts) — both caught
and fixed pre-commit, not shipped.

1. **Commit `4557e5c`** — extracted ~33 shared leaf functions/constants out
   of chat.py into `backend/app/services/answer_toolbox.py` (belongs to
   neither path); repointed `producer.py` + 7 scripts; retired
   `scripts/async_parity_check.py` (its whole purpose — proving producer.py
   stayed in sync with chat.py — had nothing left to prove); fixed an
   unrelated pre-existing broken import in `sp1_answer_harness.py`
   (`_get_anthropic`, gone from chat.py since 2026-07-18's `b4a8c8c`).
2. **Read-only diagnostic (no commit)** — diffed the two remaining
   duplicate-mirror pairs. Metering: IDENTICAL, consolidated. Conversation
   persistence: DRIFTED — chat.py's `_save_conversation` had real
   silent-data-loss bugs (stale client-supplied `conversation_id`,
   mid-persist crash, non-atomic two-write race) that
   `conversation_store.py`'s single-transaction, idempotent version already
   avoided. **Alex's call: let chat.py's version die with the deletion, not
   backported.**
3. **Commit `e223c98`** — consolidated metering onto one function; removed
   the frontend's silent fallback-to-chat.py entirely (Alex: no fallback of
   any kind, ever — a failure now surfaces as a real visible error via
   `callbacks.onError`); recharacterized `async_answer_config.serving_enabled`
   as an honest emergency pause, not a rollback (nothing left to roll back
   to); removed the `ASYNC_ANSWER_ENABLED` env gate (async mounts
   unconditionally now, same as every other router); **deleted
   `backend/app/routers/chat.py`** and its `/chat` mount. Caught and fixed,
   before deletion, a real would-be 100%-outage bug: `producer.py`'s
   house-position exclusion call still transited through
   `app.routers.chat` — retargeted to `position_paper_exclusion.py`
   directly, proven live (real Anthropic/embedding/Cohere calls) both
   before and after the deletion.
4. **Commit `5d660ee`** (docs) — CLAUDE.md's Project 1 + quote-rail
   landmines and PLAN.md's Phase 1 entry corrected to resolved-history
   framing; ARCHITECTURE.md repointed off chat.py, plus one pre-existing
   stale figure fixed along the way (`max_tokens=3000` documented, real
   value is `GEN_MAX_TOKENS = 8000`).

**Not fully proven:** a real job through the actual queue+worker (not just
a direct `produce()` call) hit connection-pool exhaustion (`max clients
reached`, local `:5432` session pooler capped at 15) on the last two smoke
runs. Read as a local-dev-environment artifact — the direct accuracy-
critical path (real citations + verified refs) and the queue mechanics for
a simple case both proved out cleanly — not a code regression, but not
independently confirmed at scale either.

**Local commits, NOT pushed:** `4557e5c`, `e223c98`, `5d660ee` (and this
close commit) — on top of the prior session's `2c2e7b8`/`b5c0b81`/`67618cb`,
which WERE pushed. Push is Alex's call, not yet requested.

**Still live (product).**

- **Answer path:** ONE path now (async; chat.py deleted). `serving_enabled`
  TRUE = live and unpaused; pooler :6543 in prod; 100-dial concurrency still
  unproven at scale (unrelated to this session's local pooler exhaustion).
- **Project 2 phase 1:** single-teacher lock + debate classifier; lock
  rarely fires.
- **Project 3 quote rail:** the only path now runs it; few approved quotes;
  threshold 0.40.
- **Position papers:** fence + exclusion + disclaimer fallback.
- **Position layer one-hop:** matcher only; injection sequence open.
- **Corpus:** props backfill complete; book chapters 8/53; counts query live.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at scale.

- **#13** `ingest_helloao.py` unconverted (only remaining chokepoint script).
- Guest→account, auth CTAs, v4 props prompt, Precept Austin citable-author
  leak, **#14 apply** (prep done — renames + `jewish_perspectives` DROP still
  need Alex), SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson
  mistag, embedded third-party quote spans.
- **Phase 1.3 flip** still open (inventory done; Settled #12 ⚠).

---

## Next

1. **One-hop injection** (Opus-shaped, not mechanical): lookup position by
   key → feed PROPOSITIONS only into hardened answer path → review /
   concurrency / rollout. Matcher is ready; wiring is not.
2. Async concurrency proof at 100-dial.
3. Phase 1.3 **flip decision** (Ravenhill/Savchuk/Poonen subset? never
   sentinel).
4. **#14 apply** when Alex says rename / drop / both — use
   `docs/audits/plan14_housekeeping_prep_2026-08-07.md` as the checklist.
5. Quote curation (chat.py wiring question is moot now — one path, always wired).
6. Hygiene: #13 helloao; #16 feedback→flag keep/kill.
7. If Alex wants real confidence in the queue+worker path at scale (not just
   this session's local smoke test), a controlled run against a connection
   pool that isn't capped at 15 would close the "not fully proven" gap above.

SP: next #43 mobile sheet. Pass B: remount `UsageRing` in drawer.
