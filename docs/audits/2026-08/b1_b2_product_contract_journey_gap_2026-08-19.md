# B1/B2 gap check — product contract & core user journey

Read-only, code-vs-doc comparison only. No live/browser testing performed —
flagged below wherever that's the actual remaining verification step.
Source docs: `PRODUCT.md`, `POSITIONING.md`. Source code: `frontend/app/**`,
`backend/app/routers/*`, `backend/app/services/async_answers/producer.py`.

## 1. Docs are stale relative to shipped code — fix before B1 freeze

- **POSITIONING.md §6/§10 say verified-verbatim quoting is "a planned, gated
  future capability; not live yet."** CLAUDE.md confirms the quote rail has
  been live in production since 2026-08-19
  (`QUOTE_SELECTION_ENABLED=true`, gold-pipeline quotes serving). This is a
  materially wrong claim in the source-of-truth positioning doc — messaging
  pillar #3 and Guardrail #3 both need a rewrite before B1 can be "frozen"
  against it.
- **PRODUCT.md's Product Purpose line names John Bevere as an example
  covered teacher** ("teachers like Derek Prince, Ern Baxter, and John
  Bevere"). CLAUDE.md Landmines records Bevere was removed from marketing
  2026-08-06 because the corpus has zero documents for him. PRODUCT.md was
  not updated to match.
- Neither doc names "Manna" — both still say "Rhemata" throughout, which is
  correct per Settled decision #25 (naming-only, no doc rewrite in scope
  yet), just noting so B1 doesn't inherit a name mismatch by accident.

## 2. Journey pieces that exist and match the docs

- Chat entry point: `frontend/app/page.tsx` (608 lines) is the primary
  authenticated chat surface, wired to `/async-chat/submit` +
  `/async-chat/result/{job_id}` (SSE) in `backend/app/routers/async_chat.py`.
- Guest/user metering happens pre-enqueue in `submit()`, fail-closed (per
  CLAUDE.md's pre-flip-blocker record) — a 429 path exists, referenced in
  `page.tsx` comment "Fail quietly on any error (e.g. cap already reached...)".
- Honest-empty / thin-retrieval behavior is real, not just documented intent:
  `producer.py` has an explicit "Graceful-degradation hint — only when
  citable sources are thin or absent" injection and a "truly_empty
  short-circuit" path (comment references the same behavior chat.py had
  before deletion).
- Study Mode: `frontend/app/study/page.tsx` exists, backed by
  `backend/app/routers/study.py` (interlinear/lexicon/teacher-card surface).
- Library: `frontend/app/library/page.tsx` +
  `frontend/app/library/authors/page.tsx` + `frontend/app/library/book/[id]`
  exist, matching POSITIONING.md's "pointer directory" description.
- Admin: `frontend/app/admin/**` (contributors, edit, quotes) + wide backend
  router surface (`admin.py`, `ingest_queue.py`, `ingest.py`) — matches
  POSITIONING.md's "unseen surface" description.
- Feedback: referenced in `frontend/app/study/page.tsx`,
  `components/admin/AdminModal.tsx`, and `components/rhemata/chat-message.tsx`,
  backed by `backend/app/routers/feedback.py` — exists, not deeply verified
  beyond confirming the wiring exists.

## 3. Real implementation gaps (B4-adjacent but B2-relevant: "recover from
   terminal states without a dead end")

- **Account deletion is confirmed still a stub** (matches CLAUDE.md
  Landmines exactly): `backend/app/routers/account.py`'s
  `submit_delete_request()` only inserts a `deletion_requests` row for
  manual admin follow-up. No cascading delete of `conversations`,
  `saved_words`, `pastors_cards`, `user_roles`, or the Supabase auth user
  exists anywhere in the codebase. If B2's "recover from expected terminal
  states without a dead end" is meant to include account lifecycle, this is
  a real, not cosmetic, gap.
- **No dedicated frontend account page found** — no `frontend/app/account`
  or similar route directory exists. Whatever UI calls
  `/account/delete-request` is not a top-level route; it's likely a modal
  or settings panel inside another page (not located in this pass — a
  targeted follow-up grep for the fetch call site would confirm, deferred
  since this pass stayed at the route-directory level).
- **No `/about` page exists**, despite PRODUCT.md's header note using
  "/about" as an example of unauthenticated brand-register surface. Minor —
  PRODUCT.md uses it as an illustrative example, not a requirement, but
  worth confirming with Alex whether an About page is expected before beta
  or was always hypothetical.

## 4. Ambiguous from code alone — needs a live check, not further reading

- Whether the guest-limit 429 path actually surfaces a user-visible,
  non-dead-end message in the UI (the code comment says "fail quietly,"
  which could mean either a clean inline message or a silent swallow that
  reads as a dead end — text alone doesn't resolve which).
- Whether "pastoral question → point to a human, don't answer" (POSITIONING
  §9 Chat guardrail) is actually enforced anywhere in `producer.py`'s prompt
  or a separate classifier — not confirmed in this pass; worth a targeted
  grep + a live pastoral-question smoke test.
- Whether citation/source navigation ("reach named teachers or Scripture")
  actually round-trips correctly on mobile and desktop — B3's own scope
  line already flags this as unverified, consistent with what's found here.

## Not attempted (explicitly out of scope for this pass)

- No app was started; no browser interaction; no live API calls made.
- B1's actual "testable criteria" were not authored — that is explicitly
  Alex's call per `docs/roadmap.md`.
