# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-07 (session: land inert `match_stored_position()` +
fold prior records work into commits).

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-07) — matcher build landed + records commits.**

1. **`match_stored_position()` DONE (inert).** `backend/app/services/
   stored_position_topics.py` + `scripts/test_stored_position_topics.py`.
   Six V1 topic keys; debate wins; paper-fenced out; multi-match → None.
   Tier A+B green (live DB: all six keys have `is_current` rows). **No live
   caller** — one-hop injection not wired.
2. **Prior records work committed** (PLAN v6.0 lean + `docs/plan-archive.md`,
   pooler residual closed in CLAUDE, status folds).

**Still live (unchanged product state).**

- **Project 1 async:** `serving_enabled` TRUE; pooler :6543 confirmed;
  concurrency at 100-dial unproven.
- **Project 2 phase 1:** single-teacher lock + debate classifier shipped;
  lock rarely fires.
- **Project 3 quote rail:** live async-only; 2 approved quotes; threshold 0.40.
- **Position papers:** fence + exclusion + disclaimer fallback.
- **Position layer one-hop:** **matcher only**; injection sequence still open.
- **Corpus:** props backfill complete; book chapters 8/53; counts query live.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at scale.

- **#13** `ingest_helloao.py` unconverted (only remaining chokepoint script).
- Guest→account, auth CTAs, v4 props prompt, Precept Austin citable-author
  leak, `jewish_perspectives` drop, SP residuals, Hebrew lexicon grant,
  Lewis/Tolkien/Wilson mistag, embedded third-party quote spans.
- **Phase 1.3 flip** still open (inventory done; Settled #12 ⚠).

---

## Next

1. **One-hop injection sequence** after matcher: lookup current position by
   key → feed its PROPOSITIONS (never rendered text) into hardened answer
   path → review / concurrency / rollout (see 2026-08-04 diagnostic).
2. Async concurrency proof at 100-dial.
3. Phase 1.3 **flip decision** (Ravenhill/Savchuk/Poonen subset? never
   sentinel).
4. Quote curation; chat.py quote wire = product call.
5. Hygiene: #13 helloao, #14 renames, roadmap #16 feedback→flag keep/kill.

SP: next #43 mobile sheet. Pass B: remount `UsageRing` in drawer.
