# B5 — Security, Privacy, and Abuse Readiness: Read-Only Snapshot

2026-08-19. Read-only code-reading pass only — no live traffic testing, no
load testing, no log inspection, no DB writes. Scoped to what a single
grep/read pass over the repo can establish. This is an inventory to inform a
later B5 session, not a completed B5 pass.

## 1. Guest/user query limits

`enforce_query_limit()` (`backend/app/services/async_answers/metering.py`)
is the single metering implementation, called from exactly one place:
`async_chat.py`'s `/submit` route (line 166), before `jobs.enqueue()`. Fails
CLOSED — any RPC exception raises 503 rather than letting the request
through unmetered. Guest limit = 6 (`GUEST_QUERY_LIMIT`), keyed on
`anon_id` + IP via `increment_guest_query`; authenticated weekly limit via
`increment_user_query` (default 50/week). Matches CLAUDE.md's description.

**Real gap found:** `GET /study/teacher/{source_id}`
(`get_teacher_card()`, `backend/app/routers/study.py:968`) requires
authentication (`Depends(require_user)`) but calls **no metering function
at all** before running its live Anthropic generation. CLAUDE.md's own
Landmines entry describes this endpoint as "a second, always-existing, live
served-generation surface" with its own Anthropic call, separate from the
metered `/async-chat/submit` path — confirmed here structurally: nothing in
`study.py` imports or calls `enforce_query_limit` or either metering RPC.
Any authenticated user (including a brand-new free signup) can call this
endpoint in a loop with a different `question` query param each time and
trigger unlimited live LLM generations at real cost (~$0.015/open per
CLAUDE.md's decision #14 cost measurement), with no query-count ceiling.
This is a genuine, unmetered abuse/cost surface, not a documented
exception — worth confirming with Alex whether it's accepted or needs its
own limit before beta.

## 2. Authorization gating

`require_admin_role` / `require_contributor` usage confirmed consistent:
`admin.py`, `ingest.py`, `ingest_queue.py`, `answer_quotes.py`, `quotes.py`,
`feedback.py`, `pastors_notes.py` all gate their mutating/admin routes.
`account.py`'s deletion-request listing/resolution is admin-gated;
submission is user-gated. User-facing read routers (`study.py`, `search.py`,
`library.py`, `document.py`) consistently use `require_user` (or
`get_optional_user` for `usage.py`'s own-usage display) — no route found
that mutates or serves gated content without *some* auth dependency, except
the one deliberate documented exception below.

`scripts/test_admin_auth_regression.py` exists and asserts the actual
distinguishing shape of the historical `da27fe4` bug: that
`_RequireRole.__call__` takes no direct `request` parameter
(`test_require_role_signature_excludes_request_param`), that a
no-token admin request returns 401 not 422
(`test_no_token_returns_401_not_422`), and that this holds across
multiple admin routes (`test_no_token_never_422s_across_multiple_admin_routes`).
Not re-run live in this pass — presence and assertions confirmed by
reading the file only.

**One deliberate, fully-documented unauthenticated endpoint:**
`GET /corpus-inventory/export` (`corpus_inventory.py`) serves
author/title/canonical-URL for every `documents` row, with **no auth of any
kind and no license/visibility gate** — by Alex's explicit 2026-08-17
decision, recorded in the file's own docstring (CORPUS-INV-001). The
docstring itself flags the boundary: this must never be extended to serve
chunk/excerpt/proposition text without revisiting the decision, since doing
so would reopen the license-gate hole. `include_in_schema=False` is
explicitly documented as "not a security boundary, just an unlisted link."
Recorded here as a known, accepted design choice, not a new finding — but
it is a real standing exception to "everything is gated" and worth Alex
re-confirming is still acceptable heading into beta (a bibliography CSV of
every document title/author/URL, including hidden/unlicensed ones, is
public to anyone with the URL).

## 3. Retention-sensitive data

No retention/expiry/TTL logic found anywhere for user-owned data.
`conversations` (via `conversation_store.py`, `jobs.py`) and
`deletion_requests` (`account.py`) accumulate with no code-level purge path.
Guest metering logs `anon_id` + `ip_address` directly to Railway logs
(`metering.py:72`, `logger.info("[GUEST] anon_id=%s ip=%s ...")`) with no
visible log-retention policy in the repo (Railway-side retention, if any,
is outside this repo and wasn't checked).

**Confirms CLAUDE.md's Landmines entry structurally:** `account.py`'s
`submit_delete_request` only inserts a `deletion_requests` row;
`resolve_delete_request` only flips its status to `resolved`. Grepped the
whole `backend/app` tree for `DELETE FROM`, `delete_after`, `retention`,
`expire`, `TTL` — zero hits tied to actually removing a user's
conversations, saved_words, pastors_cards, user_roles, or the Supabase auth
user. A "resolved" deletion request today means an admin did something
manually outside this codebase, not that anything was verified deleted by
the system.

## 4. Logging hygiene

No instance found of a full user message, API key, password, or bearer
token being logged verbatim. One partial exposure: `backend/app/auth.py:46`
logs `token[:20]` on JWT decode failure
(`"[AUTH] JWT decode failed: %s: %s | token prefix: %s..."`). A 20-character
prefix of a JWT is normally just the fixed header segment (e.g.
`eyJhbGciOiJIUzI1NiJ9...`), not enough to reconstruct a usable token — low
severity, flagged for completeness rather than as a real risk.

No `print(` calls found near auth/secret-handling code; logging goes
through the standard `logging` module throughout the sampled files.

## 5. Common abuse paths

- No general request-rate-limiting middleware found (no `slowapi` or
  similar in `backend/requirements.txt` or wired into `main.py`). The only
  rate control in the codebase is the guest-query metering RPC's
  new-guest-session-per-IP sentinel (migration 057) and the weekly
  authenticated-user limit — both scoped to `/async-chat/submit` only (see
  finding #1's gap on `/study/teacher/{source_id}`).
- No unauthenticated write endpoint found. Every `POST`/`PUT`/`PATCH`/
  `DELETE` route checked requires at least `require_user`, and every
  admin-shaped mutation requires `require_admin_role`.
- SQL string-interpolation risk: two f-string-built queries exist
  (`scripts/export_restore_document.py:239`,
  `scripts/archive/2026-06/backfill_era.py:49,57`), but both interpolate
  fixed internal table/column names (not user input) with values still
  passed via `%s` parameters — these are admin-run recovery/backfill
  scripts with no HTTP entrypoint, not a live injection surface. No
  f-string/`.format()`/`%`-built SQL was found anywhere in `backend/app`
  (the live-serving code), consistent with CLAUDE.md's Invariant 9
  discipline holding outside migrations too.
- CORS: `CORSMiddleware` is configured in `main.py` with an
  `allowed_origins` variable — not inspected further in this pass (its
  actual value wasn't traced); worth confirming it's not a wildcard before
  beta.

## Needs deeper investigation — not done here

- Whether `/study/teacher/{source_id}`'s missing metering (finding #1) is
  actually being hit in practice — needs live log inspection, not code
  reading.
- Actual `CORSMiddleware(allow_origins=...)` value and where it's sourced
  from (env var vs hardcoded) — not traced past the import/registration
  line.
- Railway/Supabase-side log retention settings for anything logged with
  `anon_id`/IP — outside this repo, not checked.
- A real guest-limit abuse drill (rotating anon_id/IP to test the migration
  057 sentinel in practice) — CLAUDE.md's own Tier-2 trigger list already
  names this as pending at ~20 beta users.
- Whether any Supabase RLS policies exist as a second layer under the
  FastAPI-level `Depends()` checks, or whether FastAPI's gate is the only
  enforcement — not checked (would require reading migrations/RLS policy
  SQL directly, out of scope for this pass).
- No security-header check (CSP, HSTS, X-Frame-Options, etc.) was run
  against the deployed backend or frontend.
- No dependency-vulnerability scan (`pip-audit`, `npm audit`) was run.
