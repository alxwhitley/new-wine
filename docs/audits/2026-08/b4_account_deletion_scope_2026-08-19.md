# B4 — Account deletion scope inventory (read-only)

**Date:** 2026-08-19. **Method:** repo read (routes + migrations) + one
read-only live-DB session via `rhemata_readonly_analysis`
(`backend/app/.env.readonly-analysis`). No writes, no schema changes.
This is a scope inventory for a future implementation session — no
design decision is made here.

## 1. Current stub behavior (confirmed live in code)

`backend/app/routers/account.py`, three routes:

- `POST /delete-request` (any authenticated user) — inserts one row into
  `deletion_requests` (`user_id`, `email`, `status='pending'`). Blocks a
  second pending request per user. **Deletes nothing.**
- `GET /delete-requests` (admin) — lists pending rows for the
  Contributors tab's "Account Deletion Requests" card.
- `POST /delete-requests/{id}/resolve` (admin) — flips `status` to
  `resolved` with a timestamp. **Still deletes nothing** — the docstring
  says so explicitly ("that still happens manually, outside this
  endpoint").

No code path anywhere in the repo performs a cascading delete of user
data or calls the Supabase Admin API to delete an `auth.users` row.

## 2. Full table inventory — FK relationship to `auth.users`

Queried live via `pg_constraint`/`pg_class`/`pg_attribute` (not
`information_schema`, which didn't resolve cross-schema refs cleanly
for this role). All FKs in `public` that reference `auth.users`:

### CASCADE on delete (auth.users row deletion auto-removes these)

| Table | Column | Note |
|---|---|---|
| `conversations` | `user_id` | Chat history root. `messages` cascades from `conversations` (`messages_conversation_id_fkey` → CASCADE), so deleting `conversations` rows also removes `messages`. |
| `saved_words` | `user_id` | |
| `study_pins` | `user_id` | |
| `user_usage` | `user_id` | Weekly query-limit counter (PK is `user_id` itself). |
| `user_roles` | `user_id` | **Caution:** deleting an admin's own auth row would silently remove their admin role via cascade — not obviously desirable, flagged as an open question below. |
| `contributor_requests` | `user_id` | |
| `deletion_requests` | `user_id` | The request row itself cascades away too — an implementation needs to snapshot audit info (email, timestamp) before the cascade fires, or the "a deletion happened" record disappears with the user. |
| `source_ingest_queue` | `submitted_by` | Corpus-pipeline row, not personal data — but still cascades, meaning a contributor's submitted ingest-queue rows vanish if they're deleted. |
| Supabase-internal: `identities`, `sessions`, `mfa_factors`, `oauth_authorizations`, `oauth_consents`, `one_time_tokens`, `webauthn_challenges`, `webauthn_credentials` | `user_id` | Auth-internal, handled automatically if the Supabase Admin API deletes the `auth.users` row. Not app-owned. |

### NO ACTION on delete (auth.users row deletion is BLOCKED while these exist — real structural finding, not just a gap)

| Table | Column | Note |
|---|---|---|
| `pastors_cards` | `user_id` | `user_id NOT NULL REFERENCES auth.users(id)` — no `ON DELETE` clause at all (defaults to `NO ACTION`). Deleting a user with a pastors_cards row would raise a live FK-violation error. |
| `quotes` | `created_by`, `approved_by`, `revoked_by` | `created_by` is `NOT NULL`; `approved_by` is nullable but `CHECK (status <> 'approved' OR approved_by IS NOT NULL)` — can't null it out on an approved quote without also reverting its status. |
| `quote_source_revisions` | `captured_by` | `NOT NULL`. |
| `document_quote_clearance` | `cleared_by` | `NOT NULL`. |
| `quote_verification_log` | `submitted_by` | Nullable — the one actor column that *can* just be set to NULL without violating a CHECK. |
| `user_roles` | `granted_by` | Nullable (who granted this role, not whose role it is). |
| `contributor_requests` | `reviewed_by` | Nullable. |

**Live finding, not hypothetical:** exactly **2 distinct auth users**
are referenced across `quotes.created_by/approved_by/revoked_by`,
`quote_source_revisions.captured_by`, and
`quote_verification_log.submitted_by` (confirmed via
`COUNT(DISTINCT ...)` — this is the whole admin/build team to date,
823 `quotes` rows, 823 `quote_source_revisions` rows, 1184
`quote_verification_log` rows). **If either of those 2 accounts ever
submitted a `/delete-request`, the current schema would refuse to
actually delete their `auth.users` row** — not "the app doesn't do it
yet," but "the database itself raises a foreign-key violation" — until
an implementation either reassigns/nulls the non-nullable actor columns
or the record is redesigned to not require a live user FK (e.g. a
snapshot `created_by_email` instead of a live reference).

### Not inventoried — read-only role has no `SELECT` grant

`rhemata_readonly_analysis` returned "permission denied" on
`conversations`, `messages`, `saved_words`, `study_pins`, `user_usage`,
`user_daily_usage`, `pastors_cards`, `user_roles`,
`contributor_requests`, `deletion_requests`, `feedback`,
`guest_sessions`, `document_quote_clearance` — this role is grant-scoped
away from user-PII tables (a deliberate privacy boundary on the role
itself, worth knowing rather than assuming it's an oversight). **Row
counts for these tables were not obtainable through this read-only
audit** — an implementation session would need the service-role
connection (attended, per the Session Routing hard rule on DB access)
to get real counts, or could query via the backend's own ORM/RPC layer
under a real session.

`feedback.user_id` has **no FK constraint at all** (bare `uuid` column,
confirmed in `migrations/020_feedback.sql`) — RLS explicitly allows
`user_id IS NULL` for guest feedback. A deleted user's feedback rows
would neither cascade nor block; they'd just retain a now-dangling
`user_id` with no referential integrity either way.

## 3. Supabase `auth.users` row itself

Separate mechanism from every table above: even after all `public`
schema data is handled, the actual `auth.users` row requires a call to
Supabase's Admin API (`auth.admin.deleteUser`) — not a `DELETE` this
codebase can issue via the anon/service Postgres role in the normal
app path. No code in this repo calls it today. This is the step that
would trigger the CASCADE tables above automatically, and be BLOCKED by
the NO ACTION tables above if not handled first.

## 4. Open questions for the eventual implementation

- **Order of operations**: NO ACTION tables must be resolved (reassign
  actor to a system/placeholder account, or redesign to a snapshot
  field) *before* calling the Admin API delete, or the call fails.
- **Admin self-deletion**: `user_roles` cascading away silently removes
  admin status — is that fine, or should admin accounts be explicitly
  blocked from self-service deletion (route through a different, manual
  process)?
- **Audit trail after deletion**: `deletion_requests` cascades away with
  the user it's about — there will be no queryable record that a
  deletion ever happened once it completes, unless the row is snapshotted
  elsewhere first (e.g. copy email + timestamp to a separate log before
  the cascade).
- **Corpus/product-integrity data with a real user pointer** (`quotes`,
  `quote_source_revisions`, `quote_verification_log`,
  `document_quote_clearance`, `pastors_cards`): these represent
  actions on shared product state, not personal data — likely want
  reassignment to a sentinel "deleted user" account or a snapshot field
  (similar in spirit to the sentinel-source pattern in CLAUDE.md
  Invariant 3), not a hard delete of the row itself. This needs an
  explicit design decision, not an inferred default.
- **Soft-delete vs hard-delete grace period**: not addressed anywhere
  in code today — `deletion_requests.status` only has `pending`/
  `resolved`, no concept of a delay window.
- **`user_daily_usage`** (migration 014) has `user_id UUID NOT NULL` with
  **no FK to `auth.users` at all** — orphaned rows are silently possible
  already; worth deciding whether this table is even still live
  (`user_usage`, migration 039, looks like its successor) before
  designing deletion logic for it.
- Real row counts for the CASCADE/PII tables (conversations, messages,
  saved_words, etc.) still need to be pulled under an attended
  session with proper table grants — not available from this
  read-only pass.
