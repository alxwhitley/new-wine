#!/usr/bin/env python3
"""Apply / verify migration 093 (search analytics + corpus-gap dashboard).

Default is dry-run verification against the live schema WITHOUT applying.
Production apply requires an explicit --apply flag (Alex's attended gate).

Usage:
  python3 scripts/apply_migration_093.py           # verify only
  python3 scripts/apply_migration_093.py --apply   # apply then verify
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "093_search_analytics.sql"
load_dotenv(ROOT / "backend" / "app" / ".env")

_pass = 0
_fail = 0


def check(label: str, passed: bool, detail: str = None) -> None:
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


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", ("public.%s" % table,))
    return cur.fetchone()[0] is not None


def rls_enabled(cur, table: str) -> bool:
    cur.execute(
        "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (table,)
    )
    row = cur.fetchone()
    return bool(row and row[0])


def has_service_role_policy(cur, table: str) -> bool:
    cur.execute(
        "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = %s "
        "AND qual LIKE %s",
        (table, "%service_role%"),
    )
    return cur.fetchone()[0] > 0


def has_no_grant(cur, table: str, role: str) -> bool:
    cur.execute(
        "SELECT count(*) FROM information_schema.role_table_grants "
        "WHERE table_schema = 'public' AND table_name = %s AND grantee = %s",
        (table, role),
    )
    return cur.fetchone()[0] == 0


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone()[0] > 0


def run_verify(cur) -> None:
    tables = ["analytics_consent", "search_occurrences", "search_gap_details"]
    for t in tables:
        check("%s exists" % t, table_exists(cur, t))
        check("%s has RLS enabled" % t, rls_enabled(cur, t))
        check("%s has a service_role policy" % t, has_service_role_policy(cur, t))
        for role in ("anon", "authenticated"):
            check("%s has no grant to %s" % (t, role), has_no_grant(cur, t, role))

    for column in (
        "user_id", "policy_version", "acknowledged_at", "withdrawn_at",
        "subject_key", "subject_key_version", "retired_subject_keys",
    ):
        check("analytics_consent.%s exists" % column,
              column_exists(cur, "analytics_consent", column))

    for column in (
        "submission_id", "job_id", "origin", "subject_key", "subject_key_version",
        "question_fingerprint", "primary_topic", "outcome", "classification_status",
        "classifier_version", "classifier_model", "classifier_prompt_version",
        "classifier_confidence", "finalized_at",
    ):
        check("search_occurrences.%s exists" % column,
              column_exists(cur, "search_occurrences", column))

    for column in (
        "occurrence_id", "redacted_question", "redaction_version", "redaction_status",
        "status", "retest_occurrence_id", "retest_outcome", "resolved_at",
        "text_purge_at", "purged_at",
    ):
        check("search_gap_details.%s exists" % column,
              column_exists(cur, "search_gap_details", column))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually apply the migration")
    args = parser.parse_args()

    sql = MIGRATION_PATH.read_text()

    conn = get_conn()
    conn.autocommit = False
    try:
        if args.apply:
            print("Applying migration 093...")
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print("Applied.")
        with conn.cursor() as cur:
            run_verify(cur)
    finally:
        conn.close()

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
