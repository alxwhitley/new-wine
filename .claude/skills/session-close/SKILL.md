---
name: session-close
description: >
  Close out a New Wine session by updating the governing status/roadmap files
  under the Session close contract. Trigger when Alex says "update the files
  to close the session", "close out the session", "session close", or
  "wrap this session" in the newwine repo (not the ~/websites/ vault wrap).
---

# Session close (New Wine)

**When to use:** end of a newwine work session, when updating durable state.
**Not for:** `~/websites/` client projects (use chat-wrap / vault wrap there).

## Contract (exact)

"Update the files to close the session" means **exactly this, not more**:

1. **`rhemata-status.md`** is the only place session narrative goes. Overwrite
   the `## Current state` section wholesale — never append below the prior
   entry. Keep only what a next session needs (deployment state, live
   blockers, what's next), not a running history. **Target ≤150 lines.** If an
   update would exceed that, cut older material as part of closing this
   session (not a separate later pass) — it survives in git history, so
   nothing is lost, only pulled out of default context.

2. **`PLAN.md`** gets roadmap-level deltas only — a new/changed decision, an
   item's status flip, one version-history line. Closing an item **replaces**
   its entry (`DONE — <one line> (commit <hash> / docs/audits/<file>)`) rather
   than adding another paragraph on top of what's already there — see its own
   Standing Session Rule on this. The reasoning trail lives in the commit and,
   where one exists, the audit doc; PLAN.md only needs the pointer.

3. **`CLAUDE.md`** changes only for a genuinely new invariant, landmine, or
   settled decision meant to outlive this session — never to narrate what
   happened. The eviction rule in CLAUDE.md already governs that file; this
   contract doesn't add a second one.

4. **No `log.md`.** One was created 2026-08-04 out of habit from the
   `~/websites/` client-project session-contract pattern (which pairs
   `log.md` + `plan.md`) — that pattern doesn't apply here. New Wine's own
   contract is `rhemata-status.md` (state) + `PLAN.md` (roadmap); do not
   create or add to `log.md` going forward.

## Why

`rhemata-status.md` was already manually re-trimmed twice (2026-08-01,
~2,700 lines; 2026-08-04, regrown to ~840 lines) because "overwritten, not
appended" had no concrete ceiling or same-session enforcement. `PLAN.md` has no
eviction rule at all and grew from 3,371 words (2026-07-09) to 36,642 words
(2026-08-04) — 260KB, roughly 65K tokens — by appending corrections on top of
already-closed items instead of replacing them: the same failure mode
CLAUDE.md's own eviction rule already exists to prevent, just never extended
past CLAUDE.md itself. Cutting text under this contract never destroys the
only copy — git history, the commit, and `docs/audits/` remain the durable
record; a one-line pointer is enough to retrieve the full trail later.

## Procedure

1. State briefly what this session actually shipped (or planned only).
2. Overwrite `rhemata-status.md` `## Current state` (and refresh **Next** /
   blockers if they changed). Stay ≤150 lines for the file as a whole target.
3. Touch `PLAN.md` only for real roadmap deltas (version-history one-liner,
   Open Decision flip, DONE pointer). Prefer replace-over-append.
4. Touch `CLAUDE.md` only for new invariants / landmines / settled decisions.
5. Commit records when Alex asks; do not invent work as "done."

## Out of scope

- Client vault session close (`~/websites/`) — different contract
- Narrating session history into CLAUDE.md
- Creating root-level `log.md`
