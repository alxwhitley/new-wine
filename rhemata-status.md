# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to, never
durable truth — the durable records are the code, git history, PLAN.md,
docs/roadmap.md, docs/plan-archive.md, and CLAUDE.md. Counts are NOT recorded
here except as a dated snapshot from a specific live query; treat any count
seen elsewhere as unverified.

Last verified: 2026-08-31. **PLAN.md has zero active blockers.** `main` =
`df2d5f9`, pushed. This session was frontend-only: the beta access code was
found broken in production and fixed, then the sign-in flow was critiqued and
rebuilt. No database writes, no backend changes.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines.

---

## Current state

**The beta access code was broken in production and is fixed (`5473265`).**
The rename sweep `a6f1575` rewrote the gate's password literal along with the
product name (`rhema` → `newwine`), so the code handed to testers was rejected
from the moment the rename went live. The code is `rhema`, now alone in
`frontend/lib/beta-access.ts` with a test asserting the literal. **Fifth
casualty of that sweep, and the first to reach executable code** — CLAUDE.md's
landmine is updated accordingly.

**Sign-in flow rebuilt (`df2d5f9`).** An impeccable critique scored it 19/40
(snapshot in `.impeccable/critique/`, dated 2026-08-31) and found two
structural causes, not polish problems: sign-in had no entry point anywhere
in the product (every surface opened signup), and a successful sign-in was
visually identical to cancelling. Now one card that is never replaced —
`BetaGate.tsx` deleted and absorbed, the access code a field checked locally
before any network call, a segmented Sign in / Sign up radiogroup above the
fields, an in-modal success confirmation, plus dialog semantics, focus trap,
Escape, focus restoration and a backdrop guard. Verified: tsc clean, eslint
0 errors, 49/49 tests, build green, screenshotted at 1280 and 390.

**Beta access moved from per-tab `sessionStorage` to per-device
`localStorage`** (`newwine_beta_access`). Sessions on the old `beta_access`
key migrate in place. Code matching is now trimmed and case-insensitive.

**`hooks/useAuthGate.ts` is the single owner of auth-modal state**, replacing
four hand-copied `openAuthGate` functions. Three copies of the same bypass bug
surfaced and were fixed — `library/authors` and study's save-a-word prompt
both called `setShowLogin(true)` directly, skipping the gate. Do not re-copy
this logic into a page.

**Not fixed, pre-existing, confirmed not ours:** a hydration mismatch on
`<html>` from `next-themes`' `forcedTheme="dark"` (`providers.tsx`). Fires on
a plain `/home` load with no modal in the DOM. Real, worth a separate look.

**Not run:** `/impeccable audit` (verify the a11y work against real code),
`animate`, `polish` — unclassified follow-ups, not blockers.

**Every push to `main` deploys production.** All four Railway services
rebuild (`watchPatterns: []`, so even docs-only commits redeploy). Treat
backend pushes as attended gates. Setting watch patterns would stop docs
commits redeploying — not done.

**Two traps.** `/async-chat/result` is SSE with JSON spanning multiple
`data:` lines — parse by EVENT, or an answer reads as zero-citation and looks
exactly like an attribution-guard failure. Railway deployment meta populates
progressively; mid-`BUILDING` it reports `rootDirectory`/`configFile` as null,
indistinguishable from Railpack drift.

**Author attribution — 7 defects fixed 2026-08-31**, both halves
(`docs/audits/2026-08/author_attribution_audit_2026-08-31.md`, `fe0718a` +
`92f9633`). Citable author groups 55 → 48. Recorded so nobody "fixes" them:
Savchuk documents with `author = NULL` correctly fall back to the source name
— the HEALTHY state; `Jamieson, Fausset & Brown` is a genuine joint work.

**Decided, do not re-raise:** guest-speaker attribution stays as-is;
`/corpus-inventory/export`'s missing auth is a decision, guarded by
`scripts/test_corpus_inventory_endpoint.py` Check 1 — never extend it to
chunk text, excerpts, or propositions. Privacy policy + ToS DEFERRED until
Alex supplies legal entity, jurisdiction, and contact address; `POLICY_COPY`
in `consent.py` is duplicated in `consent-gate.tsx` and they move together.

**Quote rail still off (`QUOTE_SELECTION_ENABLED=false`).** CLF's 63 sermons
are auto-transcribed audio under `sermon_transcript` with a confirmed
mistranscription and nothing gates on transcript status — **before the flag
flips back on, CLF needs quoting exclusion or audio confirmation.**

**CLF Church — 63 YouTube documents, 0 duplicate URLs corpus-wide.** Plus 15
non-YouTube CLF docs, so a bare `count(*)` reads 78 — filter `url ILIKE
'%youtu%'`. Zero propositions (`owned` skips the license gate). 15 are
`held_permanent` for content shape + pastoral privacy, **not runtime** — no
trimming step may be built to salvage them.

**Search analytics live; B7 done.** A degraded outcome stamps
`answer_jobs.analytics_outcome` (`scripts/analytics_health_report.py`), but
that marker has never fired. Five residuals unverified.

**New Wine A2 — NOT ingestion-ready, held by Alex.** No live-call budget
without a fresh named ceiling.

**Still on the old name deliberately:** applied migrations; this file's
filename; the DB source row and the two code sites naming it;
`rhemata_tracker.xlsx`; the Vercel project; `rhemata.app` (404 — redirect vs
retire undecided); the API hostname `rhemata-production.up.railway.app` (the
frontend's API base URL must move in lockstep); "manna"/"rhema" in corpus.

---

## Findings surfaced, not yet acted on

- **A served citation carried a dangling `chunk_id`** —
  `0b9d1930-7103-4520-8e37-e382dc7b3227` matched zero of 186,944 `chunks`
  rows while its document resolved normally. Either `chunk_id` does not
  correspond to `chunks.id` at all, or a citation can point at unresolvable
  evidence. Needs one check of how `producer.py` populates it.
- **The 301 missing local files and the 318 caption-duplication set are one
  decision, not two** — heavy overlap. One re-ingest fixes both, costs real
  money, needs a cost estimate. Parked; deferred by Alex 2026-08-29.
- **`sources/` must never go in this repo** — the GitHub remote is PUBLIC.
  Committing it would publish the magazine PDFs, Precept Austin, Derek Prince
  scrapes and living ministers' transcripts, inverting the license gate,
  safe_mode, hidden staging and the PA lockout irreversibly. **Same rule keeps
  the 60 untracked `new_wine_issue_02_1973_review_*` dirs out of git.** Backup
  is an iCloud copy (2026-08-30, verified) — sync, not versioned.
- **The house source row is still named "Rhemata"** —
  `bf6d9e28-1cfd-4431-975b-df2ca1b9cfdf`, `owned`/`shown`, slug `rhemata`.
  Publisher container for the 8 position papers + "The Gift of Prophecy":
  9 documents, 70 chunks, **0 citable**, so it never appears in a citation,
  but it is shown wherever sources are enumerated. Rename is display-only, and
  needs `sources.name`, `sources.slug` and both alias columns moved together
  (Invariant 6: `alias_key` → `new wine`). Attended DB write, not done.
- **11 ingested CLF documents contain an offering appeal**, one an usher
  direction, one a dismissal. Auditing those 11 for named-congregant content
  is open.
- **`bible_refs.py` hallucinated 2 of 625 references (~0.3%)** on real sermon
  text — extended by the 2026-08-29 clean audit, not re-measured.
- **Live account-deletion verification** — blocked, needs a real disposable
  test account from Alex first (Session Routing hard rule).
- Carried, not re-checked: staging source reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `newwine_readonly_analysis` has no grant on
  PII/user tables (deliberate).

---

## Next single item

**Unresolved contradiction, inherited — Alex resolves before work starts.**
The prior status file recorded `/corpus-inventory/export` as both "stays
public, re-confirmed 2026-08-31" and "Next: gate it behind authentication."
Both cannot stand. Not silently resolved here.

Then, unordered and none started: the auth follow-up passes; the
`next-themes` hydration mismatch; the DB source row rename and remaining
Vercel/domain/hostname identifiers; the 301/318 re-ingest (cost estimate
first); New Wine A2 (fresh ceiling); quote repair; privacy/ToS (blocked).
