#!/usr/bin/env python3
"""Apply / verify migration 090 (account-deletion provenance snapshot).

Default is dry-run verification against the live schema WITHOUT applying.
Production apply requires an explicit --apply flag (Alex attended gate).

Usage:
  python3 scripts/apply_migration_090.py           # verify only
  python3 scripts/apply_migration_090.py --apply   # apply then verify
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "090_account_deletion_provenance_snapshot.sql"
load_dotenv(ROOT / "backend" / "app" / ".env")

_pass = 0
_fail = 0


def check(label: str, passed: bool, detail: str | None = None) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if passed else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_conn():
    import psycopg2

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def column_nullable(cur, table: str, column: str):
    """Returns (exists, is_nullable) -- is_nullable is None if column doesn't exist."""
    cur.execute(
        """
        SELECT is_nullable FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    row = cur.fetchone()
    if row is None:
        return False, None
    return True, row[0] == "YES"


def fk_delete_action(cur, constraint_name: str):
    """confdeltype: 'a'=NO ACTION, 'r'=RESTRICT, 'c'=CASCADE, 'n'=SET NULL, 'd'=SET DEFAULT."""
    cur.execute(
        "SELECT confdeltype FROM pg_constraint WHERE conname = %s",
        (constraint_name,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def check_def(cur, constraint_name: str):
    cur.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint_name,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def verify(cur) -> None:
    print("\nVerify migration 090 columns / FK actions / CHECK constraints / trigger\n")

    # ── snapshot columns exist with the right nullability ──────────────────
    expectations = [
        ("pastors_cards", "author_email", False),
        ("quote_source_revisions", "captured_by_email", False),
        ("document_quote_clearance", "cleared_by_email", False),
        ("quotes", "created_by_email", False),
        ("quotes", "approved_by_email", True),
        ("quotes", "revoked_by_email", True),
    ]
    all_columns_exist = True
    for table, col, expect_nullable in expectations:
        exists, nullable = column_nullable(cur, table, col)
        check("%s.%s exists" % (table, col), exists)
        if exists:
            check(
                "%s.%s nullable=%s (expected %s)" % (table, col, nullable, expect_nullable),
                nullable == expect_nullable,
            )
        else:
            all_columns_exist = False

    if not all_columns_exist:
        print("\n  (migration not applied yet -- skipping backfill/trigger checks that depend on the new schema)")
        return

    # ── FK ON DELETE SET NULL ('n') on every relaxed FK ─────────────────────
    for constraint in (
        "pastors_cards_user_id_fkey",
        "quote_source_revisions_captured_by_fkey",
        "document_quote_clearance_cleared_by_fkey",
        "quotes_created_by_fkey",
        "quotes_approved_by_fkey",
        "quotes_revoked_by_fkey",
    ):
        action = fk_delete_action(cur, constraint)
        check("%s is ON DELETE SET NULL" % constraint, action == "n", "confdeltype=%r" % action)

    # ── narrowed CHECK constraints (no longer require the actor non-null) ──
    quotes_check = check_def(cur, "quotes_check")
    check(
        "quotes_check no longer requires approved_by IS NOT NULL",
        quotes_check is not None and "approved_by" not in quotes_check,
        quotes_check,
    )
    quotes_check1 = check_def(cur, "quotes_check1")
    check(
        "quotes_check1 no longer requires revoked_by IS NOT NULL",
        quotes_check1 is not None and "revoked_by" not in quotes_check1,
        quotes_check1,
    )

    # ── backfill sanity: no unexpected NULLs on the NOT NULL snapshot cols ──
    cur.execute("SELECT count(*) FROM pastors_cards WHERE author_email IS NULL")
    check("pastors_cards.author_email has zero NULLs", cur.fetchone()[0] == 0)
    cur.execute("SELECT count(*) FROM quote_source_revisions WHERE captured_by_email IS NULL")
    check("quote_source_revisions.captured_by_email has zero NULLs", cur.fetchone()[0] == 0)
    cur.execute("SELECT count(*) FROM document_quote_clearance WHERE cleared_by_email IS NULL")
    check("document_quote_clearance.cleared_by_email has zero NULLs", cur.fetchone()[0] == 0)
    cur.execute("SELECT count(*) FROM quotes WHERE created_by_email IS NULL")
    check("quotes.created_by_email has zero NULLs", cur.fetchone()[0] == 0)
    cur.execute("SELECT count(*) FROM quotes WHERE approved_by IS NOT NULL AND approved_by_email IS NULL")
    check("quotes.approved_by_email backfilled everywhere approved_by is set", cur.fetchone()[0] == 0)
    cur.execute("SELECT count(*) FROM quotes WHERE revoked_by IS NOT NULL AND revoked_by_email IS NULL")
    check("quotes.revoked_by_email backfilled everywhere revoked_by is set", cur.fetchone()[0] == 0)

    # ── trigger function still enforces approved_by on a fresh INSERT ──────
    cur.execute("SELECT prosrc FROM pg_proc WHERE proname = 'enforce_quote_approval_gates'")
    row = cur.fetchone()
    src = row[0] if row else ""
    check(
        "enforce_quote_approval_gates() still requires approved_by on TG_OP='INSERT'",
        "TG_OP = 'INSERT'" in src and "approved_by is required" in src,
    )
    check(
        "enforce_quote_approval_gates() still runs the speaker-confirmation gate",
        "speaker not positively confirmed" in src,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration 090 to the live database (attended gate).",
    )
    args = parser.parse_args()

    print("\nmigration 090 — account-deletion provenance snapshot")
    print("=" * 60)
    if not args.apply:
        print("Mode: VERIFY ONLY (pass --apply to mutate)\n")
    else:
        print("Mode: APPLY + VERIFY\n")

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    if args.apply:
        sql = MIGRATION_PATH.read_text()
        cur.execute(sql)
        conn.commit()
        print("Applied %s\n" % MIGRATION_PATH.name)
        # Fresh connection after apply (Invariant 9 / migration 049 lesson)
        cur.close()
        conn.close()
        conn = get_conn()
        conn.autocommit = True
        cur = conn.cursor()
    else:
        conn.autocommit = True

    verify(cur)
    cur.close()
    conn.close()

    print()
    print("%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
