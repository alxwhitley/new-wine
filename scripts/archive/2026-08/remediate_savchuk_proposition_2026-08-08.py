#!/usr/bin/env python3
"""
remediate_savchuk_proposition_2026-08-08.py -- pull the unconfirmed Savchuk
"Devil's Voice" proposition, on Alex's explicit instruction as part of the
quote-rail human-approval-removal session (CLAUDE.md "Settled product
decisions (2026-08-08)").

Same pattern as scripts/remediate_fabricated_propositions_2026-08-04.py:
eligible=false, content untouched, original row never deleted (auditability).
Unlike that script's two targets, this proposition is NOT consumed as
position evidence today (confirmed live: zero rows in position_evidence for
this id) -- no rebuild needed.

Scope, approved by Alex -- do not extend beyond this:
  Mark 23d846db-66de-4cc6-8308-138877fd3772 (Vlad Savchuk, "How to Spot the
  Devil's Voice in Your Head" -- a strong content match, never ID-confirmed
  against an original finding) eligible=false. Do NOT rewrite content.

Run once, deliberately (not idempotent in the sense that re-running after a
successful flip finds 0 rows to affect on stage 3 -- that's fine, it's a
no-op then, not an error).

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

SAVCHUK_ID = "23d846db-66de-4cc6-8308-138877fd3772"


def db_params():
    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def stage1_readonly_confirm(params):
    import psycopg2
    import psycopg2.extras

    print("=" * 90)
    print("STAGE 1 -- read-only confirmation of current state")
    print("=" * 90)
    conn = psycopg2.connect(**params)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, eligible, content, document_id FROM propositions WHERE id = %s", (SAVCHUK_ID,))
    row = cur.fetchone()
    print("  proposition:", dict(row) if row else None)
    assert row is not None, "Savchuk proposition not found -- stopping"
    assert row["eligible"] is True, "expected eligible=true before this run, found %r" % row["eligible"]
    cur.execute("SELECT count(*) AS n FROM position_evidence WHERE proposition_id = %s", (SAVCHUK_ID,))
    n = cur.fetchone()["n"]
    print("  position_evidence rows referencing this proposition:", n)
    assert n == 0, "this proposition IS consumed as position evidence -- stopping, do not proceed blindly"
    cur.close()
    conn.close()
    return row


def stage2_dry_run(params):
    import psycopg2

    print()
    print("=" * 90)
    print("STAGE 2 -- dry-run the eligibility UPDATE (transaction rolled back)")
    print("=" * 90)
    conn = psycopg2.connect(**params)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("UPDATE propositions SET eligible = false WHERE id = %s AND eligible = true", (SAVCHUK_ID,))
    print("  dry-run UPDATE would affect %d row(s) (expected 1)" % cur.rowcount)
    assert cur.rowcount == 1, "dry-run affected %d rows, expected exactly 1" % cur.rowcount
    conn.rollback()
    print("  rolled back -- no change committed")
    cur.close()
    conn.close()


def stage3_real_flip(params):
    import psycopg2

    print()
    print("=" * 90)
    print("STAGE 3 -- real eligibility UPDATE (committed)")
    print("=" * 90)
    conn = psycopg2.connect(**params)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("UPDATE propositions SET eligible = false WHERE id = %s AND eligible = true", (SAVCHUK_ID,))
    rowcount = cur.rowcount
    print("  UPDATE affected %d row(s) (expected 1)" % rowcount)
    assert rowcount == 1, "real UPDATE affected %d rows, expected exactly 1 -- rolling back" % rowcount
    conn.commit()
    print("  committed")
    cur.close()
    conn.close()


def stage4_verify(params, before):
    import psycopg2
    import psycopg2.extras

    print()
    print("=" * 90)
    print("STAGE 4 -- post-write verification (fresh connection)")
    print("=" * 90)
    conn = psycopg2.connect(**params)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, eligible, content, document_id FROM propositions WHERE id = %s", (SAVCHUK_ID,))
    after = cur.fetchone()
    print("  proposition after:", dict(after))
    assert after["eligible"] is False, "expected eligible=false after commit"
    assert after["content"] == before["content"], "content must be byte-identical -- no rewrite"
    assert after["document_id"] == before["document_id"], "document_id must be unchanged"
    print("  content byte-identical to before: OK")
    print("  row not deleted, original archive intact: OK")
    cur.close()
    conn.close()


def main():
    params = db_params()
    before = stage1_readonly_confirm(params)
    stage2_dry_run(params)
    stage3_real_flip(params)
    stage4_verify(params, before)
    print()
    print("Done. Savchuk 'Devil's Voice' proposition (%s) is now eligible=false." % SAVCHUK_ID)


if __name__ == "__main__":
    main()
