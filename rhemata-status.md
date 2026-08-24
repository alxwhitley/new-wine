# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-24 (security + dependency session; 3 commits shipped
and deployed, all verified live in production).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md`'s private-beta blocker queue is still **0** active blockers. This
session's work came from `docs/roadmap.md`'s Scheduled B5 track, pulled
forward by Alex's explicit approval — not a blocker promotion.

**Shipped and live in production, all three verified against the running
services (not dashboard status alone):**

1. **Backend dependency bumps** (`3a30639`) — `python-dotenv` 1.2.1→1.2.3,
   `python-multipart` 0.0.20→0.0.32, `PyJWT` 2.12.1→2.13.0. Verified under
   `python3.12` (not the machine's default 3.9): clean venv install,
   `pip check` clean, 7 regression scripts pass, `app.main` loads all 83
   routes. `starlette` and `pdfminer-six` deliberately NOT bumped — both
   blocked by an exact/narrow parent pin (see roadmap).
2. **Frontend lockfile fix** (`09b102a`) — `npm audit fix`, no `--force`.
   28 patch-level entries moved; the two that close advisories are `ws`
   8.20.0→8.21.3 and `postcss` 8.5.8→8.5.26. Frontend advisories 5 → 3; the
   3 remaining all sit inside `next`'s own tree and need the deferred major
   bump. `npm run build` clean, 17 routes, static/dynamic split unchanged.
3. **Baseline security headers** (`9b816a8`) — frontend gets
   `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy:
   strict-origin-when-cross-origin`, `Permissions-Policy` (camera/mic/
   geolocation off); API gets `nosniff` + its own HSTS. **Confirmed live on
   both origins**, including `X-Frame-Options: DENY` on `/admin`. Critically,
   `rhemata.app` still serves `x-vercel-cache: PRERENDER` — static caching
   survived, which is exactly what skipping a nonce-based CSP protected.

**Deploy verification:** Railway `rhemata` + `answer-worker` both SUCCESS on
all three pushes (deps `3a30639`, headers `9b816a8`, and the docs commit
`cbafeb7` — Railway rebuilds on any push to `main`, including docs-only);
Vercel Ready each time. Builder/rootDirectory drift (the past-outage
landmine) did not occur on any of them. The worker has no automatic health
check, so it was proven by hand: a real question submitted to production
returned a real answer — 7 citations across Derek Prince, Andrew Murray and
Savchuk articles, 3 verified references, `outcome=answered`, and 1 quote ID
served. `/study/teachers` and `/answer-quotes/resolve` both functional
post-deploy; final post-`cbafeb7` check confirmed API + frontend 200 and the
API's `nosniff` still present.

**Four standing findings investigated and closed as needing no work** —
`docs/audits/2026-08/findings_corrections_2026-08-24.md`. One matters beyond
itself: a subagent claimed CLAUDE.md's "2,409 legacy propositions have NULL
provenance permanently" was outdated and should be corrected. Direct live
query shows that claim is **wrong** — only `prompt_version` was backfilled,
to the sentinel `legacy_unknown`; `prompt_fingerprint` and `model` are still
NULL on exactly those 2,409 rows. CLAUDE.md is correct and was left
unchanged. Acting on the subagent's claim would have deleted a true,
load-bearing caveat from a governing doc.

Also closed: the "24 stuck documents" are not stuck (all 24 are `owned` +
`shown`, already retrievable in answers; propositions aren't on the answer
path) and 9 of them are position papers that must **never** be extracted per
Settled #8. The three empty teacher rows (Bill Johnson, Craig Keener, Randy
Clark) contradict nothing and have no user-facing effect.

---

## Findings surfaced, not yet acted on

- **Scheduled** (`docs/roadmap.md`, new "Dependency and hardening follow-up"
  section): starlette+fastapi coupled bump — do the read-only exploitability
  triage of its 7 advisories first, the same pass that reduced 3 alarming
  Next.js CVEs to zero live attack surface; pdfplumber+pdfminer coupled bump;
  CSP on the frontend; the deferred Next.js major bump.
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

Alex's call. If continuing the security track, the highest-value next step is
the read-only exploitability triage of starlette's 7 advisories — cheap, and
it decides whether the risky coupled fastapi bump is worth doing at all.
Active blocker count **0**.
