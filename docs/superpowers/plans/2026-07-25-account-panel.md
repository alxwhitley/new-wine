# Account Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sidebar's bare-bones "Your profile" `Sheet` (display name + role only) with a single "Your account" `Dialog` popup holding identity, usage, contributor status, and account actions — including a stubbed delete-account request flow.

**Architecture:** Frontend: `frontend/components/rhemata/sidebar.tsx` swaps its settings `Sheet` for a `Dialog` (same mechanism `AdminModal.tsx` already uses) and removes the now-redundant `DropdownMenu` wrapper around the footer identity button. Backend: one new table (`deletion_requests`) and one new small router (`account.py`) log a deletion request for manual admin follow-up — no cascading deletion happens anywhere in this plan. `AdminModal.tsx` gets a third card in its existing "Contributors" tab to surface pending deletion requests.

**Tech Stack:** Next.js 16 / React 19 / Tailwind 4 (frontend), FastAPI / Python 3.9 / Supabase Postgres (backend). No test runner exists in either stack — this repo verifies backend changes with standalone scripts run against a real Supabase Postgres connection and, for authenticated endpoints, the live production API (see `scripts/test_pastors_rls.py` and `scripts/verify_metering_live.py` for the established pattern this plan follows -- note that script was renamed out of the `test_*.py` namespace and given an `--apply` guard on 2026-08-31; a new production-touching verification script should copy the CURRENT shape, not the unguarded one this plan was written against).

## Global Constraints

- Python 3.9 syntax only in backend code — `Optional[str]`, never `str | None` (CLAUDE.md invariant #1).
- No semicolons inside `--` SQL comments in migrations; verify a new migration landed with `SELECT to_regclass('public.<table>')` on a **fresh** connection (CLAUDE.md invariant #9).
- **Backend deploys to Railway only on push to main. There is no local backend** (`ARCHITECTURE.md`). Backend route code cannot be run locally — only syntax-checked before deploy.
- `frontend/.env.local`'s `NEXT_PUBLIC_API_URL` already points at production (`https://rhemata-production.up.railway.app`), even under local `npm run dev`. This means the new `/account/*` endpoints must be deployed (Task 6) before any frontend piece that calls them can be exercised live in a browser.
- This is a **stub**, not real deletion: no cascading delete of `conversations`, `saved_words`, `pastors_cards`, `user_roles`, or the Supabase auth user. A deletion request is logged for manual follow-up only (per `docs/superpowers/specs/2026-07-25-account-panel-design.md`, Non-goals).
- Follow existing Tailwind semantic classes exactly as `sidebar.tsx`/`AdminModal.tsx` already do (`text-muted-foreground`, `border-border`, etc.) — no hardcoded hex, per `DESIGN.md`.
- Pushing to `main` triggers a live Railway + Vercel deploy. Task 6's push step requires explicit confirmation before running — it is not a routine reversible action.

---

### Task 1: Migration — `deletion_requests` table + RLS

**Files:**
- Create: `migrations/068_deletion_requests.sql`
- Create: `scripts/test_deletion_requests_migration.py`

**Interfaces:**
- Produces: Postgres table `public.deletion_requests(id uuid PK, user_id uuid FK auth.users, email text, status text CHECK IN ('pending','resolved'), created_at timestamptz, resolved_at timestamptz)`, a unique partial index enforcing at most one pending request per user, and 3 RLS policies (own-row read, own-row insert, service-role full access) — mirrors `contributor_requests` from migration `038_pastors_notes.sql` exactly.

- [ ] **Step 1: Write the migration**

```sql
-- 068_deletion_requests.sql
-- Account deletion requests -- stub for the account panel's "Delete account"
-- action. Logs a request for manual admin follow-up. Does NOT delete any
-- data itself -- real cascading deletion is a future migration.
--
-- Backend uses SUPABASE_SERVICE_KEY (service_role, BYPASSRLS) for all writes.
-- RLS is defense-in-depth against anon-key access.


-- -- 1. deletion_requests ----------------------------------------------------

CREATE TABLE IF NOT EXISTS deletion_requests (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  email       text        NOT NULL,
  status      text        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'resolved')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

-- At most one pending request per user at a time
CREATE UNIQUE INDEX IF NOT EXISTS deletion_requests_one_pending_idx
  ON deletion_requests (user_id)
  WHERE status = 'pending';


-- -- 2. RLS --------------------------------------------------------------------
--
-- Pattern used throughout this project (see migration 038):
--   - service_role bypass covers all backend writes
--   - authenticated policies scope to auth.uid()
--   - anon role has no matching policy -- denied by default

ALTER TABLE deletion_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "deletion_requests: own rows read"
  ON deletion_requests FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "deletion_requests: own row insert"
  ON deletion_requests FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "deletion_requests: service role full access"
  ON deletion_requests FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
```

- [ ] **Step 2: Write the verification script**

```python
#!/usr/bin/env python3
"""
test_deletion_requests_migration.py -- Apply and verify migration 068
(deletion_requests table + RLS).

Requires in backend/app/.env (or environment):
  SUPABASE_DB_URL      -- direct Postgres connection (service role)
  SUPABASE_URL         -- project URL
  SUPABASE_ANON_KEY    -- public anon key (or NEXT_PUBLIC_SUPABASE_ANON_KEY)
  SUPABASE_SERVICE_KEY -- service role key (for auth.admin.generate_link)

Usage:
  python3 scripts/test_deletion_requests_migration.py
"""

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

# Real, already-registered account used only to obtain a genuine auth.users id
# for the "authenticated user can insert their own row" RLS check below --
# same convention scripts/verify_metering_live.py already uses. A freshly-generated
# uuid4() cannot be used there: deletion_requests.user_id has a real FK to
# auth.users(id), and unlike the user_a setup insert a few lines below (which
# bypasses FK checks via session_replication_role = replica), the RLS-scoped
# insert runs as a normal role and WILL hit that FK before RLS is even
# evaluated -- a synthetic id fails with ForeignKeyViolation every time, in
# every environment, regardless of what the RLS policy itself would allow.
TEST_EMAIL = "creative@clf-church.com"


def get_db_conn():
    import psycopg2
    from urllib.parse import urlparse, unquote

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def get_anon_client():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        sys.exit(1)
    return create_client(url, key)


def get_real_user_id(service_db):
    # type: (object) -> str
    """Resolve a genuine auth.users id for TEST_EMAIL via the admin API.
    TEST_EMAIL is a real, already-registered account in this project, so
    this reuses that existing auth.users row. Note: if TEST_EMAIL did NOT
    already exist, generate_link(type="magiclink") would silently create
    one -- do not point this script at a different Supabase project without
    confirming TEST_EMAIL already exists there, or it will leave behind an
    unconfirmed auth.users row this script never cleans up."""
    link = service_db.auth.admin.generate_link({"type": "magiclink", "email": TEST_EMAIL})
    return link.user.id


_pass = 0
_fail = 0


def check(label, passed):
    # type: (str, bool) -> None
    global _pass, _fail
    tag = "PASS" if passed else "FAIL"
    print("  [%s] %s" % (tag, label))
    if passed:
        _pass += 1
    else:
        _fail += 1


def anon_insert_blocked(anon, table, payload):
    # type: (object, str, dict) -> bool
    try:
        resp = anon.table(table).insert(payload).execute()
        return not getattr(resp, "data", None)
    except Exception:
        return True


def rls_insert_as_user(conn, user_id, email):
    # type: (object, str, str) -> bool
    """Attempt an INSERT as an authenticated, non-service user. Always
    rolls back -- this only checks whether RLS would have allowed it."""
    claims = json.dumps({"sub": user_id, "role": "authenticated"})
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE authenticated")
        cur.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            (claims,),
        )
        cur.execute(
            "INSERT INTO deletion_requests (user_id, email) VALUES (%s, %s) RETURNING id",
            (user_id, email),
        )
        row = cur.fetchone()
        return row is not None
    except Exception:
        return False
    finally:
        cur.execute("ROLLBACK")
        cur.close()


def main():
    print("\nAccount deletion requests -- migration 068 verification")
    print("=" * 50)

    conn = get_db_conn()
    cur = conn.cursor()

    # -- Apply migration if not already applied ---------------------------------
    cur.execute("SELECT to_regclass('public.deletion_requests')")
    already_applied = cur.fetchone()[0] is not None
    if already_applied:
        print("Table deletion_requests already exists -- skipping apply")
    else:
        migration_sql = (Path(__file__).resolve().parent.parent / "migrations" / "068_deletion_requests.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")

    # -- Fresh connection: confirm the table is really there ---------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()
    cur2.execute("SELECT to_regclass('public.deletion_requests')")
    exists = cur2.fetchone()[0] is not None
    check("deletion_requests exists (fresh connection)", exists)

    cur2.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'deletion_requests'")
    rls_enabled = cur2.fetchone()[0]
    check("RLS enabled on deletion_requests", rls_enabled is True)

    cur2.execute("SELECT policyname FROM pg_policies WHERE tablename = 'deletion_requests'")
    policies = {row[0] for row in cur2.fetchall()}
    expected = {
        "deletion_requests: own rows read",
        "deletion_requests: own row insert",
        "deletion_requests: service role full access",
    }
    check("all 3 RLS policies present", expected.issubset(policies))
    cur2.close()
    conn2.close()

    # -- RLS behavior checks -------------------------------------------------------
    from supabase import create_client
    service_db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    anon = get_anon_client()
    user_a = str(uuid.uuid4())
    user_b = get_real_user_id(service_db)

    # Idempotency: a prior run may have left a pending row for user_b if it
    # crashed between insert and cleanup.
    cur.execute("DELETE FROM deletion_requests WHERE user_id = %s", (user_b,))
    conn.commit()

    cur.execute("SET session_replication_role = replica")
    cur.execute(
        "INSERT INTO deletion_requests (user_id, email) VALUES (%s, %s)",
        (user_a, "test-a@example.com"),
    )
    cur.execute("SET session_replication_role = DEFAULT")
    conn.commit()

    try:
        blocked = anon_insert_blocked(
            anon, "deletion_requests",
            {"user_id": str(uuid.uuid4()), "email": "anon@example.com"},
        )
        check("anon cannot INSERT into deletion_requests", blocked)

        inserted = rls_insert_as_user(conn, user_b, "test-b@example.com")
        check("authenticated user CAN insert their own deletion_requests row", inserted)

        rows = anon.table("deletion_requests").select("id").eq("user_id", user_a).execute()
        check("anon cannot SELECT deletion_requests rows", len(getattr(rows, "data", []) or []) == 0)
    finally:
        cur.execute("SET session_replication_role = replica")
        cur.execute("DELETE FROM deletion_requests WHERE user_id IN (%s, %s)", (user_a, user_b))
        cur.execute("SET session_replication_role = DEFAULT")
        conn.commit()

    cur.close()
    conn.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the verification script**

Run: `python3 scripts/test_deletion_requests_migration.py`
Expected: `6/6 checks passed` (table exists, RLS enabled, 3 policies present, anon insert blocked, authenticated own-row insert allowed, anon select blocked). Exit code 0.

- [ ] **Step 4: Commit**

```bash
git add migrations/068_deletion_requests.sql scripts/test_deletion_requests_migration.py
git commit -m "Add deletion_requests table + RLS for account-deletion stub"
```

---

### Task 2: Backend — `account.py` router

**Files:**
- Create: `backend/app/routers/account.py`
- Modify: `backend/app/main.py:25,35` (import + register)

**Interfaces:**
- Consumes: `deletion_requests` table (Task 1); `require_user`, `require_admin_role` from `app.auth`; `get_supabase` from `app.db.supabase`; the existing `get_user_emails` RPC (migration `041_pastors_notes_approval.sql`, already deployed).
- Produces:
  - `POST /account/delete-request` (any authenticated user) → `200 {"success": true}` | `400 {"detail": "You already have a pending deletion request"}`
  - `GET /account/delete-requests` (admin only) → `200 [{"id": str, "user_id": str, "email": str, "created_at": str}, ...]`
  - `POST /account/delete-requests/{request_id}/resolve` (admin only) → `200 {"success": true}` | `404` | `400 {"detail": "Request is not pending"}`

- [ ] **Step 1: Write the router**

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin_role, require_user
from app.db.supabase import get_supabase

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/delete-request")
async def submit_delete_request(user_id: str = Depends(require_user)):
    """Any authenticated user -- request account deletion. Logs the request
    for manual admin follow-up; does not delete anything itself."""
    db = get_supabase()

    existing = (
        db.table("deletion_requests")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending deletion request",
        )

    email = ""
    email_result = db.rpc("get_user_emails", {"user_ids": [user_id]}).execute()
    if email_result.data:
        email = email_result.data[0].get("email") or ""

    db.table("deletion_requests").insert({
        "user_id": user_id,
        "email": email,
        "status": "pending",
    }).execute()

    logger.info("Deletion request submitted: user_id=%s", user_id)
    return {"success": True}


@router.get("/delete-requests")
async def list_delete_requests(admin_id: str = Depends(require_admin_role)):
    """Admin only -- list all pending account deletion requests."""
    db = get_supabase()
    result = (
        db.table("deletion_requests")
        .select("id, user_id, email, created_at")
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    return result.data or []


@router.post("/delete-requests/{request_id}/resolve")
async def resolve_delete_request(
    request_id: str,
    admin_id: str = Depends(require_admin_role),
):
    """Admin only -- mark a deletion request resolved. Does not delete any
    data -- that still happens manually, outside this endpoint."""
    db = get_supabase()

    existing = (
        db.table("deletion_requests")
        .select("id, status")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")
    if existing.data[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request is not pending")

    db.table("deletion_requests").update({
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", request_id).execute()

    logger.info("Deletion request resolved: request_id=%s by admin=%s", request_id, admin_id)
    return {"success": True}
```

- [ ] **Step 2: Register the router in `main.py`**

Modify `backend/app/main.py:25`:

```python
from app.routers import chat, search, document, ingest, study, admin, feedback, library, pastors_notes, usage, account
```

Modify `backend/app/main.py:35` (add after the existing `usage` line):

```python
app.include_router(usage.router, prefix="/usage", tags=["usage"])
app.include_router(account.router, prefix="/account", tags=["account"])
```

- [ ] **Step 3: Syntax-check (no local backend exists to run it against)**

Run: `python3 -m py_compile backend/app/routers/account.py backend/app/main.py`
Expected: no output, exit code 0. This only catches syntax errors — it does not execute the module, so it will not catch a missing/wrong import (the exact landmine documented in `ARCHITECTURE.md`: "A missing fastapi import → `NameError` → uvicorn never binds → every route in that file 404s"). Full behavioral verification happens in Task 6, after this is deployed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/account.py backend/app/main.py
git commit -m "Add /account router: delete-request stub + admin list/resolve"
```

---

### Task 3: Frontend — account `Dialog` shell (Identity, Usage, Contributor status, Sign out)

Replaces the settings `Sheet` and removes the `DropdownMenu` wrapper. Delete-account (Task 4) and the admin-side deletion-requests list (Task 5) are separate tasks because they depend on Task 2 being deployed to behave correctly — everything in this task works today, against already-deployed endpoints.

**Files:**
- Modify: `frontend/components/rhemata/sidebar.tsx`

**Interfaces:**
- Consumes: existing `useUserRole()` (`role`, `displayName`, `updateDisplayName`), existing props (`user`, `accessToken`, `weeklyUsage`, `onSignOut`), existing `handleOpenContributor()`, existing `setAdminOpen`.
- Produces: `accountOpen` / `setAccountOpen` state, `handleOpenAccount()` (replaces `handleOpenSettings`), the account `Dialog` JSX block that Task 4 extends with a delete-account section.

- [ ] **Step 1: Update imports**

Replace `frontend/components/rhemata/sidebar.tsx:1-32`:

```tsx
"use client";

import { useState, useEffect } from "react";
import { Plus, LogIn, MoreHorizontal, X, MessageSquare, Compass, BookOpen, Loader2, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useUserRole } from "@/hooks/useUserRole";
import { UsageRing } from "@/components/rhemata/usage-ring";
import { AdminModal } from "@/components/admin/AdminModal";
import { FooterNav } from "@/components/marketing/footer-nav";
import { isFullNavEnabled } from "@/lib/chat-only-beta-flag";
import type { Conversation } from "@/hooks/useConversations";
import type { User } from "@supabase/supabase-js";
```

Note: `AlertDialog*` imports are added here so Task 3 only touches the import block once. They stay unused until Task 4 wires the delete-account confirm dialog — this is harmless: `eslint-config-next`'s `@typescript-eslint/no-unused-vars` is set to `warn`, not `error`, and this repo's bare `"lint": "eslint"` script doesn't pass `--max-warnings 0`, so an unused import produces a warning, not a failing lint run.

- [ ] **Step 2: Rename settings state and update `handleOpenAccount`**

Replace `frontend/components/rhemata/sidebar.tsx:114-117`:

```tsx
  // Account dialog
  const [accountOpen, setAccountOpen] = useState(false);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [settingsStatus, setSettingsStatus] = useState<"idle" | "loading" | "saved" | "error">("idle");
```

Replace `frontend/components/rhemata/sidebar.tsx:174-178`:

```tsx
  function handleOpenAccount() {
    setEditDisplayName(displayName ?? "");
    setSettingsStatus("idle");
    setAccountOpen(true);
  }
```

- [ ] **Step 3: Replace the footer dropdown with a direct-open button**

Replace `frontend/components/rhemata/sidebar.tsx:392-437` (the `{isLoggedIn ? (...) : (...)}` block inside the footer `<div>`):

```tsx
        {isLoggedIn ? (
          <button
            onClick={handleOpenAccount}
            className="flex w-full items-center gap-3 rounded-md px-2 py-2 hover:bg-accent transition-colors text-left"
          >
            {weeklyUsage && (
              <UsageRing used={weeklyUsage.used} limit={weeklyUsage.limit} />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
                {displayName ?? user?.email ?? ""}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {user?.email ?? ""}
              </p>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        ) : (
          <Button size="sm" className="w-full" onClick={onSignInClick}>
            Become a test user
          </Button>
        )}
```

This removes the only usages of `DropdownMenu`, `DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuSeparator`, `DropdownMenuTrigger` — their import block (original lines 20-26) was already dropped in Step 1.

- [ ] **Step 4: Replace the settings `Sheet` with the account `Dialog`**

Replace `frontend/components/rhemata/sidebar.tsx:500-550` (the `{/* Settings sheet */}` block):

```tsx
      {/* Account dialog */}
      <Dialog open={accountOpen} onOpenChange={setAccountOpen}>
        <DialogContent className="flex flex-col gap-0 max-w-md">
          <DialogHeader>
            <DialogTitle>Your account</DialogTitle>
            <DialogDescription>
              Manage your identity, usage, and contributor status.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-5 px-6 pb-2">
            {/* Identity */}
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <p className="text-xs text-muted-foreground">Display name</p>
                <Input
                  value={editDisplayName}
                  onChange={(e) => {
                    setEditDisplayName(e.target.value);
                    setSettingsStatus("idle");
                  }}
                  placeholder="Your name"
                  maxLength={100}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <p className="text-xs text-muted-foreground">Email</p>
                <p className="text-sm text-foreground">{user?.email ?? ""}</p>
              </div>
              {settingsStatus === "saved" && (
                <p className="text-xs text-muted-foreground">Saved.</p>
              )}
              {settingsStatus === "error" && (
                <p className="text-xs text-destructive">Something went wrong. Please try again.</p>
              )}
              <Button
                onClick={handleSaveDisplayName}
                disabled={settingsStatus === "loading" || !editDisplayName.trim()}
                size="sm"
                className="self-start"
              >
                {settingsStatus === "loading" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Save name"
                )}
              </Button>
            </div>

            <Separator />

            {/* Usage */}
            {weeklyUsage && (
              <>
                <div className="flex flex-col gap-1.5">
                  <p className="text-xs text-muted-foreground">Usage</p>
                  <p className="text-sm text-foreground">
                    {weeklyUsage.used} of {weeklyUsage.limit} questions used this week
                  </p>
                </div>
                <Separator />
              </>
            )}

            {/* Contributor status */}
            <div className="flex flex-col gap-2">
              <p className="text-xs text-muted-foreground">Contributor status</p>
              {userRole === "admin" && (
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">Admin</Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setAccountOpen(false);
                      setAdminOpen(true);
                    }}
                  >
                    Open admin panel
                  </Button>
                </div>
              )}
              {userRole === "contributor" && (
                <Badge variant="secondary">Contributor</Badge>
              )}
              {userRole === "user" && (
                <div className="flex flex-col gap-2 items-start">
                  <p className="text-sm text-muted-foreground">
                    Contribute pastoral notes readers can see alongside a passage.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setAccountOpen(false);
                      handleOpenContributor();
                    }}
                  >
                    Become a contributor
                  </Button>
                </div>
              )}
            </div>

            <Separator />

            {/* Account actions */}
            <div className="flex flex-col gap-2 items-start pb-4">
              <p className="text-xs text-muted-foreground">Account</p>
              <Button variant="outline" size="sm" onClick={onSignOut}>
                Sign out
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
```

- [ ] **Step 5: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint components/rhemata/sidebar.tsx`
Expected: `tsc` reports no errors. `eslint` may warn (not error) about the unused `AlertDialog*` imports from Step 1 — that's expected until Task 4 wires them up, and does not fail the command.

- [ ] **Step 6: Manual browser verification**

Run: `cd frontend && npm run dev`, open `http://localhost:3000`, sign in.
Expected: clicking the footer identity button opens "Your account" directly (no dropdown). Display name save still works (existing `PATCH /pastors-notes/me` behavior, untouched). Email shows correctly. Usage line shows if `weeklyUsage` is present. Contributor-status section matches your current role (test with a `user`-role and, if available, an `admin`-role account). "Open admin panel" closes the account dialog and opens `AdminModal`. "Become a contributor" closes the account dialog and opens the existing contributor-request sheet. Sign out works.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/rhemata/sidebar.tsx
git commit -m "Replace profile sheet + dropdown with a single account dialog"
```

---

### Task 4: Frontend — delete-account confirm flow

Depends on Task 2's endpoint being deployed to behave correctly at runtime, but the code itself can be written and type-checked now. Full behavioral verification is in Task 6.

**Files:**
- Modify: `frontend/components/rhemata/sidebar.tsx`

**Interfaces:**
- Consumes: Task 3's account `Dialog` block; `accessToken` prop; Task 2's `POST /account/delete-request`.
- Produces: `deleteConfirmOpen` / `deleteStatus` / `deleteError` state, `handleOpenDeleteConfirm()`, `handleDeleteRequest()`, the delete-account `AlertDialog`.

- [ ] **Step 1: Add state (or move the `AlertDialog*` import block here if Task 3 Step 5 flagged it unused)**

Add after `frontend/components/rhemata/sidebar.tsx`'s account-dialog state block (right after the `settingsStatus` line added in Task 3 Step 2):

```tsx
  // Delete account request
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState<"idle" | "loading" | "sent" | "error">("idle");
  const [deleteError, setDeleteError] = useState<string | null>(null);
```

- [ ] **Step 2: Add handlers**

Add after `handleSaveDisplayName` (which Task 3 left untouched):

```tsx
  function handleOpenDeleteConfirm() {
    setDeleteStatus("idle");
    setDeleteError(null);
    setDeleteConfirmOpen(true);
  }

  async function handleDeleteRequest() {
    if (!accessToken) return;
    setDeleteStatus("loading");
    setDeleteError(null);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/account/delete-request`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.status === 400) {
        const data = await res.json();
        setDeleteError(data.detail ?? "You already have a pending deletion request.");
        setDeleteStatus("error");
      } else if (res.ok) {
        setDeleteStatus("sent");
      } else {
        setDeleteError("Something went wrong. Please try again.");
        setDeleteStatus("error");
      }
    } catch {
      setDeleteError("Something went wrong. Please try again.");
      setDeleteStatus("error");
    }
  }
```

- [ ] **Step 3: Add the "Delete account" button next to "Sign out"**

Replace the "Account actions" block Task 3 added:

```tsx
            {/* Account actions */}
            <div className="flex flex-col gap-2 items-start pb-4">
              <p className="text-xs text-muted-foreground">Account</p>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={onSignOut}>
                  Sign out
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={handleOpenDeleteConfirm}
                >
                  Delete account
                </Button>
              </div>
            </div>
```

- [ ] **Step 4: Add the confirm `AlertDialog`**

Add immediately after the account `Dialog`'s closing `</Dialog>` tag from Task 3 (still inside the `sidebarContent` fragment, alongside the existing contributor-request `Sheet` and `AdminModal`):

```tsx
      {/* Delete account confirm. Uses plain Buttons, not AlertDialogAction, for
          the submit button -- Radix's AlertDialogAction/Cancel close the dialog
          synchronously on click and don't wait for an async onClick to resolve,
          which would close this before the "Request sent" state ever renders. */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          {deleteStatus === "sent" ? (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Request sent</AlertDialogTitle>
                <AlertDialogDescription>
                  We&apos;ve logged your request. We&apos;ll follow up by email before anything is removed.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <Button onClick={() => setDeleteConfirmOpen(false)}>Done</Button>
              </AlertDialogFooter>
            </>
          ) : (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete your account?</AlertDialogTitle>
                <AlertDialogDescription>
                  This sends a request to remove your account and data — conversations, saved words, and any
                  pastoral notes you&apos;ve contributed. We&apos;ll follow up by email to confirm before anything
                  is deleted.
                </AlertDialogDescription>
              </AlertDialogHeader>
              {deleteStatus === "error" && deleteError && (
                <p className="text-xs text-destructive mb-4">{deleteError}</p>
              )}
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleteStatus === "loading"}>Cancel</AlertDialogCancel>
                <Button
                  variant="destructive"
                  onClick={handleDeleteRequest}
                  disabled={deleteStatus === "loading"}
                >
                  {deleteStatus === "loading" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "Delete account"
                  )}
                </Button>
              </AlertDialogFooter>
            </>
          )}
        </AlertDialogContent>
      </AlertDialog>
```

- [ ] **Step 5: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint components/rhemata/sidebar.tsx`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/rhemata/sidebar.tsx
git commit -m "Add delete-account confirm flow to account dialog"
```

---

### Task 5: Frontend — admin "Account Deletion Requests" card

Depends on Task 2's `GET /account/delete-requests` and `POST /account/delete-requests/{id}/resolve` being deployed to behave correctly at runtime; the code itself can be written and type-checked now. Full behavioral verification is in Task 6.

**Files:**
- Modify: `frontend/components/admin/AdminModal.tsx`

**Interfaces:**
- Consumes: Task 2's `GET /account/delete-requests` and `POST /account/delete-requests/{id}/resolve`; existing `accessToken` (via `useAuth`), `showToast`, `Card`/`CardHeader`/`CardTitle`/`CardContent`, `Skeleton`, `fmtDate` — all already imported/defined in this file.
- Produces: a third `Card` inside the existing "Contributors" tab (`activeTab === "contributors"`), titled "Account Deletion Requests".

- [ ] **Step 1: Add the `DeletionRequest` type**

Add after the `PendingRequest` interface (`frontend/components/admin/AdminModal.tsx:68-74`):

```tsx
interface DeletionRequest {
  id: string;
  user_id: string;
  email: string;
  created_at: string;
}
```

- [ ] **Step 2: Add state**

Add after the existing Contributors state block (`frontend/components/admin/AdminModal.tsx:286-294`, right after `const [revokeLoading, setRevokeLoading] = useState(false);`):

```tsx
  const [deletionRequests, setDeletionRequests] = useState<DeletionRequest[]>([]);
  const [deletionRequestsLoaded, setDeletionRequestsLoaded] = useState(false);
  const [deletionRequestsLoading, setDeletionRequestsLoading] = useState(true);
  const [resolveIds, setResolveIds] = useState<Set<string>>(new Set());
```

- [ ] **Step 3: Add the fetch effect**

Add immediately after the existing contributors-tab fetch effect (`frontend/components/admin/AdminModal.tsx:395-409`):

```tsx
  useEffect(() => {
    if (!roleChecked || !accessToken || activeTab !== "contributors" || deletionRequestsLoaded) return;
    setDeletionRequestsLoaded(true);
    fetch(`${API}/account/delete-requests`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => r.json())
      .then((data) => setDeletionRequests(Array.isArray(data) ? data : []))
      .catch(() => setDeletionRequests([]))
      .finally(() => setDeletionRequestsLoading(false));
  }, [roleChecked, accessToken, activeTab, deletionRequestsLoaded]);
```

- [ ] **Step 4: Add the resolve handler**

Add after `handleReject` (`frontend/components/admin/AdminModal.tsx:546-564`):

```tsx
  const handleResolveDeletion = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      setResolveIds((prev) => new Set(prev).add(id));
      try {
        const res = await fetch(`${API}/account/delete-requests/${id}/resolve`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          setDeletionRequests((prev) => prev.filter((r) => r.id !== id));
          showToast("Deletion request marked resolved.");
        }
      } finally {
        setResolveIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
      }
    },
    [accessToken]
  );
```

- [ ] **Step 5: Add the card**

Add inside the "Contributors" tab's `<div className="space-y-6">`, immediately after the "Active Contributors" `Card` closes (`frontend/components/admin/AdminModal.tsx:868`, right before the wrapping `</div>` at line 869):

```tsx
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Account Deletion Requests
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        {deletionRequestsLoading ? (
                          <div className="space-y-3">
                            <Skeleton className="h-16 w-full" />
                          </div>
                        ) : deletionRequests.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No pending deletion requests.</p>
                        ) : (
                          <div className="space-y-3">
                            {deletionRequests.map((req) => (
                              <div
                                key={req.id}
                                className="flex items-start justify-between gap-4 rounded-lg border border-border p-4"
                              >
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium text-foreground truncate">
                                    {req.email || "—"}
                                  </p>
                                  <p className="text-xs text-muted-foreground mt-1">
                                    Requested {fmtDate(req.created_at)}
                                  </p>
                                </div>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleResolveDeletion(req.id)}
                                  disabled={resolveIds.has(req.id)}
                                >
                                  {resolveIds.has(req.id) ? (
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                  ) : (
                                    "Mark resolved"
                                  )}
                                </Button>
                              </div>
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
```

- [ ] **Step 6: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint components/admin/AdminModal.tsx`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/admin/AdminModal.tsx
git commit -m "Add Account Deletion Requests card to admin Contributors tab"
```

---

### Task 6: Deploy and end-to-end verification

Everything up to here is committed but the backend half (Task 2) has only been syntax-checked, never run — there is no local backend to run it against. This task deploys and proves the whole flow actually works, then does a manual pass in the browser across roles.

**Files:**
- Create: `scripts/test_account_delete_request_e2e.py`

**Interfaces:**
- Consumes: all of Tasks 1-5, deployed to production.

- [ ] **Step 1: Production build check**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type or lint errors. This is the closest thing to a pre-deploy check the frontend has (Vercel runs the same build on deploy).

- [ ] **Step 2: Push to main — confirm with Alex before running this step**

This triggers a live Railway backend deploy and a live Vercel frontend deploy. Do not run it without explicit confirmation in the moment, even though every prior task's commits are already staged for it.

```bash
git push origin main
```

- [ ] **Step 3: Wait for the Railway deploy to finish**

Check the Railway dashboard, or poll the production health/root endpoint until it responds normally:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://rhemata-production.up.railway.app/docs
```

Expected: `200` once the new deploy is live (a stale `502`/connection error means the deploy is still in progress — wait and retry).

- [ ] **Step 4: Write the end-to-end verification script**

```python
#!/usr/bin/env python3
"""
test_account_delete_request_e2e.py -- End-to-end verification of the
account deletion-request stub against the LIVE production API:
  POST /account/delete-request
  GET  /account/delete-requests
  POST /account/delete-requests/{id}/resolve

Run AFTER pushing to main and confirming the Railway deploy has finished
(see scripts/verify_metering_live.py for the established pattern this follows).

Requires in backend/app/.env (or environment):
  SUPABASE_DB_URL      -- direct Postgres connection (service role)
  SUPABASE_URL         -- project URL
  SUPABASE_SERVICE_KEY -- service role key (for admin.generate_link)

Usage:
  python3 scripts/test_account_delete_request_e2e.py
"""

import os
import sys
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

SB_URL = os.environ["SUPABASE_URL"]
API_BASE = "https://rhemata-production.up.railway.app"
TEST_EMAIL = "creative@clf-church.com"

_pass = 0
_fail = 0


def check(label, passed):
    global _pass, _fail
    tag = "PASS" if passed else "FAIL"
    print("  [%s] %s" % (tag, label))
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_db_conn():
    import psycopg2
    from urllib.parse import urlparse, unquote

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def jwt_for_email(db, email):
    """Mint a real access token for `email` via a Supabase magic link --
    same approach as scripts/verify_metering_live.py."""
    link = db.auth.admin.generate_link({"type": "magiclink", "email": email})
    resp = httpx.get(
        f"{SB_URL}/auth/v1/verify",
        params={
            "token": link.properties.hashed_token,
            "type": "magiclink",
            "redirect_to": "http://localhost:3000",
        },
        follow_redirects=False,
    )
    fragment = resp.headers.get("location", "").split("#", 1)[1]
    token = parse_qs(fragment).get("access_token", [""])[0]
    if not token:
        raise RuntimeError("Failed to obtain JWT for %s" % email)
    return token, link.user.id


def main():
    from supabase import create_client

    print("\nAccount deletion requests -- end-to-end verification")
    print("=" * 50)

    db = create_client(SB_URL, os.environ["SUPABASE_SERVICE_KEY"])
    conn = get_db_conn()
    cur = conn.cursor()

    # -- Find an admin to test the admin-only endpoints -------------------------
    cur.execute("SELECT user_id FROM user_roles WHERE role = 'admin' LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("ERROR: no admin user found in user_roles -- cannot test admin endpoints")
        sys.exit(1)
    admin_user_id = row[0]
    cur.execute("SELECT email FROM auth.users WHERE id = %s", (admin_user_id,))
    admin_email = cur.fetchone()[0]

    user_jwt, user_id = jwt_for_email(db, TEST_EMAIL)
    admin_jwt, _ = jwt_for_email(db, admin_email)
    print(f"Test user: {TEST_EMAIL} ({user_id})")
    print(f"Admin:     {admin_email} ({admin_user_id})\n")

    cur.execute("DELETE FROM deletion_requests WHERE user_id = %s", (user_id,))
    conn.commit()

    try:
        # -- TEST 1: submit a deletion request -----------------------------------
        res = httpx.post(
            f"{API_BASE}/account/delete-request",
            headers={"Authorization": f"Bearer {user_jwt}"},
        )
        check("POST /account/delete-request returns 200", res.status_code == 200)

        # -- TEST 2: duplicate submission is rejected ----------------------------
        res2 = httpx.post(
            f"{API_BASE}/account/delete-request",
            headers={"Authorization": f"Bearer {user_jwt}"},
        )
        check("duplicate POST /account/delete-request returns 400", res2.status_code == 400)

        # -- TEST 3: admin can list the pending request --------------------------
        res3 = httpx.get(
            f"{API_BASE}/account/delete-requests",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )
        listed = res3.json() if res3.status_code == 200 else []
        found = next((r for r in listed if r["user_id"] == user_id), None)
        check("GET /account/delete-requests (admin) lists the new request", found is not None)

        # -- TEST 4: non-admin cannot list requests ------------------------------
        res4 = httpx.get(
            f"{API_BASE}/account/delete-requests",
            headers={"Authorization": f"Bearer {user_jwt}"},
        )
        check("GET /account/delete-requests (non-admin) returns 403", res4.status_code == 403)

        # -- TEST 5: admin can resolve it -----------------------------------------
        if found:
            res5 = httpx.post(
                f"{API_BASE}/account/delete-requests/{found['id']}/resolve",
                headers={"Authorization": f"Bearer {admin_jwt}"},
            )
            check("POST /account/delete-requests/{id}/resolve returns 200", res5.status_code == 200)

            cur.execute("SELECT status FROM deletion_requests WHERE id = %s", (found["id"],))
            status = cur.fetchone()[0]
            check("row status is 'resolved' after resolve", status == "resolved")
    finally:
        cur.execute("DELETE FROM deletion_requests WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run it**

Run: `python3 scripts/test_account_delete_request_e2e.py`
Expected: `6/6 checks passed`. Exit code 0.

- [ ] **Step 6: Commit the script**

```bash
git add scripts/test_account_delete_request_e2e.py
git commit -m "Add end-to-end verification script for account delete-request flow"
```

- [ ] **Step 7: Manual browser QA**

Run: `cd frontend && npm run dev`, open `http://localhost:3000` (talks to the now-deployed production backend).

- Sign in as a `user`-role account. Open the account dialog: confirm Identity, Usage, "Become a contributor" CTA, Sign out, and Delete account (through to the "Request sent" state — don't actually leave a real request pending afterward; as the signed-in test user, resolve it from the admin panel afterward if you have admin access, or delete the row directly via Supabase).
- Sign in as an `admin`-role account. Open the account dialog: confirm the Admin badge + "Open admin panel" link works and closes the account dialog first. In the admin panel's Contributors tab, confirm the new "Account Deletion Requests" card lists pending requests and "Mark resolved" removes them from the list.
- If a `contributor`-role test account is available, confirm the Contributor badge renders with no dangling link.

Report back honestly if any of these don't match — this is the only step in the whole plan that exercises the real, deployed system end to end through the actual UI.

---

## Post-plan cleanup

Delete or archive `scripts/test_deletion_requests_migration.py` and `scripts/test_account_delete_request_e2e.py` only if this repo's convention is to remove one-off verification scripts after landing — check `scripts/` for whether `test_pastors_rls.py` and `verify_metering_live.py`-style scripts were kept or removed after their features shipped before deciding either way. Do not delete without checking; this plan does not make that call.
