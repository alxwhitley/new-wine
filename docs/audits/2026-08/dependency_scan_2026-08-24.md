# Dependency vulnerability scan — 2026-08-24

Read-only diagnostic, addressing the 2026-08-19 B5 snapshot's noted gap: "no
dependency or security-header scan run." `npm audit` (frontend) and
`pip-audit` (backend, via an isolated scratch venv — no system/repo Python
env touched) against the committed `backend/requirements.txt`. Also closes
the same snapshot's second open item, CORS `allow_origins` tracing (see
below) — both were listed together as unresolved.

**Update, same day, on "execute on these findings":** exploitability
triage completed for the 3 `next`-specific CVEs (all not applicable to this
app's actual config); the safe `ws` fix and three safe backend package
bumps were applied and verified. See "What was actually changed" at the
bottom. Not applied: the `next` major-version bump and the coupled
starlette/fastapi bump — both flagged back to Alex rather than done
unilaterally; reasoning below.

## CORS `allow_origins` — traced

`backend/app/main.py:11-19` reads `ALLOWED_ORIGINS` (comma-separated) from
the environment, no hardcoded fallback (empty list if unset — fails closed).
Live value on Railway `rhemata`: `ALLOWED_ORIGINS=https://rhemata.app` —
matches Vercel's registered production domain for the `rhemata` project
exactly (confirmed via `vercel project ls` / `vercel domains ls`; no
separate `www.rhemata.app` alias exists to worry about). No misconfiguration
found.

## npm audit — 5 high-severity findings (frontend, production deps)

Ran `npm audit --omit=dev` in `frontend/`. Not fixed — `npm audit fix
--force` would bump `next` to `16.3.2`, outside the stated dependency range
(a version-bump decision, not a mechanical patch).

| Package | Advisory | Issue |
|---|---|---|
| next | GHSA-p9j2-gv94-2wf4 | SSRF via rewrites, attacker-controlled destination hostname |
| next | GHSA-q8wf-6r8g-63ch | DoS in Image Optimization API via SVGs |
| next | GHSA-955p-x3mx-jcvp | Unauthenticated disclosure of internal Server Function endpoints |
| postcss (transitive via next) | GHSA-qx2v-qp2m-jg93, GHSA-6g55-p6wh-862q, GHSA-fxqj-rqcc-2cmp, GHSA-r28c-9q8g-f849 | XSS via unescaped `</style>`; sourceMappingURL path traversal / arbitrary `.map` file disclosure |
| sharp (transitive via next) | GHSA-f88m-g3jw-g9cj | Inherited libvips CVEs (2026-33327/33328/35590/35591) |
| ws | GHSA-58qx-3vcg-4xpx, GHSA-96hv-2xvq-fx4p | Uninitialized memory disclosure; DoS via tiny fragments |

**Exploitability triage, completed:**

- **SSRF via `rewrites()` (GHSA-p9j2-gv94-2wf4) — NOT APPLICABLE.**
  `frontend/next.config.ts` defines no `rewrites()` function at all, only
  `redirects()` (two static, hardcoded admin-path redirects) and a locked
  `images.remotePatterns` (Supabase storage only). No attacker-influenced
  destination exists anywhere in the config.
- **SVG DoS in Image Optimization (GHSA-q8wf-6r8g-63ch) — NOT APPLICABLE.**
  `dangerouslyAllowSVG` is not set, so it defaults to `false` — Next.js
  refuses to optimize SVGs at all. `remotePatterns` is also locked to one
  Supabase bucket path, not arbitrary user URLs.
- **Server Function endpoint disclosure (GHSA-955p-x3mx-jcvp) — NOT
  APPLICABLE.** Zero `"use server"` directives anywhere in the codebase —
  this app doesn't use Next.js Server Actions/Functions at all.
- **`ws` (GHSA-58qx-3vcg-4xpx, GHSA-96hv-2xvq-fx4p) — pulled in but not
  really reachable.** `ws` is transitive via `@supabase/realtime-js`, used
  by `components/admin/AdminModal.tsx` (`"use client"` — browser-only,
  admin-gated). Browsers use the native `WebSocket` API, not the npm `ws`
  package, so this code path doesn't actually execute the vulnerable
  package in production. Fixed anyway (below) since the fix was free.

**Net effect: all 3 `next`-specific CVEs have zero live attack surface in
this app as currently configured/coded.** The major-version bump
(`next@16.3.2`, "outside the stated dependency range") is therefore not
urgent — recommend deferring rather than forcing an untested major bump
pre-beta, revisiting at the next planned Next.js upgrade or before the
Tier-2 public-signup gate. Applied the safe fix: `npm audit fix` (no
`--force`) bumped only `ws` within its existing declared range —
`package.json` unchanged, `package-lock.json` updated, verified with a
clean `npm run build` (compiled, typechecked, all 17 routes generated,
zero errors).

## pip-audit — 24 known vulnerabilities across 5 backend packages

Ran against `backend/requirements.txt` (pinned versions, matching what's
deployed per Invariant 14's landmine).

| Package | Pinned | Fix version | Advisory count |
|---|---|---|---|
| starlette | 0.52.1 | 1.0.1 (some fixed earlier, up to 1.3.1) | 7 |
| python-multipart | 0.0.20 | 0.0.22–0.0.31 (multiple) | 6 |
| pyjwt | 2.12.1 | 2.13.0 | 8 (6 distinct IDs, 2 double-counted) |
| pdfminer-six | 20250327 | 20251107 / 20251230 | 2 |
| python-dotenv | 1.2.1 | 1.2.2 | 1 |

**pyjwt — checked against actual usage, not just version.** `backend/app/
auth.py:38` calls `jwt.decode(..., algorithms=["ES256", "RS256"])` —
asymmetric-only, no HMAC in the allowed list. This means **PYSEC-2026-179**
(algorithm-confusion vulnerability requiring both symmetric and asymmetric
algorithms configured together) **does not apply to this deployment** as
currently configured — worth recording so it isn't mistaken for exploitable
just because the version is flagged.

One pyjwt finding that **does** apply: **PYSEC-2026-177** —
`PyJWKClient.get_signing_key()` forces a fresh HTTP request to the JWKS
endpoint for every JWT bearing an unknown `kid`, with no rate limiting.
`auth.py:15` does use `PyJWKClient(os.environ["SUPABASE_JWT_JWKS_URL"])`.
An attacker sending a stream of tokens with garbage `kid` values could force
the backend into unbounded outbound HTTP calls to Supabase's JWKS endpoint —
a DoS-adjacent abuse vector relevant to B5 (guest-limit / abuse readiness).
Not reproduced live (would require driving real traffic against the JWKS
endpoint); flagged from the advisory + code read only.

**Compatibility check before bumping anything (done via `pip download
--no-deps` + reading each wheel's `METADATA`, no install):**

- `starlette` — **blocked, not applied.** All pip-audit fix versions
  (1.0.1–1.3.1) are `>=1.0.0`. The pinned `fastapi==0.128.8` declares
  `Requires-Dist: starlette<1.0.0,>=0.40.0` — starlette 1.x is outside
  fastapi's own compatible range. Fixing starlette's advisories would
  require bumping fastapi too, which is untested here and is exactly the
  coupled-version territory Invariant 14's landmine (the `da27fe4`
  422-vs-401 admin-auth bug, pydantic/starlette/FastAPI version
  interaction) warns about. **Not touched — needs a deliberate,
  tested fastapi+starlette bump as its own piece of work, not folded into
  this scan.**
- `pdfminer-six` — **blocked, not applied.** `pdfplumber==0.11.6` (pinned)
  declares `Requires-Dist: pdfminer.six==20250327` — an *exact* pin, no
  range. Bumping pdfminer-six alone breaks pdfplumber's declared
  dependency; would need a pdfplumber upgrade too, unassessed, and this
  package sits behind PDF ingestion (ranked failure-mode-adjacent —
  altered text extraction is a corpus-quality risk, not just a security
  one). **Not touched.**
- `python-dotenv`, `python-multipart`, `pyjwt` — **applied.** All three
  are either standalone leaves or loosely bounded by their consumers
  (`fastapi` requires `python-multipart>=0.0.18`; `gotrue` requires
  `pyjwt>=2.10.1,<3.0.0` — both satisfied). Bumped to latest stable:
  `python-dotenv` 1.2.1→1.2.3, `python-multipart` 0.0.20→0.0.32, `PyJWT`
  2.12.1→2.13.0 (`backend/requirements.txt`). Verified: fresh venv install
  of the full updated `requirements.txt` succeeded with no conflicts;
  `scripts/test_admin_auth_regression.py`, `test_metering.py`,
  `test_quote_rail_regressions.py`, `test_quote_selection_gate.py`,
  `test_teacher_card_bio_redaction.py`, `test_teacher_card_guards.py`,
  `test_resolve_book_abbrev_consolidation.py` all pass under the bumped
  deps; `from app.main import app` imports cleanly (exercises every
  router's module-level imports). Not yet deployed — this only changed
  the pinned versions in the repo.

## Classification (not written to PLAN.md/roadmap.md — Alex's call)

Everything here nests under `docs/roadmap.md`'s already-Scheduled **B5**
track; nothing met the Beta Critical Path bar for an interrupt-worthy
Blocker (no demonstrated live exploit, no data loss, no theological/
misattribution issue) — consistent with proceeding on the safe items
without a separate promotion step. Two items deliberately left for Alex:
whether to schedule the `next`/fastapi+starlette major bumps as their own
bounded work (neither is urgent given the exploitability findings above),
and whether the `PyJWKClient` unbounded-fetch behavior warrants a rate
limit/negative cache next time `auth.py` is touched.
