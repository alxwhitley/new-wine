# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-25 (quote containment + mobile chat UX; four code
commits shipped and all production surfaces verified live).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md`'s private-beta blocker queue is **0** active blockers. One credible
teacher-misrepresentation risk was promoted and closed in-session by
containment: Alex found the user-facing quote rail insufficiently accurate and
relevant, then explicitly changed the launch posture from quotes-on to
quotes-off-until-repaired.

**Shipped and live:**

1. **Quote rail contained.** `QUOTE_SELECTION_ENABLED=false` on Railway
   `rhemata` and `answer-worker`; both final deployments SUCCESS. The 16-case
   flag-off regression passed under Python 3.12. Production job
   `0f503115-9725-4374-a85b-eecd5e7d61c6` completed `outcome=answered` with
   `quote_ids=[]`. No quote rows were deleted; chat delivery is off while the
   repair/re-enable gate is Scheduled in `docs/roadmap.md`.
2. **Mobile app shell locked** (`732bb6d`). Safari/PWA root scrolling can no
   longer move the chat surface offscreen; only the message list owns vertical
   scrolling.
3. **Reader-owned chat scrolling** (`7ff8860`). Send reveals the new turn once;
   client-paced streaming never moves the reader afterward.
4. **Multiline composer corrected** (`4db847e`). The send button stays bottom-
   aligned and the textarea returns to one line after submission.
5. **Mobile navigation direction corrected** (`08fc91d`). The top-left drawer
   now enters and exits through the left.

**Verification:** final combined 390×844 browser pass: shell `top=0` /
`bottom=844`; drawer `[-390,0] → [0,390] → [-390,0]`; composer button bottom
delta `0px`, textarea `96px → 24px`; Send landed within `10px` of the new turn;
streaming held the manually selected position at `802px`. Frontend tests
16/16 and production build (17 routes) passed. Vercel production Ready and
aliased to `rhemata.app`; live origin returned 200 with PRERENDER caching and
security headers intact. Final Railway API and worker deployments SUCCESS;
both quote flags rechecked false.

**Session measures:** original outcome completed; unplanned investigations 0;
findings promoted to Blocker 1 and closed by containment; active critical-path
item count 0. Alex-approved scope additions: Safari/PWA shell lock and mobile
drawer direction.

---

## Findings surfaced, not yet acted on

- **Scheduled** (`docs/roadmap.md`, new "Dependency and hardening follow-up"
  section): starlette+fastapi coupled bump — do the read-only exploitability
  triage of its 7 advisories first, the same pass that reduced 3 alarming
  Next.js CVEs to zero live attack surface; pdfplumber+pdfminer coupled bump;
  CSP on the frontend; the deferred Next.js major bump.
- **Scheduled** (`docs/roadmap.md`): quote accuracy and relevance repair before
  any attended re-enable; the live rail remains off.
- **Triggered** (`docs/roadmap.md`): JWKS unknown-`kid` rate limit — PyJWT
  2.13.0 already fixed the amplifying half (cache-wipe on failed fetch); the
  residual is un-amplified and belongs at the edge, not in `auth.py`.
- Public `/docs` + `/openapi.json` on the API list every route including
  admin ones. Routes stay auth-gated, so this is a map, not an open door.
  Left as-is deliberately — Alex may use it; not yet formally classified.
- `darlenecunningham.com` confirmed to be an unrelated living romance
  novelist, not the YWAM co-founder. Spreadsheet NOT updated — its Read Me
  reserves `verification_status` for Alex personally, and precedent (Bonnke,
  2026-08-19) is to record and let him mark it.
- Staging source name still reads `"Vlad Savchuk (web staging)"` on
  citations — attended one-row `sources.name` UPDATE whenever Alex wants it.
- Carried, not re-checked this session: Bonnke URL suspect (expired cert, no
  CfaN corroboration); no retention/TTL logic for user data;
  `rhemata_readonly_analysis` has no grant on PII tables; full cascading
  account deletion still unbuilt (migration 090 removed only the DB-level
  blocker — `POST /account/delete-request` is still a stub).

---

## Next single item

Alex's call. If continuing the quote track, the next single item is to define
the representative accuracy/relevance acceptance set from reproduced bad
cases before changing selection or extraction. Active blocker count **0**.
