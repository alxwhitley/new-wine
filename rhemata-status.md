# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-07 (session: decision #5 commentary hard-exclude
pushed `c549413`; Open Decision #16 V1 topic list adopted seed-only;
session-close skill migrated out of always-loaded CLAUDE.md; Claude skill/
Notion cleanup in user home config).

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-07).**

1. **Settled decision #5 — commentaries out of answers.** Hard-exclude
   `source_kind`/`source_type` commentary at Step 2.6 + post-neighbor strip on
   both `chat.py` and `producer.py`. Soft weight + `COMMENTARY_CONTEXT_CAP`
   retired. Study Mode unchanged. Unit
   `scripts/test_commentary_answer_exclusion.py` ALL PASS; live
   `producer._retrieve` smoke: **0 commentary** in bag. Commit **`c549413`**
   on `origin/main`. CLAUDE.md conflict closed; ARCHITECTURE retrieval updated.
   PLAN.md v5.31 records it.

2. **Open Decision #16 V1 ADOPTED (seed only).** Closed set = 6 live
   `positions` topic_keys: fasting; deliverance from demons and spiritual
   warfare; how to pray effectively; the divine exchange at the cross; can a
   believer lose their salvation; holiness and personal purity. Debates +
   house-paper pillars OUT. Full table:
   `docs/audits/position_topic_list_v1_2026-08-07.md`. PLAN.md v5.32.
   **Does not build** `match_stored_position()` — next code step.

3. **Agent hygiene (user home + repo).** `skillOverrides` off for chat-wrap,
   client-pipeline, impeccable (standalone), context7-mcp, grill-me,
   workspace-architect, proudly-prospect-pass. Notion MCP
   `disabledMcpServers` for project `/Users/alexwhitley/rhemata` only.
   Session close contract moved to `.claude/skills/session-close/SKILL.md`;
   CLAUDE.md keeps a one-line pointer.

**Still live from prior sessions (unchanged this session).**

- **Project 1 async:** `serving_enabled` TRUE, real traffic; concurrency at
  100-dial unproven (one serial test).
- **Project 2 phase 1:** single-teacher lock + debate classifier shipped;
  lock rarely fires (no teacher ≥60% on real tongues Qs).
- **Project 3 quote rail:** end-to-end live async-only (chat.py deliberate);
  2 approved quotes; threshold 0.40 provisional.
- **Position papers:** fence + exclusion + disclaimer fallback (`b9af800`).
- **Position layer one-hop:** design only; #16 V1 unblocks matcher build.
- **Corpus:** propositions backfill complete; book chapters 8/53; counts query live.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at scale.

- **#4** `ingest_helloao.py` unconverted. **#6** Guest→account
  (`docs/audits/GUEST_AUTH_AUDIT.md`). **#7** Auth CTAs
  (`docs/audits/BUTTON_AUTH_UX_AUDIT.md`).
- **#9** v4 props prompt unwired. **#10** Precept Austin. **#12**
  `jewish_perspectives`. **#13** SP2 a11y. **#14** Hebrew lexicon grant.
  **#16** Lewis/Tolkien/Wilson mistag (blocker #, not OD #16). **#19**
  pipeline diagram. **#22** embedded third-party quote spans (sub-chunk).
- **Phase 1.3** hidden-by-default reverse still open (Settled #12 ⚠).

---

## Next

1. **`match_stored_position()`** against #16 V1 list, then one-hop sequence
   (review → adapter → concurrency → inject → shadow rollout).
2. Async concurrency proof + worker pooler port confirm.
3. Quote curation beyond 2; chat.py quote wire = product call.
4. Phase 1.3 visibility inventory + flip; guest/auth polish.
5. Hygiene: helloao, mistags, staging restore, roman-numeral detector fate.

SP: SP2/SP4 done; next #43 mobile sheet. Pass B: remount `UsageRing` in drawer.
