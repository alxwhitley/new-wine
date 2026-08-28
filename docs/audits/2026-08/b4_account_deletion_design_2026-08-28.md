# B4 — Account deletion design (architectural approval gate)

**Date:** 2026-08-28, Packet 4 (Task 4.2) of the back-to-back completion
queue. **Status: proposed, not approved. No implementation code has been
written.** This document is the required approval gate — Alex must approve
it before any code changes for account deletion begin.

Supersedes nothing in `docs/audits/2026-08/b4_account_deletion_scope_2026-08-19.md`'s
factual record, but corrects it where the live schema has moved since:
migration 090 (2026-08-19, same day, landed after that audit's live-DB
session) already changed 4 tables from `NO ACTION` to `SET NULL` with
`*_email` snapshot columns — re-verified live today via
`rhemata_readonly_analysis`, not assumed from the old file. Also folds in
migration 093 (search analytics — schema merged onto `main` in Packet 2 of
this same queue, not yet applied to production).

## 1. Full table inventory (verified live today)

### Auto-handled by Supabase's `auth.users` delete (no app code needed)

| Table | Column | Behavior |
|---|---|---|
| `conversations` (+`messages` via its own cascade) | `user_id` | CASCADE |
| `saved_words` | `user_id` | CASCADE |
| `study_pins` | `user_id` | CASCADE |
| `user_usage` | `user_id` | CASCADE |
| `user_roles` | `user_id` | CASCADE — if this account is an admin, their admin role is dropped with it (see open question 1) |
| `contributor_requests` | `user_id` | CASCADE |
| `deletion_requests` | `user_id` | CASCADE — the request row itself disappears; this is why a separate audit record is needed (Section 3) |
| `source_ingest_queue` | `submitted_by` | CASCADE |
| `analytics_consent` (migration 093, not yet applied) | `user_id` | CASCADE |
| `pastors_cards` | `user_id` | **SET NULL** (was `NO ACTION` on 2026-08-19; migration 090 fixed this same day) |
| `quotes` | `created_by`, `approved_by`, `revoked_by` | **SET NULL**, each with a companion `NOT NULL *_email` snapshot already captured at write time |
| `quote_source_revisions` | `captured_by` | **SET NULL** + email snapshot |
| `document_quote_clearance` | `cleared_by` | **SET NULL** + email snapshot |
| 8 Supabase-internal auth tables (`identities`, `sessions`, `mfa_factors`, etc.) | `user_id` | CASCADE, handled entirely by the Auth API call itself |

### Must be handled by app code BEFORE the Auth API call (still `NO ACTION` today — would block the delete)

| Table | Column | Nullable? |
|---|---|---|
| `user_roles` | `granted_by` | Yes |
| `contributor_requests` | `reviewed_by` | Yes |
| `quote_verification_log` | `submitted_by` | Yes |

All three are nullable and only matter if the account being deleted ever acted as an *admin* on someone else's row (granted a role, reviewed a contributor request, or submitted a quote-verification log entry) — the whole admin/build team to date is 2 accounts, so this is a small, cheap `UPDATE ... SET x = NULL WHERE x = :user_id` per table, done proactively.

### Not touched by any FK at all — must be handled explicitly

| Table | Why | Plan |
|---|---|---|
| `search_occurrences` / `search_gap_details` (migration 093) | Keyed by `subject_key` (an HMAC value), not a live FK to `auth.users` — the delete-user cascade cannot reach these | Reuse `search_analytics/consent.py::withdraw()` verbatim — it already does exactly this (deletes every occurrence/gap row for every subject key, current and retired, this account has ever held). Not forked, called directly. |
| `feedback.user_id` | Bare `uuid`, no FK constraint (`migrations/020_feedback.sql`), RLS already allows `NULL` for guest feedback | **Open question 2 below** — needs Alex's decision, not a silent default. |

### `answer_jobs`

Checked directly (`migrations/078_async_answer_path.sql`): no `user_id`/auth column at all. Out of scope — it's queue plumbing, not a durable per-user record.

## 2. Order of operations

1. Load the `pending` `deletion_requests` row (`id`, `user_id`, `email`).
2. **Idempotency guard:** call the Auth API to check whether `user_id` still resolves. If it doesn't (a retry after a prior run that succeeded but didn't finish recording), skip straight to step 6.
3. `UPDATE` the three `NO ACTION` actor columns (Section 1) to `NULL` wherever they equal this `user_id`.
4. Call `search_analytics.consent.withdraw(db, supabase, user_id)` if an `analytics_consent` row exists for this account (safe no-op otherwise).
5. Apply the approved `feedback.user_id` policy (open question 2).
6. Call Supabase's Admin API to delete the `auth.users` row. This is the one genuinely irreversible step. On failure (network/5xx/timeout): mark `deletion_requests.status = 'failed'` with a reason, leave everything else as already mutated (steps 3-5 are each independently idempotent and safe to re-run), and stop — this is the request's terminal-but-retryable state the queue's boundaries require, distinct from `resolved`.
7. On success, every CASCADE/SET NULL constraint in Section 1's first table fires atomically inside Postgres — no further app code needed for those rows, including `deletion_requests` itself, which is now gone.
8. **Reconciliation, not assumption:** re-query `conversations`, `messages`, `saved_words`, `study_pins`, `user_usage`, and `search_occurrences` directly for this `user_id`/subject keys and confirm zero rows; confirm the Auth API now reports the user not found. Any unexpected remaining row is a `failed` outcome, flagged for manual review — a successful Auth API call alone is never sufficient to call this resolved.
9. Write exactly one row to a new table, `deletion_audit_log` (Section 3), recording the outcome. This is the *only* record that survives — everything else described as "retained provenance" elsewhere in this repo (the `*_email` snapshots) already exists; nothing new is added beyond this one log row.

## 3. New table: `deletion_audit_log`

Needed because `deletion_requests` itself cascades away with the user (Section 1) — without this, there would be no queryable record that a deletion ever happened, which the 2026-08-19 audit already flagged as a real gap.

```sql
CREATE TABLE deletion_audit_log (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  original_request_id uuid NOT NULL,     -- no FK; deletion_requests row is gone by the time this is written
  deleted_user_id   uuid NOT NULL,       -- no FK, deliberately -- the account no longer exists
  email             text NOT NULL,       -- snapshot, captured before deletion
  requested_at      timestamptz NOT NULL,
  resolved_at       timestamptz NOT NULL,
  resolved_by       uuid NOT NULL REFERENCES auth.users(id), -- the admin who ran this
  outcome           text NOT NULL CHECK (outcome IN ('resolved', 'failed')),
  reconciliation    jsonb NOT NULL,      -- per-table row counts confirmed zero, for later audit
  failure_reason    text
);
```

RLS enabled, service-role-only (same standing pattern as every other
backend-internal table in this repo, e.g. migration 082's `quotes`
policies) — this table is never exposed to `anon`/`authenticated` roles or
any admin API route beyond a read for the Contributors tab's existing
"Account Deletion Requests" card, which now needs to read from here for
resolved history instead of (or alongside) the live `deletion_requests`
table for pending ones.

## 4. Retries, idempotency, failure states

- `deletion_requests.status` gains a fourth value: `'pending' | 'resolved' | 'failed'` (was `'pending' | 'resolved'`) — `'failed'` is the terminal-but-retryable state distinct from `'resolved'` the queue's boundaries require. An admin can re-trigger resolution on a `'failed'` request; the idempotency guard (step 2) and each step's own safe-to-repeat design make this safe.
- Steps 3, 4, 5 are naturally idempotent (an `UPDATE ... WHERE` matching zero rows, or a `DELETE` matching zero rows, is a safe no-op).
- Step 6 (the Auth API call) is the only step that isn't naturally repeatable — the idempotency guard in step 2 is what makes a *second* resolve attempt safe after a first one that actually succeeded at the Auth layer but failed before recording the outcome.

## 5. Test plan (after this design is approved, before it ships)

Using **one designated test account** (Alex creates and names it — the queue's own boundary requires this, not a description of an aspirational future account):

1. Populate it with at least one row in every CASCADE/SET NULL/explicit-handling table above (a conversation + message, a saved word, a study pin, a `user_roles` grant, and — if practical — an analytics-consented search occurrence).
2. Submit a deletion request, have an admin resolve it, and directly query (not assume) every table in Section 1 to confirm the exact documented disposition — gone, nulled-with-email-snapshot, or unaffected.
3. Confirm a **different, real existing user's** data is completely unchanged (a control, checked by direct query, not by absence of an error).
4. Confirm calling resolve a second time on the same (now-completed) request is a safe no-op and doesn't error or double-log.
5. Update the account-settings UI copy to say exactly what happens and on what timeline (Section 6) — never "your account has been deleted" if the real behavior is "your request was submitted and an admin will process it."

## 6. UI copy

Checked directly (`frontend/components/admin/AdminModal.tsx:1770-1814` — this is the account-settings modal every signed-in user sees, not an admin-only surface despite the file's name). Mostly already accurate: "This sends a request to remove your account and data... " correctly describes a request, not immediate deletion, and matches this design's admin-gated posture.

**One real mismatch found, to be fixed as part of this task, not held open as a question:** both the confirm dialog and the "sent" state claim *"We'll follow up by email to confirm before anything is deleted."* **No email-sending capability exists anywhere in this backend** (grepped clean — no SMTP/Resend/SendGrid/Postmark, nothing). This claim is false today regardless of this design. Building a real email-confirmation flow (sender, templates, confirmation token/link, expiry) is a genuinely separate, larger scope item, not something this packet's non-goals ("no broad refactor") permit — so the fix here is to correct the copy to describe what actually happens (an admin reviews and resolves the request; no email is sent), not to build email as a side effect of this task.

## Open questions — Alex's decision required before implementation

1. **Admin self-deletion.** An admin's own `user_roles` row cascades away silently as part of this flow — they'd lose admin status the moment their account is deleted (unsurprising, since the account no longer exists, but worth confirming rather than assuming). Should this be allowed as-is, or should an admin account be blocked from self-service deletion (routed to a separate manual process instead)?
2. **`feedback.user_id`** has no FK and won't be touched by any cascade — after deletion it's a dangling UUID with nothing left to resolve it to. Leave it as-is (it's not personally identifying once orphaned), or proactively `UPDATE feedback SET user_id = NULL WHERE user_id = :deleted_id` as part of this same flow?
3. **Trigger point.** This design keeps the existing pattern: a user's own request only starts the process once an admin resolves it (matching the current manual-gate flow, not a new automatic/self-service immediate deletion). Confirm this is still the right posture, or should resolution happen automatically/immediately without an admin step?

## Non-goals (explicit)

No production database write, migration, or code change happens as part of writing this document. No new analytics vendor. No change to how `analytics_consent`/`search_occurrences` collection itself works — only how it's purged on deletion. No change to the Contributors tab beyond pointing its history view at the new audit table.
