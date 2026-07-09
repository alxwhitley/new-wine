# Guest → Signup → Signin Flow Audit

**Date:** 2026-07-06 · **Method:** read-only code trace + live-DB verification (RPC definitions pulled via `pg_get_functiondef` on the production database, not from migration files). No code, config, or DB state was changed.

---

## 1. Beta gate

**What it actually gates:** only the *opening of the auth modal*. It does not gate any route, any page, or any API call.

- `frontend/components/auth/BetaGate.tsx:16-24` — client-side check `code === "rhema"` (the code is hardcoded in the component, i.e. present in the shipped JS bundle). On success: `sessionStorage.setItem("beta_access", "1")`.
- Trigger sites all follow the same pattern — an `openAuthGate()` helper that checks `sessionStorage.getItem("beta_access") === "1"`; if set, opens `LoginModal` directly, else shows `BetaGate` first:
  - Chat: `frontend/app/page.tsx:35-42` (gate rendered at `:309`)
  - Landing: `frontend/app/home/page.tsx:622`
  - Study: `frontend/app/study/page.tsx:891-898, 1774`
  - Library: `frontend/app/library/page.tsx:665, 1331`
- **Guests chatting are never gated.** The chat input on `/` is fully usable with no beta code — the gate only appears when clicking "Become a test user" / sign-in CTAs. The 6 free guest queries are available to anyone, code or not.
- **Server-side check: none.** `grep -rni "beta" backend/app --include="*.py"` returns zero hits. The `beta_access` value is never sent to, or checked by, the backend. Anyone can bypass the gate by (a) calling the API directly, (b) running `sessionStorage.setItem("beta_access","1")` in the console, or (c) reading `"rhema"` out of the JS bundle.
- **Lifetime:** sessionStorage — survives reloads within a tab, dies on tab close. Every new tab re-prompts for the code before the signup *or sign-in* modal can open (returning users included — see Ambiguities).

## 2. Guest identity

**Generation & storage:**
- `frontend/hooks/useChat.ts:18-26` — `getAnonId()`: `crypto.randomUUID()`, stored in **localStorage** under `"rhemata_anon_id"`, created lazily on first chat send.
- **Lifetime:** survives browser restart and sessionStorage clearing (localStorage ≠ sessionStorage). Destroyed only by clearing localStorage/site data. So: beta gate resets every tab; guest identity effectively never resets.
- Sent on every `/chat` call as `body.anon_id` (`frontend/lib/api.ts:105-106`, wired at `useChat.ts:118`). Also read by the feedback widget (`frontend/components/rhemata/chat-message.tsx:160`) and stored on feedback rows (`backend/app/routers/feedback.py:22,42`).
- Note: `useChat.ts:118` passes `anonId: getAnonId()` unconditionally — the anon_id is still transmitted after login; the backend simply ignores it when a valid JWT is present (guest branch only runs when `user_id` is None, `chat.py:521`).

**`guest_sessions` schema (verified live):**
```
id          uuid PK DEFAULT gen_random_uuid()
anon_id     text NOT NULL, UNIQUE (guest_sessions_anon_id_key)
query_count integer DEFAULT 0
created_at  timestamptz DEFAULT now()
last_seen   timestamptz DEFAULT now()
ip_address  text            ← added by migration 057
```
No `user_id` or any user-referencing column exists (verified live: zero matches).

**`increment_guest_query` RPC — LIVE definition confirmed:** the live function is the migration-057 two-arg version `(p_anon_id text, p_ip_address text DEFAULT NULL)`, and only that one overload exists (the old single-arg version was dropped). Both protections are live, not just in migration history:
- **IP cap:** new-session creation blocked at 20 new `guest_sessions` rows per IP per rolling hour; returns sentinel `-1`.
- **Metering:** upsert keyed on `anon_id`, increments `query_count`, returns the new count.

**Backend enforcement** (`backend/app/routers/chat.py`):
- `GUEST_QUERY_LIMIT = 6` (`:437`). Check at `:538`: `count < 0 or count > GUEST_QUERY_LIMIT` → 429 `guest_limit_reached`. Counts 1–6 pass, so a guest gets exactly 6 answered queries; the sentinel `-1` and ordinary exhaustion produce the identical 429 (deliberate — `:534-537`).
- Missing `anon_id` on a guest request → 400 (`:524-525`). Metering errors fail **closed** → 503 (`:543-545`).
- Client IP read from leftmost `X-Forwarded-For` (`:499-507`) — Railway edge sets it.

**Live data point:** 30 guest_sessions rows; max `query_count` = **9**; 5 rows ≥ 6. Counts above 6 exist because the RPC increments unconditionally on every attempt *before* the backend rejects — `query_count` records **attempts, not served queries** (see Ambiguities).

## 3. Signup / signin

**Method: email + password only.** `frontend/hooks/useAuth.ts:27-36` — `supabase.auth.signInWithPassword` and `supabase.auth.signUp({ email, password })`. No magic link, no OAuth. A password-reset flow exists (`LoginModal.tsx:29-48` → `resetPasswordForEmail` → `/auth/callback?next=/auth/update-password`).

**Signup submit flow** (`frontend/components/auth/LoginModal.tsx:50-71`): calls `onSignUp`; `useAuth.signUp` returns `{ hasSession: !!data.session }` (`useAuth.ts:35`). If a session came back, the modal just closes; if not, it shows "Check your email for a confirmation link." (`LoginModal.tsx:145-156`).

**Email confirmation: effectively required.** Not verifiable from the repo directly (it's a Supabase dashboard setting), but two pieces of evidence: the no-session UI branch exists and is the designed path, and **all 3 live `auth.users` rows have `email_confirmed_at` set, 0 unconfirmed** (live query). Confirmation email sender: no custom SMTP, Resend, or email service exists anywhere in the repo — it is Supabase's default project SMTP unless the dashboard says otherwise (unverifiable from code).

**Confirmation link handling:** `frontend/app/auth/callback/route.ts` expects `token_hash` + `type` query params, verifies via `supabase.auth.verifyOtp` using a **cookie-based** `createServerClient`, then redirects to `next ?? "/"`. Note: `useAuth.signUp` passes **no `emailRedirectTo`** (`useAuth.ts:33`), so where the confirmation email actually points depends entirely on the Supabase dashboard Site URL / email-template configuration — see Ambiguities for the storage-mismatch risk here.

**Default role for a brand-new signup: no row at all.**
- **No trigger exists on `auth.users`** (verified live: zero non-internal triggers) — nothing auto-creates a `user_roles` row at signup.
- Live counts: 3 users, 2 `user_roles` rows — one real user has no row.
- Role is a *code-level default*: `backend/app/auth.py:51-57` (`get_user_role` returns `"user"` when no row) and `backend/app/routers/pastors_notes.py:704-719` (`GET /me` returns `{"role": "user"}` when no row). A row is first created only by the display-name upsert (`pastors_notes.py:728-746`) or an admin role grant.

**Sign-in & session:** `lib/supabase.ts` is a plain `createClient` → session lives in **localStorage** (supabase-js default). `useAuth` exposes `session.access_token`; every API call attaches it as a Bearer header. `useUserRole` (`frontend/hooks/useUserRole.ts:36-51`) fetches `/pastors-notes/me` with a 5-minute module-level cache, defaulting to `"user"` on any error.

**Post-login experience:** none distinct. `LoginModal` closes on success (`:56-57, 60-62`); no redirect, no onboarding, no first-login-vs-returning distinction anywhere.

## 4. Guest → account conversion — **no linkage exists (verified by trace, not absence)**

The signup handler was traced end-to-end: `LoginModal.handleSubmit` (`LoginModal.tsx:59`) → `useAuth.signUp` (`useAuth.ts:32-36`) → `supabase.auth.signUp({ email, password })`. **Nothing else runs.** No API call, no anon_id read, no guest-session touch.

Every `anon_id` reference in the codebase, exhaustively:
- Frontend: `useChat.ts:18-26,118` (chat metering), `chat-message.tsx:160` (feedback), `api.ts:89,105-106` (transport), `AdminModal.tsx:61` (feedback-row display type). **Zero references in `LoginModal.tsx`, `useAuth.ts`, `BetaGate.tsx`, or `/auth/callback`.**
- Backend: `chat.py` (guest metering branch only), `feedback.py:22,42` (stored on feedback rows).
- Schema: `guest_sessions` has no user-referencing column (live-verified).

**Conclusion: there is no code path — frontend, backend, or DB — that links a prior `anon_id`/`guest_sessions` row to a new authenticated `user_id`.** The guest row is orphaned permanently on conversion (and no cleanup/retention job exists anywhere — grep across `backend/app` and `scripts/` found no other `guest_sessions` reference).

**Guest chat history:** purely client-side and ephemeral. Server-side saving happens only for authenticated users — `chat.py:980-990`: `if user_id:` → background `_save_conversation`; `else:` → `conversation_id = None`, "Skipping conversation save". Guest messages live only in React state (`useChat`'s `useState` — not even localStorage) and are lost on refresh or tab close. The only durable anon_id-keyed data anywhere is the metering row and any feedback submissions.

## 5. Rate limit / metering interaction

**Fresh meter, zero carryover — confirmed from the live RPC.** `increment_user_query` (live definition verified) lazily creates the `user_usage` row on the user's **first authenticated chat call**: `INSERT ... VALUES (p_user_id, 0, monday, 50) ON CONFLICT DO NOTHING`, then increments → first authed query returns 1/50. Monday-UTC weekly reset. The guest `query_count` is never read, never subtracted, never migrated. `GET /usage` before the first chat also degrades safely (`usage.py:24-27`: empty result → 0/50).

So a guest who used all 6 free queries gets a full, independent 50/week the moment they authenticate — and conversely, a guest with 3 remaining free queries "loses" nothing by converting; the two meters are simply unrelated.

---

## Ambiguities, untested points, and contradictions with documented intent

1. **Beta gate is cosmetic at the API layer.** Never checked server-side; code `"rhema"` ships in the JS bundle. If the intent (per CLAUDE.md's beta-gate note) is to restrict beta *signups*, note that Supabase Auth signup itself (`supabase.auth.signUp` against the anon key) is also un-gated — anyone with the project URL + anon key can create an account without ever seeing BetaGate.
2. **Beta gate blocks returning users' sign-in in every new tab.** `openAuthGate` gates both `signin` and `signup` modes behind `beta_access`, which is sessionStorage-scoped. An existing, confirmed test user opening a fresh tab (while logged out) must re-enter "rhema" before they can even open the sign-in form.
3. **`guest_sessions.query_count` semantic drift: it counts attempts, not served queries.** The RPC increments before the backend enforces the cap, so blocked retries keep inflating the counter (live max is 9 against a limit of 6). Harmless for enforcement (`> 6` still blocks) but misleading for any analytics on that column.
4. **Likely broken session handoff after email confirmation (untested at runtime).** `/auth/callback` establishes the session in **cookies** (`createServerClient` from `@supabase/auth-helpers-nextjs`), but the app's client (`lib/supabase.ts`) is plain `supabase-js`, which reads **localStorage**. Code-level reading says a user who clicks the confirmation link lands on `/` *appearing logged out* and must sign in manually with the password they just created. Needs a live test to confirm, but the storage split is real and unshared.
5. **Confirmation email target is dashboard-dependent and unverifiable from the repo.** `signUp` passes no `emailRedirectTo`; the `/auth/callback` route expects the `token_hash`-style template parameters. Whether the project's actual email template matches that format is Supabase-dashboard config invisible to this audit.
6. **No `user_roles` row at signup.** CLAUDE.md describes a "three-tier role system (user/contributor/admin)" — in practice the `user` tier is a fallback default in two code paths, not data. Live DB confirms one real user has no row. Anything that ever queries `user_roles` directly (rather than via `get_user_role`) will silently miss such users.
7. **Orphaned guest rows accumulate forever.** No cleanup, no retention policy, no linkage on conversion. 30 rows today; harmless at beta scale, unbounded by design.
8. **`anon_id` continues to be sent after authentication** (`useChat.ts:118` calls `getAnonId()` unconditionally). Ignored server-side, but it means an authenticated user's requests still carry their old guest identifier — trivially linkable server-side in logs (`chat.py:533` logs anon_id, auth logs user_id) even though no code does so. Relevant if you ever *want* conversion linkage: the data to do it already flows through `/chat`.
9. **Guest limit copy vs. mechanics match** (not a bug, recording for completeness): "You've used your 6 free searches" (`app/page.tsx:58`) is accurate — counts 1–6 are served, the 7th attempt is blocked.

---

## The scenario question, answered explicitly

> *"If a guest exhausts their 6 queries, closes the tab, and signs up 10 minutes later, what does their experience look like?"*

1. **Their guest identity survives the tab close** — `rhemata_anon_id` is localStorage. Their `beta_access` flag does not (sessionStorage).
2. **Reopening the app, they can type but not chat.** Any attempted query increments their `guest_sessions.query_count` (7, 8, …) and is rejected 429; the UI removes the attempted message and pops the signup modal with "You've used your 6 free searches. Create a free account to keep going." (`app/page.tsx:56-60`).
3. **Before they can see the signup form, they must pass BetaGate again** — enter "rhema" (fresh tab = no `beta_access`).
4. **They submit email + password.** Assuming email confirmation is on (all live users are confirmed), no session returns; they see "Check your email for a confirmation link." Their in-progress context ends here — any chat they'd had as a guest was never persisted and is already gone.
5. **They click the confirmation link.** `/auth/callback` verifies the OTP, sets a *cookie* session, and redirects to `/` — where, per the storage-mismatch finding above, the app most likely still shows them as logged out. Expected reality: they click sign in (possibly re-entering "rhema" first if this opened yet another fresh tab from their email client), and enter their email + password again.
6. **Once signed in:** they have a clean 50/week meter — first query shows 1/50 (`user_usage` row created lazily on that first call). Their 6 exhausted guest queries have zero effect, positive or negative. Their role is `user` by code default; no `user_roles` row exists yet. Their old `guest_sessions` row (query_count ≥ 6, plus any blocked-attempt inflation) sits orphaned in the table forever, and their browser continues sending the old anon_id alongside their JWT on every chat call, where it is ignored.
7. **Nothing from their guest life carries over:** no chat history (never stored), no meter state (independent), no identity linkage (none exists).

**Net experience:** functional but lumpy — the conversion path works, but it contains two authentication ceremonies (signup, then a near-certain manual sign-in after email confirmation), up to two BetaGate prompts, and total amnesia about everything they did as a guest.
