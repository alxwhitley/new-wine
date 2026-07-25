# Account panel redesign

## Status

Approved. Ready for implementation planning.

## Problem

The sidebar's "Your profile" panel (`frontend/components/rhemata/sidebar.tsx:501-550`)
holds exactly two things: an editable display-name field and a read-only role
label. Everything else user-related is scattered across a separate dropdown
menu on the same footer trigger: weekly usage (a ring icon), "Become a
contributor" (opens its own sheet), "Admin panel" (opens `AdminModal`), and
"Log out". The panel doesn't reflect what a user's account actually contains,
and the dropdown-plus-sheet split adds a click and a second UI pattern for no
reason.

## Goals

- Consolidate identity, usage, contributor status, and account actions into
  one panel.
- Remove the now-redundant dropdown menu — the footer identity button opens
  the panel directly.
- Add a delete-account entry point, stubbed as a logged request rather than
  real cascading deletion (which doesn't exist anywhere in the backend today).
- Change the panel's container from a slide-in `Sheet` to a centered `Dialog`
  popup, matching the mechanism `AdminModal` already uses.

## Non-goals

- Real account/data deletion (cascading across `conversations`, `saved_words`,
  `pastors_notes` cards, `user_roles`, the Supabase auth user). This becomes
  its own future spec once the deletion-request stub surfaces real demand.
- Study preferences (default translation, etc.) — no such settings exist
  anywhere in the app yet; out of scope here.
- Any billing/plan tier concept — the app has a single flat weekly limit
  (default 50), no paid tiers, so there's nothing to surface beyond current
  usage.
- A contributor "my notes" management page — doesn't exist today, and this
  redesign doesn't invent one. The contributor-status section doesn't link to
  it.

## Design

### Rename

"Your profile" → **"Your account"**. The panel now holds more than a
display-name editor; the title should match its contents.

### Container: Dialog, not Sheet

Replace `Sheet`/`SheetContent`/`SheetHeader`/`SheetTitle`/`SheetDescription`/
`SheetFooter` (the settings sheet only — the contributor-request sheet is
unrelated and stays a `Sheet`) with `Dialog`/`DialogContent`/`DialogHeader`/
`DialogTitle`/`DialogDescription`/`DialogFooter` from `@/components/ui/dialog`,
the same import pattern `AdminModal.tsx` uses for its outer shell.

Sizing stays the base `Dialog` default (compact, centered) — **not** the
admin console's `max-w-5xl h-[85vh]` two-column layout, which is sized for a
whole admin console, not a 4-section account panel.

### Content, in order

1. **Identity** — Display name (editable input, existing behavior unchanged)
   + email (read-only, new — pulled from the existing `user` prop already
   passed into `Sidebar`; no new fetch).
2. **Usage** — e.g. "12 of 50 questions this week". Reuses the `weeklyUsage`
   prop already piped into `Sidebar` (today only rendered as the footer
   `UsageRing`); no new data required. Simple text, optionally paired with
   the existing ring — not a second, different usage widget.
3. **Contributor status** — replaces the bare "Role: {role}" text:
   - `role === "user"`: short description line + "Become a contributor"
     button. Opens the *existing* contributor-request `Sheet` unchanged —
     only the trigger location moves, from the old dropdown into this panel.
   - `role === "contributor"`: a "Contributor" badge/label. No link out —
     there's no notes-management page to link to.
   - `role === "admin"`: an "Admin" badge/label + "Open admin panel" button
     that calls the existing `setAdminOpen(true)`, opening `AdminModal`
     unchanged.
4. **Account actions** — Sign out (moved in from the old dropdown, same
   `onSignOut` handler) + Delete account (new — see below).

### Interaction change: footer trigger

The footer identity button in `Sidebar` stops opening a `DropdownMenu` and
calls `handleOpenAccount` (renamed from `handleOpenSettings`) directly, for
every role. The `DropdownMenu`/`DropdownMenuTrigger`/`DropdownMenuContent`
wrapper is removed entirely — every destination it held (Profile, Become a
contributor, Admin panel, Log out) now lives inside the account panel.

### Delete account (stub)

Real deletion is out of scope (see Non-goals). The stub:

- Account panel's "Delete account" button opens a confirm step (new local
  state: `deleteConfirmOpen`, `deleteStatus: "idle" | "loading" | "sent" |
  "error"` — mirrors the existing `requestStatus` pattern already used for
  the contributor-request sheet).
- On confirm, calls a new `POST /account/delete-request` (authenticated).
  Inserts a row into a new `deletion_requests` table: `id`, `user_id`,
  `email`, `created_at`, `status` (`pending`/`resolved`), `resolved_at`.
  Returns 400 if a pending request already exists for that user (same
  pattern as the existing contributor-request 400 case in
  `pastors_notes.py`).
- `AdminModal` gets a small new "Deletion requests" list, reusing the
  existing pending-list UI pattern from contributor requests, so requests
  are actually visible for manual follow-up rather than sitting unseen in a
  table.

## Non-goals recap: what doesn't change

- `useUserRole` hook — already returns `role` and `displayName`, nothing new
  needed.
- `weeklyUsage` prop plumbing — already passed into `Sidebar`.
- `/pastors-notes/me` GET/PATCH — display name still goes through these
  unchanged.
- `AdminModal` itself — unchanged; the account panel just gains a button
  that opens it.
- The contributor-request `Sheet` — unchanged flow, only its trigger moves.

## Open implementation questions

- Exact backend location for `POST /account/delete-request` — either added
  to `backend/app/routers/pastors_notes.py` alongside the similar
  contributor-request endpoint, or a new small router if account-scoped
  routes should start living separately. Left for the implementation plan
  to decide.
