# Button / CTA & Sign-in UX Audit

**Date:** 2026-07-06 · **Method:** read-only grep + code trace. No files changed except this report. Line numbers reflect the working tree as of commit `c47bbd3` plus the uncommitted session files.

---

## 1. Master inventory — every auth entry point

| # | Entry point | Copy (exact) | Component | Styling source | State handled | Notes |
|---|---|---|---|---|---|---|
| 1 | `/home` nav bar — `app/home/page.tsx:372` | `Become a test user` | `ui/Button` (default, sm) | Tokens | n/a (nav click) | **Visible to logged-in users** — home never reads `user` (`:341` destructures only `signIn, signUp`) |
| 2 | `/home` hero — `app/home/page.tsx:389` | `Become a test user` | `ui/Button` (default, lg) | Tokens | n/a | Same visibility issue |
| 3 | `/home` hero secondary — `app/home/page.tsx:391` | `Try it free — no account needed` | `ui/Button` (outline, lg, `asChild` → `Link href="/"`) | Tokens | n/a | **Not an auth entry** — routes to guest chat, correctly ungated |
| 4 | `/home` final CTA — `app/home/page.tsx:575` | `Become a test user` | `ui/Button` (default, lg) | Tokens | n/a | Same visibility issue |
| 5 | Sidebar guest footer (Chat/Study/Library/Authors) — `components/rhemata/sidebar.tsx:418-420` | `Become a test user` | `ui/Button` (default, sm, `w-full`) | Tokens | n/a | Hidden when logged in (`isLoggedIn` branch `:376`). Mobile: same button inside the drawer, reached via floating menu button (chat, `app/page.tsx:192-198`) or top-bar hamburger (study, `app/study/page.tsx:1384-1390`) |
| 6 | Chat guest-limit callback — `app/page.tsx:56-60` | reason: `You've used your 6 free searches. Create a free account to keep going.` | (opens gate/modal directly) | — | n/a | → `openAuthGate("signup")`; guests only |
| 7 | Study save-word bookmark (logged out) — `app/study/page.tsx:966`; tooltips at `:343, :605` (`Sign in to save words`) | (icon button) | raw `<button>` + Tailwind | Tokens | n/a | **Bypasses BetaGate** — calls `setShowLogin(true)` directly, never `openAuthGate` |
| 8 | Library sidebar CTA — `app/library/page.tsx:576` | (sidebar copy) | via sidebar | — | n/a | Correctly routes through `openAuthGate("signup")` `:215-221` |
| 9 | Authors page sidebar CTA — `app/library/authors/page.tsx:60` | (sidebar copy: `Become a test user`) | via sidebar | — | n/a | **Bypasses BetaGate** (page has no BetaGate import at all) **and opens the wrong mode** — `LoginModal` at `:127` passes no `initialMode`, which defaults to `"signin"` (`LoginModal.tsx:18`). Button says "Become a test user", modal opens as **"Sign in to Rhemata"** |
| 10 | BetaGate submit — `components/auth/BetaGate.tsx:57` | `Continue` | `ui/Button` (default, `w-full`) | Tokens | Y (error) | Synchronous check, no loading state needed; error clears on typing (`:50`) |
| 11 | LoginModal main submit — `components/auth/LoginModal.tsx:194-196` | `Sign in` / `Become a test user` / `…` (submitting) | `ui/Button` (default, `w-full`) | Tokens | Y (disabled + error) | Ellipsis text instead of the `Loader2` spinner DESIGN.md prescribes (sidebar's contributor/settings submits **do** use `Loader2` — `sidebar.tsx:468, 523`) |
| 12 | LoginModal forgot-password submit — `components/auth/LoginModal.tsx:130-132` | `Send reset link` / `Sending…` | `ui/Button` (default, `w-full`) | Tokens | Y | Success panel + "Back to sign in" |
| 13 | LoginModal mode-switch / back links — `LoginModal.tsx:134-142, 150-155, 198-207` | `Sign up` / `Sign in` / `Back to sign in` / `Forgot password?` | raw text `<button>` | Tokens | n/a | Text-link tier; consistent |
| 14 | Logged-in sidebar dropdown — `sidebar.tsx:412-414` | `Log out` | shadcn `DropdownMenuItem` | Tokens | n/a | See §4 |
| 15 | **DEAD** — `components/auth/AuthButton.tsx:65` | `Sign out` | raw `<button>` | **Hardcoded drift** | — | See §2 |

**LoginModal `initialMode` per site:** chat `app/page.tsx:315-321` → state (default `"signup"`); home `:628-634` → hardcoded `"signup"`; study `:1776` → state (default `"signup"`); library `:666, :1333` → state (default `"signup"`); **authors `:127` → omitted → `"signin"`** (the odd one out).

## 2. Dead / duplicate / inconsistent buttons

1. **`components/auth/AuthButton.tsx` — entire component is dead.** Zero import sites anywhere in `app/` or `components/`. It's also three ways stale: `hover:border-gold` (`:24`) references a `gold` class/token that doesn't exist in `globals.css` and matches the pre-brand-reset naming DESIGN.md's migration bans killed; `z-49` (`:34`) is an off-scale z-index; and it links to `/rhemata-corpus-admin` (`:48`), a route CLAUDE.md records as deleted (now a redirect). This is the orphaned remnant of the pre-June auth button.
2. **`sidebar.tsx:4` — unused `LogIn` icon import.** Imported from lucide-react, referenced nowhere in the file. Leftover from the June "Sign in" → "Become a test user" copy swap. (Confirms the swap left no *reachable* old button — just this import and the dead component above.)
3. **Authors page mode mismatch** (row 9 above): the only reachable spot where the "Become a test user" CTA opens a sign-**in** form.
4. **Two BetaGate bypasses** (rows 7, 9): study save-word and the entire authors page skip the gate and open LoginModal directly. Whether intentional (deep-in-app users are presumably already "in") is undocumented — but it makes the gate's coverage inconsistent: same CTA, gated on four pages, ungated on one.
5. **Duplicate BetaGate/LoginModal pairs in `app/library/page.tsx`** (`:665-666` and `:1331-1333`) — *not* a double-render: the first pair lives inside the article-reader early-`return` branch, the second in the main return. Mutually exclusive, but the same modal wiring is maintained twice in one file.
6. **`ui/button.tsx` vs. DESIGN.md recipe drift.** All auth CTAs share the single shadcn Button — internally consistent, no hardcoded hex, no one-off padding. But the actual component (`components/ui/button.tsx:7-40`) no longer matches DESIGN.md's documented recipe: focus ring is `ring-[3px] ring-ring/50` (doc says `ring-1 ring-ring`), `transition-all` (doc: `transition-colors`), default variant has no `shadow` (doc: `shadow`), `lg` is `px-6` (doc: `px-8`), `sm` lacks `text-xs`, and there are undocumented `xs`/`icon-xs`/`icon-sm`/`icon-lg` sizes. The *doc* is what's stale, not the buttons.
7. Minor a11y inconsistency: LoginModal's error `<p>` (`LoginModal.tsx:190-192`) has no `role="alert"`, while the chat/study error paragraphs do (`app/page.tsx:229`, `app/study/page.tsx:1432`).

## 3. State handling on the sign-in/signup buttons

- **Double-submit: prevented.** Main form: `disabled={submitting}` (`LoginModal.tsx:194`), set before the await, released in `finally` (`:53, :69-70`). Forgot-password form: same pattern with `resetSubmitting` (`:32, :45-47`). BetaGate is synchronous — nothing to guard.
- **Error state: resets cleanly.** `setError(null)` at submit start (`:52`); raw Supabase messages render inline (e.g. "Invalid login credentials"); the `finally` re-enables the button. No stuck state found in any path. BetaGate error clears on the next keystroke (`:50`).
- **Post-submit paths:** password-with-immediate-session → modal closes silently (`:56-57, :60-62`); no-session signup → form is replaced by "Check your email for a confirmation link." + "Back to sign in" (`:145-156`). There is **no magic-link path** — email+password only (`useAuth.ts:27-36`).
- **One ambiguous state (code-level inference, untested):** Supabase's anti-enumeration behavior returns *success with no session and no error* for a signup against an already-registered confirmed email — so an existing user who taps "Become a test user" and re-enters their email sees "Check your email for a confirmation link" while no email arrives. The code (`useAuth.ts:35` checks only `data.session`) cannot distinguish this from a genuine new signup.

## 4. Logged-in state reflection

- **Sidebar swaps correctly.** `sidebar.tsx:375-421`: logged out → "Become a test user" Button; logged in → profile `DropdownMenu` (display name, email, `ChevronsUpDown`, and `UsageRing` when `weeklyUsage` is passed) with Profile / Become a contributor (role `user`) / Admin panel (role `admin`) / Log out. Caveat: only the chat page passes `weeklyUsage` (`app/page.tsx:176`) — on Study/Library/Authors the logged-in footer renders name+email without the ring. Mobile uses the identical `sidebarContent` in the drawer; MobileTabBar itself has no auth entry, so post-Pass-A the CTA is reachable only through the drawer — same component, same copy, both breakpoints.
- **`/home` never swaps.** It doesn't read `user`, so an authenticated visitor sees all three "Become a test user" CTAs.

**BetaGate-vs-authenticated-session mismatch — CONFIRMED on `/home`, ruled out in-app:**
- **Confirmed:** an authenticated user (auth session persists in localStorage) opening `/home` in a fresh tab (`beta_access` is sessionStorage, now empty) and clicking any of the three CTAs gets **BetaGate** (`openAuthGate`, `home/page.tsx:345-351` checks only sessionStorage, never auth state), then a **signup form** — despite already being signed in. Two gates deep before discovering the click was pointless.
- **Ruled out in-app:** every in-app trigger is unreachable while authenticated — the sidebar CTA renders only in the `!isLoggedIn` branch (`sidebar.tsx:376/417`), the guest-limit callback only fires on guest 429s (`useChat.ts:125-128` — impossible with a token), and the study save-word path requires `!user` (`study/page.tsx:966`).
