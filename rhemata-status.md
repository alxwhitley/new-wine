# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-07 (session close: matcher landed + #14 prep pack +
pushed to origin).

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-07) — Grok mechanical pass; origin pushed.**

1. **`match_stored_position()` DONE (inert).** Commit `2c2e7b8`. Module
   `backend/app/services/stored_position_topics.py` +
   `scripts/test_stored_position_topics.py`. Six OD #16 V1 keys; debate wins;
   paper-fenced out; multi-match → None + log. Tier A+B green (live
   `is_current` rows for all six). **No live caller** — one-hop injection
   still unbuilt.
2. **Records commits** `b5c0b81`: PLAN v6 lean + `docs/plan-archive.md`
   (v5.33 archive), CLAUDE pooler residual closed (:6543 confirmed), status.
3. **PLAN #14 prep only (no renames, no DROP).** Commit `67618cb` →
   `docs/audits/plan14_housekeeping_prep_2026-08-07.md`. Confirmed:
   `jewish_perspectives` = 2 live rows, **zero** runtime code refs; draft
   migration 084 text in that audit (not applied). Rename blast radius =
   5 scripts + ARCHITECTURE tree; `sources/stepbible` and `sources/inbox`
   do not exist yet; `sources/` is gitignored so renames are local FS +
   path edits. **Do not execute renames/DROP without Alex naming which.**

**On origin/main:** `2c2e7b8`, `b5c0b81`, `67618cb` (and this close commit).

**Still live (product).**

- **Project 1 async:** `serving_enabled` TRUE; pooler :6543; 100-dial
  concurrency unproven.
- **Project 2 phase 1:** single-teacher lock + debate classifier; lock
  rarely fires.
- **Project 3 quote rail:** async-only; few approved quotes; threshold 0.40.
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
5. Quote curation; chat.py quote wire = product call.
6. Hygiene: #13 helloao; #16 feedback→flag keep/kill.

SP: next #43 mobile sheet. Pass B: remount `UsageRing` in drawer.
