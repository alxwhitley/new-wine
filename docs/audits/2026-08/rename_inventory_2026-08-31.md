# Rename inventory: Rhemata → New Wine

**Date:** 2026-08-31. **Type:** read-only scoping sweep. Nothing was renamed.
**Scale:** 972 real hits across 219 files. (A raw sweep returns 3,361 — three
`.claude/worktrees/` copies duplicate the whole tree. Exclude `worktrees/` or
every count is inflated ~3.5×.)

**Name decision:** Alex's direction, 2026-08-31 — the product is **New Wine**,
`newwine.app` is registered and serving. This supersedes CLAUDE.md Settled #25,
which recorded the target as "Manna" (2026-08-08); Manna was never implemented
anywhere beyond one unbuilt hero plan. Settled #25 corrected the same day.

**The "New Wine" collision is accepted, not overlooked.** "New Wine" already
names a corpus source in this repo — the magazine (Invariant 17,
`scripts/magazine_review/`, roadmap A2, ~60 `new_wine_*` audit dirs). Alex's
ruling: it is New Wine *magazine* vs New Wine *app*, uncopyrighted, and the
ambiguity is acceptable. Recorded so a future session does not re-raise it.

---

## 1. User-facing text

| File | Line / field |
|---|---|
| `frontend/app/layout.tsx:8` | `title: "Rhemata — Theological Research Assistant"` — global page title |
| `frontend/app/home/page.tsx` | 98, 109, 120, 161, 176, 185 — marketing copy + `footerBrand` |
| `frontend/app/home/page.tsx:191` | `ῥήματά ἐστιν πνεῦμα καὶ ζωή εἰσιν — John 6:63` — **the Greek tagline is the name's etymology and stops making sense under any new name.** A rename decision, not a find-and-replace |
| `frontend/app/study/page.tsx:1092`, `library/page.tsx:568,661`, `library/authors/page.tsx:67` | Mobile header `<h1>Rhemata</h1>` ×4 |
| `frontend/components/rhemata/sidebar.tsx:164` | Sidebar wordmark |
| `frontend/components/auth/LoginModal.tsx:91` | `"Sign in to Rhemata"` |
| `frontend/components/rhemata/chat-message.tsx:234` | `"Your feedback helps improve Rhemata"` |
| `frontend/lib/api.ts:229` | Error copy: `"…reach Rhemata's answer service…"` |
| `frontend/app/beliefs/page.tsx:15` | SEO `description` meta |
| `frontend/app/beliefs/page.tsx` | 23, 29, 32, 52, 94, 102 — body copy |
| `frontend/app/sources/page.tsx:14,15` | Page title + SEO description |
| `frontend/app/sources/page.tsx` | 21, 27, 29, 32, 35, 40, 47, 66, 77, 89, 92 — body copy |
| `backend/app/system_prompt.txt:1,32,53` | `"You are Rhemata…"` — **shapes every generated answer** |
| `backend/app/services/position_papers.py` | 916, 918, 922, 927, 1107 — house-voice template |
| `backend/app/services/position_papers.py:1154` | `DISCLAIMER_TEXT = "Rhemata can make mistakes…"` |
| `backend/app/services/async_answers/producer.py:806` | `"Rhemata's own settled house position on %s"` |
| `backend/app/main.py:10,102` | FastAPI `title`, root `{"message": "Rhemata API"}` |

No favicon/logo alt text and no email templates contain the name — none exist.

## 2. Legal / policy

**There is no privacy policy and no terms of service page.** Routes are `/`,
`/home`, `/beliefs`, `/sources`, `/library`, `/study`, `/admin`, `/auth/*`,
`/document/[id]`. Confirmed a real gap, independent of the rename; Alex flagged
it for work 2026-08-31. Unclassified — needs a Blocker/Scheduled decision.

| File | Line / field |
|---|---|
| `frontend/app/home/page.tsx:191` | `© 2026 Rhemata. All rights reserved.` |
| `backend/app/services/search_analytics/consent.py:22-23` | `POLICY_COPY` — **binding consent text users agree to at signup** |
| `frontend/components/rhemata/consent-gate.tsx:98` | The same copy **duplicated** as a client fallback — **these two must change together** or the gate shows stale wording |

## 3. Config and identifiers

| Where | Value | Note |
|---|---|---|
| Vercel project | `rhemata` (`frontend/.vercel/project.json`) | Rename changes the `*.vercel.app` subdomain |
| Railway service | `rhemata` (1 of 4) | Project is `dependable-enthusiasm` — no change needed |
| Railway env var | `RAILWAY_SERVICE_RHEMATA_URL` | **Auto-generated from the service name**, on all four services |
| Postgres role | `rhemata_readonly_analysis` | Live role — 61 refs in migration 084, 8 in 087 |
| `frontend/next.config.ts:21` | redirect `/rhemata-corpus-admin` | Admin URL path |
| `frontend/components/auth/BetaGate.tsx:18` | `code === "rhema"` | **Variant spelling** — a code users type |
| `frontend/components/admin/corpus-data.ts:5` | `REPO_ROOT = "/Users/alexwhitley/rhemata"` | Hardcoded local path |
| `tools/discovery-review-extension/manifest.json:3,5` | `"Rhemata Discovery Review"` | Local unpacked extension, no store listing |
| localStorage keys | `rhemata_anon_id`, `rhemata_pending_pin`, `rhemata_guest_chat_v1`, `rhemata:library:authors`, `rhemata:library:era` | **Renaming these silently logs out guests and drops saved filters** unless migrated |
| `frontend/components/rhemata/` | directory — ~40 import paths | Cosmetic, wide blast radius |

Supabase ref `jjerxncanaxlbdzcybab`, database `postgres`, and
`frontend/package.json` (`"name": "frontend"`) contain no "rhemata" — nothing to do.

## 4. Domain and DNS

**Live state, 2026-08-31:** `newwine.app` and `www.newwine.app` both return 200
and serve the app. DNS on **Cloudflare** (`clara`/`hans.ns.cloudflare.com`) →
Vercel. The older `rhemata.app` is on GoDaddy (`ns67/ns68.domaincontrol.com`),
resolves to Vercel, and returns 404.

| Where | Value |
|---|---|
| Railway `ALLOWED_ORIGINS` | **FIXED this session** — was `https://rhemata.app` alone; now `https://rhemata.app,https://newwine.app,https://www.newwine.app`. See §6 |
| `frontend/.env.local:1` | `NEXT_PUBLIC_API_URL=https://rhemata-production.up.railway.app` |
| Railway public domain | `rhemata-production.up.railway.app` (derived from service name) |
| `scripts/verify_metering_live.py`, `test_account_delete_request_e2e.py`, `test_ingest_queue_endpoints.py`, 2 archived smokes | `API_BASE` hardcoded to that host |
| `.claude/settings.local.json` | 4 permission entries scoped to that host |

No OAuth callbacks, CSP headers, or webhook URLs contain the name.

## 5. Documentation / internal — low priority

~780 of 972 hits. Not user-facing. `docs/` 483 · agent config
(`.claude`/`.codex`/`.grok`/`.agents`/`.impeccable`) 85 · root governing docs 79
(`CLAUDE.md` 29, `POSITIONING.md` 26, `PLAN.md` 5, `ARCHITECTURE.md` 5,
`rhemata-status.md` 4, `DESIGN.md` 4, `PRODUCT.md` 3, `HARNESS.md` 2,
`AGENTS.md` 1) · `scripts/` 115 · `migrations/` 76 (61 are the role name).

**`rhemata-status.md` is referenced by filename** in `config.py:18,41`, four
migrations, and the session-close skill — renaming the file breaks those.

## 6. Stored as data, not code

| Table / row | Field | Note |
|---|---|---|
| `sources` `bf6d9e28-1cfd-4431-975b-df2ca1b9cfdf` | `name='Rhemata'`, `slug='rhemata'`, `owned`, `shown` | **The house position-paper source** — all 9 papers hang off it |
| `source_aliases` | `alias_key='rhemata'`, `alias_display='Rhemata'` | Resolver alias |
| `chunks` | **14 chunks** across the 9 position papers | e.g. *"Rhemata's position: a genuine believer cannot be possessed"* — injected as `[House Position]` context and servable in house voice |
| `pg_roles` | `rhemata_readonly_analysis` | Live role |

`propositions` 0 · `documents` title/author/url 0 · `app_settings` holds only
`safe_mode`. No feature-flag or site-config table carries the name.

Source markdown for those chunks is `docs/position_papers/*.md` (11 refs) —
**files and DB chunks must change together** or served text diverges from source.

## 7. Requires external, non-code action

1. **Cloudflare DNS** — `newwine.app` records already in place and serving.
2. **GoDaddy** — `rhemata.app` still registered; needs a redirect or
   let-lapse decision. Currently 404.
3. **SSL** — Vercel-issued; already valid for `newwine.app`.
4. **Vercel project rename** (`rhemata` → …) — dashboard action; changes the
   preview subdomain.
5. **Railway service rename** — regenerates `rhemata-production.up.railway.app`
   **and** `RAILWAY_SERVICE_RHEMATA_URL` on all four services. Would break the
   hardcoded `API_BASE` in three live scripts and `frontend/.env.local`, and
   must be coordinated with `ALLOWED_ORIGINS` or CORS rejects the frontend.
6. **Postgres role rename** — attended production DB operation.
7. **Supabase Auth** — email templates and site URL / redirect allowlist live in
   the dashboard and will carry the old name or domain. Not enumerable
   read-only from here; check before beta.

No app store listings, no third-party OAuth app registrations.

## 8. Do not rename — verified false positive

A `chunks` row in **"Jamieson-Fausset-Brown Commentary - Revelation"** contains
`"ta rhemata"` — transliterated Greek in a public-domain commentary:

> …Greek, "hoi logoi," in A, B, and ANDREAS. English Version reading is Greek,
> "ta rhemata," which is not well supported…

Any case-insensitive sweep of `chunks.content` will hit this. **Exclude it** —
editing it corrupts a public-domain source text.

---

## Fixed this session: CORS was blocking the new domain

Found while verifying that `newwine.app` was "connected and working." It served
the app, but the backend's allowlist did not include it, so **every browser API
call from that origin failed** — the page loaded and chat was broken.

```
BEFORE   ALLOWED_ORIGINS=https://rhemata.app
         OPTIONS /async-chat/submit  Origin: newwine.app  -> 400, no allow-origin
AFTER    ALLOWED_ORIGINS=https://rhemata.app,https://newwine.app,https://www.newwine.app
```

Verified live after the redeploy (`rhemata` service only, 16:10:36Z):

| Origin | HTTP | allow-origin |
|---|---|---|
| `https://newwine.app` | 200 | `https://newwine.app` |
| `https://www.newwine.app` | 200 | `https://www.newwine.app` |
| `https://rhemata.app` | 200 | `https://rhemata.app` |
| `https://evil.example.com` | 400 | none |

The negative control matters: the list is still exclusive, not wildcarded
(`allow_credentials=True` makes `*` illegal anyway). Real `GET` responses were
checked too, not just preflight — both new origins return
`200 {"async_enabled":true}` with the header attached.

`www` needed its own entry: it is a distinct origin to a browser.
`rhemata.app` was deliberately retained so the old domain keeps working through
the transition.

Rollback: `railway variable set "ALLOWED_ORIGINS=https://rhemata.app" --service rhemata`
