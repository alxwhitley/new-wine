#!/usr/bin/env python3
"""
apply_migration_082.py -- Apply and verify migration 082
(quote rail schema: quote_source_revisions, document_quote_clearance,
quotes, chunks.quote_ineligible_reason).

Idempotent: detects whether the quotes table already exists and skips the
apply if so. Schema-level verification on a FRESH connection (migration 049
landmine, Invariant 9).

Usage:
  python3 scripts/apply_migration_082.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

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

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def _has_table(cur, table):
    cur.execute("SELECT to_regclass(%s)", ("public.%s" % table,))
    return cur.fetchone()[0] is not None


def main():
    print("\nquote rail -- migration 082 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()

    if _has_table(cur, "quotes"):
        print("Table quotes already exists -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "082_quotes.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection ------------------------------------------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    check("table quote_source_revisions present", _has_table(cur2, "quote_source_revisions"))
    check("table document_quote_clearance present", _has_table(cur2, "document_quote_clearance"))
    check("table quotes present", _has_table(cur2, "quotes"))

    cur2.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'chunks' AND column_name = 'quote_ineligible_reason'"
    )
    row = cur2.fetchone()
    check("chunks.quote_ineligible_reason column present", row is not None)

    cur2.execute(
        "SELECT count(*) FROM chunks WHERE quote_ineligible_reason = 'ccel_editorial_description_not_teacher_authored'"
    )
    check("3 chunks marked CCEL front matter (New Life 0-2)", cur2.fetchone()[0] == 3)

    cur2.execute(
        "SELECT count(*) FROM chunks WHERE quote_ineligible_reason = 'translators_note_not_teacher_authored'"
    )
    check("3 chunks marked translator's note (New Life 3-5)", cur2.fetchone()[0] == 3)

    cur2.execute(
        "SELECT tgname FROM pg_trigger WHERE tgname = 'trg_enforce_source_revision_eligibility'"
    )
    check("trigger trg_enforce_source_revision_eligibility present", cur2.fetchone() is not None)

    cur2.execute(
        "SELECT tgname FROM pg_trigger WHERE tgname = 'trg_enforce_quote_approval_gates'"
    )
    check("trigger trg_enforce_quote_approval_gates present", cur2.fetchone() is not None)

    cur2.execute("SELECT count(*) FROM quotes")
    check("quotes table starts empty", cur2.fetchone()[0] == 0)

    cur2.execute("SELECT count(*) FROM quote_source_revisions")
    check("quote_source_revisions table starts empty", cur2.fetchone()[0] == 0)

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
