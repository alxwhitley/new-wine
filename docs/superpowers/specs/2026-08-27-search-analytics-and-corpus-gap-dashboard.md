# Search Analytics and Corpus-Gap Dashboard

**Date:** 2026-08-27

**Status:** Design accepted from Alex's directive (this session). Building in
worktree `search-analytics-corpus-gap` off `main` at `34c2a74`. No migration
applied, no deploy, no production mutation — repo-only.

**Scope:** Answers `docs/roadmap.md` Horizon item 4, "Consent-based search
analytics and corpus-gap alerts." Backend schema + services + APIs, admin
dashboard tab, signup/login consent gate. Explicitly does not touch
answer-generation, retrieval, citations, or outcome rules.

---

## Objective

Alex has no visibility into what beta testers actually search for, which
topics are in demand, or where the corpus has real content gaps — today the
only signal is manual `feedback` thumbs and ad hoc spot-checks. This builds
an anonymous, consent-gated analytics ledger that answers three questions:
what topics are searched, how often a topic search fails with
`no_material`, and what the (redacted) failing questions actually said, so
missing-content work can be prioritized by real demand instead of guesswork.

Privacy is the load-bearing constraint, not an afterthought: successfully
answered question wording is never persisted or returned by any API,
tester identity is never derivable from stored rows, and even the one
exception (a `no_material` question, needed to diagnose *why* the corpus
failed) is deterministically redacted and time-boxed for automatic
deletion after the gap is resolved.

## Non-goals (restated from the directive, binding)

Same list as the driving prompt: no teacher-family taxonomy, no new topic
vocabulary, no answer-path changes, no `answer_jobs`-as-ledger, no
third-party analytics, no automatic gap resolution, no named-user
analytics, no public-user consent UI, no AdminModal refactor beyond adding
one tab, no unrelated fixes (classified and reported instead).

## Assumptions made without stopping to ask (Auto Mode; recorded so Alex can
overrule any of them)

1. **`AsyncChatRequest.submission_id` is optional and server-fills a UUID4
   when absent.** Keeps the change purely additive for any client build
   that predates this feature; only the updated frontend actually supplies
   a stable client-generated id, which is what makes retry-idempotency
   real. A server-generated fallback still creates exactly one occurrence
   per HTTP call, it just can't collapse a client-level retry into the
   same occurrence — acceptable since the old frontend doesn't retry with
   a reused id today either.
2. **`origin` on a search occurrence is never client-suppliable.** The
   public `/async-chat/submit` route always creates `origin='user'` rows;
   `origin='admin_retest'` is only ever written by the admin retest
   endpoint calling the internal occurrence-creation function directly. If
   `origin` were a request field, a malicious client could self-label as
   an admin retest to escape demand counting.
3. **Admin retest resubmits the stored *redacted* question, not an
   unredacted original.** The original `no_material` question text is
   never stored anywhere (only the redacted form is), so the redacted form
   is definitionally the only text available to retest with. Redaction
   only strips obvious direct identifiers (email/phone/address/IP/account
   ids), so the theological substance an admin needs to retest survives
   redaction in the overwhelming majority of cases. This is stated
   explicitly because it's the one place "gap wording" round-trips back
   into a live system action.
4. **The consent gate blocks the frontend UX, not the backend API.** The
   backend does not hard-refuse a chat submission from an authenticated
   user lacking current consent — it simply skips occurrence creation for
   that submission (a normal, unmonitored search, same as a guest). Adding
   a server-side hard block on core chat access is bigger-blast-radius
   auth work than this feature's scope and isn't required by any
   acceptance criterion; the frontend gate (mandatory at signup, one-time
   blocking gate at next login, decline signs out) is the actual
   enforcement point. Flagged as a parked follow-up if Alex wants
   defense-in-depth here later.
5. **Classification is a same-repo retryable finalizer function, not a
   deployed Railway worker.** Mirrors `scripts/answer_worker.py`'s shape
   (a poll loop calling a pure `finalize_ready_jobs()` function) but
   actually running it as a service is a rollout decision for Alex, listed
   in the rollout checklist at the end — this session ships the function
   and its CLI wrapper, not a live deployment.
6. **Occurrence creation happens synchronously in `/submit`, after
   enqueue.** It needs a real `job_id`, so it can't run before
   `jobs.enqueue()` returns. This means a rare DB failure on the occurrence
   insert surfaces as a 503 to the caller *after* a job already exists in
   the queue — the existing single-flight/reuse keys mean a client's retry
   converges onto that same job rather than wasting a second generation,
   so this is a bounded, self-healing cost, not a resource leak.
7. **HMAC secret is a new env var, `ANALYTICS_HMAC_SECRET_V1`, versioned by
   suffix.** No existing generic app-secret convention was found to reuse
   (grepped for `hmac`/`SECRET_KEY` repo-wide — only provider API keys
   exist). Rotation procedure: set `ANALYTICS_HMAC_SECRET_V2`, bump
   `CURRENT_SUBJECT_KEY_VERSION`; old rows keep their v1 `subject_key`
   value (stored, not re-derived), so withdrawal/deletion for a
   still-v1-keyed user keeps working as long as `ANALYTICS_HMAC_SECRET_V1`
   is still configured — deleting the v1 env var forecloses future v1
   derivation but never mutates already-stored rows.

## Data model — migration `093_search_analytics.sql`

Three new tables, RLS-enabled, service-role-only (this backend's standing
pattern for tables PostgREST must never expose directly — migration 082's
`quotes`/`document_quote_clearance` policies are the template). Explicit
`REVOKE ALL ... FROM anon, authenticated` on all three as defense-in-depth
per the directive, on top of RLS default-deny.

### `analytics_consent` — one row per account

```
user_id               uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE
policy_version        text NOT NULL
acknowledged_at       timestamptz NOT NULL
withdrawn_at          timestamptz
subject_key           text NOT NULL          -- current HMAC(secret_v, user_id)
subject_key_version   integer NOT NULL
retired_subject_keys  jsonb NOT NULL DEFAULT '[]'  -- [{"version":1,"key":"..."}] appended on rotation
created_at            timestamptz NOT NULL DEFAULT now()
updated_at            timestamptz NOT NULL DEFAULT now()
```

No question/topic/answer data — by construction, no column exists to put
it in.

### `search_occurrences` — one row per accepted submission

```
id                        uuid PRIMARY KEY DEFAULT gen_random_uuid()
submission_id             text NOT NULL UNIQUE       -- client idempotency key (or server-filled uuid4)
job_id                    uuid NOT NULL REFERENCES answer_jobs(id)
origin                    text NOT NULL CHECK (origin IN ('user','admin_retest'))
subject_key               text                        -- NULL only for admin_retest
subject_key_version       integer                     -- NULL only for admin_retest
question_fingerprint      text NOT NULL               -- sha256(subject_key||normalized question), opaque
primary_topic             text                        -- one of VALID_TAGS, or 'Unclassified'; NULL until classified
outcome                   text                        -- copied from answer_jobs.outcome at finalize time
classification_status     text NOT NULL DEFAULT 'pending' CHECK (IN ('pending','classified','failed'))
classifier_version        text
classifier_model          text
classifier_prompt_version text
classifier_confidence     numeric(4,3)
created_at                timestamptz NOT NULL DEFAULT now()
finalized_at              timestamptz
CHECK ((origin = 'user' AND subject_key IS NOT NULL AND subject_key_version IS NOT NULL)
    OR (origin = 'admin_retest' AND subject_key IS NULL AND subject_key_version IS NULL))
```

No account id, conversation id, or answer text — by construction. Indexes:
`job_id` (finalizer fan-out), partial on `classification_status='pending'`
(finalizer claim scan), `subject_key` (withdrawal purge), composite
`(primary_topic, outcome)` (dashboard aggregation).

### `search_gap_details` — one row per `no_material` occurrence

```
id                    uuid PRIMARY KEY DEFAULT gen_random_uuid()
occurrence_id         uuid NOT NULL UNIQUE REFERENCES search_occurrences(id) ON DELETE CASCADE
redacted_question     text                        -- NULL once purged, or if redaction_failed
redaction_version     text NOT NULL
redaction_status      text NOT NULL CHECK (IN ('redacted','redaction_failed'))
status                text NOT NULL DEFAULT 'open' CHECK (IN ('open','resolved'))
retest_occurrence_id  uuid REFERENCES search_occurrences(id)
retest_outcome        text
resolved_at           timestamptz
text_purge_at         timestamptz                 -- resolved_at + 30 days, set at resolution
purged_at             timestamptz
created_at            timestamptz NOT NULL DEFAULT now()
updated_at            timestamptz NOT NULL DEFAULT now()
```

No account identity or answer text — by construction. Resolution requires
`retest_outcome IS NOT NULL AND retest_outcome <> 'no_material'`, enforced
in the router, not a DB trigger (no service-role bypass concern here since
this table has no external write path at all beyond the backend).

## Backend services (`backend/app/services/search_analytics/`)

- `subject_key.py` — `derive_subject_key(user_id, version) -> str` =
  `hmac.new(secret_bytes, user_id.encode(), hashlib.sha256).hexdigest()`,
  secret read from `ANALYTICS_HMAC_SECRET_V{version}`. Irreversible by
  construction (HMAC, not encryption); never logged, never returned by any
  API.
- `consent.py` — `CURRENT_POLICY_VERSION`, `get_consent_status()`,
  `acknowledge()` (idempotent upsert — a repeat PUT with the same version
  is a no-op success, not a second row), `withdraw()` (sets
  `withdrawn_at`, deletes every `search_occurrences`/`search_gap_details`
  row matching any of the account's current + retired subject keys, then
  future submissions simply see "no current consent" and stop creating
  occurrences — no separate "stop collection" flag needed).
- `redaction.py` — `REDACTION_VERSION`, deterministic regex passes for
  email, phone, street address (number + street-suffix heuristic), IPv4/
  IPv6, and UUID-shaped direct account identifiers. Explicitly does NOT
  touch capitalized words generally (no blind name-stripping — teacher and
  biblical names must survive, matching the corpus-wide
  `common_religious_vocab.json` precedent of not treating capitalization
  as a name signal). Caps stored length at 500 chars. Returns
  `redaction_status='redaction_failed'` (never partially-redacted text) on
  a regex engine exception, which the caller stores with
  `redacted_question=NULL`.
- `occurrences.py` — `create_occurrence()` via the same
  `INSERT ... ON CONFLICT (submission_id) DO NOTHING RETURNING id` /
  fallback-`SELECT` shape `jobs.enqueue()` already uses for its own
  idempotency, over the existing `async_answers.db.Db` direct-Postgres
  helper (reused, not forked — same "one shared implementation" posture as
  `normalize_alias_key`).
- `classifier.py` — `CLASSIFIER_VERSION`, `classify_topic(question) ->
  ClassificationResult`. Groq `openai/gpt-oss-120b` (matches this
  codebase's existing query-expansion/metadata/extraction model
  assignment), same prompt-then-parse-then-fence-strip convention as
  `scripts/propositions.py` (no native JSON tool-calling anywhere else in
  this repo to mirror). Output is validated, not trusted: parsed topic
  must be an exact match in `app.constants.VALID_TAGS` or the result is
  forced to `Unclassified`; confidence below `CONFIDENCE_THRESHOLD = 0.70`
  is also forced to `Unclassified` regardless of the returned label; any
  parse failure raises a typed exception the finalizer treats as a
  retryable failure, never a crash into the caller.
- `finalizer.py` — `finalize_ready_jobs(db, supabase, limit=50)`. Scans
  `search_occurrences` for `classification_status='pending'` rows whose
  `answer_jobs.status='done'`, groups by `job_id`, classifies once per
  job, fans the result to every occurrence row sharing that job. On
  `outcome='no_material'` and `origin='user'`, creates the gap row
  (redacting `answer_jobs.question`). On `outcome='no_material'` and
  `origin='admin_retest'`, updates the existing gap's `retest_outcome`
  instead of creating a second gap. On any other outcome for an
  `admin_retest` occurrence, likewise updates `retest_outcome` (making
  `PATCH .../resolve` eligible). Never reads or writes `answer_jobs.answer`
  /`citations`/`outcome` columns themselves — read-only on that table
  besides the join.
- `gaps.py` — cursor-paginated topic gap listing, retest creation (calls
  `jobs.enqueue()` + `create_occurrence(origin='admin_retest')` +
  stamps `retest_occurrence_id` on the gap), resolve (validates
  `retest_outcome` before flipping `status`).
- `retention.py` — `purge_expired_gap_text()`: `UPDATE search_gap_details
  SET redacted_question = NULL, purged_at = now() WHERE status='resolved'
  AND text_purge_at <= now() AND redacted_question IS NOT NULL`. Idempotent
  by construction (the `WHERE` clause excludes already-purged rows).
- `aggregation.py` — summary counts (monitored searches, `no_material`
  count, missing-content rate, topics-with-open-gaps count, `Unclassified`
  rate, finalization health = pending-vs-classified ratio) and the ranked
  topic bar-chart dataset, both scoped to `origin='user'` only (criterion
  12) and a rolling window (`created_at >= now() - interval`).

## APIs

- `GET/PUT/DELETE /analytics/consent` (`require_user`) — status,
  idempotent acknowledge, withdraw.
- `GET /admin/analytics/summary` (`require_admin_role`) — the dashboard
  header numbers, `?days=30` default.
- `GET /admin/analytics/topics/{topic_key}/gaps` (`require_admin_role`,
  cursor pagination) — redacted question, dates, status, retest state.
- `POST /admin/analytics/gaps/{gap_id}/retests` (`require_admin_role`).
- `PATCH /admin/analytics/gaps/{gap_id}` (`require_admin_role`) — resolve
  only; rejects if the linked retest hasn't succeeded.

All typed Pydantic request/response models declared inline in their router
file (this repo's existing convention — no `schemas/` package exists
anywhere to fit into).

## Submission-path change

`AsyncChatRequest` (`backend/app/routers/async_chat.py`) gains
`submission_id: Optional[str] = None` (additive). `/submit` creates one
`origin='user'` occurrence per accepted request, after enqueue, only when
`user_id` is present and `analytics_consent` shows current-version,
non-withdrawn acknowledgment. A durable-write failure for a consented
account raises `503 analytics_unavailable` (mirrors the existing
`metering_unavailable` fail-closed shape) — for anyone else (guest,
non-consented account), occurrence creation is simply skipped, no error.

## Frontend

- `components/rhemata/consent-gate.tsx` — new blocking modal (styled like
  `LoginModal`'s overlay, no close/backdrop-dismiss). Mounts in
  `app/page.tsx` beside `LoginModal`/`BetaGate`; checks
  `GET /analytics/consent` whenever `accessToken` is set; blocks with the
  directive's exact copy until `PUT` succeeds; "Decline" calls `signOut()`.
  One component covers both "new signup" and "existing account, next
  login" cases — both are just "authenticated, no current consent yet."
- `components/admin/AnalyticsPanel.tsx` — new tab body: summary stat row,
  ranked horizontal bar chart with `no_material` segment (color +
  text-labeled, not color-only) plus an accessible `<table>` equivalent,
  topic-click-through gap list with Retest/Resolve buttons. Plain `fetch`
  + local state, same convention as `SourceQueuePanel.tsx` (no shared
  API-client library exists to reuse).
- `components/admin/AdminModal.tsx` — add `"analytics"` to `TopTab`, one
  `NAV_TABS` entry (`BarChart3` icon), one render branch. No other change
  to this file.

## Testing

Plain-script convention (`scripts/test_*.py`, `check()`/`AssertionError`,
no pytest — matches `scripts/test_quote_selection_gate.py`). Mocked Groq
for classifier tests; fake `Db`/cursor objects (same shape as that file's
`_CaptureDb`) for occurrence/finalizer tests — no real DB touched by any
test. Migration correctness verified by `scripts/apply_migration_093.py`
in dry-run mode only (schema/RLS/grant introspection against the live
schema, same as `apply_migration_090.py`'s pattern) — never `--apply`d
this session.

## Rollout checklist (Alex's attended gate — not executed here)

1. Review this spec + the diff.
2. `python3.12 scripts/apply_migration_093.py --apply` against Supabase,
   then re-run its verify pass on a fresh connection.
3. Set `ANALYTICS_HMAC_SECRET_V1` on both Railway services (`rhemata`,
   `answer-worker`) — a long random value, never logged.
4. Decide whether the finalizer runs as its own Railway service (polling
   loop) or a scheduled job; deploy accordingly. Nothing here auto-starts
   it.
5. Deploy backend + frontend.
6. Confirm the signup/login consent gate renders and blocks correctly in
   production for one real test account before wider beta exposure.
7. Decide the retention-purge job's own schedule (e.g. daily) and where it
   runs.
8. Revisit Assumption 4 above (server-side consent enforcement) if Alex
   wants defense-in-depth beyond the frontend gate.
